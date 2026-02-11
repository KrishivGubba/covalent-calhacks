use anyhow::{Context, Result};
use async_trait::async_trait;
use reqwest;
use serde::{Deserialize, Serialize};

use super::config::ProviderConfig;
use super::traits::LLMProvider;

#[derive(Debug, Serialize)]
struct OllamaRequest {
    model: String,
    prompt: String,
    stream: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    images: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    options: Option<OllamaOptions>,
}

#[derive(Debug, Serialize)]
struct OllamaOptions {
    num_predict: usize,
    temperature: f32,
    top_p: f32,
    top_k: u32,
    repeat_penalty: f32,
}

#[derive(Debug, Deserialize)]
struct OllamaResponse {
    response: String,
}

pub struct OllamaProvider {
    client: reqwest::Client,
    base_url: String,
    model: String,
}

impl OllamaProvider {
    pub fn new() -> Result<Self> {
        let config = ProviderConfig::from_env();
        Self::new_with_config(&config)
    }

    pub fn new_with_config(config: &ProviderConfig) -> Result<Self> {
        Ok(Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(config.ollama_timeout))
                .build()?,
            base_url: config.ollama_base_url.clone(),
            model: config.ollama_model.clone(),
        })
    }

    /// Internal method to call Ollama API
    async fn call_ollama(&self, prompt: String, images: Option<Vec<String>>) -> Result<String> {
        let request = OllamaRequest {
            model: self.model.clone(),
            prompt,
            stream: false,
            images,
            options: Some(OllamaOptions {
                num_predict: 512,
                temperature: 0.7,
                top_p: 0.95,
                top_k: 40,
                repeat_penalty: 1.1,
            }),
        };

        let url = format!("{}/api/generate", self.base_url);
        
        let response = self
            .client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send request to Ollama API")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "Ollama API returned error status {}: {}",
                status,
                error_text
            ));
        }

        let ollama_response: OllamaResponse = response
            .json()
            .await
            .context("Failed to parse Ollama API response")?;

        Ok(ollama_response.response.trim().to_string())
    }
}

#[async_trait]
impl LLMProvider for OllamaProvider {
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String> {
        // Combine system and user prompts for Ollama
        let combined_prompt = format!("{}\n\n{}", system_prompt, user_prompt);
        self.call_ollama(combined_prompt, None).await
    }

    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        image_base64: &str,
    ) -> Result<String> {
        // Combine system and user prompts
        let combined_prompt = format!("{}\n\n{}", system_prompt, user_prompt);
        
        // Ollama expects images as base64 strings in an array
        let images = vec![image_base64.to_string()];
        
        self.call_ollama(combined_prompt, Some(images)).await
    }

    fn supports_vision(&self) -> bool {
        // Some Ollama models support vision (e.g., llava, bakllava)
        self.model.contains("llava") || self.model.contains("vision")
    }

    fn provider_name(&self) -> &str {
        "Ollama"
    }
}

impl Default for OllamaProvider {
    fn default() -> Self {
        Self::new().expect("Failed to create Ollama provider")
    }
}
