use anyhow::{Context as AnyhowContext, Result};
use crossbeam::channel::{self, Receiver, Sender};
use futures::future::{join_all, select_all};
use futures::FutureExt;
use std::collections::{BinaryHeap, HashMap};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{Mutex, RwLock};
use tokio::time::timeout;

use crate::screen_context::accessibility_bridge::AccessibilityBridge;
use crate::screen_context::chromium_bridge::ChromiumBridge;
use crate::screen_context::context_data::{
    ActivityMetrics, CollectionError, CollectionMetadata, CollectionTask, DataSourceAttempt,
    DataSourceType, RawContext,
};
use crate::screen_context::macos_app_detector::MacOSAppDetector;
use crate::screen_context::ocr_tesseract::TesseractEngine;
use crate::screen_context::safari_bridge::SafariBridge;
use crate::screen_context::screen_capture::ScreenCapture;

pub struct SmartCollector {
    app_detector: Arc<Mutex<MacOSAppDetector>>,
    chromium_bridge: Arc<ChromiumBridge>,
    safari_bridge: Arc<SafariBridge>,
    accessibility_bridge: Arc<Mutex<AccessibilityBridge>>,
    ocr_engine: Arc<TesseractEngine>,
    screen_capture: Arc<ScreenCapture>,
    
    // Collection management
    task_queue: Arc<Mutex<BinaryHeap<CollectionTask>>>,
    active_tasks: Arc<AtomicU32>,
    max_concurrent_tasks: u32,
    global_timeout: Duration,
    
    // Caching
    cache: Arc<RwLock<HashMap<String, CachedResult>>>,
    cache_ttl: Duration,
    
    // Metrics
    collection_stats: Arc<Mutex<CollectionStats>>,
}

#[derive(Debug, Clone)]
struct CachedResult {
    data: CachedData,
    cached_at: Instant,
    hit_count: u32,
}

#[derive(Debug, Clone)]
enum CachedData {
    AppInfo(crate::screen_context::context_data::AppInfo),
    DOMData(crate::screen_context::context_data::DOMData),
    AccessibilityData(crate::screen_context::context_data::AccessibilityData),
    Screenshot(image::DynamicImage),
    OCRData(crate::screen_context::context_data::OCRData),
}

#[derive(Debug, Default, Clone)]
pub struct CollectionStats {
    pub total_collections: u32,
    pub successful_collections: u32,
    pub cache_hits: u32,
    pub cache_misses: u32,
    pub average_duration_ms: f64,
    pub timeout_count: u32,
    pub error_count: u32,
}

