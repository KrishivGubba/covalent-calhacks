use anyhow::Result;
use cocoa::base::{id, nil};
use cocoa::foundation::{NSAutoreleasePool, NSString};
use objc::{class, msg_send, sel, sel_impl};
use std::collections::HashMap;
use std::ffi::CStr;
use std::process::Command;

use crate::screen_context::context_data::{AppInfo, BrowserType, IDEType};

pub struct MacOSAppDetector {
    workspace: id,
    cache: HashMap<u32, AppInfo>,
}

// SAFETY: MacOSAppDetector is only accessed through Mutex, which provides synchronization.
// The Objective-C runtime operations we use are thread-safe.
unsafe impl Send for MacOSAppDetector {}
unsafe impl Sync for MacOSAppDetector {}

impl MacOSAppDetector {
    pub fn new() -> Result<Self> {
        unsafe {
            let _pool = NSAutoreleasePool::new(nil);
            // Get NSWorkspace sharedWorkspace manually
            let workspace_class = class!(NSWorkspace);
            let workspace: id = msg_send![workspace_class, sharedWorkspace];
            
            Ok(Self {
                workspace,
                cache: HashMap::new(),
            })
        }
    }
    
    /// Get information about the currently active application
    pub fn get_active_app_info(&mut self) -> Result<AppInfo> {
        unsafe {
            let _pool = NSAutoreleasePool::new(nil);
            
            // Get frontmost application
            let frontmost_app: id = msg_send![self.workspace, frontmostApplication];
            if frontmost_app == nil {
                return Err(anyhow::anyhow!("No frontmost application found"));
            }
            
            let mut app_info = self.extract_app_info_from_nsrunningapp(frontmost_app)?;
            
            // Debug logging
            if std::env::var("COVALENT_DEBUG").is_ok() {
                eprintln!("🐛 App Debug: name='{}', bundle_id='{}', is_browser={}, is_ide={}",
                    app_info.name, app_info.bundle_id, app_info.is_browser, app_info.is_ide);
            }
            
            // If bundle ID is empty or unknown, try process-based detection
            if app_info.bundle_id.is_empty() || app_info.name == "Unknown" {
                if let Ok(fallback_info) = self.get_app_info_from_process_list(&app_info.name, app_info.process_id) {
                    if !fallback_info.bundle_id.is_empty() {
                        app_info.bundle_id = fallback_info.bundle_id;
                        if app_info.name == "Unknown" {
                            app_info.name = fallback_info.name;
                        }
                    }
                }
            }
            
            Ok(app_info)
        }
    }
    
    /// Get information about all running applications
    pub fn get_running_apps(&self) -> Result<Vec<AppInfo>> {
        unsafe {
            let _pool = NSAutoreleasePool::new(nil);
            
            let running_apps: id = msg_send![self.workspace, runningApplications];
            let count: usize = msg_send![running_apps, count];
            
            let mut apps = Vec::new();
            for i in 0..count {
                let app: id = msg_send![running_apps, objectAtIndex: i];
                if let Ok(app_info) = self.extract_app_info_from_nsrunningapp(app) {
                    apps.push(app_info);
                }
            }
            
            Ok(apps)
        }
    }
    
    /// Get the window title for the active application
    pub fn get_active_window_title(&self) -> Result<Option<String>> {
        unsafe {
            let _pool = NSAutoreleasePool::new(nil);
            
            // Get the frontmost application
            let frontmost_app: id = msg_send![self.workspace, frontmostApplication];
            if frontmost_app == nil {
                return Ok(None);
            }
            
            // Get process identifier
            let pid: i32 = msg_send![frontmost_app, processIdentifier];
            
            // Use AXUIElement to get window title
            self.get_window_title_via_accessibility(pid)
        }
    }
    
    /// Get file path for IDEs and text editors
    pub fn get_current_file_path(&self, app_info: &AppInfo) -> Result<Option<String>> {
        if !app_info.is_ide {
            return Ok(None);
        }
        
        match app_info.ide_type {
            Some(IDEType::VSCode) => self.get_vscode_current_file(),
            Some(IDEType::Xcode) => self.get_xcode_current_file(),
            Some(IDEType::Sublime) => self.get_sublime_current_file(),
            _ => Ok(None),
        }
    }
    
