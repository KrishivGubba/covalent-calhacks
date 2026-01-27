use anyhow::Result;
use tauri::{AppHandle, Manager, WebviewWindow, LogicalPosition, LogicalSize, Emitter, WebviewWindowBuilder, WebviewUrl};
use serde::Serialize;

use super::cursor_position::CursorPosition;
use super::trigger::CompletionSuggestion;

/// Manages the ghost text and completion popup windows
pub struct CompletionWindowManager {
    app_handle: AppHandle,
}

#[derive(Debug, Clone, Serialize)]
struct GhostTextPayload {
    text: String,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionPopupPayload {
    text: String,
    confidence: f32,
    cache_level: String,
}

impl CompletionWindowManager {
    pub fn new(app_handle: AppHandle) -> Self {
        Self { app_handle }
    }
    
    /// Show completion suggestion - tries ghost text first, falls back to popup
    pub fn show_suggestion(&self, suggestion: &CompletionSuggestion) -> Result<()> {
        // Validate suggestion text to prevent crashes from malformed data
        if suggestion.text.is_empty() {
            eprintln!("⚠️  Empty suggestion text, skipping");
            return Ok(());
        }
        
        // Sanitize text - remove control characters that could cause issues
        let sanitized_text = suggestion.text
            .chars()
            .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
            .collect::<String>();
        
        if sanitized_text.is_empty() {
            eprintln!("⚠️  Suggestion contains only control characters, skipping");
            return Ok(());
        }
        
        // Truncate very long suggestions to prevent UI issues
        let final_text = if sanitized_text.len() > 500 {
            format!("{}...", &sanitized_text[..497])
        } else {
            sanitized_text
        };
        
        // Create sanitized suggestion
        let safe_suggestion = CompletionSuggestion {
            text: final_text.clone(),
            cache_level: suggestion.cache_level.clone(),
            latency_ms: suggestion.latency_ms,
            context_type: suggestion.context_type.clone(),
            confidence: suggestion.confidence,
        };
        
        println!("🎯 Attempting to show suggestion: {}", &safe_suggestion.text[..safe_suggestion.text.len().min(50)]);
        
        // Try tiered cursor detection
        let cursor_pos = self.get_cursor_position_tiered();
        
        // Always use popup for now (ghost text disabled due to stability)
        // Wrap in additional error handling to prevent crashes
        match self.show_popup(&safe_suggestion, cursor_pos) {
            Ok(_) => Ok(()),
            Err(e) => {
                eprintln!("⚠️  Failed to show completion popup: {}", e);
                // Don't propagate error - just log and continue
                Ok(())
            }
        }
        
        /* Disabled temporarily due to crashes in Accessibility API
        // Try to get cursor position with timeout in separate thread
        use std::sync::mpsc;
        use std::time::Duration;
        
        let (tx, rx) = mpsc::channel();
        
        std::thread::spawn(move || {
            let result = get_cursor_position_with_fallback();
            let _ = tx.send(result);
        });
        
        // Wait for result with timeout
        match rx.recv_timeout(Duration::from_millis(100)) {
            Ok(Ok(cursor_pos)) => {
                // Try to show ghost text overlay
                match self.show_ghost_text(suggestion, cursor_pos) {
                    Ok(_) => {
                        println!("✅ Showing ghost text overlay");
                        return Ok(());
                    }
                    Err(e) => {
                        println!("⚠️  Ghost text failed: {}, falling back to popup", e);
                        self.show_popup(suggestion, Some(cursor_pos))
                    }
                }
            }
            Ok(Err(e)) => {
                println!("⚠️  Cursor detection failed: {}, using popup", e);
                self.show_popup(suggestion, None)
            }
            Err(_) => {
                println!("⚠️  Cursor detection timed out, using popup");
                self.show_popup(suggestion, None)
            }
        }
        */
    }
    
