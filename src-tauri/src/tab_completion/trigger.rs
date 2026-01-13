use anyhow::Result;
use parking_lot::Mutex;
#[cfg(not(target_os = "macos"))]
use rdev::{listen, Event, EventType, Key};
#[cfg(target_os = "macos")]
use super::macos_keyboard::{MacOSKeyboardListener, KeyboardEvent};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};
use sha2::{Sha256, Digest};
use tokio::runtime::Runtime;

use super::cache::{CacheResult, MultiTierCache, CachedContext, AppContext, current_timestamp};
use super::model::MODEL;
use super::api_client::{TabCompletionApiClient, PredictionRequest, ContextUpdateRequest};

pub struct CompletionTrigger {
    text_buffer: Arc<Mutex<TextBuffer>>,
    cache: Arc<MultiTierCache>,
    current_app: Arc<Mutex<String>>,
    suggestion_callback: Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
    api_client: Arc<TabCompletionApiClient>,
    runtime: Arc<Runtime>,
    last_prediction_time: Arc<Mutex<Instant>>,
    prediction_debounce: Duration,
    prediction_counter: Arc<Mutex<usize>>, // Counter to throttle Flask learning updates
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
            #[cfg(target_os = "macos")]
            keyboard_listener: Arc::new(Mutex::new(None)),
        })
    }
    
    /// Set callback for when a suggestion is generated (for UI integration)
    pub fn set_suggestion_callback<F>(&self, callback: F)
    where
        F: Fn(CompletionSuggestion) + Send + Sync + 'static,
    {
        *self.suggestion_callback.lock() = Some(Box::new(callback));
    }
    
    pub fn start_listening(self: Arc<Self>) {
        println!("⌨️  Starting proactive tab completion listener...");
        
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
        loop {
            // Get the keyboard listener
            let listener_guard = self.keyboard_listener.lock();
            let listener = match listener_guard.as_ref() {
                Some(l) => l,
                None => {
                    eprintln!("⚠️  Keyboard listener not initialized");
                    return;
                }
            };
            
            // Try to receive keyboard events (non-blocking with small sleep)
            match listener.try_recv() {
                Ok(event) => {
                    // Process the keyboard event
                    if let Some(ch) = event.character {
                        // Add character to text buffer
                        {
                            let mut buffer = self.text_buffer.lock();
                            buffer.append(ch);
                            
                            // Check if we should trigger prediction
                            if !buffer.should_trigger_prediction() {
                                continue;
                            }
                            
                            buffer.reset_prediction_counter();
                        }
                        
                        // Check debounce
                        let now = Instant::now();
                        let last_prediction = *self.last_prediction_time.lock();
                        if now.duration_since(last_prediction) < self.prediction_debounce {
                            continue; // Too soon, skip
                        }
                        
                        *self.last_prediction_time.lock() = now;
                        
                        // Trigger proactive completion
                        self.trigger_completion();
                    }
                }
                Err(std::sync::mpsc::TryRecvError::Empty) => {
                    // No events available, sleep briefly
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                    eprintln!("⚠️  Keyboard event channel disconnected");
                    return;
                }
            }
        }
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
        let text = self.text_buffer.lock().get_last_n(100); // Get more context
        let app = self.current_app.lock().clone();
        let cache = self.cache.clone();
        let api_client = self.api_client.clone();
        let runtime = self.runtime.clone();
        let prediction_counter = self.prediction_counter.clone();

        // Check if callback is set
        let has_callback = self.suggestion_callback.lock().is_some();
        let callback_ref = self.suggestion_callback.clone();

        if text.trim().is_empty() {
            return; // Silent skip for empty buffer
        }

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
    
    fn get_and_show_prediction(
        cache: Arc<MultiTierCache>,
        app: &str,
        text: &str,
        callback_ref: Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
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

        // Use 15 tokens for faster completion (average 5-10 words)
        match MODEL.predict_sync(&prompt, 15) {
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
        }
    }
    
    fn emit_suggestion(
        prediction: &str,
        cache_level: &str,
        latency_ms: u128,
        context_type: &str,
        confidence: f32,
        callback_ref: &Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
    ) {
        use std::fs::OpenOptions;
        use std::io::Write;
        use super::terminal_display::TerminalDisplay;

        let preview = &prediction[..prediction.len().min(50)];

        // Compact logging for proactive system
        let log_message = if latency_ms < 10 {
            format!("⚡ {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        } else if latency_ms < 200 {
            format!("💨 {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        } else {
            format!("🔍 {} ({}ms, conf:{:.2}): {}", cache_level, latency_ms, confidence, preview)
        };

        println!("{}", log_message);

        // Show inline ghost text in terminal (ANSI escape sequences)
        // This will appear dimmed in the terminal if the user is typing
        if let Err(e) = TerminalDisplay::show_inline_suggestion(prediction, cache_level, latency_ms) {
            // Silently fail if terminal doesn't support ANSI
            eprintln!("⚠️  Failed to show terminal ghost text: {}", e);
        }

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

        // Emit to UI callback for ghost text display
        if has_callback {
            if let Some(ref cb) = *callback_ref.lock() {
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
    }
    
    pub fn set_current_app(&self, app_name: String) {
        *self.current_app.lock() = app_name;
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

