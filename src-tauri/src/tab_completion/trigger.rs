use anyhow::Result;
use parking_lot::Mutex;
#[cfg(not(target_os = "macos"))]
use rdev::{listen, Event, EventType, Key};
#[cfg(target_os = "macos")]
use super::macos_keyboard::{MacOSKeyboardListener, KeyboardEvent};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use sha2::{Sha256, Digest};
use tokio::runtime::Runtime;

use super::cache::{CacheResult, MultiTierCache, CachedContext, AppContext, current_timestamp};
use super::model::MODEL;
use super::api_client::{TabCompletionApiClient, PredictionRequest, ContextUpdateRequest, DeclineFeedbackRequest};
use super::decline::{DeclineContext, ActionSummary, EnrichedPredictionContext};
use super::prompt_builder::build_enriched_prompt;
#[cfg(target_os = "macos")]
use crate::screen_context::macos_app_detector::MacOSAppDetector;

pub struct CompletionTrigger {
    text_buffer: Arc<Mutex<TextBuffer>>,
    cache: Arc<MultiTierCache>,
    current_app: Arc<Mutex<String>>,
    suggestion_callback: Arc<Mutex<Option<Arc<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
    api_client: Arc<TabCompletionApiClient>,
    runtime: Arc<Runtime>,
    last_prediction_time: Arc<Mutex<Instant>>,
    prediction_debounce: Duration,
    prediction_counter: Arc<Mutex<usize>>, // Counter to throttle Flask learning updates
    /// Current decline context for retry predictions
    decline_context: Arc<Mutex<Option<DeclineContext>>>,
    /// Callback to get current recommended actions
    actions_getter: Arc<Mutex<Option<Box<dyn Fn() -> Vec<ActionSummary> + Send + Sync>>>>,
    /// Whether tab completion is enabled (off by default)
    is_enabled: Arc<AtomicBool>,
    #[cfg(target_os = "macos")]
    keyboard_listener: Arc<Mutex<Option<MacOSKeyboardListener>>>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CompletionSuggestion {
    pub text: String,
    pub cache_level: String,
    pub latency_ms: u128,
    pub context_type: String,
    pub confidence: f32,
}

#[derive(Default)]
struct TextBuffer {
    buffer: String,
    max_size: usize,
    last_update: Option<Instant>,
    chars_since_prediction: usize,
}

impl TextBuffer {
    fn new() -> Self {
        Self {
            buffer: String::new(),
            max_size: 500, // Keep last 500 chars for better context
            last_update: None,
            chars_since_prediction: 0,
        }
    }
    
    fn append(&mut self, ch: char) {
        self.buffer.push(ch);
        self.chars_since_prediction += 1;
        
        if self.buffer.len() > self.max_size {
            self.buffer = self.buffer.chars()
                .skip(self.buffer.len() - self.max_size)
                .collect();
        }
        self.last_update = Some(Instant::now());
    }

    fn backspace(&mut self) {
        if self.buffer.pop().is_some() {
            self.chars_since_prediction = self.chars_since_prediction.saturating_sub(1);
        }
        self.last_update = Some(Instant::now());
    }
    
    fn get_last_n(&self, n: usize) -> String {
        self.buffer.chars().rev().take(n).collect::<String>()
            .chars().rev().collect()
    }
    
    fn get_full_buffer(&self) -> String {
        self.buffer.clone()
    }
    
    fn reset_prediction_counter(&mut self) {
        self.chars_since_prediction = 0;
    }
    
    fn should_trigger_prediction(&self) -> bool {
        // Trigger on word boundaries (space, newline, punctuation) 
        // or every 3 characters
        if self.chars_since_prediction >= 3 {
            return true;
        }
        
        if let Some(last_char) = self.buffer.chars().last() {
            matches!(last_char, ' ' | '\n' | '.' | ',' | ';' | ':' | '!' | '?')
        } else {
            false
        }
    }
    
    fn clear(&mut self) {
        self.buffer.clear();
        self.last_update = None;
        self.chars_since_prediction = 0;
    }

    /// Remove the last n characters from the buffer.
    /// Used to keep the buffer in sync with the terminal after the injector
    /// erases overlap/grace-period chars.
    fn erase_last_n(&mut self, n: usize) {
        let char_count = self.buffer.chars().count();
        let keep = char_count.saturating_sub(n);
        self.buffer = self.buffer.chars().take(keep).collect();
    }
}

/// Confidence threshold configuration for predictions
const CONFIDENCE_THRESHOLD_L0: f32 = 0.0; // L0 exact cache: always accept (instant, exact match)
const CONFIDENCE_THRESHOLD_L1: f32 = 0.5; // L1 LLM: semi-correct is fine (speed priority)
const CONFIDENCE_THRESHOLD_L2: f32 = 0.6; // L2 graph: more context, slightly higher bar
const CONFIDENCE_THRESHOLD_FALLBACK: f32 = 0.4; // L3 fallback: lower bar since it's last resort

impl CompletionTrigger {
    pub fn new(cache: Arc<MultiTierCache>) -> Result<Self> {
        let runtime = Runtime::new()
            .expect("Failed to create tokio runtime for tab completion");

        Ok(Self {
            text_buffer: Arc::new(Mutex::new(TextBuffer::new())),
            cache,
            current_app: Arc::new(Mutex::new(String::from("Unknown"))),
            suggestion_callback: Arc::new(Mutex::new(None)),
            api_client: Arc::new(TabCompletionApiClient::new()),
            runtime: Arc::new(runtime),
            last_prediction_time: Arc::new(Mutex::new(Instant::now())),
            prediction_debounce: Duration::from_millis(150), // 150ms debounce
            prediction_counter: Arc::new(Mutex::new(0)),
            decline_context: Arc::new(Mutex::new(None)),
            actions_getter: Arc::new(Mutex::new(None)),
            is_enabled: Arc::new(AtomicBool::new(false)), // OFF by default
            #[cfg(target_os = "macos")]
            keyboard_listener: Arc::new(Mutex::new(None)),
        })
    }

