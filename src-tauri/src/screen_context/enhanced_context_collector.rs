use anyhow::Result;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::screen_context::activity_monitor::ActivityMonitor;
use crate::screen_context::context_data::{
    FileContext, RawContext, SystemState,
};
use crate::screen_context::context_type::ContextType;
use crate::screen_context::macos_app_detector::MacOSAppDetector;
use crate::screen_context::smart_collector::SmartCollector;
use crate::screen_context::context_api::ContextApiClient;

/// Enhanced ContextCollector that integrates all macOS-specific functionality
pub struct EnhancedContextCollector {
    smart_collector: Arc<SmartCollector>,
    activity_monitor: Arc<ActivityMonitor>,
    app_detector: Arc<Mutex<MacOSAppDetector>>,
    previous_state: Arc<Mutex<Option<SystemState>>>,
    collection_history: Arc<Mutex<Vec<CollectionHistoryEntry>>>,
    api_client: Arc<ContextApiClient>,
}

#[derive(Debug, Clone)]
struct CollectionHistoryEntry {
    timestamp: Instant,
    context_type: ContextType,
    app_name: String,
    collection_duration: Duration,
    success: bool,
}

impl EnhancedContextCollector {
    /// Create a new enhanced context collector
    pub fn new() -> Result<Self> {
        let smart_collector = Arc::new(SmartCollector::new()?);
        let activity_monitor = Arc::new(ActivityMonitor::new()?);
        let app_detector = Arc::new(Mutex::new(MacOSAppDetector::new()?));
        let api_client = Arc::new(ContextApiClient::new());
        
        Ok(Self {
            smart_collector,
            activity_monitor,
            app_detector,
            previous_state: Arc::new(Mutex::new(None)),
            collection_history: Arc::new(Mutex::new(Vec::new())),
            api_client,
        })
    }
    
    /// Initialize the collector and start monitoring
    pub async fn initialize(&self) -> Result<()> {
        // Start activity monitoring
        self.activity_monitor.start_monitoring().await?;
        
        // Check permissions and availability
        self.check_system_readiness().await?;
        
        Ok(())
    }
    
    /// Perform comprehensive context collection
    pub async fn collect_context(&self) -> Result<RawContext> {
        let start_time = Instant::now();
        
        // Perform smart collection
        let mut context = self.smart_collector.collect_context().await?;
        
        // Enrich with activity metrics
        context.activity_metrics = self.activity_monitor.get_activity_metrics().await;
        
        // Add file context for IDEs
        if context.app_info.is_ide {
            context.file_context = self.collect_file_context(&context.app_info).await.ok();
        }
        
        // Detect context type and record context switch
        let detected_context_type = self.detect_context_type(&context).await;
        
        // Record context switch if context changed
        if let Some(ref previous) = *self.previous_state.lock().await {
            if previous.context_type != detected_context_type || 
               previous.app_info.name != context.app_info.name {
                
                self.activity_monitor.record_context_switch(
                    context.app_info.name.clone(),
                    context.app_info.window_title.clone(),
                    detected_context_type.clone(),
                ).await?;
            }
        }
        
        // Update previous state
        let screenshot = image::DynamicImage::new_rgb8(1, 1); // Placeholder
        let screenshot_hash = format!("{:?}", start_time); // Placeholder hash
        
        let new_state = SystemState {
            screenshot,
            screenshot_hash,
            app_info: context.app_info.clone(),
            context_type: detected_context_type.clone(),
            captured_at: start_time,
            activity_level: context.activity_metrics.activity_level.clone(),
        };
        
        *self.previous_state.lock().await = Some(new_state);
        
        // Record collection history
        {
            let mut history = self.collection_history.lock().await;
            history.push(CollectionHistoryEntry {
                timestamp: start_time,
                context_type: detected_context_type.clone(),
                app_name: context.app_info.name.clone(),
                collection_duration: start_time.elapsed(),
                success: true,
            });
            
            // Keep history manageable
            if history.len() > 100 {
                history.remove(0);
            }
        }
        
        // Send context to Flask API (non-blocking, log errors)
        let api_client = self.api_client.clone();
        let context_clone = context.clone();
        let detected_context_type_clone = detected_context_type.clone();
        
        tokio::spawn(async move {
            match api_client.send_raw_context(&context_clone, &detected_context_type_clone).await {
                Ok(response) => {
                    println!("✓ Context sent to Flask API successfully. Node UUID: {}", response.written);
                }
                Err(e) => {
                    eprintln!("✗ Failed to send context to Flask API: {}", e);
                }
            }
        });
        
        Ok(context)
    }
    
    /// Get activity timeline
    pub async fn get_activity_timeline(&self) -> Result<crate::screen_context::context_data::ActivityTimeline> {
        Ok(self.activity_monitor.get_activity_timeline().await)
    }
    
    /// Check if user is currently active
    pub async fn is_user_active(&self) -> bool {
        self.activity_monitor.is_user_active().await
    }
    
    /// Get context switching patterns
    pub async fn get_context_patterns(&self) -> HashMap<String, u32> {
        self.activity_monitor.get_context_patterns().await
    }
    
