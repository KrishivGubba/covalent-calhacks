use anyhow::Result;
use chrono::{DateTime, Utc};
use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::{broadcast, Mutex, RwLock};
use tokio::time::interval;
use crate::screen_context::macos_app_detector::MacOSAppDetector;
use crate::screen_context::context_data::AppInfo;

use crate::screen_context::context_data::{
    ActivityEntry, ActivityLevel, ActivityMetrics, ActivityTimeline, MouseActivity, MousePatterns,
    ScrollActivity, ScrollDirection, TransitionType, TypingActivity, TypingPatterns,
};
use crate::screen_context::context_type::{ContextType, DevelopmentType, ResearchType};

// CGEventTap implementation for macOS
// DISABLED: Using rdev causes version conflicts with core-graphics and can lead to crashes
// The tab completion system already has event monitoring via MacOSKeyboardListener
#[cfg(target_os = "macos")]
mod cg_event_tap {
    use super::*;
    use std::sync::mpsc as std_mpsc;

    pub struct EventTapHandle {
        _phantom: std::marker::PhantomData<()>,
    }

    impl Drop for EventTapHandle {
        fn drop(&mut self) {
            // Nothing to clean up
        }
    }

    pub fn start_event_tap(_event_sender: std_mpsc::Sender<ActivityEvent>) -> Result<EventTapHandle> {
        // Event tap disabled - activity monitoring will rely on periodic polling
        // This prevents conflicts with the MacOSKeyboardListener and HotkeyHandler event taps
        eprintln!("ℹ️  ActivityMonitor CGEventTap disabled to prevent conflicts");
        eprintln!("   Activity metrics will be computed from periodic context collection");
        
        Ok(EventTapHandle { 
            _phantom: std::marker::PhantomData 
        })
    }
}

#[derive(Debug, Clone)]
pub struct ActivityEvent {
    pub timestamp: Instant,
    pub event_type: ActivityEventType,
}

#[derive(Debug, Clone)]
pub enum ActivityEventType {
    KeyPressed,
    MouseClicked { x: f64, y: f64 },
    MouseMoved { x: f64, y: f64 },
    ScrollEvent { delta_x: f64, delta_y: f64 },
    AppSwitched { from_app: String, to_app: String },
    WindowFocused { app_name: String, window_title: String },
}

pub struct ActivityMonitor {
    // Event tracking
    recent_events: Arc<Mutex<VecDeque<ActivityEvent>>>,
    event_retention_duration: Duration,
    
    // Activity metrics
    last_activity: Arc<Mutex<Instant>>,
    keystroke_count: Arc<AtomicU64>,
    mouse_click_count: Arc<AtomicU64>,
    scroll_count: Arc<AtomicU64>,
    
    // Context tracking
    current_context: Arc<RwLock<Option<ContextEntry>>>,
    current_app: Arc<Mutex<Option<AppInfo>>>,
    app_detector: Arc<Mutex<MacOSAppDetector>>,
    context_history: Arc<Mutex<VecDeque<ContextEntry>>>,
    context_switches_today: Arc<AtomicU64>,
    app_switch_tx: broadcast::Sender<AppInfo>,
    
    // Timeline
    activity_timeline: Arc<Mutex<ActivityTimeline>>,
    session_start: DateTime<Utc>,
    
    // Configuration
    idle_threshold: Duration,
    activity_window: Duration,
    max_history_size: usize,
    
    // CGEventTap handle
    #[cfg(target_os = "macos")]
    event_tap_handle: Arc<Mutex<Option<cg_event_tap::EventTapHandle>>>,
    
    // Channel for receiving events from CGEventTap
    event_receiver: Arc<Mutex<Option<std::sync::mpsc::Receiver<ActivityEvent>>>>,
}

#[derive(Debug, Clone)]
struct ContextEntry {
    app_name: String,
    window_title: Option<String>,
    context_type: ContextType,
    started_at: Instant,
    last_activity: Instant,
    activity_level: ActivityLevel,
}

