use super::cache::{CachedContext, ActivityType};

pub fn build_prompt(context: &CachedContext, text: &str) -> String {
    // Build context-aware prompts based on activity type
    
    // Add few-shot examples from learned patterns if available
    let examples = if !context.learned_patterns.is_empty() {
        context.learned_patterns.iter()
            .take(3)
            .map(|p| format!("Input: {}\nOutput: {}", p.trigger, p.completion))
            .collect::<Vec<_>>()
            .join("\n\n")
    } else {
        String::new()
    };
    
    let examples_section = if !examples.is_empty() {
        format!("\nExamples:\n{}\n", examples)
    } else {
        String::new()
    };
    
    match &context.activity_type {
        ActivityType::Terminal { cwd, .. } => {
            let cwd_info = if !cwd.is_empty() {
                format!("Working directory: {}\n", cwd)
            } else {
                String::new()
            };
            
            format!(
                "<|system|>You are a terminal command completion assistant.
{}{}Complete this command concisely (one line only):
<|user|>{}
<|assistant|>",
                cwd_info, examples_section, text
            )
        }
        
        ActivityType::Browser { page_type, .. } => {
            match page_type.as_str() {
                "google_docs" => {
                    format!(
                        "<|system|>You are a writing assistant for Google Docs.
{}Continue this text naturally (1-2 sentences):
<|user|>{}
<|assistant|>",
                        examples_section, text
                    )
                }
                "whatsapp" => {
                    format!(
                        "<|system|>You are a messaging assistant for WhatsApp.
{}Complete this message naturally and briefly:
<|user|>{}
<|assistant|>",
                        examples_section, text
                    )
                }
                "notion" => {
                    format!(
                        "<|system|>You are a writing assistant for Notion.
{}Continue this text professionally:
<|user|>{}
<|assistant|>",
                        examples_section, text
                    )
                }
                _ => {
                    format!(
                        "<|system|>Complete this text naturally:
{}
<|user|>{}
<|assistant|>",
                        examples_section, text
                    )
                }
            }
        }
        
        ActivityType::Code { language, .. } => {
            let lang_info = if !language.is_empty() && language != "unknown" {
                format!("Language: {}\n", language)
            } else {
                String::new()
            };
            
            format!(
                "<|system|>You are a code completion assistant.
{}{}Complete this code concisely:
<|user|>
```
{}
```
<|assistant|>",
                lang_info, examples_section, text
            )
        }
        
        ActivityType::NativeText { .. } => {
            format!(
                "<|system|>Complete this text naturally:
{}
<|user|>{}
<|assistant|>",
                examples_section, text
            )
        }
        
        ActivityType::Unknown => {
            format!(
                "<|system|>Complete this text:
<|user|>{}
<|assistant|>",
                text
            )
        }
    }
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