    /// Returns whether tab completion is currently enabled.
    pub fn is_tab_completion_enabled(&self) -> bool {
        self.is_enabled.load(Ordering::Relaxed)
    }

    /// Enable or disable tab completion.
    pub fn set_tab_completion_enabled(&self, enabled: bool) {
        self.is_enabled.store(enabled, Ordering::Relaxed);
        if enabled {
            println!("🟢 Tab completion ENABLED");
        } else {
            println!("🔴 Tab completion DISABLED");
        }
    }

    /// Toggle tab completion on/off and return the new state.
    pub fn toggle_tab_completion(&self) -> bool {
        let new_state = !self.is_tab_completion_enabled();
        self.set_tab_completion_enabled(new_state);
        new_state
    }
    
    /// Set callback for when a suggestion is generated (for UI integration)
    pub fn set_suggestion_callback<F>(&self, callback: F)
    where
        F: Fn(CompletionSuggestion) + Send + Sync + 'static,
    {
        *self.suggestion_callback.lock() = Some(Arc::new(callback));
    }

    /// Set callback to get current recommended actions for enhanced predictions
    pub fn set_actions_getter<F>(&self, getter: F)
    where
        F: Fn() -> Vec<ActionSummary> + Send + Sync + 'static,
    {
        *self.actions_getter.lock() = Some(Box::new(getter));
    }

    /// Get the full text buffer content
    pub fn get_full_buffer(&self) -> String {
        self.text_buffer.lock().get_full_buffer()
    }

    /// Handle a declined prediction and trigger retry with enhanced context
    pub fn handle_decline(&self, dismissed_text: String, time_shown_ms: u64, chars_typed_after: String) {
        let typed_text = self.get_full_buffer();

        // Create decline context
        let decline = DeclineContext::new(
            dismissed_text.clone(),
            typed_text.clone(),
            chars_typed_after.clone(),
            time_shown_ms,
        );

        // Check if we should retry
        if decline.should_stop_retrying() {
            println!("⚠️  Max retries reached - not retrying prediction");
            *self.decline_context.lock() = None;
            return;
        }

        // Store decline context for the next prediction
        *self.decline_context.lock() = Some(decline.clone());

        // Send decline feedback to Flask (fire-and-forget)
        let api_client = self.api_client.clone();
        let runtime = self.runtime.clone();
        let app = self.current_app.lock().clone();
        let activity_id = Self::generate_activity_id(&app);

        runtime.spawn(async move {
            let request = DeclineFeedbackRequest {
                app_name: app,
                activity_id,
                declined_prediction: dismissed_text,
                typed_text,
                chars_after: chars_typed_after,
                time_to_decline_ms: time_shown_ms,
                signal: "negative".to_string(),
            };

            match api_client.send_decline_feedback(request).await {
                Ok(_) => println!("📤 Decline feedback sent to Flask"),
                Err(e) => eprintln!("⚠️  Failed to send decline feedback: {}", e),
            }
        });

        // Trigger retry prediction with decline context
        self.trigger_completion_with_decline();
    }

    /// Trigger completion with decline context (for retry after decline)
    fn trigger_completion_with_decline(&self) {
        let text = self.text_buffer.lock().get_last_n(100);
        let app = self.current_app.lock().clone();
        let cache = self.cache.clone();
        let api_client = self.api_client.clone();
        let runtime = self.runtime.clone();
        let prediction_counter = self.prediction_counter.clone();
        let decline_context = self.decline_context.lock().clone();
        let callback_ref = self.suggestion_callback.clone();
        let has_callback = self.suggestion_callback.lock().is_some();

        // Get recommended actions if getter is set
        let actions: Vec<ActionSummary> = if let Some(ref getter) = *self.actions_getter.lock() {
            getter()
        } else {
            Vec::new()
        };

        if text.trim().is_empty() {
            return;
        }

        println!("🔄 Triggering retry prediction with decline context");

        // Spawn thread to avoid blocking
        std::thread::spawn(move || {
            Self::get_and_show_prediction_with_decline(
                cache,
                &app,
                &text,
                callback_ref,
                has_callback,
                api_client,
                runtime,
                prediction_counter,
                decline_context,
                actions,
            );
        });
    }
    
