use anyhow::Result;
use std::time::Instant;
use serde::{Deserialize, Serialize};

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
        // Try to detect available model backend
        // For now, use Ollama as fallback
        Ok(Self {
            model_type: ModelType::Ollama {
                base_url: "http://localhost:11434".to_string(),
                model: "qwen2.5-coder:3b".to_string(),
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
                "prompt": prompt,
                "suffix": "",  // Enable Fill-in-the-Middle mode for completion
                "stream": false,
                "keep_alive": "5m",  // Keep model loaded for 5 minutes to avoid reload delays
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.2,   // Slightly higher for FIM mode
                    "top_p": 0.9,         // Standard for FIM
                    "top_k": 50,          // Standard for FIM
                    "stop": ["\n"],       // Only stop at newline for FIM
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
    /// FIM mode should give cleaner output, but we still validate
    fn clean_prediction(text: &str) -> String {
        let text = text.trim();

        // FIM mode outputs completion directly, so minimal processing needed

        // Extract first line only (completions should be single line)
        let result = text.lines().next().unwrap_or(text);

        // Remove any backticks or special characters
        let result = result.trim().trim_matches('`').trim();

        // If it starts with explanation words, reject it
        if result.starts_with("It ") ||
           result.starts_with("This ") ||
           result.starts_with("You ") ||
           result.starts_with("The ") {
            return String::new();
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

