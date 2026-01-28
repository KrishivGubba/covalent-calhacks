use anyhow::Result;
use std::time::Instant;
use serde::{Deserialize, Serialize};
use crate::ai_provider::ProviderConfig;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelResponse {
    pub text: String,
    pub inference_time_ms: u64,
}

/// Model invoker that can use either llama.cpp (fast) or Ollama (fallback)
pub struct ModelInvoker {
    model_type: ModelType,
}

enum ModelType {
    Ollama {
        base_url: String,
        model: String,
    },
    // LlamaCpp will be added when model is downloaded
    // LlamaCpp {
    //     context: LlamaContext,
    // }
}

impl ModelInvoker {
    pub fn new() -> Result<Self> {
        // Load configuration from ai_provider
        let config = ProviderConfig::from_env();

        Ok(Self {
            model_type: ModelType::Ollama {
                base_url: config.ollama_base_url,
                model: config.ollama_model,
            },
        })
    }

    /// Synchronous inference with automatic Haiku fallback
    /// Tries local Ollama first, falls back to Claude Haiku if prediction fails sanity check
    pub fn predict_with_fallback(&self, prompt: &str, max_tokens: usize) -> Result<String> {
        let start = Instant::now();

        // 1. Try local Ollama first
        let local_result = match &self.model_type {
            ModelType::Ollama { base_url, model } => {
                self.predict_ollama_internal(base_url, model, prompt, max_tokens)
            }
        };

        if let Ok(ref pred) = local_result {
            if !pred.is_empty() && Self::passes_sanity_check(pred) {
                let elapsed = start.elapsed().as_millis();
                println!("✅ Local prediction passed sanity check ({}ms): {}", elapsed, &pred[..pred.len().min(50)]);
                return local_result;
            }
            println!("⚠️  Local prediction failed sanity check: '{}'", &pred[..pred.len().min(50)]);
        } else if let Err(ref e) = local_result {
            println!("⚠️  Local Ollama failed: {}", e);
        }

        // 2. Fallback to Claude Haiku
        println!("🔄 Falling back to Claude Haiku...");
        match self.predict_haiku(prompt, max_tokens) {
            Ok(pred) => {
                let elapsed = start.elapsed().as_millis();
                println!("✅ Haiku prediction ({}ms): {}", elapsed, &pred[..pred.len().min(50)]);
                Ok(pred)
            }
            Err(e) => {
                println!("❌ Haiku fallback also failed: {}", e);
                // Return original local result if Haiku fails (might be better than nothing)
                local_result
            }
        }
    }