    pub fn start_listening(self: Arc<Self>) {
        println!("⌨️  Starting proactive tab completion listener...");

        // Start background app detector — periodically updates current_app
        // so trigger_completion() never needs to call detect_current_app()
        // (which is far too heavy for the keyboard listener thread).
        self.start_app_detector();

        // Start background context updater
        self.start_context_updater();
        
        #[cfg(not(target_os = "macos"))]
        {
            // Use rdev on non-macOS platforms
            let self_clone = self.clone();
            std::thread::spawn(move || {
                if let Err(e) = listen(move |event| {
                    self_clone.handle_event(event);
                }) {
                    eprintln!("Error in keyboard listener: {:?}", e);
                }
            });
        }
        
        #[cfg(target_os = "macos")]
        {
            // Use CGEventTap on macOS
            match MacOSKeyboardListener::new() {
                Ok(listener) => {
                    println!("✅ CGEventTap keyboard listener initialized");
                    *self.keyboard_listener.lock() = Some(listener);
                    
                    // Start processing keyboard events
                    let self_clone = self.clone();
                    std::thread::spawn(move || {
                        self_clone.process_macos_keyboard_events();
                    });
                }
                Err(e) => {
                    eprintln!("⚠️  Failed to initialize CGEventTap: {}", e);
                    eprintln!("   Tab completion will work via API/context updates only");
                    eprintln!("   To enable keyboard tracking, grant Accessibility permissions:");
                    eprintln!("   System Preferences > Security & Privacy > Privacy > Accessibility");
                }
            }
        }
        
        println!("✅ Proactive tab completion listener started");
    }
    
    /// Process keyboard events from macOS CGEventTap (macOS only)
    #[cfg(target_os = "macos")]
    fn process_macos_keyboard_events(&self) {
        let mut event_count: u64 = 0;
        let mut last_event_time = Instant::now();
        let mut seen_any_event = false;
        loop {
            // Skip all processing when tab completion is disabled
            if !self.is_tab_completion_enabled() {
                std::thread::sleep(Duration::from_millis(100));
                continue;
            }
            let listener_guard = self.keyboard_listener.lock();
            let listener = match listener_guard.as_ref() {
                Some(l) => l,
                None => {
                    eprintln!("⚠️  Keyboard listener not initialized");
                    return;
                }
            };

            match listener.try_recv() {
                Ok(event) => {
                    event_count += 1;
                    last_event_time = Instant::now(); // Reset watchdog
                    seen_any_event = true;
                    // Drop lock before processing
                    drop(listener_guard);

                    // Process the keyboard event
                    if event.is_special_key && (event.keycode == 0x33 || event.keycode == 0x75) {
                        // Backspace/delete should update the buffer to avoid desync.
                        self.handle_backspace();
                        if tab_debug_enabled() {
                            tab_debug_log("handled backspace/delete");
                        }
                        continue;
                    }
                    if let Some(ch) = event.character {
                        // Log every 10th event to avoid spam
                        if event_count % 10 == 0 {
                            println!("⌨️  Keyboard event #{}: char='{}'", event_count, ch);
                        }
                        if tab_debug_enabled() {
                            tab_debug_log(&format!(
                                "keyboard event received: #{} char='{}'",
                                event_count, ch
                            ));
                        }

                        // Add character to text buffer
                        {
                            let mut buffer = self.text_buffer.lock();
                            buffer.append(ch);

                            // Check if we should trigger prediction
                            if !buffer.should_trigger_prediction() {
                                if tab_debug_enabled() {
                                    tab_debug_log("prediction skipped: should_trigger_prediction=false");
                                }
                                continue;
                            }

                            buffer.reset_prediction_counter();
                        }

                        // Check debounce
                        let now = Instant::now();
                        let last_prediction = *self.last_prediction_time.lock();
                        if now.duration_since(last_prediction) < self.prediction_debounce {
                            if tab_debug_enabled() {
                                tab_debug_log("prediction skipped: debounce");
                            }
                            continue; // Too soon, skip
                        }

                        *self.last_prediction_time.lock() = now;

                        println!("🔮 Triggering completion from keyboard event #{}", event_count);
                        // Trigger proactive completion
                        self.trigger_completion();
                    }
                }
                Err(std::sync::mpsc::TryRecvError::Empty) => {
                    // Drop lock before sleeping
                    drop(listener_guard);

                    // Watchdog: if no events for 30s, assume tap is dead.
                    // Only after we've seen at least one real event.
                    if seen_any_event && last_event_time.elapsed() > Duration::from_secs(30) {
                        eprintln!("⚠️  No keyboard events for 30s — recreating listener");
                        tab_debug_log("watchdog: no keyboard events for 30s, recreating listener");
                        *self.keyboard_listener.lock() = None;
                        match MacOSKeyboardListener::new() {
                            Ok(new_listener) => {
                                eprintln!("✅ Keyboard listener recreated via watchdog");
                                tab_debug_log("watchdog: keyboard listener recreated");
                                *self.keyboard_listener.lock() = Some(new_listener);
                                last_event_time = Instant::now(); // Reset watchdog
                            }
                            Err(e) => {
                                eprintln!("❌ Watchdog recovery failed: {}", e);
                                tab_debug_log("watchdog: keyboard listener recovery failed");
                            }
                        }
                    }

                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                    eprintln!("⚠️  Keyboard event channel disconnected, attempting recovery...");
                    // Drop lock before recovery
                    drop(listener_guard);

                    // Clear the old listener
                    *self.keyboard_listener.lock() = None;

                    // Try to create a new keyboard listener
                    match MacOSKeyboardListener::new() {
                        Ok(new_listener) => {
                            eprintln!("✅ Keyboard listener recovered!");
                            *self.keyboard_listener.lock() = Some(new_listener);
                            last_event_time = Instant::now(); // Reset watchdog
                            // Small delay before retrying
                            std::thread::sleep(Duration::from_millis(100));
                            continue; // Try again with new listener
                        }
                        Err(e) => {
                            eprintln!("❌ Failed to recover keyboard listener: {}", e);
                            eprintln!("   Predictions will not work until app restart.");
                            return; // Give up
                        }
                    }
                }
            }
        }
    }
    