impl ActivityMonitor {
    pub fn new() -> Result<Self> {
        let (app_switch_tx, _) = broadcast::channel(100);
        
        // Create channel for CGEventTap events
        let (event_sender, event_receiver) = std::sync::mpsc::channel();
        
        // Start CGEventTap on macOS
        #[cfg(target_os = "macos")]
        let event_tap_handle = match cg_event_tap::start_event_tap(event_sender) {
            Ok(handle) => {
                println!("✓ CGEventTap started successfully - activity monitoring enabled");
                Some(handle)
            }
            Err(e) => {
                eprintln!("⚠ Failed to start CGEventTap: {}. Activity detection will be limited.", e);
                eprintln!("  Make sure the app has Accessibility permissions in System Settings.");
                None
            }
        };
        
        Ok(Self {
            recent_events: Arc::new(Mutex::new(VecDeque::new())),
            event_retention_duration: Duration::from_secs(300), // 5 minutes
            
            last_activity: Arc::new(Mutex::new(Instant::now())),
            keystroke_count: Arc::new(AtomicU64::new(0)),
            mouse_click_count: Arc::new(AtomicU64::new(0)),
            scroll_count: Arc::new(AtomicU64::new(0)),
            
            current_context: Arc::new(RwLock::new(None)),
            current_app: Arc::new(Mutex::new(None)),
            app_detector: Arc::new(Mutex::new(MacOSAppDetector::new()?)),
            context_history: Arc::new(Mutex::new(VecDeque::new())),
            context_switches_today: Arc::new(AtomicU64::new(0)),
            app_switch_tx,
            
            activity_timeline: Arc::new(Mutex::new(ActivityTimeline {
                entries: Vec::new(),
                current_session_start: Utc::now(),
                total_active_time: Duration::from_secs(0),
                context_switches_today: 0,
            })),
            session_start: Utc::now(),
            
            idle_threshold: Duration::from_secs(30),
            activity_window: Duration::from_secs(60),
            max_history_size: 1000,
            
            #[cfg(target_os = "macos")]
            event_tap_handle: Arc::new(Mutex::new(event_tap_handle)),
            event_receiver: Arc::new(Mutex::new(Some(event_receiver))),
        })
    }

    pub fn with_idle_threshold(mut self, threshold: Duration) -> Self {
        self.idle_threshold = threshold;
        self
    }
    
    pub fn with_activity_window(mut self, window: Duration) -> Self {
        self.activity_window = window;
        self
    }
    
