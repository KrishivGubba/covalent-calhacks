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
                "stream": false,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.3,
                    "top_p": 0.9,
                }
            }))
            .timeout(std::time::Duration::from_millis(500))
            .send()?;
        
        let result: serde_json::Value = response.json()?;
        let text = result["response"]
            .as_str()
            .unwrap_or("")
            .to_string();
        
        Ok(text)
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