impl SmartCollector {
    pub fn new() -> Result<Self> {
        Ok(Self {
            app_detector: Arc::new(Mutex::new(MacOSAppDetector::new()?)),
            chromium_bridge: Arc::new(ChromiumBridge::new()),
            safari_bridge: Arc::new(SafariBridge::new()),
            accessibility_bridge: Arc::new(Mutex::new(AccessibilityBridge::new()?)),
            ocr_engine: Arc::new(TesseractEngine::new()?),
            screen_capture: Arc::new(ScreenCapture::new()?),
            
            task_queue: Arc::new(Mutex::new(BinaryHeap::new())),
            active_tasks: Arc::new(AtomicU32::new(0)),
            max_concurrent_tasks: 4,
            global_timeout: Duration::from_millis(500),
            
            cache: Arc::new(RwLock::new(HashMap::new())),
            cache_ttl: Duration::from_millis(100),
            
            collection_stats: Arc::new(Mutex::new(CollectionStats::default())),
        })
    }
    
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.global_timeout = timeout;
        self
    }
    
    pub fn with_max_concurrent_tasks(mut self, max_tasks: u32) -> Self {
        self.max_concurrent_tasks = max_tasks;
        self
    }
    
    /// Perform intelligent context collection with priority-based execution
    pub async fn collect_context(&self) -> Result<RawContext> {
        let start_time = Instant::now();
        let mut context = RawContext::default();
        
        // Update stats
        {
            let mut stats = self.collection_stats.lock().await;
            stats.total_collections += 1;
        }
        
        // Build collection plan
        let tasks = self.build_collection_plan().await;
        
        // Execute collection with smart strategy
        let results = self.execute_collection_plan(tasks).await?;
        
        // Assemble context from results
        context = self.assemble_context_from_results(results).await?;
        
        // Update metadata
        let duration = start_time.elapsed();
        context.collection_metadata = self.build_collection_metadata(duration).await;
        
        // Update stats
        {
            let mut stats = self.collection_stats.lock().await;
            stats.successful_collections += 1;
            stats.average_duration_ms = 
                (stats.average_duration_ms * (stats.successful_collections - 1) as f64 + duration.as_millis() as f64) 
                / stats.successful_collections as f64;
        }
        
        Ok(context)
    }
    
    /// Check what data sources are currently available
    pub async fn check_available_sources(&self) -> HashMap<DataSourceType, bool> {
        let mut sources = HashMap::new();
        
        // Check app detection (always available)
        sources.insert(DataSourceType::AppInfo, true);
        
        // Check browser availability
        let chromium_available = self.chromium_bridge.is_available().await;
        let safari_available = self.safari_bridge.is_available().await;
        sources.insert(DataSourceType::DOM, chromium_available || safari_available);
        
        // Check accessibility permissions
        let accessibility_available = {
            let bridge = self.accessibility_bridge.lock().await;
            bridge.check_accessibility_permissions()
        };
        sources.insert(DataSourceType::Accessibility, accessibility_available);
        
        // Check OCR engine
        let ocr_available = true; // OCR is always available, may fallback gracefully
        sources.insert(DataSourceType::OCR, ocr_available);
        
        // Check screen capture permissions
        let screenshot_available = self.screen_capture.check_permission();
        sources.insert(DataSourceType::Screenshot, screenshot_available);
        
        sources.insert(DataSourceType::FileSystem, true); // Always available
        sources.insert(DataSourceType::ActivityMonitoring, true); // Always available
        
        sources
    }
    
    /// Get collection statistics
    pub async fn get_stats(&self) -> CollectionStats {
        let stats = self.collection_stats.lock().await;
        (*stats).clone()
    }
    
    /// Clear cache
    pub async fn clear_cache(&self) {
        let mut cache = self.cache.write().await;
        cache.clear();
    }
    
    // Private implementation methods
    
    async fn build_collection_plan(&self) -> Vec<CollectionTask> {
        let available_sources = self.check_available_sources().await;
        let mut tasks = Vec::new();
        
        // Priority 0 (highest): App info - always first, fast, needed by others
        if *available_sources.get(&DataSourceType::AppInfo).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::AppInfo, 0, 50)
                    .sequential() // Must run first
            );
        }
        
        // Priority 1: Browser context - fast when available
        if *available_sources.get(&DataSourceType::DOM).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::DOM, 1, 200)
                    .with_dependencies(vec![DataSourceType::AppInfo])
            );
        }
        
        // Priority 2: Accessibility - medium speed, good data
        if *available_sources.get(&DataSourceType::Accessibility).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::Accessibility, 2, 150)
                    .with_dependencies(vec![DataSourceType::AppInfo])
            );
        }
        
        // Priority 3: File system context - fast for IDEs
        if *available_sources.get(&DataSourceType::FileSystem).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::FileSystem, 3, 100)
                    .with_dependencies(vec![DataSourceType::AppInfo])
            );
        }
        
        // Priority 4: Activity monitoring - always available, fast
        if *available_sources.get(&DataSourceType::ActivityMonitoring).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::ActivityMonitoring, 4, 50)
            );
        }
        
        // Priority 5: Screenshot - needed for OCR, slower
        if *available_sources.get(&DataSourceType::Screenshot).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::Screenshot, 5, 300)
            );
        }
        
        // Priority 6 (lowest): OCR - slowest, only when needed
        if *available_sources.get(&DataSourceType::OCR).unwrap_or(&false) {
            tasks.push(
                CollectionTask::new(DataSourceType::OCR, 6, 2000)
                    .with_dependencies(vec![DataSourceType::Screenshot])
                    .sequential() // OCR is CPU intensive
            );
        }
        
        tasks
    }
    
    async fn execute_collection_plan(&self, tasks: Vec<CollectionTask>) -> Result<HashMap<DataSourceType, CollectionResult>> {
        let mut results = HashMap::new();
        let mut pending_tasks = BinaryHeap::new();
        let mut completed_types = std::collections::HashSet::new();
        
        // Add all tasks to queue
        for task in tasks {
            pending_tasks.push(task);
        }
        
        let global_start = Instant::now();
        
        while !pending_tasks.is_empty() && global_start.elapsed() < self.global_timeout {
            // Find tasks that can run now (dependencies satisfied)
            let mut ready_tasks = Vec::new();
            let mut remaining_tasks = BinaryHeap::new();
            
            while let Some(task) = pending_tasks.pop() {
                let dependencies_met = task.depends_on.iter()
                    .all(|dep| completed_types.contains(dep));
                
                if dependencies_met {
                    ready_tasks.push(task);
                } else {
                    remaining_tasks.push(task);
                }
            }
            
            pending_tasks = remaining_tasks;
            
            if ready_tasks.is_empty() {
                break; // No more tasks can run (circular dependencies?)
            }
            
            // Execute ready tasks
            if ready_tasks.iter().any(|t| !t.can_run_parallel) {
                // Run sequential tasks one by one
                for task in ready_tasks {
                    if global_start.elapsed() >= self.global_timeout {
                        break;
                    }
                    
                    let remaining_time = self.global_timeout.saturating_sub(global_start.elapsed());
                    let result = self.execute_single_task(task.task_type, remaining_time).await;
                    results.insert(task.task_type, result);
                    completed_types.insert(task.task_type);
                }
            } else {
                // Run parallel tasks concurrently
                let parallel_tasks = ready_tasks.into_iter()
                    .take(self.max_concurrent_tasks as usize)
                    .collect::<Vec<_>>();
                
                let task_futures = parallel_tasks.iter().map(|task| {
                    let remaining_time = self.global_timeout.saturating_sub(global_start.elapsed());
                    let task_type = task.task_type;
                    async move {
                        let result = self.execute_single_task(task_type, remaining_time).await;
                        (task_type, result)
                    }
                });
                
                let parallel_results = join_all(task_futures).await;
                
                for (task_type, result) in parallel_results {
                    results.insert(task_type, result);
                    completed_types.insert(task_type);
                }
            }
        }
        
        Ok(results)
    }
    
    async fn execute_single_task(&self, task_type: DataSourceType, timeout_duration: Duration) -> CollectionResult {
        let start_time = Instant::now();
        
        // Check cache first
        if let Some(cached) = self.get_from_cache(&task_type).await {
            let mut stats = self.collection_stats.lock().await;
            stats.cache_hits += 1;
            
            return CollectionResult {
                success: true,
                data: Some(cached.data),
                duration: start_time.elapsed(),
                from_cache: true,
                error: None,
            };
        }
        
        // Execute task with timeout
        let result = timeout(timeout_duration, self.execute_task_impl(task_type)).await;
        
        let (success, data, error) = match result {
            Ok(Ok(data)) => (true, Some(data), None),
            Ok(Err(e)) => (false, None, Some(e.to_string())),
            Err(_) => {
                let mut stats = self.collection_stats.lock().await;
                stats.timeout_count += 1;
                (false, None, Some("Task timeout".to_string()))
            }
        };
        
        let duration = start_time.elapsed();
        
        // Cache successful results
        if success && data.is_some() {
            self.cache_result(task_type, data.as_ref().unwrap().clone()).await;
        }
        
        // Update stats
        {
            let mut stats = self.collection_stats.lock().await;
            stats.cache_misses += 1;
            if !success {
                stats.error_count += 1;
            }
        }
        
        CollectionResult {
            success,
            data,
            duration,
            from_cache: false,
            error,
        }
    }
    
    async fn execute_task_impl(&self, task_type: DataSourceType) -> Result<CachedData> {
        match task_type {
            DataSourceType::AppInfo => {
                let mut detector = self.app_detector.lock().await;
                let app_info = detector.get_active_app_info()?;
                Ok(CachedData::AppInfo(app_info))
            }
            
            DataSourceType::DOM => {
                // Try Chrome first, then Safari
                if self.chromium_bridge.is_available().await {
                    let dom_data = self.chromium_bridge.extract_browser_context().await?;
                    Ok(CachedData::DOMData(dom_data))
                } else if self.safari_bridge.is_available().await {
                    let dom_data = self.safari_bridge.extract_browser_context().await?;
                    Ok(CachedData::DOMData(dom_data))
                } else {
                    Err(anyhow::anyhow!("No browser available"))
                }
            }
            
            DataSourceType::Accessibility => {
                // Need app PID from cache or fresh collection
                let app_pid = if let Some(CachedData::AppInfo(app_info)) = self.get_cached_data(&DataSourceType::AppInfo).await {
                    app_info.process_id
                } else {
                    let mut detector = self.app_detector.lock().await;
                    let app_info = detector.get_active_app_info()?;
                    app_info.process_id
                };
                
                let mut bridge = self.accessibility_bridge.lock().await;
                let accessibility_data = bridge.get_accessibility_data(app_pid).await?;
                Ok(CachedData::AccessibilityData(accessibility_data))
            }
            
            DataSourceType::Screenshot => {
                let screenshot = self.screen_capture.capture_full_screen()?;
                Ok(CachedData::Screenshot(screenshot))
            }
            
            DataSourceType::OCR => {
                // OCR needs a screenshot
                let screenshot = if let Some(CachedData::Screenshot(img)) = self.get_cached_data(&DataSourceType::Screenshot).await {
                    img
                } else {
                    self.screen_capture.capture_full_screen()?
                };

                let start_time = std::time::Instant::now();

                // Detect text regions and process with OCR
                let regions = self.ocr_engine.detect_text_regions(&screenshot)?;
                let ocr_results = self.ocr_engine.batch_process_regions(&regions, &screenshot).await?;

                // OCRResult from ocr_tesseract is already the correct type for OCRData
                let total_confidence = if ocr_results.is_empty() {
                    0.0
                } else {
                    ocr_results.iter().map(|r| r.confidence).sum::<f32>() / ocr_results.len() as f32
                };

                let ocr_data = crate::screen_context::context_data::OCRData {
                    results: ocr_results,
                    total_confidence,
                    processing_time_ms: start_time.elapsed().as_millis() as u64,
                };

                Ok(CachedData::OCRData(ocr_data))
            }
            
            DataSourceType::FileSystem => {
                // File system context collection would go here
                Err(anyhow::anyhow!("FileSystem collection not implemented"))
            }
            
            DataSourceType::ActivityMonitoring => {
                // Activity monitoring would go here
                Err(anyhow::anyhow!("ActivityMonitoring collection not implemented"))
            }
        }
    }
    
    async fn get_from_cache(&self, task_type: &DataSourceType) -> Option<CachedResult> {
        let cache = self.cache.read().await;
        let key = format!("{:?}", task_type);
        
        if let Some(cached) = cache.get(&key) {
            if cached.cached_at.elapsed() < self.cache_ttl {
                return Some(cached.clone());
            }
        }
        
        None
    }
    
    async fn get_cached_data(&self, task_type: &DataSourceType) -> Option<CachedData> {
        self.get_from_cache(task_type).await.map(|result| result.data)
    }
    
    async fn cache_result(&self, task_type: DataSourceType, data: CachedData) {
        let mut cache = self.cache.write().await;
        let key = format!("{:?}", task_type);
        
        cache.insert(key, CachedResult {
            data,
            cached_at: Instant::now(),
            hit_count: 0,
        });
    }
    
    async fn assemble_context_from_results(&self, results: HashMap<DataSourceType, CollectionResult>) -> Result<RawContext> {
        let mut context = RawContext::default();
        
        // Extract app info
        if let Some(result) = results.get(&DataSourceType::AppInfo) {
            if let Some(CachedData::AppInfo(app_info)) = &result.data {
                context.app_info = app_info.clone();
            }
        }
        
        // Extract DOM data
        if let Some(result) = results.get(&DataSourceType::DOM) {
            if let Some(CachedData::DOMData(dom_data)) = &result.data {
                context.dom_data = Some(dom_data.clone());
            }
        }
        
        // Extract accessibility data
        if let Some(result) = results.get(&DataSourceType::Accessibility) {
            if let Some(CachedData::AccessibilityData(acc_data)) = &result.data {
                context.accessibility_data = Some(acc_data.clone());
            }
        }
        
        // Extract screenshot data and create visual data
        if let Some(result) = results.get(&DataSourceType::Screenshot) {
            if let Some(CachedData::Screenshot(screenshot)) = &result.data {
                // Create basic visual data with screenshot hash
                let mut hasher = DefaultHasher::new();
                screenshot.as_bytes().hash(&mut hasher);
                let screenshot_hash = format!("{:x}", hasher.finish());

                context.visual_data = Some(crate::screen_context::context_data::VisualData {
                    screenshot_hash,
                    changed_regions: Vec::new(),
                    dominant_colors: Vec::new(),
                    text_regions: Vec::new(),
                    ui_elements_detected: Vec::new(),
                });
            }
        }

        // Extract OCR data
        if let Some(result) = results.get(&DataSourceType::OCR) {
            if let Some(CachedData::OCRData(ocr_data)) = &result.data {
                context.ocr_data = Some(ocr_data.clone());
            }
        }

        Ok(context)
    }
    
    async fn build_collection_metadata(&self, duration: Duration) -> CollectionMetadata {
        let stats = self.collection_stats.lock().await;
        
        CollectionMetadata {
            collection_duration_ms: duration.as_millis() as u64,
            data_sources_attempted: Vec::new(), // Would populate from execution results
            total_timeout_ms: self.global_timeout.as_millis() as u64,
            cache_hits: stats.cache_hits,
            cache_misses: stats.cache_misses,
            errors: Vec::new(), // Would populate from execution errors
            parallel_collections: self.max_concurrent_tasks,
        }
    }
}