    /// Start monitoring system activity
    pub async fn start_monitoring(&self) -> Result<()> {
        // Take ownership of the event receiver
        let event_receiver = {
            let mut receiver_guard = self.event_receiver.lock().await;
            receiver_guard.take()
        };
        
        // Start event collection task from CGEventTap
        let events_clone = Arc::clone(&self.recent_events);
        let last_activity_clone = Arc::clone(&self.last_activity);
        let keystroke_count_clone = Arc::clone(&self.keystroke_count);
        let mouse_click_count_clone = Arc::clone(&self.mouse_click_count);
        let scroll_count_clone = Arc::clone(&self.scroll_count);
        
        if let Some(receiver) = event_receiver {
            tokio::spawn(async move {
                loop {
                    // Try to receive events from CGEventTap (non-blocking with timeout)
                    match receiver.recv_timeout(Duration::from_millis(50)) {
                        Ok(event) => {
                            let now = Instant::now();
                            
                            // Update counters based on event type
                            match &event.event_type {
                                ActivityEventType::KeyPressed => {
                                    keystroke_count_clone.fetch_add(1, Ordering::Relaxed);
                                }
                                ActivityEventType::MouseClicked { .. } => {
                                    mouse_click_count_clone.fetch_add(1, Ordering::Relaxed);
                                }
                                ActivityEventType::ScrollEvent { .. } => {
                                    scroll_count_clone.fetch_add(1, Ordering::Relaxed);
                                }
                                _ => {}
                            }
                            
                            // Update last activity time
                            {
                                let mut last_activity = last_activity_clone.lock().await;
                                *last_activity = now;
                            }
                            
                            // Add to event queue
                            {
                                let mut events = events_clone.lock().await;
                                events.push_back(event);
                                
                                // Keep only recent events (5 minutes)
                                let cutoff = now - Duration::from_secs(300);
                                while let Some(front) = events.front() {
                                    if front.timestamp < cutoff {
                                        events.pop_front();
                                    } else {
                                        break;
                                    }
                                }
                            }
                        }
                        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                            // No events, continue
                            tokio::time::sleep(Duration::from_millis(10)).await;
                        }
                        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                            eprintln!("CGEventTap channel disconnected");
                            break;
                        }
                    }
                }
            });
        } else {
            eprintln!("⚠ No event receiver available - activity monitoring disabled");
        }
        
        let mut interval = interval(Duration::from_secs(1));
        let mut app_switch_rx = self.app_switch_tx.subscribe();
        
        loop {
            tokio::select! {
                _ = interval.tick() => {
                    // Regular activity check - no longer needed to update last_activity
                    // as CGEventTap handles it
                }
                
                result = app_switch_rx.recv() => {
                    if let Ok(new_app) = result {
                        // Handle app switch
                        self.handle_app_switch(new_app).await?;
                    }
                }
            }
        }
        
        #[allow(unreachable_code)]
        Ok(())
    }
    
    /// Get current activity metrics
    pub async fn get_activity_metrics(&self) -> ActivityMetrics {
        let now = Instant::now();
        let last_activity_time = *self.last_activity.lock().await;
        let idle_duration = now.duration_since(last_activity_time);
        
        let is_idle = idle_duration > self.idle_threshold;
        
        // Calculate activity level based on recent events
        let activity_level = self.calculate_activity_level().await;
        
        // Get typing activity
        let typing_activity = self.calculate_typing_activity().await;
        
        // Get mouse activity
        let mouse_activity = self.calculate_mouse_activity().await;
        
        // Get context information
        let (time_in_current_context, context_switches) = {
            let current_context = self.current_context.read().await;
            let time_in_context = if let Some(ref context) = *current_context {
                now.duration_since(context.started_at)
            } else {
                Duration::from_secs(0)
            };
            
            let switches = self.context_switches_today.load(Ordering::Relaxed) as u32;
            (time_in_context, switches)
        };
        
        ActivityMetrics {
            is_idle,
            idle_duration: if is_idle { Some(idle_duration) } else { None },
            last_activity: DateTime::from(
                UNIX_EPOCH + Duration::from_secs(
                    last_activity_time.elapsed().as_secs().saturating_sub(
                        SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()
                    )
                )
            ),
            activity_level,
            context_switches,
            time_in_current_context,
            typing_activity,
            mouse_activity,
        }
    }
    
    /// Record a context switch
    pub async fn record_context_switch(
        &self,
        app_name: String,
        window_title: Option<String>,
        context_type: ContextType,
    ) -> Result<()> {
        let now = Instant::now();
        
        // Get current context to determine transition type
        let (transition_type, previous_context) = {
            let mut current_context = self.current_context.write().await;
            let transition_type = if let Some(ref current) = *current_context {
                if current.app_name == app_name {
                    TransitionType::ContextSwitch
                } else {
                    TransitionType::AppSwitch
                }
            } else {
                TransitionType::NewSession
            };
            
            let previous = current_context.clone();
            
            // Set new context
            *current_context = Some(ContextEntry {
                app_name: app_name.clone(),
                window_title: window_title.clone(),
                context_type: context_type.clone(),
                started_at: now,
                last_activity: now,
                activity_level: ActivityLevel::Medium,
            });
            
            (transition_type, previous)
        };
        
        // Update context switch counter
        self.context_switches_today.fetch_add(1, Ordering::Relaxed);
        
        // Add to timeline
        {
            let mut timeline = self.activity_timeline.lock().await;
            
            // If there was a previous context, add it to the timeline
            if let Some(prev_context) = previous_context.clone() {
                let duration = now.duration_since(prev_context.started_at);
                
                timeline.entries.push(ActivityEntry {
                    timestamp: DateTime::from(
                        UNIX_EPOCH + Duration::from_secs(
                            prev_context.started_at.elapsed().as_secs().saturating_sub(
                                SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()
                            )
                        )
                    ),
                    context_type: prev_context.context_type,
                    app_name: prev_context.app_name,
                    activity_level: prev_context.activity_level,
                    duration,
                    transition_type: transition_type.clone(),
                });
                
                timeline.total_active_time += duration;
            }
            
            timeline.context_switches_today = self.context_switches_today.load(Ordering::Relaxed) as u32;
        }
        
        // Add to context history
        {
            let mut history = self.context_history.lock().await;
            if let Some(prev_context) = previous_context {
                history.push_back(prev_context);
                
                // Keep history size manageable
                if history.len() > self.max_history_size {
                    history.pop_front();
                }
            }
        }
        
        Ok(())
    }
    
    /// Get activity timeline
    pub async fn get_activity_timeline(&self) -> ActivityTimeline {
        self.activity_timeline.lock().await.clone()
    }
    
    /// Detect if user is currently active vs idle
    pub async fn is_user_active(&self) -> bool {
        let last_activity = *self.last_activity.lock().await;
        let idle_duration = Instant::now().duration_since(last_activity);
        idle_duration <= self.idle_threshold
    }
    
    /// Get context switching patterns
    pub async fn get_context_patterns(&self) -> HashMap<String, u32> {
        let history = self.context_history.lock().await;
        let mut patterns = HashMap::new();
        
        for context in history.iter() {
            let key = format!("{}:{}", context.app_name, context.context_type.category_name());
            *patterns.entry(key).or_insert(0) += 1;
        }
        
        patterns
    }
    
    // Private helper methods
    
    async fn handle_app_switch(&self, new_app: AppInfo) -> Result<()> {
        let mut current_app = self.current_app.lock().await;
        
        // Check if this is actually a new app
        if let Some(ref current) = *current_app {
            if current.bundle_id == new_app.bundle_id {
                return Ok(());
            }
        }
        
        // Update current app
        *current_app = Some(new_app.clone());
        
        // Record context switch
        let (mut detected_context, _) = if let Some(title) = new_app.window_title.as_deref() {
            ContextType::from_window_title(title, Some(&new_app.bundle_id))
        } else {
            ContextType::from_app_bundle_id(&new_app.bundle_id)
        };

        if new_app.is_ide {
            detected_context = ContextType::Development(DevelopmentType::Frontend);
        } else if new_app.is_browser {
            detected_context = ContextType::Research(ResearchType::TechnicalResearch);
        }

        self.record_context_switch(
            new_app.name,
            new_app.window_title,
            detected_context,
        ).await?;
        
        Ok(())
    }
    
    #[allow(dead_code)]
    async fn detect_system_activity() -> Option<ActivityEvent> {
        // This is now handled by CGEventTap
        None
    }
    
    async fn calculate_activity_level(&self) -> ActivityLevel {
        let now = Instant::now();
        let window_start = now - self.activity_window;
        
        let events = self.recent_events.lock().await;
        let recent_events: Vec<_> = events
            .iter()
            .filter(|event| event.timestamp >= window_start)
            .collect();
        
        let event_count = recent_events.len();
        
        // Classify activity level based on event frequency
        match event_count {
            0..=5 => ActivityLevel::Idle,
            6..=20 => ActivityLevel::Low,
            21..=50 => ActivityLevel::Medium,
            _ => ActivityLevel::High,
        }
    }
    
    async fn calculate_typing_activity(&self) -> TypingActivity {
        let now = Instant::now();
        let window_start = now - self.activity_window;
        
        let events = self.recent_events.lock().await;
        let key_events: Vec<_> = events
            .iter()
            .filter(|event| {
                event.timestamp >= window_start && 
                matches!(event.event_type, ActivityEventType::KeyPressed)
            })
            .collect();
        
        let keystrokes_per_minute = if !key_events.is_empty() {
            (key_events.len() as f32 / self.activity_window.as_secs() as f32) * 60.0
        } else {
            0.0
        };
        
        // Analyze typing patterns
        let patterns = self.analyze_typing_patterns(&key_events).await;
        
        let last_keystroke = key_events.last().map(|event| {
            DateTime::from(
                UNIX_EPOCH + Duration::from_secs(
                    event.timestamp.elapsed().as_secs().saturating_sub(
                        SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()
                    )
                )
            )
        });
        
        TypingActivity {
            keystrokes_per_minute,
            last_keystroke,
            typing_patterns: patterns,
        }
    }
    
    async fn analyze_typing_patterns(&self, key_events: &[&ActivityEvent]) -> TypingPatterns {
        if key_events.len() < 3 {
            return TypingPatterns::default();
        }
        
        // Analyze intervals between keystrokes
        let mut intervals = Vec::new();
        for window in key_events.windows(2) {
            let interval = window[1].timestamp.duration_since(window[0].timestamp);
            intervals.push(interval);
        }
        
        // Calculate statistics
        let avg_interval = if !intervals.is_empty() {
            intervals.iter().sum::<Duration>() / intervals.len() as u32
        } else {
            Duration::from_millis(500)
        };
        
        // Detect patterns
        let burst_typing = intervals.iter().any(|&interval| interval < Duration::from_millis(100));
        let steady_typing = intervals.iter().all(|&interval| {
            let diff = if interval > avg_interval {
                interval - avg_interval
            } else {
                avg_interval - interval
            };
            diff < Duration::from_millis(200)
        });
        let hunt_and_peck = avg_interval > Duration::from_millis(800);
        
        TypingPatterns {
            burst_typing,
            steady_typing,
            hunt_and_peck,
        }
    }
    
    async fn calculate_mouse_activity(&self) -> MouseActivity {
        let now = Instant::now();
        let window_start = now - self.activity_window;
        
        let events = self.recent_events.lock().await;
        
        // Count mouse clicks
        let click_events: Vec<_> = events
            .iter()
            .filter(|event| {
                event.timestamp >= window_start && 
                matches!(event.event_type, ActivityEventType::MouseClicked { .. })
            })
            .collect();
        
        let clicks_per_minute = if !click_events.is_empty() {
            (click_events.len() as f32 / self.activity_window.as_secs() as f32) * 60.0
        } else {
            0.0
        };
        
        let last_click = click_events.last().map(|event| {
            DateTime::from(
                UNIX_EPOCH + Duration::from_secs(
                    event.timestamp.elapsed().as_secs().saturating_sub(
                        SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()
                    )
                )
            )
        });
        
        // Analyze scroll activity
        let scroll_activity = self.analyze_scroll_activity(&events, window_start).await;
        
        // Analyze movement patterns
        let movement_patterns = self.analyze_mouse_patterns(&events, window_start).await;
        
        MouseActivity {
            clicks_per_minute,
            last_click,
            scroll_activity,
            movement_patterns,
        }
    }
    
    async fn analyze_scroll_activity(&self, events: &VecDeque<ActivityEvent>, window_start: Instant) -> ScrollActivity {
        let scroll_events: Vec<_> = events
            .iter()
            .filter(|event| {
                event.timestamp >= window_start && 
                matches!(event.event_type, ActivityEventType::ScrollEvent { .. })
            })
            .collect();
        
        let scrolls_per_minute = if !scroll_events.is_empty() {
            (scroll_events.len() as f32 / self.activity_window.as_secs() as f32) * 60.0
        } else {
            0.0
        };
        
        // Determine predominant scroll direction
        let mut up_count = 0;
        let mut down_count = 0;
        let mut left_count = 0;
        let mut right_count = 0;
        
        for event in &scroll_events {
            if let ActivityEventType::ScrollEvent { delta_x, delta_y } = &event.event_type {
                if delta_y.abs() > delta_x.abs() {
                    if *delta_y > 0.0 { up_count += 1; } else { down_count += 1; }
                } else {
                    if *delta_x > 0.0 { right_count += 1; } else { left_count += 1; }
                }
            }
        }
        
        let predominant_direction = if down_count > up_count && down_count > left_count && down_count > right_count {
            ScrollDirection::Down
        } else if up_count > left_count && up_count > right_count {
            ScrollDirection::Up
        } else if left_count > right_count {
            ScrollDirection::Left
        } else if right_count > 0 {
            ScrollDirection::Right
        } else {
            ScrollDirection::Mixed
        };
        
        ScrollActivity {
            scrolls_per_minute,
            predominant_direction,
        }
    }
    
    async fn analyze_mouse_patterns(&self, events: &VecDeque<ActivityEvent>, window_start: Instant) -> MousePatterns {
        let mouse_events: Vec<_> = events
            .iter()
            .filter(|event| {
                event.timestamp >= window_start && 
                (matches!(event.event_type, ActivityEventType::MouseMoved { .. }) ||
                 matches!(event.event_type, ActivityEventType::MouseClicked { .. }))
            })
            .collect();
        
        if mouse_events.len() < 2 {
            return MousePatterns::default();
        }
        
        // Analyze movement distances
        let mut distances = Vec::new();
        let mut positions = Vec::new();
        
        for event in &mouse_events {
            match &event.event_type {
                ActivityEventType::MouseMoved { x, y } | 
                ActivityEventType::MouseClicked { x, y } => {
                    positions.push((*x, *y));
                }
                _ => {}
            }
        }
        
        for window in positions.windows(2) {
            let (x1, y1) = window[0];
            let (x2, y2) = window[1];
            let distance = ((x2 - x1).powi(2) + (y2 - y1).powi(2)).sqrt();
            distances.push(distance);
        }
        
        let avg_distance = if !distances.is_empty() {
            distances.iter().sum::<f64>() / distances.len() as f64
        } else {
            0.0
        };
        
        // Classify patterns
        let precise_movements = avg_distance < 50.0;
        let broad_movements = avg_distance > 200.0;
        let hovering_behavior = distances.iter().filter(|&&d| d < 5.0).count() > distances.len() / 3;
        
        MousePatterns {
            precise_movements,
            broad_movements,
            hovering_behavior,
        }
    }
}

