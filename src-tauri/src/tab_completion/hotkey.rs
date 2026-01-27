use anyhow::Result;
use parking_lot::Mutex;
use std::sync::Arc;

#[cfg(target_os = "macos")]
use core_graphics::event::{
    CGEvent, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, EventField, CGEventFlags,
};

/// Hotkey handler for accepting/dismissing completions
pub struct HotkeyHandler {
    current_suggestion: Arc<Mutex<Option<String>>>,
    accept_callback: Arc<Mutex<Option<Box<dyn Fn(String) + Send + Sync>>>>,
    dismiss_callback: Arc<Mutex<Option<Box<dyn Fn() + Send + Sync>>>>,
}

impl HotkeyHandler {
    pub fn new() -> Self {
        Self {
            current_suggestion: Arc::new(Mutex::new(None)),
            accept_callback: Arc::new(Mutex::new(None)),
            dismiss_callback: Arc::new(Mutex::new(None)),
        }
    }
    
    /// Set the current suggestion text
    pub fn set_suggestion(&self, text: Option<String>) {
        *self.current_suggestion.lock() = text;
    }
    
    /// Set callback for when suggestion is accepted
    pub fn set_accept_callback<F>(&self, callback: F)
    where
        F: Fn(String) + Send + Sync + 'static,
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
                        // Check for Tab key (keycode 0x30)
                        if keycode == 0x30 {
                            if let Some(suggestion) = handler.current_suggestion.lock().clone() {
                                println!("✅ Tab pressed - accepting suggestion");
                                
                                // Call accept callback
                                if let Some(ref callback) = *handler.accept_callback.lock() {
                                    callback(suggestion);
                                }
                                
                                // Clear suggestion
                                *handler.current_suggestion.lock() = None;
                                
                                // Suppress the Tab key event by returning None
                                return None;
                            }
                        }
                        // Check for Escape key (keycode 0x35)
                        else if keycode == 0x35 {
                            println!("❌ Escape pressed - dismissing suggestion");
                            
                            // Call dismiss callback
                            if let Some(ref callback) = *handler.dismiss_callback.lock() {
                                callback();
                            }
                            
                            // Clear suggestion
                            *handler.current_suggestion.lock() = None;
                            
                            // Let Escape pass through
                        }
                        // Any other key: auto-dismiss the suggestion
                        else {
                            // Ignore modifier keys (Shift, Cmd, Ctrl, Option)
                            let is_modifier = matches!(keycode, 
                                0x37 | 0x38 | 0x3A | 0x3B | 0x3C | 0x3D | 0x3E | 0x3F // Cmd, Shift, Option, Ctrl
                            );
                            
                            if !is_modifier {
                                println!("⏭️  Other key pressed - auto-dismissing suggestion");
                                
                                // Call dismiss callback
                                if let Some(ref callback) = *handler.dismiss_callback.lock() {
                                    callback();
                                }
                                
                                // Clear suggestion
                                *handler.current_suggestion.lock() = None;
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
        
        println!("✅ Hotkey listener started (Tab to accept, Esc to dismiss)");
        
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

impl Default for HotkeyHandler {
    fn default() -> Self {
        Self::new()
    }
}