    /// Background thread to periodically detect the current app.
    /// Runs every 2 seconds on its own thread so that a slow or hanging
    /// MacOSAppDetector call never blocks the keyboard listener thread.
    fn start_app_detector(&self) {
        let current_app = self.current_app.clone();

        std::thread::spawn(move || {
            loop {
                #[cfg(target_os = "macos")]
                {
                    if let Some(app) = Self::detect_current_app() {
                        *current_app.lock() = app;
                    }
                }
                std::thread::sleep(Duration::from_secs(2));
            }
        });
    }

    /// Background thread to continuously update context in graph.db
    fn start_context_updater(&self) {
        let cache = self.cache.clone();
        let api_client = self.api_client.clone();
        let current_app = self.current_app.clone();
        let runtime = self.runtime.clone();
        
        std::thread::spawn(move || {
            loop {
                std::thread::sleep(Duration::from_secs(30)); // Update every 30 seconds
                
                let app = current_app.lock().clone();
                let activity_id = Self::generate_activity_id(&app);
                
                // Get current context from cache
                if let Some(context) = cache.get_context(&app, &activity_id) {
                    let context_json = serde_json::to_string(&context).unwrap_or_default();
                    
                    let request = ContextUpdateRequest {
                        app_name: app.clone(),
                        activity_id: activity_id.clone(),
                        context_data: context_json,
                        activity_type: format!("{:?}", context.activity_type),
                    };
                    
                    // Send to server asynchronously
                    let api_client_clone = api_client.clone();
                    runtime.spawn(async move {
                        match api_client_clone.update_context(request).await {
                            Ok(response) => {
                                println!("🔄 Context updated in graph.db: {}", response.message);
                            }
                            Err(e) => {
                                eprintln!("⚠️  Context update failed: {}", e);
                            }
                        }
                    });
                }
            }
        });
    }
    
    /// Handle keyboard events from rdev (non-macOS platforms)
    #[cfg(not(target_os = "macos"))]
    fn handle_event(&self, event: Event) {
        // Skip if tab completion is disabled
        if !self.is_tab_completion_enabled() {
            return;
        }

        match event.event_type {
            EventType::KeyPress(key) => {
                // Capture all typeable characters
                if let Some(ch) = self.key_to_char(&key) {
                    {
                        let mut buffer = self.text_buffer.lock();
                        buffer.append(ch);
                        
                        // Check if we should trigger prediction
                        if !buffer.should_trigger_prediction() {
                            return;
                        }
                        
                        buffer.reset_prediction_counter();
                    }
                    
                    // Check debounce
                    let now = Instant::now();
                    let last_prediction = *self.last_prediction_time.lock();
                    if now.duration_since(last_prediction) < self.prediction_debounce {
                        return; // Too soon, skip
                    }
                    
                    *self.last_prediction_time.lock() = now;
                    
                    // Trigger proactive completion
                    self.trigger_completion();
                }
            }
            _ => {}
        }
    }
    
    #[cfg(not(target_os = "macos"))]
    fn key_to_char(&self, key: &Key) -> Option<char> {
        // Basic key to char mapping
        match key {
            Key::KeyA => Some('a'),
            Key::KeyB => Some('b'),
            Key::KeyC => Some('c'),
            Key::KeyD => Some('d'),
            Key::KeyE => Some('e'),
            Key::KeyF => Some('f'),
            Key::KeyG => Some('g'),
            Key::KeyH => Some('h'),
            Key::KeyI => Some('i'),
            Key::KeyJ => Some('j'),
            Key::KeyK => Some('k'),
            Key::KeyL => Some('l'),
            Key::KeyM => Some('m'),
            Key::KeyN => Some('n'),
            Key::KeyO => Some('o'),
            Key::KeyP => Some('p'),
            Key::KeyQ => Some('q'),
            Key::KeyR => Some('r'),
            Key::KeyS => Some('s'),
            Key::KeyT => Some('t'),
            Key::KeyU => Some('u'),
            Key::KeyV => Some('v'),
            Key::KeyW => Some('w'),
            Key::KeyX => Some('x'),
            Key::KeyY => Some('y'),
            Key::KeyZ => Some('z'),
            Key::Num0 => Some('0'),
            Key::Num1 => Some('1'),
            Key::Num2 => Some('2'),
            Key::Num3 => Some('3'),
            Key::Num4 => Some('4'),
            Key::Num5 => Some('5'),
            Key::Num6 => Some('6'),
            Key::Num7 => Some('7'),
            Key::Num8 => Some('8'),
            Key::Num9 => Some('9'),
            Key::Space => Some(' '),
            Key::Minus => Some('-'),
            Key::Equal => Some('='),
            _ => None,
        }
    }
    
    fn trigger_completion(&self) {
        // Skip if tab completion is disabled
        if !self.is_tab_completion_enabled() {
            return;
        }

        let text = self.text_buffer.lock().get_last_n(100); // Get more context

        // Use cached app name — updated by the background app detector thread.
        // Do NOT call detect_current_app() here: it creates a MacOSAppDetector,
        // runs `mdls` as a subprocess, and calls CGWindowListCopyWindowInfo on
        // every invocation. That is far too heavy for a function called every
        // 3 keystrokes and can hang after window operations (accept/hide).
        let app = self.current_app.lock().clone();
        let cache = self.cache.clone();
        let api_client = self.api_client.clone();
        let runtime = self.runtime.clone();
        let prediction_counter = self.prediction_counter.clone();

        // Check if callback is set
        let has_callback = self.suggestion_callback.lock().is_some();
        let callback_ref = self.suggestion_callback.clone();

        // Clear any stale decline context when doing normal predictions
        // This ensures we don't carry over state from previous dismiss cycles
        *self.decline_context.lock() = None;

        if text.trim().is_empty() {
            println!("⏭️  trigger_completion: empty buffer, skipping");
            return; // Silent skip for empty buffer
        }

        let trig_preview: String = text.chars().take(20).collect();
        println!("🔮 trigger_completion: app={}, text='{}...' has_callback={}",
                 app, trig_preview, has_callback);

        // Spawn thread to avoid blocking key listener
        std::thread::spawn(move || {
            Self::get_and_show_prediction(
                cache,
                &app,
                &text,
                callback_ref,
                has_callback,
                api_client,
                runtime,
                prediction_counter,
            );
        });
    }

