use anyhow::Result;
use parking_lot::Mutex;
use std::sync::Arc;
use std::time::Instant;
use std::time::{SystemTime, UNIX_EPOCH};

#[cfg(target_os = "macos")]
use core_graphics::event::{
    CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, EventField, CGEventFlags,
};

/// Grace period in milliseconds - popup stays visible even if user keeps typing
const SUGGESTION_GRACE_PERIOD_MS: u64 = 1000;

/// Information about a dismissed suggestion for enhanced retry
#[derive(Debug, Clone)]
pub struct DismissInfo {
    /// The prediction that was dismissed
    pub dismissed_text: String,
    /// How long the suggestion was shown before dismiss (ms)
    pub time_shown_ms: u64,
    /// Characters typed after the suggestion was shown
    pub chars_typed_after: String,
    /// Number of chars typed (for quick reference)
    pub chars_count: usize,
}

/// Consolidated suggestion state - protected by a SINGLE lock to avoid contention.
/// Previously these were 4 separate mutexes, causing severe lock contention between
/// the CGEventTap thread (processing keystrokes) and the main thread (updating state).
/// With a single lock, each thread acquires/releases once instead of 4 times per operation.
#[derive(Default)]
struct SuggestionState {
    current_suggestion: Option<String>,
    shown_at: Option<Instant>,
    chars_typed: usize,
    chars_buffer: String,
}

impl SuggestionState {
    fn clear(&mut self) {
        self.current_suggestion = None;
        self.shown_at = None;
        self.chars_typed = 0;
        self.chars_buffer.clear();
    }

    fn set(&mut self, text: Option<String>) {
        if text.is_some() {
            self.shown_at = Some(Instant::now());
            self.chars_typed = 0;
            self.chars_buffer.clear();
        } else {
            self.shown_at = None;
            self.chars_typed = 0;
            self.chars_buffer.clear();
        }
        self.current_suggestion = text;
    }
}

/// Hotkey handler for accepting/dismissing completions
pub struct HotkeyHandler {
    /// Consolidated suggestion state - single lock for all suggestion-related fields.
    /// This dramatically reduces lock contention compared to 4 separate locks.
    state: Arc<Mutex<SuggestionState>>,
    accept_callback: Arc<Mutex<Option<Box<dyn Fn(String, usize) + Send + Sync>>>>,
    dismiss_callback: Arc<Mutex<Option<Box<dyn Fn() + Send + Sync>>>>,
    /// Enhanced dismiss callback with full decline info
    dismiss_with_info_callback: Arc<Mutex<Option<Box<dyn Fn(DismissInfo) + Send + Sync>>>>,
}

impl HotkeyHandler {
    pub fn new() -> Self {
        Self {
            state: Arc::new(Mutex::new(SuggestionState::default())),
            accept_callback: Arc::new(Mutex::new(None)),
            dismiss_callback: Arc::new(Mutex::new(None)),
            dismiss_with_info_callback: Arc::new(Mutex::new(None)),
        }
    }

    /// Set the current suggestion text and record when it was shown.
    /// Uses a SINGLE lock acquisition instead of 4 separate locks to minimize
    /// contention with the CGEventTap thread that processes keystrokes.
    pub fn set_suggestion(&self, text: Option<String>) {
        if tab_debug_enabled() {
            if text.is_some() {
                let snippet = text.as_ref().map(|t| t.chars().take(30).collect::<String>()).unwrap_or_default();
                tab_debug_log(&format!("set_suggestion: Some('{}...')", snippet));
            } else {
                tab_debug_log("set_suggestion: None");
            }
        }
        // Single lock acquisition for all state updates
        self.state.lock().set(text);
    }

    /// Set callback for when suggestion is accepted (includes chars to erase)
    pub fn set_accept_callback<F>(&self, callback: F)
    where
        F: Fn(String, usize) + Send + Sync + 'static,
    {
        *self.accept_callback.lock() = Some(Box::new(callback));
    }
    
    /// Set callback for when suggestion is dismissed
    pub fn set_dismiss_callback<F>(&self, callback: F)
    where
        F: Fn() + Send + Sync + 'static,
    {
        *self.dismiss_callback.lock() = Some(Box::new(callback));
    }

    /// Set callback for when suggestion is dismissed with full context info
    /// This is the enhanced callback that provides decline info for retry predictions
    pub fn set_dismiss_with_info_callback<F>(&self, callback: F)
    where
        F: Fn(DismissInfo) + Send + Sync + 'static,
    {
        *self.dismiss_with_info_callback.lock() = Some(Box::new(callback));
    }

    /// Build DismissInfo from current state (single lock acquisition)
    #[allow(dead_code)]
    fn build_dismiss_info(&self) -> Option<DismissInfo> {
        let state = self.state.lock();
        let suggestion = state.current_suggestion.clone()?;
        let shown_at = state.shown_at?;
        Some(DismissInfo {
            dismissed_text: suggestion,
            time_shown_ms: shown_at.elapsed().as_millis() as u64,
            chars_typed_after: state.chars_buffer.clone(),
            chars_count: state.chars_typed,
        })
    }
    
