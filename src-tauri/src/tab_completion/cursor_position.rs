use anyhow::{Result, anyhow};
use core_foundation::base::TCFType;
use core_foundation::string::CFString;

#[cfg(target_os = "macos")]
use cocoa::base::{id, nil};
#[cfg(target_os = "macos")]
use cocoa::foundation::NSRect;
#[cfg(target_os = "macos")]
use objc::{class, msg_send, sel, sel_impl};

/// Position of the text cursor in screen coordinates
#[derive(Debug, Clone, Copy)]
pub struct CursorPosition {
    pub x: f64,
    pub y: f64,
}

/// Get the text cursor position from the currently focused text field
/// using macOS Accessibility API
#[cfg(target_os = "macos")]
pub fn get_text_cursor_position() -> Result<CursorPosition> {
    use accessibility_sys::{
        AXUIElementRef, AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue,
        AXValueGetValue, kAXFocusedUIElementAttribute, kAXSelectedTextRangeAttribute,
        kAXBoundsForRangeParameterizedAttribute,
    };
    use core_foundation::base::CFRelease;
    use std::ptr;
    use std::panic;
    
    // Wrap the entire operation in a panic catch to prevent crashes
    let result = panic::catch_unwind(|| {
        unsafe {
            // Get system-wide accessibility element
            let system_wide = AXUIElementCreateSystemWide();
            if system_wide.is_null() {
                return Err(anyhow!("Failed to create system-wide AX element"));
            }
            
            // Get focused element
            let focused_attr = CFString::new(kAXFocusedUIElementAttribute).as_concrete_TypeRef();
            let mut focused_element: AXUIElementRef = ptr::null_mut();
            
            let result = AXUIElementCopyAttributeValue(
                system_wide,
                focused_attr,
                &mut focused_element as *mut _ as *mut _,
            );
            
            if result != 0 || focused_element.is_null() {
                CFRelease(system_wide as *const _);
                return Err(anyhow!("Failed to get focused element (code: {})", result));
            }
            
            // Get selected text range
            let range_attr = CFString::new(kAXSelectedTextRangeAttribute).as_concrete_TypeRef();
            let mut range_value: *mut std::ffi::c_void = ptr::null_mut();
            
            let result = AXUIElementCopyAttributeValue(
                focused_element,
                range_attr,
                &mut range_value as *mut _ as *mut _,
            );
            
            if result != 0 || range_value.is_null() {
                CFRelease(focused_element as *const _);
                CFRelease(system_wide as *const _);
                return Err(anyhow!("Failed to get selected text range (code: {})", result));
            }
            
            // Get bounds for the range (this gives us cursor position)
            let bounds_attr = CFString::new(kAXBoundsForRangeParameterizedAttribute).as_concrete_TypeRef();
            let mut bounds_value: *mut std::ffi::c_void = ptr::null_mut();
            
            let result = AXUIElementCopyParameterizedAttributeValue(
                focused_element,
                bounds_attr,
                range_value as _,
                &mut bounds_value as *mut _ as *mut _,
            );
            
            CFRelease(range_value as *const _);
            
            if result != 0 || bounds_value.is_null() {
                CFRelease(focused_element as *const _);
                CFRelease(system_wide as *const _);
                return Err(anyhow!("Failed to get bounds for range (code: {})", result));
            }
            
            // Extract CGRect from AXValue
            let mut rect = core_graphics::geometry::CGRect::new(
                &core_graphics::geometry::CGPoint::new(0.0, 0.0),
                &core_graphics::geometry::CGSize::new(0.0, 0.0),
            );
            
            // kAXValueCGRectType = 2 (from AXValueType enum)
            let extracted = AXValueGetValue(
                bounds_value as _,
                2, // kAXValueCGRectType
                &mut rect as *mut _ as *mut _,
            );
            
            CFRelease(bounds_value as *const _);
            CFRelease(focused_element as *const _);
            CFRelease(system_wide as *const _);
            
            if !extracted {
                return Err(anyhow!("Failed to extract CGRect from AXValue"));
            }
            
            // Validate rect values to prevent invalid coordinates
            if rect.origin.x.is_nan() || rect.origin.y.is_nan() || 
               rect.origin.x < -10000.0 || rect.origin.x > 10000.0 ||
               rect.origin.y < -10000.0 || rect.origin.y > 10000.0 {
                return Err(anyhow!("Invalid cursor coordinates"));
            }
            
            // Convert from Cocoa coordinates (bottom-left origin) to screen coordinates (top-left origin)
            // Use the height of the screen containing this point for proper multi-monitor support
            let screen_height = get_screen_height_for_point(rect.origin.x, rect.origin.y);
            let cursor_x = rect.origin.x;
            let cursor_y = screen_height - rect.origin.y - rect.size.height;
            
            Ok(CursorPosition {
                x: cursor_x,
                y: cursor_y,
            })
        }
    });
    
    match result {
        Ok(pos_result) => pos_result,
        Err(e) => {
            eprintln!("⚠️  Panic caught in cursor position detection: {:?}", e);
            Err(anyhow!("Cursor position detection panicked"))
        }
    }
}