    /// Detect the currently active application using macOS APIs
    #[cfg(target_os = "macos")]
    fn detect_current_app() -> Option<String> {
        // Use MacOSAppDetector to get the frontmost app
        let mut detector = match MacOSAppDetector::new() {
            Ok(d) => d,
            Err(_) => return None,
        };
        match detector.get_active_app_info() {
            Ok(app_info) => Some(app_info.name),
            Err(e) => {
                // Silently fail - not critical for predictions
                if cfg!(debug_assertions) {
                    eprintln!("⚠️  Could not detect current app: {}", e);
                }
                None
            }
        }
    }
    
    fn get_and_show_prediction(
        cache: Arc<MultiTierCache>,
        app: &str,
        text: &str,
        callback_ref: Arc<Mutex<Option<Arc<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
        api_client: Arc<TabCompletionApiClient>,
        runtime: Arc<Runtime>,
        prediction_counter: Arc<Mutex<usize>>,
    ) {
        let start = Instant::now();
        let activity_id = Self::generate_activity_id(app);

        // L0: Try exact match from cache (instant)
        match cache.get_prediction_or_context(app, text, &activity_id) {
            CacheResult::ExactHit(prediction) => {
                let latency = start.elapsed().as_millis();
                if latency < 10 {
                    let confidence = 1.0; // Exact cache hit = 100% confidence
                    if confidence >= CONFIDENCE_THRESHOLD_L0 {
                        Self::emit_suggestion(&prediction, "L0-exact", latency, "cached", confidence, &callback_ref, has_callback);
                        return;
                    }
                }
            }
            CacheResult::ContextHit(context) => {
                // L1: Local LLM inference with cached context
                let latency = start.elapsed().as_millis();
                if let Some((pred, confidence)) = Self::infer_with_context(&context, text) {
                    if latency < 200 && confidence >= CONFIDENCE_THRESHOLD_L1 {
                        cache.cache_prediction(app, text, &pred);
                        let context_type = format!("{:?}", context.activity_type);
                        Self::emit_suggestion(&pred, "L1-llm", latency, &context_type, confidence, &callback_ref, has_callback);
                        return;
                    } else if confidence < CONFIDENCE_THRESHOLD_L1 {
                        println!("⚠️  L1 prediction confidence too low: {:.2} (threshold: {:.2})", confidence, CONFIDENCE_THRESHOLD_L1);
                    }
                }
            }
            CacheResult::GraphHit(context) => {
                // L2: Graph database context (from direct SQLite query)
                let latency = start.elapsed().as_millis();
                if let Some((pred, confidence)) = Self::infer_with_context(&context, text) {
                    if confidence >= CONFIDENCE_THRESHOLD_L2 {
                        cache.cache_prediction(app, text, &pred);
                        let context_type = format!("{:?}", context.activity_type);
                        Self::emit_suggestion(&pred, "L2-graph", latency, &context_type, confidence, &callback_ref, has_callback);

                        // Occasionally send to Flask for learning (every 10 predictions)
                        Self::maybe_send_to_flask_for_learning(
                            prediction_counter,
                            api_client,
                            runtime,
                            app.to_string(),
                            text.to_string(),
                            pred.clone(),
                            activity_id,
                        );
                        return;
                    } else {
                        println!("⚠️  L2 prediction confidence too low: {:.2} (threshold: {:.2})", confidence, CONFIDENCE_THRESHOLD_L2);
                    }
                }
            }
            CacheResult::NeedExtraction => {
                // L3: No context found, use fallback
                let context = Self::extract_full_context(app);
                if let Some((pred, confidence)) = Self::infer_with_context(&context, text) {
                    let latency = start.elapsed().as_millis();
                    if confidence >= CONFIDENCE_THRESHOLD_FALLBACK {
                        cache.cache_prediction(app, text, &pred);
                        Self::emit_suggestion(
                            &pred,
                            "L3-fallback",
                            latency,
                            "local_extraction",
                            confidence,
                            &callback_ref,
                            has_callback,
                        );
                        return;
                    }
                }
            }
        }

        // If we get here, all prediction methods failed or had low confidence
        println!("⚠️  No prediction generated (all methods failed or confidence too low)");
    }
    