    /// Start listening for hotkeys (Tab to accept, Esc to dismiss)
    #[cfg(target_os = "macos")]
    pub fn start_listening(self: Arc<Self>) -> Result<()> {
        let self_clone = self.clone();
        
        std::thread::spawn(move || {
            if let Err(e) = Self::run_hotkey_listener(self_clone) {
                eprintln!("⚠️  Hotkey listener error: {}", e);
            }
        });
        
        Ok(())
    }
    
    #[cfg(not(target_os = "macos"))]
    pub fn start_listening(self: Arc<Self>) -> Result<()> {
        eprintln!("⚠️  Hotkey listening only supported on macOS");
        Ok(())
    }
    
    #[cfg(target_os = "macos")]
    fn run_hotkey_listener(handler: Arc<Self>) -> Result<()> {
        use objc::rc::autoreleasepool;
        use core_foundation::runloop::{kCFRunLoopCommonModes, CFRunLoopGetCurrent, CFRunLoopAddSource};
        use core_foundation::base::TCFType;
        
        // Create event tap for Tab and Escape keys
        let event_tap = CGEventTap::new(
            CGEventTapLocation::HID,
            CGEventTapPlacement::HeadInsertEventTap,
            CGEventTapOptions::Default, // Use Default to intercept events
            // NOTE: TapDisabled* are sentinel values and must NOT be included
            // in the mask, or core-graphics will panic on overflow.
            vec![CGEventType::KeyDown].into(),
            move |_proxy, event_type, event| {
                if matches!(
                    event_type,
                    CGEventType::TapDisabledByTimeout | CGEventType::TapDisabledByUserInput
                ) {
                    tab_debug_log("hotkey tap disabled (timeout/user input)");
                    return Some(event.clone());
                }
                // Use autoreleasepool and return its result
                autoreleasepool(|| {
                    let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE) as u16;
                    let flags = event.get_flags();
                    
                    // Check for Option+Tab (keycode 0x30 with Option/Alt flag)
                    // We use Option+Tab instead of Cmd+Tab because Cmd+Tab is a
                    // macOS protected system shortcut. Intercepting it causes macOS
                    // to flag the entire process and auto-disable ALL event taps
                    // (both hotkey and keyboard listener), permanently breaking
                    // tab completion until app restart.
                    let option_pressed = flags.contains(CGEventFlags::CGEventFlagAlternate);
                    let is_opt_tab = keycode == 0x30 && option_pressed;

                    if is_opt_tab {
                        // Single lock acquisition for accept: extract data, clear state, release lock
                        let accept_data = {
                            let mut state = handler.state.lock();
                            if let Some(suggestion) = state.current_suggestion.take() {
                                let chars_to_erase = state.chars_typed;
                                state.clear();
                                Some((suggestion, chars_to_erase))
                            } else {
                                None
                            }
                        };

                        if let Some((suggestion, chars_to_erase)) = accept_data {
                            println!("✅ Option+Tab pressed - accepting suggestion (erasing {} chars)", chars_to_erase);

                            // Call accept callback with panic protection
                            // Wrap in catch_unwind to prevent callback panics from killing CGEventTap thread
                            let callback_result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                if let Some(ref callback) = *handler.accept_callback.lock() {
                                    callback(suggestion.clone(), chars_to_erase);
                                }
                            }));
                            if let Err(e) = callback_result {
                                eprintln!("🔴 PANIC in accept callback: {:?}", e);
                            }

                            println!("✅ Accept callback completed, returning event");

                            // Pass through the original event instead of creating synthetic event.
                            // Creating synthetic events was causing crashes on some macOS versions.
                            // The Option key modifier will be stripped by the system anyway since
                            // we're returning from an event tap.
                            return Some(event.clone());
                        } else if tab_debug_enabled() {
                            tab_debug_log("Option+Tab pressed with no active suggestion");
                        }
                    }

                    // Single lock acquisition to check state and handle keypress
                    let (has_suggestion, is_escape, _chars_typed, within_grace_period) = {
                        let state = handler.state.lock();
                        let has = state.current_suggestion.is_some();
                        let grace = state.shown_at
                            .map(|t| t.elapsed().as_millis() < SUGGESTION_GRACE_PERIOD_MS as u128)
                            .unwrap_or(false);
                        (has, keycode == 0x35, state.chars_typed, grace)
                    };

                    if has_suggestion {
                        if tab_debug_enabled() {
                            tab_debug_log(&format!(
                                "hotkey keydown: keycode=0x{:X} flags=0x{:X} has_suggestion=true",
                                keycode,
                                flags.bits()
                            ));
                        }

                        if is_escape {
                            println!("❌ Escape pressed - dismissing suggestion");

                            // Build dismiss info and clear state in single lock acquisition
                            let dismiss_info = {
                                let mut state = handler.state.lock();
                                let info = if let (Some(suggestion), Some(shown_at)) = 
                                    (state.current_suggestion.clone(), state.shown_at) {
                                    Some(DismissInfo {
                                        dismissed_text: suggestion,
                                        time_shown_ms: shown_at.elapsed().as_millis() as u64,
                                        chars_typed_after: state.chars_buffer.clone(),
                                        chars_count: state.chars_typed,
                                    })
                                } else {
                                    None
                                };
                                state.clear();
                                info
                            };

                            // Call callbacks with panic protection (state lock released)
                            if let Some(info) = dismiss_info {
                                let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                    if let Some(ref callback) = *handler.dismiss_with_info_callback.lock() {
                                        callback(info);
                                    }
                                }));
                            }
                            let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                if let Some(ref callback) = *handler.dismiss_callback.lock() {
                                    callback();
                                }
                            }));
                        } else {
                            // Any other key: update char counter and check grace period
                            let is_modifier = matches!(keycode,
                                0x37 | 0x38 | 0x3A | 0x3B | 0x3C | 0x3D | 0x3E | 0x3F // Cmd, Shift, Option, Ctrl
                            );

                            if !is_modifier {
                                // Single lock acquisition for keystroke tracking
                                let updated_chars = {
                                    let mut state = handler.state.lock();
                                    state.chars_typed += 1;
                                    if let Some(ch) = keycode_to_char(keycode) {
                                        state.chars_buffer.push(ch);
                                    }
                                    state.chars_typed
                                };

                                if within_grace_period {
                                    println!("⏳ Key pressed during grace period ({} chars typed)", updated_chars);
                                } else if tab_debug_enabled() {
                                    tab_debug_log("grace expired: keeping suggestion active");
                                }
                            }
                        }
                    }
                    
                    // Pass through all events (clone the event to return it)
                    Some(event.clone())
                })
            },
        ).map_err(|e| anyhow::anyhow!("Failed to create hotkey event tap: {:?}", e))?;
        
        // Enable the event tap
        event_tap.enable();

        println!("✅ Hotkey listener started (⌥+Tab to accept, Esc to dismiss)");

        // Run the event loop with periodic tap re-enable.
        // macOS automatically disables active filter event taps that suppress system
        // shortcuts (like Cmd+Tab) or take too long to process events. Once disabled,
        // the tap silently stops receiving events — accept/dismiss stop working.
        // By periodically re-enabling, we recover automatically without app restart.
        unsafe {
            use core_foundation::runloop::kCFRunLoopDefaultMode;

            extern "C" {
                fn CFRunLoopRunInMode(
                    mode: core_foundation::string::CFStringRef,
                    seconds: f64,
                    returnAfterSourceHandled: u8,
                ) -> i32;
            }

            let run_loop = CFRunLoopGetCurrent();
            let source = match event_tap.mach_port.create_runloop_source(0) {
                Ok(s) => s,
                Err(_) => {
                    return Err(anyhow::anyhow!("Failed to create run loop source for hotkey event tap"));
                }
            };
            CFRunLoopAddSource(run_loop, source.as_concrete_TypeRef(), kCFRunLoopCommonModes);

            loop {
                // Process events for 2 seconds, then check tap status
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, 2.0, 0);
                // Re-enable the event tap in case macOS disabled it.
                // CGEventTapEnable is idempotent — no-op if already enabled.
                event_tap.enable();
            }
        }
    }
}

