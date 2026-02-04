use anyhow::Result;
use std::sync::Arc;

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
        
        // Try to extract DOM data using tokio runtime
        // This approach is safer than spawning threads and handles async properly
        let dom_data_result = tokio::runtime::Handle::try_current()
            .and_then(|handle| {
                Ok(tokio::task::block_in_place(|| {
                    handle.block_on(bridge.extract_browser_context())
                }))
            })
            .or_else(|_| {
                // Fallback: create a temporary runtime if we're not in async context
                tokio::runtime::Runtime::new()
                    .map(|rt| rt.block_on(bridge.extract_browser_context()))
            });
        
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
                    screen_context: None, // TODO: Add OCR/DOM text extraction
                    timestamp: current_timestamp(),
                    ttl: 120, // 2 minutes for browser (pages change fast)
                    context_chain: None,
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
                    screen_context: None,
                    timestamp: current_timestamp(),
                    ttl: 120,
                    context_chain: None,
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
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 300, // 5 minutes (terminal context is stable)
            context_chain: None,
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
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 180, // 3 minutes
            context_chain: None,
        })
    }
    
    fn should_trigger(&self, text: &str) -> bool {
        // Trigger after typing 10+ characters
        text.len() >= 10
    }
}

/// Code editor adapter - for Xcode, IntelliJ, PyCharm, etc.
pub struct CodeAdapter;

impl CodeAdapter {
    pub fn new() -> Self {
        Self
    }
    
    /// Detect the programming language and file type from window title
    fn detect_code_context(&self, app_ctx: &AppContext) -> (String, String) {
        if let Some(ref window_title) = app_ctx.window_title {
            let title_lower = window_title.to_lowercase();
            
            // Try to extract file extension from window title
            if let Some(file_type) = self.extract_file_extension(&title_lower) {
                let language = self.language_from_extension(&file_type);
                return (language, file_type);
            }
            
            // Try to infer from app-specific patterns
            if app_ctx.bundle_id.contains("Xcode") {
                // Xcode often shows the file name in the title
                if title_lower.contains(".swift") {
                    return ("swift".to_string(), "swift".to_string());
                } else if title_lower.contains(".m") || title_lower.contains(".h") {
                    return ("objective-c".to_string(), "m".to_string());
                }
            } else if app_ctx.bundle_id.contains("jetbrains") || app_ctx.bundle_id.contains("intellij") {
                // JetBrains IDEs show file names
                if title_lower.contains(".java") {
                    return ("java".to_string(), "java".to_string());
                } else if title_lower.contains(".kt") {
                    return ("kotlin".to_string(), "kt".to_string());
                } else if title_lower.contains(".py") {
                    return ("python".to_string(), "py".to_string());
                }
            } else if app_ctx.bundle_id.contains("pycharm") {
                return ("python".to_string(), "py".to_string());
            }
        }
        
        // Fallback based on bundle ID
        let bundle_lower = app_ctx.bundle_id.to_lowercase();
        if bundle_lower.contains("xcode") {
            ("swift".to_string(), "swift".to_string())
        } else if bundle_lower.contains("pycharm") {
            ("python".to_string(), "py".to_string())
        } else if bundle_lower.contains("intellij") {
            ("java".to_string(), "java".to_string())
        } else if bundle_lower.contains("android") {
            ("kotlin".to_string(), "kt".to_string())
        } else {
            ("unknown".to_string(), String::new())
        }
    }
    
    /// Extract file extension from window title
    fn extract_file_extension(&self, title: &str) -> Option<String> {
        // Look for common patterns: "filename.ext" or "filename.ext - App Name"
        let words: Vec<&str> = title.split_whitespace().collect();
        
        for word in words {
            if let Some(dot_pos) = word.rfind('.') {
                let ext = &word[dot_pos + 1..];
                // Remove trailing punctuation
                let ext_clean = ext.trim_end_matches(|c: char| !c.is_alphanumeric());
                if ext_clean.len() >= 1 && ext_clean.len() <= 5 {
                    return Some(ext_clean.to_string());
                }
            }
        }
        
        None
    }
    