    /// Occasionally send predictions to Flask for learning and graph updates
    /// Only sends every FLASK_UPDATE_INTERVAL predictions to avoid overwhelming the server
    fn maybe_send_to_flask_for_learning(
        prediction_counter: Arc<Mutex<usize>>,
        api_client: Arc<TabCompletionApiClient>,
        runtime: Arc<Runtime>,
        app: String,
        text: String,
        prediction: String,
        activity_id: String,
    ) {
        const FLASK_UPDATE_INTERVAL: usize = 10; // Send to Flask every 10 predictions

        let mut counter = prediction_counter.lock();
        *counter += 1;
        let should_update = *counter % FLASK_UPDATE_INTERVAL == 0;
        let current_count = *counter;
        drop(counter); // Release lock

        if should_update {
            println!("🔄 Sending prediction #{} to Flask for learning", current_count);

            runtime.spawn(async move {
                let request = PredictionRequest {
                    app_name: app.clone(),
                    text_buffer: text.clone(),
                    context_type: "learning_update".to_string(),
                    activity_id: activity_id.clone(),
                };

                match api_client.get_prediction(request).await {
                    Ok(_) => {
                        println!("✅ Flask learning update successful");
                    }
                    Err(e) => {
                        eprintln!("⚠️  Flask learning update failed: {}", e);
                    }
                }
            });
        }
    }

    /// Enhanced prediction with decline context and recommended actions
    /// Used for retry predictions after user declines initial suggestion
    fn get_and_show_prediction_with_decline(
        cache: Arc<MultiTierCache>,
        app: &str,
        text: &str,
        callback_ref: Arc<Mutex<Option<Arc<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
        api_client: Arc<TabCompletionApiClient>,
        runtime: Arc<Runtime>,
        prediction_counter: Arc<Mutex<usize>>,
        decline_context: Option<DeclineContext>,
        actions: Vec<ActionSummary>,
    ) {
        let start = Instant::now();
        let activity_id = Self::generate_activity_id(app);

        // Build enriched context
        let mut enriched = EnrichedPredictionContext::new(app.to_string())
            .with_actions(actions);

        if let Some(decline) = decline_context.clone() {
            enriched = enriched.with_decline(decline);
        }

        // Lower confidence threshold for retries (we're being more speculative)
        let retry_confidence_threshold = 0.35;

        // Skip L0 cache on retry (exact match already failed/was rejected)
        // Go straight to L1/L2/L3 with enriched prompt

        // Try to get context from cache
        match cache.get_prediction_or_context(app, text, &activity_id) {
            CacheResult::ExactHit(_) if decline_context.is_some() => {
                // Skip exact hits on retry - user already rejected this
                println!("⏭️  Skipping L0 cache hit on retry (was declined)");
            }
            CacheResult::ExactHit(prediction) => {
                let latency = start.elapsed().as_millis();
                Self::emit_suggestion(&prediction, "L0-exact", latency, "cached", 1.0, &callback_ref, has_callback);
                return;
            }
            CacheResult::ContextHit(context) | CacheResult::GraphHit(context) => {
                // Use enriched prompt for retry
                if let Some((pred, confidence)) = Self::infer_with_enriched_context(&context, text, &enriched) {
                    let latency = start.elapsed().as_millis();

                    // Check against declined prediction
                    let is_same_as_declined = decline_context
                        .as_ref()
                        .map(|d| d.declined_prediction.trim() == pred.trim())
                        .unwrap_or(false);

                    if is_same_as_declined {
                        println!("⏭️  Skipping prediction (same as declined): {}", &pred[..pred.len().min(30)]);
                        // Don't emit, try fallback
                    } else if confidence >= retry_confidence_threshold {
                        let cache_level = if enriched.is_retry() { "L1-retry" } else { "L1-llm" };
                        cache.cache_prediction(app, text, &pred);
                        let context_type = format!("{:?}", context.activity_type);
                        Self::emit_suggestion(&pred, cache_level, latency, &context_type, confidence, &callback_ref, has_callback);
                        return;
                    }
                }
            }
            CacheResult::NeedExtraction => {
                // L3: Full extraction with enriched context
                let context = Self::extract_full_context(app);
                if let Some((pred, confidence)) = Self::infer_with_enriched_context(&context, text, &enriched) {
                    let latency = start.elapsed().as_millis();

                    // Check against declined prediction
                    let is_same_as_declined = decline_context
                        .as_ref()
                        .map(|d| d.declined_prediction.trim() == pred.trim())
                        .unwrap_or(false);

                    if !is_same_as_declined && confidence >= retry_confidence_threshold {
                        cache.cache_prediction(app, text, &pred);
                        Self::emit_suggestion(
                            &pred,
                            "L3-retry",
                            latency,
                            "enriched_extraction",
                            confidence,
                            &callback_ref,
                            has_callback,
                        );
                        return;
                    }
                }
            }
        }

        println!("⚠️  No retry prediction generated (all methods failed or same as declined)");
    }

    /// Infer with enriched context (includes decline info and recommended actions)
    fn infer_with_enriched_context(
        context: &CachedContext,
        text: &str,
        enriched: &EnrichedPredictionContext,
    ) -> Option<(String, f32)> {
        let prompt = build_enriched_prompt(context, text, enriched);

        // Debug: Show enriched prompt
        if cfg!(debug_assertions) && std::env::var("DEBUG_PROMPTS").is_ok() {
            println!("🔍 Enriched Prompt: {}", &prompt[..prompt.len().min(400)]);
        }

        // Use slightly more tokens for enriched predictions (context is richer)
        match MODEL.predict_with_fallback(&prompt, 40) {
            Ok(prediction) => {
                let prediction = prediction.trim().to_string();

                // Skip empty or invalid predictions
                if prediction.is_empty() || prediction.len() > 200 {
                    return None;
                }

                // Calculate confidence with boost for matching user's typed chars
                let mut confidence = Self::calculate_prediction_confidence(&prediction, text, context);

                // Boost confidence if prediction matches chars typed after decline
                if let Some(ref decline) = enriched.decline_context {
                    if !decline.chars_after_prediction.is_empty() {
                        let chars_lower = decline.chars_after_prediction.to_lowercase();
                        let pred_lower = prediction.to_lowercase();

                        // If prediction starts with or contains the chars user typed, boost confidence
                        if pred_lower.starts_with(&chars_lower) {
                            confidence += 0.15;
                            println!("📈 Confidence boosted: prediction matches user's typed chars");
                        } else if pred_lower.contains(&chars_lower) {
                            confidence += 0.1;
                        }
                    }
                }

                Some((prediction, confidence.min(1.0)))
            }
            Err(e) => {
                eprintln!("❌ Enriched model inference failed: {}", e);
                None
            }
        }
    }

