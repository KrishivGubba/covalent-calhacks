use anyhow::Result;
use arboard::Clipboard;
use std::thread;
use std::time::Duration;

/// Inject completion text into the foreground application
#[tauri::command]
pub fn inject_completion_text(text: String) -> Result<(), String> {
    inject_with_backspace(text, 0)
}

/// Inject completion text after erasing N characters (for accepting suggestion after continued typing)
pub fn inject_with_backspace(text: String, chars_to_erase: usize) -> Result<(), String> {
    if chars_to_erase > 0 {
        println!("🔙 Erasing {} chars before injection", chars_to_erase);
        if let Err(e) = send_backspaces(chars_to_erase) {
            eprintln!("⚠️  Failed to send backspaces: {}", e);
            // Continue anyway - better to inject without erasing than fail completely
        }
        // Small delay after backspaces to let the app process them
        thread::sleep(Duration::from_millis(50));
    }

    println!("💉 Injecting text: '{}'", text);

    // Method 1: Try clipboard paste (fastest, most reliable)
    if inject_via_clipboard(&text).is_ok() {
        println!("✅ Text injected via clipboard");
        return Ok(());
    }

    println!("⚠️  Clipboard method failed, trying event-based injection");

    // Method 2: Character-by-character injection (slower, but works everywhere)
    inject_via_events(&text).map_err(|e| e.to_string())
}

/// Send N backspace key events to erase characters
fn send_backspaces(count: usize) -> Result<()> {
    #[cfg(target_os = "macos")]
    {
        use core_graphics::event::{CGEvent, CGKeyCode, CGEventFlags};
        use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};

        const kVK_Delete: CGKeyCode = 0x33; // Backspace key

        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState)
            .map_err(|_| anyhow::anyhow!("Failed to create event source"))?;

        for i in 0..count {
            // Key down — explicitly clear modifier flags so Option being held
            // doesn't turn this into Option+Delete (word deletion)
            let key_down = CGEvent::new_keyboard_event(source.clone(), kVK_Delete, true)
                .map_err(|_| anyhow::anyhow!("Failed to create backspace key down event"))?;
            key_down.set_flags(CGEventFlags::empty());
            key_down.post(core_graphics::event::CGEventTapLocation::HID);

            // Small delay between key events
            thread::sleep(Duration::from_millis(10));

            // Key up
            let key_up = CGEvent::new_keyboard_event(source.clone(), kVK_Delete, false)
                .map_err(|_| anyhow::anyhow!("Failed to create backspace key up event"))?;
            key_up.set_flags(CGEventFlags::empty());
            key_up.post(core_graphics::event::CGEventTapLocation::HID);

            // Small delay between backspaces
            if i < count - 1 {
                thread::sleep(Duration::from_millis(5));
            }
        }

        Ok(())
    }

    #[cfg(not(target_os = "macos"))]
    {
        // Fallback: use AppleScript-style approach or just skip
        eprintln!("⚠️  Backspace injection only supported on macOS");
        Ok(())
    }
}

fn inject_via_clipboard(text: &str) -> Result<()> {
    let mut clipboard = Clipboard::new()?;
    
    // Save old clipboard content
    let old_clipboard = clipboard.get_text().ok();
    
    // Set new clipboard content
    clipboard.set_text(text)?;
    
    // Wait a moment for clipboard to be ready
    thread::sleep(Duration::from_millis(50));
    
    // Use AppleScript to paste
    send_paste_command()?;
    
    // Wait for paste to complete
    thread::sleep(Duration::from_millis(100));
    
    // Restore old clipboard content
    if let Some(old_text) = old_clipboard {
        if let Err(e) = clipboard.set_text(old_text) {
            eprintln!("⚠️  Failed to restore clipboard: {}", e);
        }
    }
    
    Ok(())
}

fn inject_via_events(text: &str) -> Result<()> {
    println!("⌨️  Injecting {} characters via events", text.len());
    
    // Use AppleScript to type the text character by character
    send_text_via_applescript(text)?;
    
    Ok(())
}

fn send_paste_command() -> Result<()> {
    // Use AppleScript to send Cmd+V
    let script = r#"
        tell application "System Events"
            keystroke "v" using command down
        end tell
    "#;

    execute_applescript(script)
}

fn send_text_via_applescript(text: &str) -> Result<()> {
    // Escape special characters for AppleScript
    let escaped_text = text
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t");
    
    let script = format!(
        r#"
        tell application "System Events"
            keystroke "{}"
        end tell
        "#,
        escaped_text
    );
    
    execute_applescript(&script)
}

fn execute_applescript(script: &str) -> Result<()> {
    use osascript::JavaScript;
    
    // Note: osascript crate actually supports AppleScript by default
    let result = std::process::Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()?;
    
    if !result.status.success() {
        let error_msg = String::from_utf8_lossy(&result.stderr);
        return Err(anyhow::anyhow!("AppleScript failed: {}", error_msg));
    }
    
    Ok(())
}