    /// Map file extension to programming language
    fn language_from_extension(&self, ext: &str) -> String {
        match ext {
            "rs" => "rust",
            "py" => "python",
            "js" => "javascript",
            "ts" => "typescript",
            "jsx" => "javascript",
            "tsx" => "typescript",
            "java" => "java",
            "kt" | "kts" => "kotlin",
            "swift" => "swift",
            "m" | "mm" => "objective-c",
            "h" | "hpp" => "c++",
            "c" | "cpp" | "cc" | "cxx" => "c++",
            "go" => "go",
            "rb" => "ruby",
            "php" => "php",
            "cs" => "csharp",
            "html" | "htm" => "html",
            "css" | "scss" | "sass" => "css",
            "sql" => "sql",
            "sh" | "bash" | "zsh" => "shell",
            "json" => "json",
            "xml" => "xml",
            "yaml" | "yml" => "yaml",
            "md" | "markdown" => "markdown",
            _ => "unknown",
        }
        .to_string()
    }
}

impl ContextExtractor for CodeAdapter {
    fn extract_context(&self, app_ctx: &AppContext) -> Result<CachedContext> {
        let (language, file_type) = self.detect_code_context(app_ctx);

        Ok(CachedContext {
            app_context: app_ctx.clone(),
            activity_type: ActivityType::Code {
                language,
                file_type,
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 240, // 4 minutes (code context is relatively stable)
            context_chain: None,
        })
    }
    
    fn should_trigger(&self, text: &str) -> bool {
        // Trigger after typing 3+ characters in code editors
        // Code completion should be more responsive
        text.len() >= 3
    }
}

/// Factory function to get the appropriate adapter based on app
pub fn get_adapter(app_bundle_id: &str) -> Box<dyn ContextExtractor> {
    if is_chromium_based(app_bundle_id) {
        Box::new(BrowserAdapter::new())
    } else if is_terminal(app_bundle_id) {
        Box::new(TerminalAdapter::new())
    } else if is_code_editor(app_bundle_id) {
        Box::new(CodeAdapter::new())
    } else {
        Box::new(NativeTextAdapter::new())
    }
}

pub(crate) fn is_chromium_based(bundle_id: &str) -> bool {
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

pub(crate) fn is_terminal(bundle_id: &str) -> bool {
    let bundle_lower = bundle_id.to_lowercase();
    bundle_lower.contains("terminal") ||
    bundle_lower.contains("iterm") ||
    bundle_lower.contains("warp") ||
    bundle_lower.contains("alacritty")
}

pub(crate) fn is_code_editor(bundle_id: &str) -> bool {
    let bundle_lower = bundle_id.to_lowercase();
    bundle_lower.contains("xcode") ||
    bundle_lower.contains("jetbrains") ||
    bundle_lower.contains("intellij") ||
    bundle_lower.contains("pycharm") ||
    bundle_lower.contains("android studio") ||
    bundle_lower.contains("webstorm") ||
    bundle_lower.contains("phpstorm") ||
    bundle_lower.contains("rubymine") ||
    bundle_lower.contains("clion") ||
    bundle_lower.contains("goland") ||
    bundle_lower.contains("rider")
    // Note: VSCode is already handled as chromium-based in is_chromium_based()
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
    fn test_is_code_editor() {
        assert!(is_code_editor("com.apple.dt.Xcode"));
        assert!(is_code_editor("com.jetbrains.intellij"));
        assert!(is_code_editor("com.jetbrains.pycharm"));
        assert!(!is_code_editor("com.google.Chrome"));
        assert!(!is_code_editor("com.apple.Terminal"));
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
    
    #[test]
    fn test_get_adapter_code_editor() {
        let adapter = get_adapter("com.apple.dt.Xcode");
        let ctx = AppContext {
            name: "Xcode".to_string(),
            bundle_id: "com.apple.dt.Xcode".to_string(),
            window_title: Some("MyApp.swift".to_string()),
        };
        assert!(adapter.extract_context(&ctx).is_ok());
    }
}

