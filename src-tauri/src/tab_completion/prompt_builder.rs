use super::cache::{CachedContext, ActivityType};

pub fn build_prompt(context: &CachedContext, text: &str) -> String {
    // Build a context-aware prompt that helps the model understand what to complete
    let mut prompt = String::new();
    
    // Add activity-specific context
    match &context.activity_type {
        ActivityType::Terminal { shell, cwd } => {
            prompt.push_str(&format!("# Terminal context ({})\n", shell));
            if !cwd.is_empty() {
                prompt.push_str(&format!("# Working directory: {}\n", cwd));
            }
            prompt.push_str("# Complete this shell command:\n");
        },
        ActivityType::Browser { domain, page_type } => {
            if page_type == "google_docs" {
                prompt.push_str("# Writing in Google Docs\n");
            } else {
                prompt.push_str(&format!("# Browser: {} ({})\n", domain, page_type));
            }
            prompt.push_str("# Complete this text:\n");
        },
        ActivityType::Code { language, file_type } => {
            prompt.push_str(&format!("# Code editor - {} ({})\n", language, file_type));
            prompt.push_str("# Complete this code:\n");
        },
        ActivityType::NativeText { app_name } => {
            prompt.push_str(&format!("# Text editor: {}\n", app_name));
            prompt.push_str("# Complete this text:\n");
        },
        ActivityType::Unknown => {
            prompt.push_str(&format!("# App: {}\n", context.app_context.name));
            prompt.push_str("# Complete this:\n");
        }
    }
    
    // Add window title if available (can provide additional context)
    if let Some(title) = &context.app_context.window_title {
        if !title.is_empty() {
            prompt.push_str(&format!("# Window: {}\n", title));
        }
    }
    
    // Add learned patterns if available
    if !context.learned_patterns.is_empty() {
        prompt.push_str("\n# Common patterns:\n");
        for pattern in context.learned_patterns.iter().take(3) {
            prompt.push_str(&format!("# - {} → {}\n", pattern.trigger, pattern.completion));
        }
    }
    
    // Add recent actions for additional context
    if !context.recent_actions.is_empty() {
        prompt.push_str("\n# Recent actions:\n");
        for action in context.recent_actions.iter().take(3) {
            prompt.push_str(&format!("# - {}\n", action));
        }
    }
    
    // Add screen/document context if available (most important for quality)
    if let Some(ref screen_text) = context.screen_context {
        if !screen_text.is_empty() {
            prompt.push_str("\n# Surrounding document context:\n");
            // Limit to last 500 chars to avoid overwhelming the model
            let context_snippet = if screen_text.len() > 500 {
                &screen_text[screen_text.len() - 500..]
            } else {
                screen_text
            };
            prompt.push_str(context_snippet);
            prompt.push_str("\n\n# Continue from here:\n");
        }
    }
    
    // Add separator and the actual text to complete
    prompt.push_str("\n");
    prompt.push_str(text);
    
    prompt
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
        // Check for key context elements
        assert!(prompt.contains("Terminal context") || prompt.contains("shell command"));
        assert!(prompt.contains("git co"));
        assert!(prompt.contains("/Users/test/project"));
        // Verify it starts with a comment (context info)
        assert!(prompt.starts_with("#"));
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
    
    #[test]
    fn test_prompt_with_learned_patterns() {
        let context = CachedContext {
            app_context: AppContext {
                name: "Terminal".to_string(),
                bundle_id: "com.apple.Terminal".to_string(),
                window_title: None,
            },
            activity_type: ActivityType::Terminal {
                shell: "bash".to_string(),
                cwd: "/home/user".to_string(),
            },
            learned_patterns: vec![
                Pattern {
                    trigger: "git st".to_string(),
                    completion: "git status".to_string(),
                    confidence: 0.95,
                    use_count: 42,
                },
                Pattern {
                    trigger: "git co".to_string(),
                    completion: "git commit -m \"".to_string(),
                    confidence: 0.88,
                    use_count: 35,
                },
            ],
            recent_actions: vec![
                "git add .".to_string(),
                "npm test".to_string(),
            ],
            timestamp: current_timestamp(),
            ttl: 300,
        };
        
        let prompt = build_prompt(&context, "git ");
        
        // Should include context
        assert!(prompt.contains("bash"));
        assert!(prompt.contains("/home/user"));
        
        // Should include learned patterns
        assert!(prompt.contains("Common patterns"));
        assert!(prompt.contains("git st → git status"));
        assert!(prompt.contains("git co → git commit"));
        
        // Should include recent actions
        assert!(prompt.contains("Recent actions"));
        assert!(prompt.contains("git add ."));
        assert!(prompt.contains("npm test"));
        
        // Should end with the actual text
        assert!(prompt.ends_with("git "));
    }
}

