use anyhow::Result;
use parking_lot::Mutex;
use std::sync::Arc;
use std::time::Instant;

#[cfg(target_os = "macos")]
use core_graphics::event::{
    CGEvent, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, EventField, CGEventFlags,
};

/// Grace period in milliseconds - popup stays visible even if user keeps typing
const SUGGESTION_GRACE_PERIOD_MS: u64 = 300;

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

/// Hotkey handler for accepting/dismissing completions
pub struct HotkeyHandler {
    current_suggestion: Arc<Mutex<Option<String>>>,
    suggestion_shown_at: Arc<Mutex<Option<Instant>>>,
    chars_typed_since_suggestion: Arc<Mutex<usize>>,
    /// Buffer of chars typed since suggestion was shown
    chars_buffer_since_suggestion: Arc<Mutex<String>>,
    accept_callback: Arc<Mutex<Option<Box<dyn Fn(String, usize) + Send + Sync>>>>,
    dismiss_callback: Arc<Mutex<Option<Box<dyn Fn() + Send + Sync>>>>,
    /// Enhanced dismiss callback with full decline info
    dismiss_with_info_callback: Arc<Mutex<Option<Box<dyn Fn(DismissInfo) + Send + Sync>>>>,
}

impl HotkeyHandler {
    pub fn new() -> Self {
        Self {
            current_suggestion: Arc::new(Mutex::new(None)),
            suggestion_shown_at: Arc::new(Mutex::new(None)),
            chars_typed_since_suggestion: Arc::new(Mutex::new(0)),
            chars_buffer_since_suggestion: Arc::new(Mutex::new(String::new())),
            accept_callback: Arc::new(Mutex::new(None)),
            dismiss_callback: Arc::new(Mutex::new(None)),
            dismiss_with_info_callback: Arc::new(Mutex::new(None)),
        }
    }