/// Map macOS keycodes to characters for tracking what user typed
/// This is a best-effort mapping - may not capture all characters
#[cfg(target_os = "macos")]
fn keycode_to_char(keycode: u16) -> Option<char> {
    // Based on macOS keycode layout
    match keycode {
        0x00 => Some('a'),
        0x01 => Some('s'),
        0x02 => Some('d'),
        0x03 => Some('f'),
        0x04 => Some('h'),
        0x05 => Some('g'),
        0x06 => Some('z'),
        0x07 => Some('x'),
        0x08 => Some('c'),
        0x09 => Some('v'),
        0x0B => Some('b'),
        0x0C => Some('q'),
        0x0D => Some('w'),
        0x0E => Some('e'),
        0x0F => Some('r'),
        0x10 => Some('y'),
        0x11 => Some('t'),
        0x12 => Some('1'),
        0x13 => Some('2'),
        0x14 => Some('3'),
        0x15 => Some('4'),
        0x16 => Some('6'),
        0x17 => Some('5'),
        0x19 => Some('9'),
        0x1A => Some('7'),
        0x1C => Some('8'),
        0x1D => Some('0'),
        0x1F => Some('o'),
        0x20 => Some('u'),
        0x22 => Some('i'),
        0x23 => Some('p'),
        0x25 => Some('l'),
        0x26 => Some('j'),
        0x28 => Some('k'),
        0x2D => Some('n'),
        0x2E => Some('m'),
        0x31 => Some(' '), // Space
        0x2B => Some(','),
        0x2F => Some('.'),
        0x2C => Some('/'),
        0x27 => Some(';'),
        0x29 => Some(';'),
        0x1B => Some('-'),
        0x18 => Some('='),
        _ => None,
    }
}

impl Default for HotkeyHandler {
    fn default() -> Self {
        Self::new()
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