    /// Generate a session-based activity ID that remains stable for a few minutes
    /// This allows context caching while still being responsive to app/context switches
    fn generate_activity_id(app: &str) -> String {
        let now = SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        // Create 5-minute time buckets for stable activity sessions
        let time_bucket = now / 300; // 5 minutes = 300 seconds
        
        // Hash app name + time bucket to create unique activity ID
        let mut hasher = Sha256::new();
        hasher.update(app.as_bytes());
        hasher.update(time_bucket.to_string().as_bytes());
        let result = hasher.finalize();
        
        // Use first 16 chars of hash as activity ID
        format!("{:x}", result)[..16].to_string()
    }
    
    fn infer_with_context(context: &CachedContext, text: &str) -> Option<(String, f32)> {
        use super::prompt_builder::build_prompt;

        let prompt = build_prompt(context, text);

        // Debug: Show prompt (only in debug builds)
        if cfg!(debug_assertions) && std::env::var("DEBUG_PROMPTS").is_ok() {
            println!("🔍 Prompt: {}", &prompt[..prompt.len().min(200)]);
        }

        // Use 30 tokens for better completions, with automatic Haiku fallback
        match MODEL.predict_with_fallback(&prompt, 30) {
            Ok(prediction) => {
                let prediction = prediction.trim().to_string();

                // Skip empty or invalid predictions
                if prediction.is_empty() || prediction.len() > 200 {
                    if cfg!(debug_assertions) {
                        eprintln!("⚠️  Prediction rejected: empty or too long ({} chars)", prediction.len());
                    }
                    return None;
                }

                // Calculate confidence based on prediction quality heuristics
                let confidence = Self::calculate_prediction_confidence(&prediction, text, context);

                Some((prediction, confidence))
            }
            Err(e) => {
                eprintln!("❌ Model inference failed: {}", e);
                None
            }
        }
    }
    
    /// Calculate confidence score for a prediction based on heuristics
    /// Returns a value between 0.0 and 1.0
    fn calculate_prediction_confidence(prediction: &str, input_text: &str, context: &CachedContext) -> f32 {
        let mut confidence = 0.6; // Base confidence for LLM predictions
        
        // Length check: very short or very long predictions are less confident
        if prediction.len() < 3 {
            confidence -= 0.2;
        } else if prediction.len() > 200 {
            confidence -= 0.1;
        } else if prediction.len() >= 5 && prediction.len() <= 100 {
            confidence += 0.1; // Sweet spot
        }
        
        // Relevance check: prediction should relate to input
        if !prediction.is_empty() && !input_text.is_empty() {
            let input_lower = input_text.to_lowercase();
            let pred_lower = prediction.to_lowercase();
            
            // Check if prediction continues the input naturally
            if pred_lower.starts_with(&input_lower) {
                confidence += 0.1;
            }
            
            // Check for common words overlap (simple relevance check)
            let input_words: std::collections::HashSet<&str> = input_lower.split_whitespace().collect();
            let pred_words: std::collections::HashSet<&str> = pred_lower.split_whitespace().collect();
            let overlap = input_words.intersection(&pred_words).count();
            
            if overlap > 0 {
                confidence += 0.05 * (overlap.min(3) as f32);
            }
        }
        
        // Context quality: more recent context = higher confidence
        if context.learned_patterns.len() > 2 {
            confidence += 0.05;
        }
        if context.recent_actions.len() > 2 {
            confidence += 0.05;
        }
        
        // Clamp to [0.0, 1.0]
        confidence.max(0.0).min(1.0)
    }
    
    fn extract_full_context(app: &str) -> CachedContext {
        // Full context extraction would use:
        // - ChromiumBridge for browser apps
        // - Accessibility API for other apps
        // - OCR as fallback
        
        // For MVP, create basic context
        use super::cache::{ActivityType, AppContext};
        
        CachedContext {
            app_context: AppContext {
                name: app.to_string(),
                bundle_id: String::new(),
                window_title: None,
            },
            activity_type: ActivityType::from_app(app),
            learned_patterns: vec![],
            recent_actions: vec![],
            screen_context: None, // TODO: Add OCR/screen capture here
            timestamp: current_timestamp(),
            ttl: 180, // 3 minutes
            context_chain: None,
        }
    }
    