    /// Show ghost text overlay at cursor position
    fn show_ghost_text(&self, suggestion: &CompletionSuggestion, cursor_pos: CursorPosition) -> Result<()> {
        // Validate cursor position
        if cursor_pos.x < 0.0 || cursor_pos.y < 0.0 || 
           cursor_pos.x > 10000.0 || cursor_pos.y > 10000.0 {
            return Err(anyhow::anyhow!("Invalid cursor position: ({}, {})", cursor_pos.x, cursor_pos.y));
        }
        
        let window = self.get_or_create_ghost_window()?;
        
        // Position window at cursor
        let offset_x = 0.0; // Slight offset to the right of cursor
        let offset_y = 20.0; // Below the cursor line
        
        // Catch any positioning errors
        if let Err(e) = window.set_position(LogicalPosition::new(
            cursor_pos.x + offset_x,
            cursor_pos.y + offset_y,
        )) {
            return Err(anyhow::anyhow!("Failed to position ghost window: {}", e));
        }
        
        // Update text content
        let payload = GhostTextPayload {
            text: suggestion.text.clone(),
        };
        
        if let Err(e) = window.emit("update-ghost-text", payload) {
            return Err(anyhow::anyhow!("Failed to emit ghost text: {}", e));
        }
        
        // Show window
        if let Err(e) = window.show() {
            return Err(anyhow::anyhow!("Failed to show ghost window: {}", e));
        }
        
        Ok(())
    }
    