    /// Get workspace/project root for IDEs
    pub fn get_workspace_path(&self, app_info: &AppInfo) -> Result<Option<String>> {
        if !app_info.is_ide {
            return Ok(None);
        }
        
        match app_info.ide_type {
            Some(IDEType::VSCode) => self.get_vscode_workspace(),
            Some(IDEType::Xcode) => self.get_xcode_workspace(),
            _ => Ok(None),
        }
    }
    
    // Private helper methods
    
    unsafe fn extract_app_info_from_nsrunningapp(&self, app: id) -> Result<AppInfo> {
        // Get basic app information
        let bundle_id: id = msg_send![app, bundleIdentifier];
        let localized_name: id = msg_send![app, localizedName];
        let executable_url: id = msg_send![app, executableURL];
        let pid: i32 = msg_send![app, processIdentifier];
        
        let bundle_id_str = if bundle_id != nil {
            unsafe {
                let cstr = CStr::from_ptr(NSString::UTF8String(bundle_id));
                cstr.to_string_lossy().to_string()
            }
        } else {
            String::new()
        };
        
        let name = if localized_name != nil {
            unsafe {
                let cstr = CStr::from_ptr(NSString::UTF8String(localized_name));
                cstr.to_string_lossy().to_string()
            }
        } else {
            "Unknown".to_string()
        };
        
        let executable_path = if executable_url != nil {
            let path: id = msg_send![executable_url, path];
            if path != nil {
                unsafe {
                    let cstr = CStr::from_ptr(NSString::UTF8String(path));
                    Some(cstr.to_string_lossy().to_string())
                }
            } else {
                None
            }
        } else {
            None
        };
        
        // Detect browser type
        let (is_browser, browser_type) = self.detect_browser_type(&bundle_id_str, &name);
        
        // Detect IDE type
        let (is_ide, ide_type) = self.detect_ide_type(&bundle_id_str, &name);
        
        // Get window title
        let window_title = self.get_window_title_via_accessibility(pid).ok().flatten();
        
        // Get version if possible
        let version = self.get_app_version(&bundle_id_str).ok();
        
        // Get display ID for the app's window
        let display_id = self.get_display_for_app(pid);
        
        Ok(AppInfo {
            name,
            bundle_id: bundle_id_str,
            version,
            window_title,
            window_id: None, // Will be set by accessibility API
            process_id: pid as u32,
            executable_path,
            is_browser,
            browser_type,
            is_ide,
            ide_type,
            current_file_path: None, // Will be set separately
            workspace_path: None,    // Will be set separately
            display_id,              // Display containing the app's window
        })
    }
    
    fn detect_browser_type(&self, bundle_id: &str, name: &str) -> (bool, Option<BrowserType>) {
        let bundle_lower = bundle_id.to_lowercase();
        let name_lower = name.to_lowercase();
        
        if bundle_lower.contains("chrome") || name_lower.contains("chrome") {
            (true, Some(BrowserType::Chrome))
        } else if bundle_lower.contains("safari") || name_lower.contains("safari") {
            (true, Some(BrowserType::Safari))
        } else if bundle_lower.contains("firefox") || name_lower.contains("firefox") {
            (true, Some(BrowserType::Firefox))
        } else if bundle_lower.contains("edge") || name_lower.contains("edge") {
            (true, Some(BrowserType::Edge))
        } else if bundle_lower.contains("arc") || name_lower.contains("arc") {
            (true, Some(BrowserType::Arc))
        } else if bundle_lower.contains("browser") || 
                  bundle_lower.contains("webkit") ||
                  name_lower.contains("browser") {
            (true, Some(BrowserType::Other(name.to_string())))
        } else {
            (false, None)
        }
    }
    
    fn detect_ide_type(&self, bundle_id: &str, name: &str) -> (bool, Option<IDEType>) {
        let bundle_lower = bundle_id.to_lowercase();
        let name_lower = name.to_lowercase();
        
        if bundle_lower.contains("vscode") || 
           bundle_lower.contains("code") && bundle_lower.contains("microsoft") {
            (true, Some(IDEType::VSCode))
        } else if bundle_lower.contains("xcode") {
            (true, Some(IDEType::Xcode))
        } else if bundle_lower.contains("intellij") {
            (true, Some(IDEType::IntelliJ))
        } else if bundle_lower.contains("pycharm") {
            (true, Some(IDEType::PyCharm))
        } else if bundle_lower.contains("webstorm") {
            (true, Some(IDEType::WebStorm))
        } else if bundle_lower.contains("sublime") || name_lower.contains("sublime") {
            (true, Some(IDEType::Sublime))
        } else if bundle_lower.contains("atom") || name_lower.contains("atom") {
            (true, Some(IDEType::Atom))
        } else if name_lower.contains("vim") || name_lower.contains("nvim") {
            (true, Some(IDEType::Vim))
        } else if name_lower.contains("emacs") {
            (true, Some(IDEType::Emacs))
        } else if name_lower.contains("editor") || 
                  name_lower.contains("ide") ||
                  bundle_lower.contains("editor") {
            (true, Some(IDEType::Other(name.to_string())))
        } else {
            (false, None)
        }
    }
    
