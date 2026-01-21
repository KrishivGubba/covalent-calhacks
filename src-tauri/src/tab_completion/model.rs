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
    
    /// Synchronous inference - no async overhead!
    pub fn predict_sync(&self, prompt: &str, max_tokens: usize) -> Result<String> {
        let start = Instant::now();
        
        let result = match &self.model_type {
            ModelType::Ollama { base_url, model } => {
                self.predict_ollama(base_url, model, prompt, max_tokens)
            }
        }?;
        
        let elapsed = start.elapsed().as_millis();
        println!("🤖 Model inference: {}ms", elapsed);
        
        Ok(result)
    }
    
    fn predict_ollama(&self, base_url: &str, model: &str, prompt: &str, max_tokens: usize) -> Result<String> {
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

        // Find the first non-empty line
        let result = text
            .lines()
            .find(|line| !line.trim().is_empty())
            .unwrap_or("")
            .trim();

        // Remove any backticks or special characters
        let result = result.trim_matches('`').trim();

        // Reject if it's empty after cleaning
        if result.is_empty() {
            return String::new();
        }

        // Reject if it starts with conversational phrases
        let conversational_starts = [
            "It ", "This ", "You ", "I ",
            "Let me ", "I'll ", "I can ",
            "Complete this", "Only output",
            "The ", "Here ", "Sure",
            "Here's", "Certainly", "Of course",
        ];

        for start in &conversational_starts {
            if result.starts_with(start) {
                return String::new();
            }
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