#[derive(Debug)]
struct CollectionResult {
    success: bool,
    data: Option<CachedData>,
    duration: Duration,
    from_cache: bool,
    error: Option<String>,
}

impl Default for SmartCollector {
    fn default() -> Self {
        Self::new().expect("Failed to initialize SmartCollector")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_smart_collector_creation() {
        let collector = SmartCollector::new();
        assert!(collector.is_ok());
    }
    
    #[test]
    fn test_configuration() {
        let collector = SmartCollector::new().unwrap()
            .with_timeout(Duration::from_secs(1))
            .with_max_concurrent_tasks(2);
        
        assert_eq!(collector.global_timeout, Duration::from_secs(1));
        assert_eq!(collector.max_concurrent_tasks, 2);
    }
    
    #[tokio::test]
    async fn test_check_available_sources() {
        let collector = SmartCollector::new().unwrap();
        let sources = collector.check_available_sources().await;
        
        // App info should always be available
        assert_eq!(sources.get(&DataSourceType::AppInfo), Some(&true));
        
        // Other sources depend on system state
        assert!(sources.contains_key(&DataSourceType::DOM));
        assert!(sources.contains_key(&DataSourceType::Accessibility));
    }
    
    #[tokio::test]
    async fn test_build_collection_plan() {
        let collector = SmartCollector::new().unwrap();
        let tasks = collector.build_collection_plan().await;
        
        // Should have at least the always-available tasks
        assert!(!tasks.is_empty());
        
        // App info should have highest priority (lowest number)
        let app_task = tasks.iter().find(|t| t.task_type == DataSourceType::AppInfo);
        assert!(app_task.is_some());
        assert_eq!(app_task.unwrap().priority, 0);
    }
    
    #[tokio::test]
    async fn test_cache_operations() {
        let collector = SmartCollector::new().unwrap();
        
        // Cache should be empty initially
        let cached = collector.get_from_cache(&DataSourceType::AppInfo).await;
        assert!(cached.is_none());
        
        // Clear cache should not panic
        collector.clear_cache().await;
    }
}