    /// Show completion popup window
    fn show_popup(&self, suggestion: &CompletionSuggestion, cursor_pos: Option<CursorPosition>) -> Result<()> {
        let window = match self.get_or_create_popup_window() {
            Ok(w) => w,
            Err(e) => {
                eprintln!("⚠️  Failed to get popup window: {}", e);
                return Err(e);
            }
        };
        
        // Position window near cursor if available, otherwise center of screen
        let position_result = if let Some(pos) = cursor_pos {
            // Validate position
            if pos.x >= 0.0 && pos.y >= 0.0 && pos.x < 10000.0 && pos.y < 10000.0 {
                // Calculate position with offset
                let offset_x = 20.0; // Slightly to the right of cursor
                let offset_y = 30.0; // Below cursor
                let mut final_x = pos.x + offset_x;
                let mut final_y = pos.y + offset_y;
                
                // Get screen dimensions to clamp position
                let (screen_width, screen_height) = self.get_screen_dimensions();
                let popup_width = 500.0;
                let popup_height = 200.0;
                
                // Clamp to ensure popup stays on screen
                final_x = final_x.max(0.0).min(screen_width - popup_width);
                final_y = final_y.max(0.0).min(screen_height - popup_height);
                
                println!("📍 Positioning popup at ({:.0}, {:.0})", final_x, final_y);
                
                window.set_position(LogicalPosition::new(final_x, final_y))
            } else {
                // Invalid position, use fallback
                window.set_position(LogicalPosition::new(100.0, 100.0))
            }
        } else {
            // Fallback: position in upper-right area
            window.set_position(LogicalPosition::new(100.0, 100.0))
        };
        
        if let Err(e) = position_result {
            eprintln!("⚠️  Failed to position popup window: {}, continuing anyway", e);
        }
        
        // Show window first
        if let Err(e) = window.show() {
            eprintln!("⚠️  Failed to show popup window: {}", e);
            return Err(anyhow::anyhow!("Failed to show popup window: {}", e));
        }
        
        // Update popup content
        let payload = CompletionPopupPayload {
            text: suggestion.text.clone(),
            confidence: suggestion.confidence,
            cache_level: suggestion.cache_level.clone(),
        };
        
        // Emit immediately - with error handling to prevent crashes
        match window.emit("update-completion-popup", &payload) {
            Ok(_) => println!("✅ Emitted popup content"),
            Err(e) => {
                eprintln!("⚠️  Failed to emit popup content: {}", e);
                // If initial emit fails, likely the window is broken - return error
                return Err(anyhow::anyhow!("Failed to emit to popup window: {}", e));
            }
        }
        
        // Also emit after a small delay to ensure the window's JS is ready
        // Spawn threads with error handling to prevent crashes
        let window_clone = window.clone();
        let payload_clone = payload.clone();
        std::thread::Builder::new()
            .name("popup-emit-delay-1".to_string())
            .spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(50));
                if let Err(e) = window_clone.emit("update-completion-popup", &payload_clone) {
                    eprintln!("⚠️  Delayed emit failed: {}", e);
                }
            })
            .map_err(|e| eprintln!("⚠️  Failed to spawn delay thread: {}", e))
            .ok();
        
        // And one more time after 150ms for good measure
        let window_clone2 = window.clone();
        let payload_clone2 = payload.clone();
        std::thread::Builder::new()
            .name("popup-emit-delay-2".to_string())
            .spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(150));
                if let Err(e) = window_clone2.emit("update-completion-popup", &payload_clone2) {
                    eprintln!("⚠️  Delayed emit 2 failed: {}", e);
                }
            })
            .map_err(|e| eprintln!("⚠️  Failed to spawn delay thread 2: {}", e))
            .ok();
        
        Ok(())
    }
    
    /// Get screen dimensions for bounds checking
    fn get_screen_dimensions(&self) -> (f64, f64) {
        // Try to get primary monitor dimensions
        #[cfg(target_os = "macos")]
        {
            use cocoa::appkit::NSScreen;
            use cocoa::base::nil;
            use cocoa::foundation::NSRect;
            use objc::{class, msg_send, sel, sel_impl};
            
            unsafe {
                let screen: cocoa::base::id = msg_send![class!(NSScreen), mainScreen];
                if screen != nil {
                    let frame: NSRect = msg_send![screen, frame];
                    return (frame.size.width, frame.size.height);
                }
            }
        }
        
        // Fallback to reasonable defaults
        (1920.0, 1080.0)
    }
    
    /// Get cursor position using tiered fallback approach
    /// NOTE: This method is called from the main thread, so we MUST NOT block.
    /// The previous implementation used recv_timeout which blocks the main thread
    /// and causes crashes on macOS (main thread blocking triggers AppKit assertions).
    fn get_cursor_position_tiered(&self) -> Option<CursorPosition> {
        // Try mouse cursor directly - this is fast and non-blocking (uses CGEvent)
        // We skip the text cursor detection because it uses Accessibility APIs
        // which can be slow and may cause issues when called frequently
        if let Ok(pos) = super::cursor_position::get_mouse_cursor_position() {
            println!("✅ Got mouse cursor position: ({:.0}, {:.0})", pos.x, pos.y);
            return Some(pos);
        }

        // Fallback: Use a reasonable default position
        // This ensures we never block and always have a position
        println!("⚠️  Mouse cursor detection failed, using default position");
        Some(CursorPosition {
            x: 100.0,  // Upper-left area, safe default
            y: 100.0,
        })
    }
    
    /// Hide all completion windows
    pub fn hide_all(&self) -> Result<()> {
        // Hide ghost text
        if let Some(window) = self.app_handle.get_webview_window("ghost-text") {
            let _ = window.hide();
            let _ = window.emit("hide-ghost-text", ());
        }
        
        // Hide popup
        if let Some(window) = self.app_handle.get_webview_window("completion-popup") {
            let _ = window.hide();
        }
        
        Ok(())
    }
    
    /// Get or create ghost text window
    fn get_or_create_ghost_window(&self) -> Result<WebviewWindow> {
        match self.app_handle.get_webview_window("ghost-text") {
            Some(window) => Ok(window),
            None => {
                // Window should be created from tauri.conf.json
                Err(anyhow::anyhow!("Ghost text window not found - check tauri.conf.json"))
            }
        }
    }
    
    /// Get or create popup window
    fn get_or_create_popup_window(&self) -> Result<WebviewWindow> {
        match self.app_handle.get_webview_window("completion-popup") {
            Some(window) => {
                println!("✅ Found existing popup window");
                Ok(window)
            },
            None => {
                println!("⚠️  Popup window not found, creating it...");
                // Create the window programmatically
                use tauri::WebviewWindowBuilder;
                use tauri::WebviewUrl;
                
                let window = WebviewWindowBuilder::new(
                    &self.app_handle,
                    "completion-popup",
                    WebviewUrl::App("completion-popup.html".into())
                )
                .title("Completion")
                .inner_size(500.0, 200.0)
                .position(200.0, 200.0)
                .decorations(false)
                .transparent(true)
                .resizable(false)
                .visible_on_all_workspaces(true)
                .skip_taskbar(true)
                .visible(false)
                .always_on_top(true)
                .focused(false)
                .build()
                .map_err(|e| anyhow::anyhow!("Failed to create popup window: {}", e))?;
                
                println!("✅ Created popup window");
                Ok(window)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_payload_serialization() {
        let payload = GhostTextPayload {
            text: "test".to_string(),
        };
        
        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("test"));
    }
}

