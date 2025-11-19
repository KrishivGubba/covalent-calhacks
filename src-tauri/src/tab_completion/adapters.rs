use anyhow::Result;
use std::sync::Arc;
use tokio::runtime::Handle;

use super::cache::{CachedContext, AppContext, ActivityType, current_timestamp};
use crate::screen_context::chromium_bridge::ChromiumBridge;

pub trait ContextExtractor: Send + Sync {
    fn extract_context(&self, app_ctx: &AppContext) -> Result<CachedContext>;
    fn should_trigger(&self, text: &str) -> bool;
}

/// Browser adapter - uses ChromiumBridge for all Chromium-based and Electron apps
pub struct BrowserAdapter {
    chromium_bridge: Arc<ChromiumBridge>,
}

impl BrowserAdapter {
    pub fn new() -> Self {
        Self {
            chromium_bridge: Arc::new(ChromiumBridge::new()),
        }
    }
    
    pub fn with_debugging_port(port: u16) -> Self {
        Self {
            chromium_bridge: Arc::new(ChromiumBridge::new().with_debugging_port(port)),
        }
    }
}

impl ContextExtractor for BrowserAdapter {
    fn extract_context(&self, app_ctx: &AppContext) -> Result<CachedContext> {
        // Use existing ChromiumBridge to extract browser DOM context
        let bridge = self.chromium_bridge.clone();
        
        // Run async operation in blocking context
        let dom_data_result = std::thread::spawn(move || {
            // Try to get existing tokio runtime, or create a temporary one
            match Handle::try_current() {
                Ok(handle) => {
                    tokio::task::block_in_place(|| {
                        handle.block_on(bridge.extract_browser_context())
                    })
                }
                Err(_) => {
                    // Create a temporary runtime if no runtime exists
                    let rt = tokio::runtime::Runtime::new().unwrap();
                    rt.block_on(bridge.extract_browser_context())
                }
            }
        }).join();
        
        match dom_data_result {
            Ok(Ok(dom_data)) => {
                // Successfully extracted DOM data
                let page_type = classify_page_from_url(&dom_data.url);
                let domain = extract_domain(&dom_data.url);
                
                // Extract recent actions from buttons and links
                let mut recent_actions = dom_data.buttons.clone();
                recent_actions.extend(dom_data.links.iter().map(|l| l.text.clone()));
                recent_actions.truncate(10); // Keep last 10 actions
                
                Ok(CachedContext {
                    app_context: app_ctx.clone(),
                    activity_type: ActivityType::Browser {
                        domain,
                        page_type,
                    },
                    learned_patterns: vec![],
                    recent_actions,
                    timestamp: current_timestamp(),
                    ttl: 120, // 2 minutes for browser (pages change fast)
                })
            }
            Ok(Err(_)) | Err(_) => {
                // Fallback to basic context if ChromiumBridge fails
                let page_type = classify_page_from_bundle(&app_ctx.bundle_id);
                
                Ok(CachedContext {
                    app_context: app_ctx.clone(),
                    activity_type: ActivityType::Browser {
                        domain: String::new(),
                        page_type,
                    },
                    learned_patterns: vec![],
                    recent_actions: vec![],
                    timestamp: current_timestamp(),
                    ttl: 120,
                })
            }
        }
    }
    
    fn should_trigger(&self, text: &str) -> bool {
        // Trigger after typing 5+ characters
        text.len() >= 5
    }
}

fn extract_domain(url: &str) -> String {
    if let Ok(parsed_url) = url::Url::parse(url) {
        parsed_url.host_str().unwrap_or("").to_string()
    } else {
        String::new()
    }
}

fn classify_page_from_url(url: &str) -> String {
    let url_lower = url.to_lowercase();
    
    if url_lower.contains("docs.google.com") {
        "google_docs".to_string()
    } else if url_lower.contains("web.whatsapp.com") {
        "whatsapp".to_string()
    } else if url_lower.contains("notion.so") {
        "notion".to_string()
    } else if url_lower.contains("slack.com") {
        "slack".to_string()
    } else if url_lower.contains("discord.com") {
        "discord".to_string()
    } else if url_lower.contains("github.com") {
        "github".to_string()
    } else {
        "generic_web".to_string()
    }
}

/// Terminal adapter - for Terminal, iTerm, etc.
pub struct TerminalAdapter;

impl TerminalAdapter {
    pub fn new() -> Self {
        Self
    }
    
    fn get_terminal_cwd(&self) -> Option<String> {
        // Try to get CWD from Terminal.app using AppleScript
        let terminal_script = r#"
            tell application "Terminal"
                try
                    do shell script "lsof -a -p " & (do shell script "pgrep -n bash || pgrep -n zsh || pgrep -n fish") & " -d cwd -Fn | grep cwd | cut -c 5-"
                on error
                    return ""
                end try
            end tell
        "#;
        
        // Try iTerm2 if Terminal fails
        let iterm_script = r#"
            tell application "iTerm"
                try
                    tell current session of current window
                        get variable "session.path"
                    end tell
                on error
                    return ""
                end try
            end tell
        "#;
        
        // Try Terminal first
        if let Ok(cwd) = execute_applescript_for_output(terminal_script) {
            if !cwd.trim().is_empty() {
                return Some(cwd.trim().to_string());
            }
        }
        
        // Try iTerm
        if let Ok(cwd) = execute_applescript_for_output(iterm_script) {
            if !cwd.trim().is_empty() {
                return Some(cwd.trim().to_string());
            }
        }
        
        None
    }
    
