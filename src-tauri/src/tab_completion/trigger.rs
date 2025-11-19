use anyhow::Result;
use parking_lot::Mutex;
use rdev::{listen, Event, EventType, Key};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};
use sha2::{Sha256, Digest};

use super::cache::{CacheResult, MultiTierCache, CachedContext, AppContext, current_timestamp};
use super::model::MODEL;

pub struct CompletionTrigger {
    text_buffer: Arc<Mutex<TextBuffer>>,
    cache: Arc<MultiTierCache>,
    current_app: Arc<Mutex<String>>,
    cmd_pressed: Arc<Mutex<bool>>,
    suggestion_callback: Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CompletionSuggestion {
    pub text: String,
    pub cache_level: String,
    pub latency_ms: u128,
    pub context_type: String,
}

#[derive(Default)]
struct TextBuffer {
    buffer: String,
    max_size: usize,
    last_update: Option<Instant>,
}

impl TextBuffer {
    fn new() -> Self {
        Self {
            buffer: String::new(),
            max_size: 200, // Keep last 200 chars
            last_update: None,
        }
    }
    
    fn append(&mut self, ch: char) {
        self.buffer.push(ch);
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
    
    fn clear(&mut self) {
        self.buffer.clear();
        self.last_update = None;
    }
}

impl CompletionTrigger {
    pub fn new(cache: Arc<MultiTierCache>) -> Result<Self> {
        Ok(Self {
            text_buffer: Arc::new(Mutex::new(TextBuffer::new())),
            cache,
            current_app: Arc::new(Mutex::new(String::from("Unknown"))),
            cmd_pressed: Arc::new(Mutex::new(false)),
            suggestion_callback: Arc::new(Mutex::new(None)),
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
        println!("⌨️  Starting Cmd+Tab listener...");
        
        let self_clone = self.clone();
        std::thread::spawn(move || {
            if let Err(e) = listen(move |event| {
                self_clone.handle_event(event);
            }) {
                eprintln!("Error in keyboard listener: {:?}", e);
            }
        });
        
        println!("✅ Cmd+Tab listener started");
    }
    
    fn handle_event(&self, event: Event) {
        match event.event_type {
            EventType::KeyPress(key) => {
                match key {
                    Key::MetaLeft | Key::MetaRight => {
                        *self.cmd_pressed.lock() = true;
                    }
                    Key::Tab => {
                        if *self.cmd_pressed.lock() {
                            println!("⚡ Cmd+Tab detected!");
                            self.trigger_completion();
                        }
                    }
                    _ => {
                        if let Some(ch) = self.key_to_char(&key) {
                            self.text_buffer.lock().append(ch);
                        }
                    }
                }
            }
            EventType::KeyRelease(key) => {
                match key {
                    Key::MetaLeft | Key::MetaRight => {
                        *self.cmd_pressed.lock() = false;
                    }
                    _ => {}
                }
            }
            _ => {}
        }
    }
    
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
        let text = self.text_buffer.lock().get_last_n(50);
        let app = self.current_app.lock().clone();
        let cache = self.cache.clone();
        
        // Check if callback is set
        let has_callback = self.suggestion_callback.lock().is_some();
        let callback_ref = self.suggestion_callback.clone();
        
        if text.trim().is_empty() {
            println!("⚠️  No text in buffer, skipping completion");
            return;
        }
        
        println!("🎯 Triggering completion for: '{}'", text);
        
        // Spawn thread to avoid blocking key listener
        std::thread::spawn(move || {
            Self::get_and_show_prediction(cache, &app, &text, callback_ref, has_callback);
        });
    }
    
    fn get_and_show_prediction(
        cache: Arc<MultiTierCache>,
        app: &str,
        text: &str,
        callback_ref: Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
    ) {
        let start = Instant::now();
        
        // Generate activity_id based on app name and timestamp
        // This creates a session-based ID that's stable for a few minutes
        let activity_id = Self::generate_activity_id(app);
        
        // Try cache tiers
        match cache.get_prediction_or_context(app, text, &activity_id) {
            CacheResult::ExactHit(prediction) => {
                let latency = start.elapsed().as_millis();
                println!("⚡ L0 cache hit: {}ms", latency);
                Self::emit_suggestion(&prediction, "L0", latency, "exact_match", &callback_ref, has_callback);
            }
            CacheResult::ContextHit(context) => {
                let latency = start.elapsed().as_millis();
                println!("💾 L1 cache hit: {}ms", latency);
                let prediction = Self::infer_with_context(&context, text);
                if let Some(pred) = prediction {
                    cache.cache_prediction(app, text, &pred);
                    let context_type = format!("{:?}", context.activity_type);
                    Self::emit_suggestion(&pred, "L1", latency, &context_type, &callback_ref, has_callback);
                }
            }
            CacheResult::GraphHit(context) => {
                let latency = start.elapsed().as_millis();
                println!("🔍 L2 graph hit: {}ms", latency);
                let prediction = Self::infer_with_context(&context, text);
                if let Some(pred) = prediction {
                    cache.cache_prediction(app, text, &pred);
                    let context_type = format!("{:?}", context.activity_type);
                    Self::emit_suggestion(&pred, "L2", latency, &context_type, &callback_ref, has_callback);
                }
            }
            CacheResult::NeedExtraction => {
                println!("🆕 L3 full extraction");
                let context = Self::extract_full_context(app);
                let prediction = Self::infer_with_context(&context, text);
                if let Some(pred) = prediction {
                    cache.cache_context(app, &activity_id, context.clone());
                    cache.cache_prediction(app, text, &pred);
                    let latency = start.elapsed().as_millis();
                    let context_type = format!("{:?}", context.activity_type);
                    Self::emit_suggestion(&pred, "L3", latency, &context_type, &callback_ref, has_callback);
                }
            }
        }
        
        println!("✅ Total time: {}ms", start.elapsed().as_millis());
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
    
    fn infer_with_context(context: &CachedContext, text: &str) -> Option<String> {
        use super::prompt_builder::build_prompt;
        
        let prompt = build_prompt(context, text);
        match MODEL.predict_sync(&prompt, 50) {
            Ok(prediction) => Some(prediction.trim().to_string()),
            Err(e) => {
                eprintln!("❌ Model inference failed: {}", e);
                None
            }
        }
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
            timestamp: current_timestamp(),
            ttl: 180, // 3 minutes
        }
    }
    
    fn emit_suggestion(
        prediction: &str,
        cache_level: &str,
        latency_ms: u128,
        context_type: &str,
        callback_ref: &Arc<Mutex<Option<Box<dyn Fn(CompletionSuggestion) + Send + Sync>>>>,
        has_callback: bool,
    ) {
        // Print to console
        println!("\n┌─────────────────────────────────────┐");
        println!("│ 💡 Suggestion ({}):", cache_level);
        println!("│ {}", prediction);
        println!("│ Press Cmd+Return to accept");
        println!("└─────────────────────────────────────┘\n");
        
        // Emit to UI callback if set
        if has_callback {
            if let Some(ref cb) = *callback_ref.lock() {
                let suggestion = CompletionSuggestion {
                    text: prediction.to_string(),
                    cache_level: cache_level.to_string(),
                    latency_ms,
                    context_type: context_type.to_string(),
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