    /// Set the current suggestion text and record when it was shown
    pub fn set_suggestion(&self, text: Option<String>) {
        if text.is_some() {
            // Record timestamp and reset char counter when new suggestion appears
            *self.suggestion_shown_at.lock() = Some(Instant::now());
            *self.chars_typed_since_suggestion.lock() = 0;
            *self.chars_buffer_since_suggestion.lock() = String::new();
        } else {
            // Clear timestamp when suggestion is cleared
            *self.suggestion_shown_at.lock() = None;
            *self.chars_typed_since_suggestion.lock() = 0;
            *self.chars_buffer_since_suggestion.lock() = String::new();
        }
        *self.current_suggestion.lock() = text;
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

    /// Build DismissInfo from current state
    fn build_dismiss_info(&self) -> Option<DismissInfo> {
        let suggestion = self.current_suggestion.lock().clone()?;
        let shown_at = (*self.suggestion_shown_at.lock())?;
        let chars_count = *self.chars_typed_since_suggestion.lock();
        let chars_typed_after = self.chars_buffer_since_suggestion.lock().clone();

        Some(DismissInfo {
            dismissed_text: suggestion,
            time_shown_ms: shown_at.elapsed().as_millis() as u64,
            chars_typed_after,
            chars_count,
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
        use core_foundation::runloop::{kCFRunLoopCommonModes, CFRunLoopRun, CFRunLoopGetCurrent, CFRunLoopAddSource};
        use core_foundation::base::TCFType;
        
        // Create event tap for Tab and Escape keys
        let event_tap = CGEventTap::new(
            CGEventTapLocation::HID,
            CGEventTapPlacement::HeadInsertEventTap,
            CGEventTapOptions::Default, // Use Default to intercept events
            vec![CGEventType::KeyDown].into(),
            move |_proxy, _event_type, event| {
                // Use autoreleasepool and return its result
                autoreleasepool(|| {
                    let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE) as u16;
                    let _flags = event.get_flags();
                    
                    // Check if we have an active suggestion
                    let has_suggestion = handler.current_suggestion.lock().is_some();

                    if has_suggestion {
                        // Check for Cmd+Tab (keycode 0x30 with Command flag)
                        let flags = event.get_flags();
                        let cmd_pressed = flags.contains(CGEventFlags::CGEventFlagCommand);

                        if keycode == 0x30 && cmd_pressed {
                            if let Some(suggestion) = handler.current_suggestion.lock().clone() {
                                let chars_to_erase = *handler.chars_typed_since_suggestion.lock();
                                println!("✅ Cmd+Tab pressed - accepting suggestion (erasing {} chars)", chars_to_erase);

                                // Call accept callback with suggestion and char count
                                if let Some(ref callback) = *handler.accept_callback.lock() {
                                    callback(suggestion, chars_to_erase);
                                }

                                // Clear suggestion state
                                *handler.current_suggestion.lock() = None;
                                *handler.suggestion_shown_at.lock() = None;
                                *handler.chars_typed_since_suggestion.lock() = 0;
                                *handler.chars_buffer_since_suggestion.lock() = String::new();

                                // Suppress the Cmd+Tab key event by returning None
                                return None;
                            }
                        }
                        // Check for Escape key (keycode 0x35)
                        else if keycode == 0x35 {
                            println!("❌ Escape pressed - dismissing suggestion");

                            // Build dismiss info before clearing state
                            let dismiss_info = handler.build_dismiss_info();

                            // Call enhanced dismiss callback with info (for retry predictions)
                            if let Some(info) = dismiss_info {
                                if let Some(ref callback) = *handler.dismiss_with_info_callback.lock() {
                                    callback(info);
                                }
                            }

                            // Call legacy dismiss callback
                            if let Some(ref callback) = *handler.dismiss_callback.lock() {
                                callback();
                            }

                            // Clear suggestion state
                            *handler.current_suggestion.lock() = None;
                            *handler.suggestion_shown_at.lock() = None;
                            *handler.chars_typed_since_suggestion.lock() = 0;
                            *handler.chars_buffer_since_suggestion.lock() = String::new();

                            // Let Escape pass through
                        }
                        // Any other key: check grace period before dismissing
                        else {
                            // Ignore modifier keys (Shift, Cmd, Ctrl, Option)
                            let is_modifier = matches!(keycode,
                                0x37 | 0x38 | 0x3A | 0x3B | 0x3C | 0x3D | 0x3E | 0x3F // Cmd, Shift, Option, Ctrl
                            );

                            if !is_modifier {
                                // Increment char counter
                                *handler.chars_typed_since_suggestion.lock() += 1;
                                let chars_typed = *handler.chars_typed_since_suggestion.lock();

                                // Try to capture the actual character typed
                                // Map common keycodes to characters for tracking
                                if let Some(ch) = keycode_to_char(keycode) {
                                    handler.chars_buffer_since_suggestion.lock().push(ch);
                                }

                                // Check if we're still within the grace period
                                let within_grace_period = if let Some(shown_at) = *handler.suggestion_shown_at.lock() {
                                    shown_at.elapsed().as_millis() < SUGGESTION_GRACE_PERIOD_MS as u128
                                } else {
                                    false
                                };

                                if within_grace_period {
                                    println!("⏳ Key pressed during grace period ({} chars typed)", chars_typed);
                                    // Don't dismiss - let the key pass through
                                } else {
                                    println!("⏭️  Grace period expired - auto-dismissing suggestion");

                                    // Build dismiss info before clearing state
                                    let dismiss_info = handler.build_dismiss_info();

                                    // Call enhanced dismiss callback with info (for retry predictions)
                                    if let Some(info) = dismiss_info {
                                        if let Some(ref callback) = *handler.dismiss_with_info_callback.lock() {
                                            callback(info);
                                        }
                                    }

                                    // Call legacy dismiss callback
                                    if let Some(ref callback) = *handler.dismiss_callback.lock() {
                                        callback();
                                    }

                                    // Clear suggestion state
                                    *handler.current_suggestion.lock() = None;
                                    *handler.suggestion_shown_at.lock() = None;
                                    *handler.chars_typed_since_suggestion.lock() = 0;
                                    *handler.chars_buffer_since_suggestion.lock() = String::new();
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
        
        println!("✅ Hotkey listener started (⌘+Tab to accept, Esc to dismiss)");
        
        // Run the event loop
        unsafe {
            let run_loop = CFRunLoopGetCurrent();
            let source = match event_tap.mach_port.create_runloop_source(0) {
                Ok(s) => s,
                Err(_) => {
                    return Err(anyhow::anyhow!("Failed to create run loop source for hotkey event tap"));
                }
            };
            CFRunLoopAddSource(run_loop, source.as_concrete_TypeRef(), kCFRunLoopCommonModes);
            CFRunLoopRun();
        }

        Ok(())
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