    fn detect_shell(&self) -> String {
        // Try to detect the current shell
        if let Ok(shell) = std::env::var("SHELL") {
            if let Some(shell_name) = shell.split('/').last() {
                return shell_name.to_string();
            }
        }
        "zsh".to_string() // Default to zsh on macOS
    }
}

impl ContextExtractor for TerminalAdapter {
    fn extract_context(&self, app_ctx: &AppContext) -> Result<CachedContext> {
        let cwd = self.get_terminal_cwd().unwrap_or_else(|| {
            // Fallback to home directory
            std::env::var("HOME").unwrap_or_else(|_| "~".to_string())
        });
        
        let shell = self.detect_shell();
        
        Ok(CachedContext {
            app_context: app_ctx.clone(),
            activity_type: ActivityType::Terminal {
                shell,
                cwd,
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            timestamp: current_timestamp(),
            ttl: 300, // 5 minutes (terminal context is stable)
        })
    }
    
    fn should_trigger(&self, text: &str) -> bool {
        // Trigger after typing 3+ characters in terminal
        text.len() >= 3 && !text.ends_with('\n')
    }
}

fn execute_applescript_for_output(script: &str) -> Result<String> {
    let result = std::process::Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()?;
    
    if result.status.success() {
        Ok(String::from_utf8_lossy(&result.stdout).to_string())
    } else {
        Err(anyhow::anyhow!("AppleScript failed"))
    }
}

/// Native text adapter - for Notes, TextEdit, and other native text apps
pub struct NativeTextAdapter;

impl NativeTextAdapter {
    pub fn new() -> Self {
        Self
    }
}

impl ContextExtractor for NativeTextAdapter {
    fn extract_context(&self, app_ctx: &AppContext) -> Result<CachedContext> {
        Ok(CachedContext {
            app_context: app_ctx.clone(),
            activity_type: ActivityType::NativeText {
                app_name: app_ctx.name.clone(),
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            timestamp: current_timestamp(),
            ttl: 180, // 3 minutes
        })
    }
    
    fn should_trigger(&self, text: &str) -> bool {
        // Trigger after typing 10+ characters
        text.len() >= 10
    }
}

/// Factory function to get the appropriate adapter based on app
pub fn get_adapter(app_bundle_id: &str) -> Box<dyn ContextExtractor> {
    if is_chromium_based(app_bundle_id) {
        Box::new(BrowserAdapter::new())
    } else if is_terminal(app_bundle_id) {
        Box::new(TerminalAdapter::new())
    } else {
        Box::new(NativeTextAdapter::new())
    }
}

fn is_chromium_based(bundle_id: &str) -> bool {
    let bundle_lower = bundle_id.to_lowercase();
    bundle_lower.contains("chrome") ||
    bundle_lower.contains("electron") ||
    bundle_lower.contains("brave") ||
    bundle_lower.contains("edge") ||
    bundle_lower.contains("notion") ||
    bundle_lower.contains("slack") ||
    bundle_lower.contains("discord") ||
    bundle_lower.contains("spotify") ||
    bundle_lower.contains("vscode")
}

fn is_terminal(bundle_id: &str) -> bool {
    let bundle_lower = bundle_id.to_lowercase();
    bundle_lower.contains("terminal") ||
    bundle_lower.contains("iterm") ||
    bundle_lower.contains("warp") ||
    bundle_lower.contains("alacritty")
}

fn classify_page_from_bundle(bundle_id: &str) -> String {
    let bundle_lower = bundle_id.to_lowercase();
    
    if bundle_lower.contains("notion") {
        "notion".to_string()
    } else if bundle_lower.contains("slack") {
        "slack".to_string()
    } else if bundle_lower.contains("discord") {
        "discord".to_string()
    } else if bundle_lower.contains("vscode") || bundle_lower.contains("code") {
        "vscode".to_string()
    } else {
        "generic_web".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_is_chromium_based() {
        assert!(is_chromium_based("com.google.Chrome"));
        assert!(is_chromium_based("com.notion.app"));
        assert!(is_chromium_based("com.tinyspeck.slackmacgap"));
        assert!(!is_chromium_based("com.apple.Terminal"));
    }
    
    #[test]
    fn test_is_terminal() {
        assert!(is_terminal("com.apple.Terminal"));
        assert!(is_terminal("com.googlecode.iterm2"));
        assert!(!is_terminal("com.google.Chrome"));
    }
    
    #[test]
    fn test_get_adapter() {
        let adapter = get_adapter("com.google.Chrome");
        let ctx = AppContext {
            name: "Chrome".to_string(),
            bundle_id: "com.google.Chrome".to_string(),
            window_title: None,
        };
        assert!(adapter.extract_context(&ctx).is_ok());
    }
}

