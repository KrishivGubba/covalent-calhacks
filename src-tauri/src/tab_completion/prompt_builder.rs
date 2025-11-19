use super::cache::{CachedContext, ActivityType};

pub fn build_prompt(context: &CachedContext, text: &str) -> String {
    // For FIM (Fill-in-the-Middle) mode, we just need the prefix text
    // The model will complete it naturally without examples or instructions

    // Just return the text - FIM mode handles the rest
    text.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::cache::{AppContext, Pattern, current_timestamp};
    
    #[test]
    fn test_terminal_prompt() {
        let context = CachedContext {
            app_context: AppContext {
                name: "Terminal".to_string(),
                bundle_id: "com.apple.Terminal".to_string(),
                window_title: None,
            },
            activity_type: ActivityType::Terminal {
                shell: "zsh".to_string(),
                cwd: "/Users/test/project".to_string(),
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            timestamp: current_timestamp(),
            ttl: 300,
        };
        
        let prompt = build_prompt(&context, "git co");
        assert!(prompt.contains("terminal"));
        assert!(prompt.contains("git co"));
        assert!(prompt.contains("/Users/test/project"));
    }
    
    #[test]
    fn test_browser_prompt() {
        let context = CachedContext {
            app_context: AppContext {
                name: "Chrome".to_string(),
                bundle_id: "com.google.Chrome".to_string(),
                window_title: None,
            },
            activity_type: ActivityType::Browser {
                domain: "docs.google.com".to_string(),
                page_type: "google_docs".to_string(),
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            timestamp: current_timestamp(),
            ttl: 120,
        };
        
        let prompt = build_prompt(&context, "The key innovation is");
        assert!(prompt.contains("Google Docs"));
        assert!(prompt.contains("The key innovation is"));
    }
}