    unsafe fn get_window_title_via_accessibility(&self, _pid: i32) -> Result<Option<String>> {
        // Stub implementation - accessibility API is complex to configure properly
        Ok(None)
    }
    
    fn get_app_version(&self, bundle_id: &str) -> Result<String> {
        let output = Command::new("mdls")
            .arg("-name")
            .arg("kMDItemVersion")
            .arg("-raw")
            .arg(format!("/Applications/{}.app", bundle_id))
            .output()?;
        
        if output.status.success() {
            let version = String::from_utf8(output.stdout)?
                .trim()
                .to_string();
            if version != "(null)" && !version.is_empty() {
                Ok(version)
            } else {
                Err(anyhow::anyhow!("Version not found"))
            }
        } else {
            Err(anyhow::anyhow!("Failed to get version"))
        }
    }
    
    // IDE-specific file path detection
    
    fn get_vscode_current_file(&self) -> Result<Option<String>> {
        // VSCode stores current file info in its state
        // We can use AppleScript to query VSCode
        let script = r#"
            tell application "Visual Studio Code"
                if (count of windows) > 0 then
                    tell window 1
                        set currentDoc to active tab of group 1 of active tab group
                        return name of currentDoc
                    end tell
                end if
            end tell
        "#;
        
        self.execute_applescript(script)
    }
    
    fn get_xcode_current_file(&self) -> Result<Option<String>> {
        let script = r#"
            tell application "Xcode"
                if (count of windows) > 0 then
                    tell window 1
                        set currentDoc to document 1
                        if currentDoc exists then
                            return path of currentDoc
                        end if
                    end tell
                end if
            end tell
        "#;
        
        self.execute_applescript(script)
    }
    
    fn get_sublime_current_file(&self) -> Result<Option<String>> {
        // Sublime Text file path can often be found in window title
        if let Ok(Some(title)) = self.get_active_window_title() {
            // Sublime often shows file path in title
            if title.contains("/") && !title.contains("Untitled") {
                // Extract file path from title (usually at the end)
                let parts: Vec<&str> = title.split(" — ").collect();
                if let Some(last_part) = parts.last() {
                    if last_part.starts_with("/") || last_part.contains("\\") {
                        return Ok(Some(last_part.to_string()));
                    }
                }
            }
        }
        Ok(None)
    }
    
    fn get_vscode_workspace(&self) -> Result<Option<String>> {
        let script = r#"
            tell application "Visual Studio Code"
                if (count of windows) > 0 then
                    tell window 1
                        -- Try to get workspace folder from window title
                        set windowTitle to name
                        return windowTitle
                    end tell
                end if
            end tell
        "#;
        
        // VSCode window title often contains workspace name
        if let Ok(Some(title)) = self.execute_applescript(script) {
            // Parse workspace from title like "file.js — project-name — Visual Studio Code"
            let parts: Vec<&str> = title.split(" — ").collect();
            if parts.len() >= 2 {
                return Ok(Some(parts[parts.len() - 2].to_string()));
            }
        }
        
        Ok(None)
    }
    
    fn get_xcode_workspace(&self) -> Result<Option<String>> {
        let script = r#"
            tell application "Xcode"
                if (count of windows) > 0 then
                    tell window 1
                        set currentProject to project document 1
                        if currentProject exists then
                            return path of currentProject
                        end if
                    end tell
                end if
            end tell
        "#;
        
        self.execute_applescript(script)
    }
    
    fn execute_applescript(&self, script: &str) -> Result<Option<String>> {
        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()?;
        
        if output.status.success() {
            let result = String::from_utf8(output.stdout)?
                .trim()
                .to_string();
            
            if result.is_empty() || result == "missing value" {
                Ok(None)
            } else {
                Ok(Some(result))
            }
        } else {
            Ok(None) // Don't fail on AppleScript errors
        }
    }
    
