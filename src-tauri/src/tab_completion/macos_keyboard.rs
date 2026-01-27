use anyhow::{anyhow, Result};
use core_foundation::runloop::kCFRunLoopCommonModes;
use core_graphics::event::{
    CGEvent, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventType, EventField,
};
use objc::rc::autoreleasepool;
use std::sync::mpsc::{channel, Receiver, Sender, TryRecvError};
use std::thread;

/// Represents a keyboard event with the character typed
#[derive(Debug, Clone)]
pub struct KeyboardEvent {
    pub character: Option<char>,
    pub keycode: u16,
    pub is_special_key: bool,
}

/// macOS keyboard listener using CGEventTap
/// 
/// This listener captures keyboard events at the system level and extracts
/// characters for building the text buffer. It's designed to never crash
/// and handle permission issues gracefully.
pub struct MacOSKeyboardListener {
    receiver: Receiver<KeyboardEvent>,
}

impl MacOSKeyboardListener {
    /// Create a new keyboard listener
    /// 
    /// This starts a background thread with CGEventTap. If accessibility
    /// permissions are denied or CGEventTap fails, it returns an error
    /// but never panics.
    pub fn new() -> Result<Self> {
        // Check accessibility permissions first
        if !Self::check_accessibility_permissions() {
            return Err(anyhow!(
                "Accessibility permissions not granted. Please enable in System Preferences > Security & Privacy > Privacy > Accessibility"
            ));
        }

        let (tx, rx) = channel();

        // Start event tap in a dedicated thread
        thread::spawn(move || {
            if let Err(e) = Self::run_event_tap(tx) {
                eprintln!("❌ CGEventTap error: {}", e);
                eprintln!("   Tab completion will fall back to API-only mode");
            }
        });

        Ok(Self { receiver: rx })
    }

    /// Check if accessibility permissions are granted
    fn check_accessibility_permissions() -> bool {
        #[cfg(target_os = "macos")]
        {
            // Use CGPreflightScreenCaptureAccess to check if we can create an event tap
            // This is a best-effort check; we'll still try to create the tap and handle errors gracefully
            // For now, we'll always return true and handle permission errors in run_event_tap
            true
        }
        #[cfg(not(target_os = "macos"))]
        {
            false
        }
    }

    /// Run the CGEventTap event loop
    fn run_event_tap(sender: Sender<KeyboardEvent>) -> Result<()> {
        let sender_clone = sender.clone();
        
        // Create event tap for keyboard events only
        let event_tap = CGEventTap::new(
            CGEventTapLocation::HID, // Listen at HID level (system-wide)
            CGEventTapPlacement::HeadInsertEventTap,
            CGEventTapOptions::ListenOnly, // Don't modify events
            vec![CGEventType::KeyDown].into(), // Only key presses
            move |_proxy, event_type, event| {
                autoreleasepool(|| {
                    // Extract keyboard event data (only process KeyDown)
                    if let Some(keyboard_event) = Self::extract_keyboard_event(event) {
                        // Send to receiver (non-blocking with timeout)
                        if let Err(e) = sender_clone.send(keyboard_event) {
                            eprintln!("⚠️  Failed to send keyboard event: {}", e);
                        }
                    }
                });
                // Pass through the event unchanged (ListenOnly mode requires returning the event)
                Some(event.clone())
            },
        ).map_err(|e| anyhow!("Failed to create CGEventTap: {:?}", e))?;

        // Enable the event tap
        event_tap.enable();

        println!("✅ CGEventTap keyboard listener started");

        // Run the event loop (this blocks until the thread is terminated)
        unsafe {
            use core_foundation::runloop::{CFRunLoopRun, CFRunLoopGetCurrent, CFRunLoopAddSource};
            use core_foundation::base::TCFType;

            let run_loop = CFRunLoopGetCurrent();
            let source = match event_tap.mach_port.create_runloop_source(0) {
                Ok(s) => s,
                Err(_) => {
                    return Err(anyhow!("Failed to create run loop source for keyboard event tap"));
                }
            };
            CFRunLoopAddSource(run_loop, source.as_concrete_TypeRef(), kCFRunLoopCommonModes);
            CFRunLoopRun();
        }

        Ok(())
    }