// Alternative implementation using core-graphics for macOS key events
// This can be used as a fallback if AppleScript doesn't work
#[cfg(target_os = "macos")]
#[allow(dead_code)]
fn send_key_combo_native(keycode: u16, flags: u64) -> Result<()> {
    use core_graphics::event::{CGEvent, CGKeyCode, CGEventFlags};
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
    
    let source = match CGEventSource::new(CGEventSourceStateID::HIDSystemState) {
        Ok(src) => src,
        Err(_) => return Err(anyhow::anyhow!("Failed to create event source")),
    };
    
    // Create key down event
    let key_down = match CGEvent::new_keyboard_event(source.clone(), keycode as CGKeyCode, true) {
        Ok(event) => event,
        Err(_) => return Err(anyhow::anyhow!("Failed to create key down event")),
    };
    
    key_down.set_flags(CGEventFlags::from_bits_truncate(flags));
    key_down.post(core_graphics::event::CGEventTapLocation::HID);
    
    thread::sleep(Duration::from_millis(20));
    
    // Create key up event
    let key_up = match CGEvent::new_keyboard_event(source, keycode as CGKeyCode, false) {
        Ok(event) => event,
        Err(_) => return Err(anyhow::anyhow!("Failed to create key up event")),
    };
    
    key_up.set_flags(CGEventFlags::from_bits_truncate(flags));
    key_up.post(core_graphics::event::CGEventTapLocation::HID);
    
    Ok(())
}

#[cfg(not(target_os = "macos"))]
#[allow(dead_code)]
fn send_key_combo_native(_keycode: u16, _flags: u64) -> Result<()> {
    Err(anyhow::anyhow!("Native key injection only supported on macOS"))
}

fn char_to_keycode(ch: char) -> Option<u16> {
    match ch {
        'a' => Some(kVK_ANSI_A),
        'b' => Some(kVK_ANSI_B),
        'c' => Some(kVK_ANSI_C),
        'd' => Some(kVK_ANSI_D),
        'e' => Some(kVK_ANSI_E),
        'f' => Some(kVK_ANSI_F),
        'g' => Some(kVK_ANSI_G),
        'h' => Some(kVK_ANSI_H),
        'i' => Some(kVK_ANSI_I),
        'j' => Some(kVK_ANSI_J),
        'k' => Some(kVK_ANSI_K),
        'l' => Some(kVK_ANSI_L),
        'm' => Some(kVK_ANSI_M),
        'n' => Some(kVK_ANSI_N),
        'o' => Some(kVK_ANSI_O),
        'p' => Some(kVK_ANSI_P),
        'q' => Some(kVK_ANSI_Q),
        'r' => Some(kVK_ANSI_R),
        's' => Some(kVK_ANSI_S),
        't' => Some(kVK_ANSI_T),
        'u' => Some(kVK_ANSI_U),
        'v' => Some(kVK_ANSI_V),
        'w' => Some(kVK_ANSI_W),
        'x' => Some(kVK_ANSI_X),
        'y' => Some(kVK_ANSI_Y),
        'z' => Some(kVK_ANSI_Z),
        '0' => Some(kVK_ANSI_0),
        '1' => Some(kVK_ANSI_1),
        '2' => Some(kVK_ANSI_2),
        '3' => Some(kVK_ANSI_3),
        '4' => Some(kVK_ANSI_4),
        '5' => Some(kVK_ANSI_5),
        '6' => Some(kVK_ANSI_6),
        '7' => Some(kVK_ANSI_7),
        '8' => Some(kVK_ANSI_8),
        '9' => Some(kVK_ANSI_9),
        ' ' => Some(kVK_Space),
        '-' => Some(kVK_ANSI_Minus),
        '=' => Some(kVK_ANSI_Equal),
        _ => None,
    }
}

// macOS keycodes
const kVK_ANSI_A: u16 = 0x00;
const kVK_ANSI_B: u16 = 0x0B;
const kVK_ANSI_C: u16 = 0x08;
const kVK_ANSI_D: u16 = 0x02;
const kVK_ANSI_E: u16 = 0x0E;
const kVK_ANSI_F: u16 = 0x03;
const kVK_ANSI_G: u16 = 0x05;
const kVK_ANSI_H: u16 = 0x04;
const kVK_ANSI_I: u16 = 0x22;
const kVK_ANSI_J: u16 = 0x26;
const kVK_ANSI_K: u16 = 0x28;
const kVK_ANSI_L: u16 = 0x25;
const kVK_ANSI_M: u16 = 0x2E;
const kVK_ANSI_N: u16 = 0x2D;
const kVK_ANSI_O: u16 = 0x1F;
const kVK_ANSI_P: u16 = 0x23;
const kVK_ANSI_Q: u16 = 0x0C;
const kVK_ANSI_R: u16 = 0x0F;
const kVK_ANSI_S: u16 = 0x01;
const kVK_ANSI_T: u16 = 0x11;
const kVK_ANSI_U: u16 = 0x20;
const kVK_ANSI_V: u16 = 0x09;
const kVK_ANSI_W: u16 = 0x0D;
const kVK_ANSI_X: u16 = 0x07;
const kVK_ANSI_Y: u16 = 0x10;
const kVK_ANSI_Z: u16 = 0x06;
const kVK_ANSI_0: u16 = 0x1D;
const kVK_ANSI_1: u16 = 0x12;
const kVK_ANSI_2: u16 = 0x13;
const kVK_ANSI_3: u16 = 0x14;
const kVK_ANSI_4: u16 = 0x15;
const kVK_ANSI_5: u16 = 0x17;
const kVK_ANSI_6: u16 = 0x16;
const kVK_ANSI_7: u16 = 0x1A;
const kVK_ANSI_8: u16 = 0x1C;
const kVK_ANSI_9: u16 = 0x19;
const kVK_Space: u16 = 0x31;
const kVK_ANSI_Minus: u16 = 0x1B;
const kVK_ANSI_Equal: u16 = 0x18;

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_char_to_keycode() {
        assert_eq!(char_to_keycode('a'), Some(kVK_ANSI_A));
        assert_eq!(char_to_keycode('z'), Some(kVK_ANSI_Z));
        assert_eq!(char_to_keycode(' '), Some(kVK_Space));
        assert_eq!(char_to_keycode('@'), None);
    }
}