    /// Call Claude Haiku API for fast, accurate completions
    fn predict_haiku(&self, prompt: &str, max_tokens: usize) -> Result<String> {
        let api_key = std::env::var("ANTHROPIC_API_KEY")
            .or_else(|_| std::env::var("CLAUDE_API_KEY"))
            .map_err(|_| anyhow::anyhow!("ANTHROPIC_API_KEY or CLAUDE_API_KEY not set"))?;

        let client = reqwest::blocking::Client::new();

        // Use a completion-focused system prompt for Haiku
        let system_prompt = "You are a command-line autocomplete assistant. Output ONLY the completion text that should be appended to the user's input. No explanations, no quotes, no markdown. Just the raw completion.";

        let response = client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&serde_json::json!({
                "model": "claude-3-haiku-20240307",
                "max_tokens": max_tokens.max(50),  // At least 50 tokens for reasonable completions
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}]
            }))
            .timeout(std::time::Duration::from_millis(3000))
            .send()?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().unwrap_or_default();
            return Err(anyhow::anyhow!("Haiku API error {}: {}", status, error_text));
        }

        let result: serde_json::Value = response.json()?;
        let text = result["content"][0]["text"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(Self::clean_prediction(&text))
    }

    /// Check if prediction passes sanity checks (not an explanation, reasonable length, etc.)
    fn passes_sanity_check(pred: &str) -> bool {
        // Empty or too short
        if pred.len() < 1 {
            return false;
        }

        // Too long for a completion
        if pred.len() > 150 {
            return false;
        }

        // Check for explanation patterns (already filtered by clean_prediction, but double-check)
        let bad_patterns = [
            "is a", "is the", "are ", "The ", "This ",
            "will ", "would ", "should ", "can be",
            "refers to", "means ", "used to", "allows you",
            "command that", "system for",
        ];

        let pred_lower = pred.to_lowercase();
        for pattern in bad_patterns {
            if pred_lower.contains(pattern) {
                return false;
            }
        }

        true
    }

    /// Synchronous inference - no async overhead!
    pub fn predict_sync(&self, prompt: &str, max_tokens: usize) -> Result<String> {
        let start = Instant::now();

        let result = match &self.model_type {
            ModelType::Ollama { base_url, model } => {
                self.predict_ollama_internal(base_url, model, prompt, max_tokens)
            }
        }?;

        let elapsed = start.elapsed().as_millis();
        println!("🤖 Model inference: {}ms", elapsed);

        Ok(result)
    }

    fn predict_ollama_internal(&self, base_url: &str, model: &str, prompt: &str, max_tokens: usize) -> Result<String> {
        // Use blocking reqwest for sync call
        let client = reqwest::blocking::Client::new();

        let response = client
            .post(format!("{}/api/generate", base_url))
            .json(&serde_json::json!({
                "model": model,
                "prompt": prompt,  // Use raw prompt without instructions
                "stream": false,
                "keep_alive": "5m",  // Keep model loaded for 5 minutes to avoid reload delays
                "raw": true,  // Use raw mode to avoid chat template - this is key!
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "top_k": 40,
                    "repeat_penalty": 1.1,
                    // Don't use stop tokens - we'll extract the first line in post-processing
                }
            }))
            .timeout(std::time::Duration::from_millis(10000))  // Increased to 10s to handle concurrent request queuing
            .send()?;

        let result: serde_json::Value = response.json()?;
        let raw_text = result["response"]
            .as_str()
            .unwrap_or("")
            .to_string();

        // Post-process: Clean up the output
        let cleaned = Self::clean_prediction(&raw_text);

        Ok(cleaned)
    }

    /// Clean up model output to extract just the completion
    fn clean_prediction(text: &str) -> String {
        // Trim whitespace including leading/trailing newlines
        let text = text.trim();

        // If empty, return early
        if text.is_empty() {
            return String::new();
        }

        // Take only the first line (completions should be single-line or we take first)
        let first_line = text
            .lines()
            .find(|line| !line.trim().is_empty())
            .unwrap_or("")
            .trim();

        // Remove any backticks, quotes, or markdown formatting
        let result = first_line
            .trim_matches('`')
            .trim_matches('"')
            .trim_matches('\'')
            .trim();

        // If the model output includes "->", take what's after it
        // (handles cases where model echoes our format)
        let result = if let Some(idx) = result.find("->") {
            result[idx + 2..].trim()
        } else {
            result
        };

        // Reject if empty
        if result.is_empty() {
            return String::new();
        }

        // Reject if it starts with conversational/explanatory phrases
        let bad_starts = [
            "It ", "This ", "You ", "I ",
            "Let me", "I'll ", "I can",
            "Complete", "Output", "Here",
            "The ", "Sure", "Certainly",
            "Of course", "Based on",
            "In ", "For ", "To ",
            "#", "//", "/*",  // Comments indicating explanation
        ];

        for start in &bad_starts {
            if result.starts_with(start) {
                return String::new();
            }
        }

        // Reject if it looks like a full sentence explanation (contains common verbs)
        let explanation_markers = [
            " is ", " are ", " will ", " would ", " should ",
            " shows ", " displays ", " runs ", " executes ",
            " command ", " because ", " which ",
        ];

        let result_lower = result.to_lowercase();
        for marker in &explanation_markers {
            if result_lower.contains(marker) {
                return String::new();
            }
        }

        // Limit length - completions shouldn't be super long
        if result.len() > 100 {
            // Take first 100 chars, try to break at word boundary
            let truncated = &result[..100];
            if let Some(last_space) = truncated.rfind(' ') {
                return truncated[..last_space].to_string();
            }
            return truncated.to_string();
        }

        result.to_string()
    }
}

impl Default for ModelInvoker {
    fn default() -> Self {
        Self::new().expect("Failed to create ModelInvoker")
    }
}

// Global model instance - will be lazy loaded
lazy_static::lazy_static! {
    pub static ref MODEL: ModelInvoker = ModelInvoker::new()
        .expect("Failed to initialize model");
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_model_creation() {
        let model = ModelInvoker::new();
        assert!(model.is_ok());
    }
}