    /// Get collection statistics
    pub async fn get_collection_stats(&self) -> Result<EnhancedCollectionStats> {
        let smart_stats = self.smart_collector.get_stats().await;
        let history = self.collection_history.lock().await;
        
        let total_collections = history.len();
        let successful_collections = history.iter().filter(|e| e.success).count();
        let average_duration = if !history.is_empty() {
            history.iter().map(|e| e.collection_duration.as_millis()).sum::<u128>() / history.len() as u128
        } else {
            0
        };
        
        // Context type distribution
        let mut context_distribution = HashMap::new();
        for entry in history.iter() {
            *context_distribution.entry(entry.context_type.category_name().to_string()).or_insert(0) += 1;
        }
        
        Ok(EnhancedCollectionStats {
            total_collections,
            successful_collections,
            average_duration_ms: average_duration,
            context_distribution,
            cache_hit_rate: if smart_stats.cache_hits + smart_stats.cache_misses > 0 {
                smart_stats.cache_hits as f64 / (smart_stats.cache_hits + smart_stats.cache_misses) as f64
            } else {
                0.0
            },
        })
    }
    
    /// Check system readiness and permissions
    pub async fn check_system_readiness(&self) -> Result<SystemReadiness> {
        let available_sources = self.smart_collector.check_available_sources().await;
        
        // Check accessibility permissions
        let accessibility_available = available_sources.get(&crate::screen_context::context_data::DataSourceType::Accessibility).unwrap_or(&false);
        
        // Check screen recording permissions
        let screen_recording_available = available_sources.get(&crate::screen_context::context_data::DataSourceType::Screenshot).unwrap_or(&false);
        
        // Check browser availability
        let browser_available = available_sources.get(&crate::screen_context::context_data::DataSourceType::DOM).unwrap_or(&false);
        
        let readiness = SystemReadiness {
            accessibility_permission: *accessibility_available,
            screen_recording_permission: *screen_recording_available,
            browser_integration: *browser_available,
            ocr_engine: true, // Always available
            overall_ready: *accessibility_available && *screen_recording_available,
        };
        
        Ok(readiness)
    }
    
    /// Clear all caches
    pub async fn clear_caches(&self) {
        self.smart_collector.clear_cache().await;
        
        // Clear collection history
        {
            let mut history = self.collection_history.lock().await;
            history.clear();
        }
    }
    
    // Private helper methods
    
    async fn detect_context_type(&self, context: &RawContext) -> ContextType {
        // Use both bundle ID and window title for better detection
        let (context_from_bundle, confidence1) = ContextType::from_app_bundle_id(&context.app_info.bundle_id);
        
        let (context_from_title, confidence2) = if let Some(ref title) = context.app_info.window_title {
            ContextType::from_window_title(title, Some(&context.app_info.bundle_id))
        } else {
            (ContextType::Unknown, 0.0)
        };
        
        // Use the detection with higher confidence
        if confidence2 > confidence1 {
            context_from_title
        } else {
            context_from_bundle
        }
    }
    
    async fn collect_file_context(&self, _app_info: &crate::screen_context::context_data::AppInfo) -> Result<FileContext> {
        // Placeholder implementation
        Ok(FileContext {
            current_file_path: None,
            file_type: None,
            file_size: None,
            last_modified: None,
            project_root: None,
            git_info: None,
            recent_files: Vec::new(),
            open_tabs: Vec::new(),
        })
    }
}

#[derive(Debug, Clone)]
pub struct EnhancedCollectionStats {
    pub total_collections: usize,
    pub successful_collections: usize,
    pub average_duration_ms: u128,
    pub context_distribution: HashMap<String, u32>,
    pub cache_hit_rate: f64,
}

#[derive(Debug, Clone)]
pub struct SystemReadiness {
    pub accessibility_permission: bool,
    pub screen_recording_permission: bool,
    pub browser_integration: bool,
    pub ocr_engine: bool,
    pub overall_ready: bool,
}

impl Default for EnhancedContextCollector {
    fn default() -> Self {
        Self::new().expect("Failed to initialize EnhancedContextCollector")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_enhanced_context_collector_creation() {
        let collector = EnhancedContextCollector::new();
        assert!(collector.is_ok());
    }
    
    #[tokio::test]
    async fn test_system_readiness_check() {
        let collector = EnhancedContextCollector::new().unwrap();
        let readiness = collector.check_system_readiness().await;
        
        assert!(readiness.is_ok());
        let readiness = readiness.unwrap();
        
        // OCR engine should always be available
        assert!(readiness.ocr_engine);
    }
    
    #[tokio::test]
    async fn test_activity_monitoring() {
        let collector = EnhancedContextCollector::new().unwrap();
        
        // Should be able to check if user is active
        let _is_active = collector.is_user_active().await;
        
        // Should be able to get context patterns
        let patterns = collector.get_context_patterns().await;
        assert!(patterns.is_empty()); // Should be empty initially
    }
    
    #[tokio::test]
    async fn test_collection_stats() {
        let collector = EnhancedContextCollector::new().unwrap();
        let stats = collector.get_collection_stats().await;
        
        assert!(stats.is_ok());
        let stats = stats.unwrap();
        
        // Should have initial values
        assert_eq!(stats.total_collections, 0);
        assert_eq!(stats.successful_collections, 0);
    }
    
    #[tokio::test]
    async fn test_cache_clearing() {
        let collector = EnhancedContextCollector::new().unwrap();
        
        // Should not panic
        collector.clear_caches().await;
    }
}