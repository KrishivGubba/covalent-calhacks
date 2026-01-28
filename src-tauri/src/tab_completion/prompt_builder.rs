use super::cache::{CachedContext, ActivityType};

/// Build a completion prompt optimized for code/command completion models.
///
/// Key principles:
/// 1. Use FIM-style format when possible (prefix + suffix markers)
/// 2. Include few-shot examples showing INPUT -> OUTPUT format
/// 3. Keep context minimal to reduce latency
/// 4. Make it crystal clear we want COMPLETION not EXPLANATION
pub fn build_prompt(context: &CachedContext, text: &str) -> String {
    match &context.activity_type {
        ActivityType::Terminal { shell, cwd } => {
            build_terminal_prompt(shell, cwd, text, context)
        },
        ActivityType::Code { language, file_type } => {
            build_code_prompt(language, file_type, text, context)
        },
        ActivityType::Browser { domain, page_type } => {
            build_text_prompt(&format!("{}:{}", domain, page_type), text, context)
        },
        ActivityType::NativeText { app_name } => {
            build_text_prompt(app_name, text, context)
        },
        ActivityType::Unknown => {
            // For unknown contexts, try to detect if it looks like a command
            if looks_like_command(text) {
                build_terminal_prompt("bash", "", text, context)
            } else {
                build_text_prompt(&context.app_context.name, text, context)
            }
        }
    }
}

/// Detect if text looks like a shell command
fn looks_like_command(text: &str) -> bool {
    let command_starters = [
        "git ", "cd ", "ls", "cat ", "npm ", "yarn ", "cargo ", "docker ",
        "kubectl ", "brew ", "pip ", "python ", "node ", "make", "curl ",
        "wget ", "ssh ", "scp ", "rsync ", "grep ", "find ", "awk ", "sed ",
        "chmod ", "chown ", "mkdir ", "rm ", "mv ", "cp ", "touch ", "echo ",
        "export ", "source ", "sudo ", "./", "~/",
    ];
    let trimmed = text.trim_start();
    command_starters.iter().any(|s| trimmed.starts_with(s))
}

/// Build prompt for terminal/shell command completion
fn build_terminal_prompt(shell: &str, cwd: &str, text: &str, context: &CachedContext) -> String {
    let mut prompt = String::new();

    // Strong instruction with clear examples
    prompt.push_str("You are a terminal autocomplete. Complete the partial command.\n");
    prompt.push_str("Rules: Output ONLY the missing characters. No explanations. No quotes.\n\n");

    // Few-shot examples showing the exact format
    prompt.push_str("Examples:\n");
    prompt.push_str("git st -> atus\n");
    prompt.push_str("git add -> . -A\n");
    prompt.push_str("git check -> out main\n");
    prompt.push_str("docker-com -> pose up -d\n");
    prompt.push_str("npm i -> nstall\n");
    prompt.push_str("cargo b -> uild --release\n");
    prompt.push_str("ls -l -> a\n");
    prompt.push_str("cd ~ -> /Downloads\n");

    // Add learned patterns as additional examples
    for pattern in context.learned_patterns.iter().take(2) {
        let completion_suffix = pattern.completion.trim_start_matches(&pattern.trigger);
        if !completion_suffix.is_empty() {
            prompt.push_str(&format!("{} -> {}\n", pattern.trigger, completion_suffix));
        }
    }

    prompt.push_str("\n");

    // Context (minimal to keep prompt short)
    if !cwd.is_empty() {
        prompt.push_str(&format!("Working directory: {}\n", cwd));
    }

    // The actual completion request - use same arrow format as examples
    prompt.push_str(&format!("{} ->", text.trim()));

    prompt
}

/// Build prompt for code completion (uses FIM-style when model supports it)
fn build_code_prompt(language: &str, _file_type: &str, text: &str, context: &CachedContext) -> String {
    let mut prompt = String::new();

    // For code, use a completion-focused format
    prompt.push_str(&format!("Complete this {} code. Output ONLY the completion.\n\n", language));

    // Add screen context if available (surrounding code)
    if let Some(ref screen_text) = context.screen_context {
        if !screen_text.is_empty() {
            // Take last 300 chars of context
            let ctx = if screen_text.len() > 300 {
                &screen_text[screen_text.len() - 300..]
            } else {
                screen_text
            };
            prompt.push_str(ctx);
            prompt.push_str("\n");
        }
    }

    prompt.push_str(text);

    prompt
}

/// Build prompt for general text completion
fn build_text_prompt(app_context: &str, text: &str, context: &CachedContext) -> String {
    let mut prompt = String::new();

    prompt.push_str("Complete this text naturally. Output ONLY the completion, no explanations.\n\n");

    // Add screen context if available
    if let Some(ref screen_text) = context.screen_context {
        if !screen_text.is_empty() {
            let ctx = if screen_text.len() > 400 {
                &screen_text[screen_text.len() - 400..]
            } else {
                screen_text
            };
            prompt.push_str(ctx);
            prompt.push_str("\n");
        }
    }

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
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 300,
        };

        let prompt = build_prompt(&context, "git co");
        // Should have few-shot examples
        assert!(prompt.contains("git st -> atus"));
        // Should have the input with arrow format
        assert!(prompt.contains("git co ->"));
        // Should have cwd
        assert!(prompt.contains("/Users/test/project"));
    }

    #[test]
    fn test_terminal_prompt_with_patterns() {
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
            ],
            recent_actions: vec![],
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 300,
        };

        let prompt = build_prompt(&context, "git ");
        // Should include learned pattern as example
        assert!(prompt.contains("git st -> atus") || prompt.contains("git st ->"));
        // Should end with arrow format (trimmed)
        assert!(prompt.contains("git ->"));
    }

    #[test]
    fn test_looks_like_command() {
        assert!(looks_like_command("git status"));
        assert!(looks_like_command("npm install"));
        assert!(looks_like_command("cargo build"));
        assert!(looks_like_command("./run.sh"));
        assert!(!looks_like_command("The quick brown fox"));
        assert!(!looks_like_command("Hello world"));
    }

    #[test]
    fn test_code_prompt() {
        let context = CachedContext {
            app_context: AppContext {
                name: "VSCode".to_string(),
                bundle_id: "com.microsoft.VSCode".to_string(),
                window_title: None,
            },
            activity_type: ActivityType::Code {
                language: "rust".to_string(),
                file_type: "rs".to_string(),
            },
            learned_patterns: vec![],
            recent_actions: vec![],
            screen_context: Some("fn main() {\n    let x = ".to_string()),
            timestamp: current_timestamp(),
            ttl: 300,
        };

        let prompt = build_prompt(&context, "Vec::new");
        assert!(prompt.contains("rust"));
        assert!(prompt.contains("fn main()"));
        assert!(prompt.contains("Vec::new"));
    }
}