    /// Get the display ID containing the app's main window
    fn get_display_for_app(&self, pid: i32) -> Option<u32> {
        use core_graphics::display::{CGGetActiveDisplayList, CGDisplayBounds, CGMainDisplayID};
        use core_graphics::window::{kCGWindowListOptionOnScreenOnly, kCGWindowListExcludeDesktopElements, 
                                     CGWindowListCopyWindowInfo, kCGNullWindowID};
        use core_foundation::array::CFArray;
        use core_foundation::dictionary::CFDictionary;
        use core_foundation::string::CFString;
        use core_foundation::number::CFNumber;
        use core_foundation::base::{CFTypeRef, TCFType};
        
        unsafe {
            // Get the window list for this app
            let options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements;
            let window_list_ref = CGWindowListCopyWindowInfo(options, kCGNullWindowID);
            
            if window_list_ref.is_null() {
                return None;
            }
            
            let window_list: CFArray<CFDictionary<CFString, CFTypeRef>> =
                TCFType::wrap_under_create_rule(window_list_ref as *const _);
            
            // Find the first window belonging to this PID
            let mut window_bounds: Option<(f64, f64, f64, f64)> = None;
            
            for i in 0..window_list.len() {
                if let Some(window_dict) = window_list.get(i) {
                    // Check if this window belongs to our PID
                    let pid_key = CFString::new("kCGWindowOwnerPID");
                    if let Some(pid_ref) = window_dict.find(&pid_key) {
                        let window_pid: CFNumber = TCFType::wrap_under_get_rule(*pid_ref as *const _);
                        if let Some(window_pid_val) = window_pid.to_i32() {
                            if window_pid_val == pid {
                                // Get the window bounds
                                let bounds_key = CFString::new("kCGWindowBounds");
                                if let Some(bounds_ref) = window_dict.find(&bounds_key) {
                                    let bounds_dict: CFDictionary<CFString, CFTypeRef> = 
                                        TCFType::wrap_under_get_rule(*bounds_ref as *const _);
                                    
                                    let x_key = CFString::new("X");
                                    let y_key = CFString::new("Y");
                                    let width_key = CFString::new("Width");
                                    let height_key = CFString::new("Height");
                                    
                                    let x = bounds_dict.find(&x_key)
                                        .map(|r| CFNumber::wrap_under_get_rule(*r as *const _))
                                        .and_then(|n| n.to_f64());
                                    let y = bounds_dict.find(&y_key)
                                        .map(|r| CFNumber::wrap_under_get_rule(*r as *const _))
                                        .and_then(|n| n.to_f64());
                                    let width = bounds_dict.find(&width_key)
                                        .map(|r| CFNumber::wrap_under_get_rule(*r as *const _))
                                        .and_then(|n| n.to_f64());
                                    let height = bounds_dict.find(&height_key)
                                        .map(|r| CFNumber::wrap_under_get_rule(*r as *const _))
                                        .and_then(|n| n.to_f64());
                                    
                                    if let (Some(x), Some(y), Some(width), Some(height)) = (x, y, width, height) {
                                        window_bounds = Some((x, y, width, height));
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            // If we found window bounds, determine which display contains it
            if let Some((x, y, width, height)) = window_bounds {
                // Get all displays
                let max_displays = 32;
                let mut display_count = 0u32;
                let mut display_list = vec![0u32; max_displays];
                
                let result = CGGetActiveDisplayList(
                    max_displays as u32,
                    display_list.as_mut_ptr(),
                    &mut display_count,
                );
                
                if result == 0 {
                    display_list.truncate(display_count as usize);
                    
                    // Calculate window center
                    let center_x = x + width / 2.0;
                    let center_y = y + height / 2.0;
                    
                    // Find which display contains the window center
                    for &display_id in &display_list {
                        let bounds = CGDisplayBounds(display_id);
                        
                        if center_x >= bounds.origin.x && center_x < bounds.origin.x + bounds.size.width &&
                           center_y >= bounds.origin.y && center_y < bounds.origin.y + bounds.size.height {
                            return Some(display_id);
                        }
                    }
                    
                    // If not found, return main display
                    return Some(CGMainDisplayID());
                }
            }
            
            None
        }
    }
    
    /// Fallback method to get app info using process list and bundle IDs
    fn get_app_info_from_process_list(&self, _app_name: &str, process_id: u32) -> Result<AppInfo> {
        // Use ps to get the process command line, which often contains bundle info
        let output = Command::new("ps")
            .arg("-p")
            .arg(process_id.to_string())
            .arg("-o")
            .arg("comm=")
            .output()?;
        
        if output.status.success() {
            let comm = String::from_utf8(output.stdout)?.trim().to_string();
            
            // Try to extract bundle ID from the executable path
            if comm.contains(".app/Contents/MacOS/") {
                if let Some(app_name) = comm.split(".app/Contents/MacOS/").next() {
                    if let Some(app_name) = app_name.split('/').last() {
                        // Derive a likely bundle ID
                        let bundle_id = if app_name.contains("Visual Studio Code") || app_name.contains("Code") {
                            "com.microsoft.VSCode".to_string()
                        } else if app_name.contains("Google Chrome") || app_name.contains("Chrome") {
                            "com.google.Chrome".to_string()
                        } else if app_name.contains("Slack") {
                            "com.tinyspeck.slackmacgap".to_string()
                        } else if app_name.contains("Safari") {
                            "com.apple.Safari".to_string()
                        } else if app_name.contains("Finder") {
                            "com.apple.finder".to_string()
                        } else {
                            format!("com.app.{}", app_name.to_lowercase().replace(" ", ""))
                        };
                        
                        let display_id = self.get_display_for_app(process_id as i32);
                        
                        return Ok(AppInfo {
                            name: app_name.to_string(),
                            bundle_id,
                            version: None,
                            window_title: None,
                            window_id: None,
                            process_id,
                            executable_path: Some(comm),
                            is_browser: false,
                            browser_type: None,
                            is_ide: false,
                            ide_type: None,
                            current_file_path: None,
                            workspace_path: None,
                            display_id,
                        });
                    }
                }
            }
        }
        
        Err(anyhow::anyhow!("Could not extract app info from process"))
    }
}

impl Default for MacOSAppDetector {
    fn default() -> Self {
        Self::new().expect("Failed to initialize MacOSAppDetector")
    }
}

// Helper trait for NSString conversion
trait NSStringExt {
    fn to_string(self) -> String;
}

impl NSStringExt for id {
    fn to_string(self) -> String {
        unsafe {
            if self == nil {
                return String::new();
            }
            
            let bytes = NSString::UTF8String(self);
            if bytes.is_null() {
                return String::new();
            }
            
            CStr::from_ptr(bytes)
                .to_string_lossy()
                .into_owned()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_app_detector_creation() {
        let detector = MacOSAppDetector::new();
        assert!(detector.is_ok());
    }
    
    #[test]
    fn test_browser_detection() {
        let detector = MacOSAppDetector::new().unwrap();
        
        let (is_browser, browser_type) = detector.detect_browser_type(
            "com.google.Chrome", 
            "Google Chrome"
        );
        assert!(is_browser);
        assert!(matches!(browser_type, Some(BrowserType::Chrome)));
        
        let (is_browser, browser_type) = detector.detect_browser_type(
            "com.apple.Safari", 
            "Safari"
        );
        assert!(is_browser);
        assert!(matches!(browser_type, Some(BrowserType::Safari)));
    }
    
    #[test]
    fn test_ide_detection() {
        let detector = MacOSAppDetector::new().unwrap();
        
        let (is_ide, ide_type) = detector.detect_ide_type(
            "com.microsoft.VSCode", 
            "Visual Studio Code"
        );
        assert!(is_ide);
        assert!(matches!(ide_type, Some(IDEType::VSCode)));
        
        let (is_ide, ide_type) = detector.detect_ide_type(
            "com.apple.dt.Xcode", 
            "Xcode"
        );
        assert!(is_ide);
        assert!(matches!(ide_type, Some(IDEType::Xcode)));
    }
    
    #[tokio::test]
    async fn test_get_active_app() {
        let mut detector = MacOSAppDetector::new().unwrap();
        let result = detector.get_active_app_info();
        
        // This test might fail in headless environments
        match result {
            Ok(app_info) => {
                assert!(!app_info.name.is_empty());
                assert!(!app_info.bundle_id.is_empty());
            }
            Err(e) => {
                println!("Note: Active app detection failed (expected in headless): {}", e);
            }
        }
    }
}