#[cfg(target_os = "macos")]
extern "C" {
    fn AXUIElementCopyParameterizedAttributeValue(
        element: accessibility_sys::AXUIElementRef,
        attribute: core_foundation::string::CFStringRef,
        parameter: core_foundation::base::CFTypeRef,
        value: *mut core_foundation::base::CFTypeRef,
    ) -> i32;
}

/// Get the height of the main screen (needed for coordinate conversion)
#[allow(dead_code)]
#[cfg(target_os = "macos")]
fn get_main_screen_height() -> f64 {
    unsafe {
        let screen: id = msg_send![class!(NSScreen), mainScreen];
        if screen == nil {
            return 1080.0; // Default fallback
        }
        let frame: NSRect = msg_send![screen, frame];
        frame.size.height
    }
}

/// Get the screen frame (origin and height) for a specific point in Cocoa coordinates
/// Returns (screen_origin_y, screen_height) for proper coordinate conversion
#[cfg(target_os = "macos")]
fn get_screen_frame_for_point(x: f64, y_cocoa: f64) -> (f64, f64) {
    
    unsafe {
        // Get all screens
        let screens: id = msg_send![class!(NSScreen), screens];
        if screens == nil {
            let main_screen: id = msg_send![class!(NSScreen), mainScreen];
            if main_screen != nil {
                let frame: NSRect = msg_send![main_screen, frame];
                return (frame.origin.y, frame.size.height);
            }
            return (0.0, 1080.0);
        }
        
        let count: usize = msg_send![screens, count];
        
        // In Cocoa coordinates, Y increases upward from bottom-left of the main screen
        // We need to find which screen contains this point
        for i in 0..count {
            let screen: id = msg_send![screens, objectAtIndex: i];
            if screen == nil {
                continue;
            }
            
            let frame: NSRect = msg_send![screen, frame];
            
            // Check if point is within this screen's bounds (Cocoa coordinates)
            if x >= frame.origin.x && x < frame.origin.x + frame.size.width &&
               y_cocoa >= frame.origin.y && y_cocoa < frame.origin.y + frame.size.height {
                return (frame.origin.y, frame.size.height);
            }
        }
        
        // If no screen found, use main screen
        let main_screen: id = msg_send![class!(NSScreen), mainScreen];
        if main_screen != nil {
            let frame: NSRect = msg_send![main_screen, frame];
            return (frame.origin.y, frame.size.height);
        }
        
        (0.0, 1080.0)
    }
}

/// Get the screen height for a specific point (for multi-monitor coordinate conversion)
/// This finds which screen contains the point and returns its height
#[cfg(target_os = "macos")]
fn get_screen_height_for_point(x: f64, y_cocoa: f64) -> f64 {
    let (_origin_y, height) = get_screen_frame_for_point(x, y_cocoa);
    height
}

/// Fallback: Get mouse cursor position (not text cursor, but better than nothing)
#[cfg(target_os = "macos")]
pub fn get_mouse_cursor_position() -> Result<CursorPosition> {
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
    
    let event_source = CGEventSource::new(CGEventSourceStateID::HIDSystemState)
        .map_err(|_| anyhow!("Failed to create event source"))?;
    
    let location = core_graphics::event::CGEvent::new(event_source)
        .map_err(|_| anyhow!("Failed to create event"))?
        .location();
    
    Ok(CursorPosition {
        x: location.x,
        y: location.y,
    })
}

#[cfg(not(target_os = "macos"))]
pub fn get_text_cursor_position() -> Result<CursorPosition> {
    Err(anyhow!("Cursor position detection only supported on macOS"))
}

#[cfg(not(target_os = "macos"))]
pub fn get_mouse_cursor_position() -> Result<CursorPosition> {
    Err(anyhow!("Cursor position detection only supported on macOS"))
}

/// Try to get text cursor position, fall back to mouse position if that fails
pub fn get_cursor_position_with_fallback() -> Result<CursorPosition> {
    match get_text_cursor_position() {
        Ok(pos) => {
            println!("📍 Got text cursor position: ({:.0}, {:.0})", pos.x, pos.y);
            Ok(pos)
        }
        Err(e) => {
            println!("⚠️  Failed to get text cursor position: {}", e);
            println!("📍 Falling back to mouse cursor position");
            get_mouse_cursor_position()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    #[cfg(target_os = "macos")]
    fn test_get_cursor_position() {
        // This test requires accessibility permissions
        match get_cursor_position_with_fallback() {
            Ok(pos) => {
                println!("Cursor position: ({}, {})", pos.x, pos.y);
                assert!(pos.x >= 0.0);
                assert!(pos.y >= 0.0);
            }
            Err(e) => {
                println!("Note: Test requires accessibility permissions: {}", e);
            }
        }
    }
}