impl Default for ActivityMonitor {
    fn default() -> Self {
        Self::new().expect("Failed to initialize ActivityMonitor")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_activity_monitor_creation() {
        let monitor = ActivityMonitor::new();
        assert!(monitor.is_ok());
    }
    
    #[test]
    fn test_configuration() {
        let monitor = ActivityMonitor::new().unwrap()
            .with_idle_threshold(Duration::from_secs(60))
            .with_activity_window(Duration::from_secs(120));
        
        assert_eq!(monitor.idle_threshold, Duration::from_secs(60));
        assert_eq!(monitor.activity_window, Duration::from_secs(120));
    }
    
    #[tokio::test]
    async fn test_activity_metrics() {
        let monitor = ActivityMonitor::new().unwrap();
        let metrics = monitor.get_activity_metrics().await;
        
        // Should have default values
        assert!(metrics.is_idle); // Should be idle initially
        assert_eq!(metrics.context_switches, 0);
        assert_eq!(metrics.typing_activity.keystrokes_per_minute, 0.0);
    }
    
    #[tokio::test]
    async fn test_context_switch_recording() {
        let monitor = ActivityMonitor::new().unwrap();
        
        let result = monitor.record_context_switch(
            "TestApp".to_string(),
            Some("Test Window".to_string()),
            ContextType::Unknown,
        ).await;
        
        assert!(result.is_ok());
        
        let metrics = monitor.get_activity_metrics().await;
        assert_eq!(metrics.context_switches, 1);
    }
    
    #[tokio::test]
    async fn test_activity_timeline() {
        let monitor = ActivityMonitor::new().unwrap();
        
        // Record a context switch
        monitor.record_context_switch(
            "App1".to_string(),
            None,
            ContextType::Unknown,
        ).await.unwrap();
        
        let timeline = monitor.get_activity_timeline().await;
        assert_eq!(timeline.context_switches_today, 1);
    }
    
    #[tokio::test]
    async fn test_user_activity_detection() {
        let monitor = ActivityMonitor::new().unwrap();
        
        // Should be active initially (just created)
        let _is_active = monitor.is_user_active().await;
        // Note: This depends on when last_activity was set during initialization
        // In a real scenario, this would be updated by actual system events
    }
}