    fn emit_suggestion(
        prediction: &str,
        cache_level: &str,
        latency_ms: u128,
        context_type: &str,
        confidence: f32,
        callback_ref: &Arc<Mutex<Option<Arc<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
    ) {
        use std::fs::OpenOptions;
        use std::io::Write;
        use super::terminal_display::TerminalDisplay;

        let preview: String = prediction.chars().take(50).collect();

        // Compact logging for proactive system
        let log_message = if latency_ms < 10 {
            format!("⚡ {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        } else if latency_ms < 200 {
            format!("💨 {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        } else {
            format!("🔍 {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        };

        println!("{}", log_message);

        // Log to file for monitoring
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .append(true)
            .open("/tmp/predictions.log")
        {
            let timestamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
            let full_log = format!(
                "[{}] {} | Full: {}\n",
                timestamp,
                log_message,
                prediction
            );
            let _ = file.write_all(full_log.as_bytes());
        }

        // Emit to UI callback for popup display BEFORE ANSI inline text.
        // show_inline_suggestion uses \x1b[s / \x1b[u (cursor save/restore)
        // which corrupts the terminal cursor position for any println! that
        // runs after it on the same thread. By calling the callback first,
        // the popup dispatch happens with clean stdout state.
        if has_callback {
            let cb_clone = callback_ref.lock().as_ref().cloned();
            // Lock is released here ^^^

            if let Some(cb) = cb_clone {
                let suggestion = CompletionSuggestion {
                    text: prediction.to_string(),
                    cache_level: cache_level.to_string(),
                    latency_ms,
                    context_type: context_type.to_string(),
                    confidence,
                };
                cb(suggestion);
            }
        }

        // Show inline ghost text in terminal (ANSI escape sequences)
        // This runs AFTER the popup callback so cursor save/restore doesn't
        // interfere with the callback's println/dispatch operations.
        if let Err(e) = TerminalDisplay::show_inline_suggestion(prediction, cache_level, latency_ms) {
            // Silently fail if terminal doesn't support ANSI
            eprintln!("⚠️  Failed to show terminal ghost text: {}", e);
        }
    }
    
    pub fn set_current_app(&self, app_name: String) {
        *self.current_app.lock() = app_name;
    }

    /// Erase the last n characters from the buffer.
    /// Called before append_to_buffer to remove overlap/grace-period chars
    /// that were erased from the terminal by the injector, keeping the
    /// internal buffer in sync with what's actually on screen.
    pub fn erase_from_buffer(&self, n: usize) {
        if n > 0 {
            let mut buffer = self.text_buffer.lock();
            println!("📝 erase_from_buffer: removing {} chars from end", n);
            buffer.erase_last_n(n);
        }
    }

    fn handle_backspace(&self) {
        let mut buffer = self.text_buffer.lock();
        buffer.backspace();
    }

    /// Append text to the buffer (called after accepting a suggestion)
    /// This updates the internal state so predictions can continue from the new position
    pub fn append_to_buffer(&self, text: String) {
        let text_preview: String = text.chars().take(30).collect();
        println!("📝 append_to_buffer: adding '{}' ({} chars)",
                 text_preview, text.len());

        {
            let mut buffer = self.text_buffer.lock();
            for ch in text.chars() {
                buffer.append(ch);
            }
            // Don't reset prediction counter - we want the next keystroke to
            // potentially trigger a prediction immediately, not wait for 3 chars
        }

        // Clear decline context since we just accepted a prediction
        *self.decline_context.lock() = None;

        // Trigger a new prediction after a short delay
        let self_clone = self.cache.clone();
        let app = self.current_app.lock().clone();
        let text_buffer = self.text_buffer.clone();
        let callback_ref = self.suggestion_callback.clone();
        let has_callback = self.suggestion_callback.lock().is_some();
        let api_client = self.api_client.clone();
        let runtime = self.runtime.clone();
        let prediction_counter = self.prediction_counter.clone();

        println!("📝 append_to_buffer: spawning prediction thread (app={}, has_callback={})",
                 app, has_callback);

        std::thread::spawn(move || {
            // Small delay before re-triggering
            std::thread::sleep(Duration::from_millis(300));

            let text = text_buffer.lock().get_last_n(100);
            if text.trim().is_empty() {
                println!("⏭️  append_to_buffer thread: buffer is empty, skipping prediction");
                return;
            }

            let buf_preview: String = text.chars().take(30).collect();
            println!("🔮 append_to_buffer thread: generating prediction for '{}...'",
                     buf_preview);

            Self::get_and_show_prediction(
                self_clone,
                &app,
                &text,
                callback_ref,
                has_callback,
                api_client,
                runtime,
                prediction_counter,
            );
        });
    }

    /// Get the last N characters from the buffer for overlap detection
    pub fn get_buffer_suffix(&self, n: usize) -> String {
        self.text_buffer.lock().get_last_n(n)
    }

    pub fn get_stats(&self) {
        self.cache.print_stats();
    }
    
    /// Visualize cache state to terminal
    pub fn visualize_cache(&self) {
        self.cache.visualize();
    }
    
    /// Get cache state as JSON
    pub fn get_cache_state_json(&self) -> String {
        self.cache.get_state_json()
    }
}

fn tab_debug_enabled() -> bool {
    match std::env::var("TAB_DEBUG") {
        Ok(v) => {
            let v = v.to_lowercase();
            v == "1" || v == "true" || v == "yes"
        }
        Err(_) => false,
    }
}

fn tab_debug_log(msg: &str) {
    if !tab_debug_enabled() {
        return;
    }
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    println!("[TAB_DEBUG {}] {}", ts, msg);
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_text_buffer() {
        let mut buffer = TextBuffer::new();
        buffer.append('a');
        buffer.append('b');
        buffer.append('c');
        assert_eq!(buffer.get_last_n(3), "abc");
    }
    
    #[test]
    fn test_trigger_creation() {
        let cache = Arc::new(MultiTierCache::new("test.db".to_string()));
        let trigger = CompletionTrigger::new(cache);
        assert!(trigger.is_ok());
    }
}