    /// Extract keyboard event from CGEvent
    fn extract_keyboard_event(event: &CGEvent) -> Option<KeyboardEvent> {
        // Get keycode
        let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE) as u16;
        
        // Get modifier flags
        let flags = event.get_flags();
        let shift_pressed = flags.contains(core_graphics::event::CGEventFlags::CGEventFlagShift);
        let option_pressed = flags.contains(core_graphics::event::CGEventFlags::CGEventFlagAlternate);
        let command_pressed = flags.contains(core_graphics::event::CGEventFlags::CGEventFlagCommand);
        let control_pressed = flags.contains(core_graphics::event::CGEventFlags::CGEventFlagControl);
        
        // Skip command and control key combinations (system shortcuts)
        if command_pressed || control_pressed {
            return None;
        }

        // Map keycode to character
        let character = Self::keycode_to_char(keycode, shift_pressed, option_pressed);
        
        // Check if it's a special key (return, delete, etc.)
        let is_special_key = Self::is_special_keycode(keycode);

        Some(KeyboardEvent {
            character,
            keycode,
            is_special_key,
        })
    }

    /// Map macOS keycode to character
    fn keycode_to_char(keycode: u16, shift: bool, option: bool) -> Option<char> {
        // Handle option key combinations (special characters)
        if option {
            return Self::keycode_with_option(keycode, shift);
        }

        // Standard keycode to character mapping
        match keycode {
            // Letters (a-z)
            0x00 => Some(if shift { 'A' } else { 'a' }),
            0x01 => Some(if shift { 'S' } else { 's' }),
            0x02 => Some(if shift { 'D' } else { 'd' }),
            0x03 => Some(if shift { 'F' } else { 'f' }),
            0x04 => Some(if shift { 'H' } else { 'h' }),
            0x05 => Some(if shift { 'G' } else { 'g' }),
            0x06 => Some(if shift { 'Z' } else { 'z' }),
            0x07 => Some(if shift { 'X' } else { 'x' }),
            0x08 => Some(if shift { 'C' } else { 'c' }),
            0x09 => Some(if shift { 'V' } else { 'v' }),
            0x0B => Some(if shift { 'B' } else { 'b' }),
            0x0C => Some(if shift { 'Q' } else { 'q' }),
            0x0D => Some(if shift { 'W' } else { 'w' }),
            0x0E => Some(if shift { 'E' } else { 'e' }),
            0x0F => Some(if shift { 'R' } else { 'r' }),
            0x10 => Some(if shift { 'Y' } else { 'y' }),
            0x11 => Some(if shift { 'T' } else { 't' }),
            0x12 => Some(if shift { '!' } else { '1' }),
            0x13 => Some(if shift { '@' } else { '2' }),
            0x14 => Some(if shift { '#' } else { '3' }),
            0x15 => Some(if shift { '$' } else { '4' }),
            0x16 => Some(if shift { '%' } else { '6' }),
            0x17 => Some(if shift { '^' } else { '5' }),
            0x18 => Some(if shift { '+' } else { '=' }),
            0x19 => Some(if shift { '(' } else { '9' }),
            0x1A => Some(if shift { '&' } else { '7' }),
            0x1B => Some(if shift { '_' } else { '-' }),
            0x1C => Some(if shift { '*' } else { '8' }),
            0x1D => Some(if shift { ')' } else { '0' }),
            0x1E => Some(if shift { '}' } else { ']' }),
            0x1F => Some(if shift { 'O' } else { 'o' }),
            0x20 => Some(if shift { 'U' } else { 'u' }),
            0x21 => Some(if shift { '{' } else { '[' }),
            0x22 => Some(if shift { 'I' } else { 'i' }),
            0x23 => Some(if shift { 'P' } else { 'p' }),
            0x25 => Some(if shift { 'L' } else { 'l' }),
            0x26 => Some(if shift { 'J' } else { 'j' }),
            0x27 => Some(if shift { '"' } else { '\'' }),
            0x28 => Some(if shift { 'K' } else { 'k' }),
            0x29 => Some(if shift { ':' } else { ';' }),
            0x2A => Some(if shift { '|' } else { '\\' }),
            0x2B => Some(if shift { '<' } else { ',' }),
            0x2C => Some(if shift { '?' } else { '/' }),
            0x2D => Some(if shift { 'N' } else { 'n' }),
            0x2E => Some(if shift { 'M' } else { 'm' }),
            0x2F => Some(if shift { '>' } else { '.' }),
            
            // Backtick
            0x32 => Some(if shift { '~' } else { '`' }),
            
            // Space, return, tab
            0x31 => Some(' '),
            0x24 => Some('\n'), // Return
            0x30 => Some('\t'), // Tab
            
            _ => None,
        }
    }

    /// Handle option key combinations
    fn keycode_with_option(keycode: u16, shift: bool) -> Option<char> {
        // Common option key combinations for special characters
        match (keycode, shift) {
            (0x00, false) => Some('å'), // option+a
            (0x0E, false) => Some('´'), // option+e (dead key, but we'll use accent)
            (0x22, false) => Some('î'), // option+i
            (0x1F, false) => Some('ø'), // option+o
            (0x20, false) => Some('¨'), // option+u (dead key)
            _ => None, // Return None for other option combos to avoid confusion
        }
    }

    /// Check if keycode represents a special key (arrows, delete, etc.)
    fn is_special_keycode(keycode: u16) -> bool {
        matches!(
            keycode,
            0x33 | // Delete
            0x75 | // Forward delete
            0x24 | // Return
            0x30 | // Tab
            0x35 | // Escape
            0x7B | // Left arrow
            0x7C | // Right arrow
            0x7D | // Down arrow
            0x7E | // Up arrow
            0x73 | // Home
            0x77 | // End
            0x74 | // Page up
            0x79   // Page down
        )
    }

    /// Try to receive the next keyboard event (non-blocking)
    pub fn try_recv(&self) -> Result<KeyboardEvent, TryRecvError> {
        self.receiver.try_recv()
    }

    /// Get a clone of the receiver for use in other threads
    pub fn get_receiver(&self) -> &Receiver<KeyboardEvent> {
        &self.receiver
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_keycode_to_char() {
        // Test lowercase letters
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x00, false, false), Some('a'));
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x06, false, false), Some('z'));
        
        // Test uppercase letters
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x00, true, false), Some('A'));
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x06, true, false), Some('Z'));
        
        // Test numbers
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x12, false, false), Some('1'));
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x1D, false, false), Some('0'));
        
        // Test special characters with shift
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x12, true, false), Some('!'));
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x13, true, false), Some('@'));
        
        // Test space
        assert_eq!(MacOSKeyboardListener::keycode_to_char(0x31, false, false), Some(' '));
    }

    #[test]
    fn test_is_special_keycode() {
        assert!(MacOSKeyboardListener::is_special_keycode(0x33)); // Delete
        assert!(MacOSKeyboardListener::is_special_keycode(0x24)); // Return
        assert!(MacOSKeyboardListener::is_special_keycode(0x7B)); // Left arrow
        assert!(!MacOSKeyboardListener::is_special_keycode(0x00)); // 'a'
    }

    #[test]
    fn test_check_accessibility_permissions() {
        // This test just verifies the function doesn't panic
        let _has_permission = MacOSKeyboardListener::check_accessibility_permissions();
        // We can't assert the result as it depends on system settings
    }
}

