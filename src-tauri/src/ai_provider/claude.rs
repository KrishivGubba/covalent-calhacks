use anyhow::{Context, Result};
use async_trait::async_trait;
use base64::{engine::general_purpose, Engine as _};
use reqwest;
use serde::{Deserialize, Serialize};

use super::config::ProviderConfig;
use super::traits::LLMProvider;

const CLAUDE_API_URL: &str = "https://api.anthropic.com/v1/messages";
const CLAUDE_API_VERSION: &str = "2023-06-01";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaudeMessage {
    pub role: String,
    pub content: Vec<ContentBlock>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "image")]
    Image { source: ImageSource },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageSource {
    #[serde(rename = "type")]
    pub source_type: String,
    pub media_type: String,
    pub data: String,
}

#[derive(Debug, Serialize)]
struct ClaudeRequest {
    model: String,
    max_tokens: u32,
    messages: Vec<ClaudeMessage>,
}

#[derive(Debug, Deserialize)]
struct ClaudeResponse {
    content: Vec<ClaudeContentBlock>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum ClaudeContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
}

pub struct ClaudeProvider {
    client: reqwest::Client,
    api_key: String,
    model: String,
}

impl ClaudeProvider {
    pub fn new() -> Result<Self> {
        let config = ProviderConfig::from_env();
        Self::new_with_config(&config)
    }

    pub fn new_with_config(config: &ProviderConfig) -> Result<Self> {
        let api_key = config.anthropic_api_key.clone()
            .ok_or_else(|| anyhow::anyhow!("ANTHROPIC_API_KEY not available in config"))?;

        Ok(Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(config.anthropic_timeout))
                .build()?,
            api_key,
            model: config.anthropic_model.clone(),
        })
    }

    /// Internal method to call Claude API
    async fn call_claude(&self, system_prompt: &str, messages: Vec<ClaudeMessage>) -> Result<String> {
        let request = ClaudeRequest {
            model: self.model.clone(),
            max_tokens: 1024,
            messages,
        };

        let response = self
            .client
            .post(CLAUDE_API_URL)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", CLAUDE_API_VERSION)
            .header("content-type", "application/json")
            .json(&serde_json::json!({
                "model": request.model,
                "max_tokens": request.max_tokens,
                "system": system_prompt,
                "messages": request.messages,
            }))
            .send()
            .await
            .context("Failed to send request to Claude API")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "Claude API returned error status {}: {}",
                status,
                error_text
            ));
        }

        let claude_response: ClaudeResponse = response
            .json()
            .await
            .context("Failed to parse Claude API response")?;

        // Extract text from the first content block
        match claude_response.content.first() {
            Some(ClaudeContentBlock::Text { text }) => Ok(text.clone()),
            None => Err(anyhow::anyhow!("No content in Claude response")),
        }
    }

    /// Encode an image to base64
    pub fn encode_image_to_base64(image_data: &[u8]) -> String {
        general_purpose::STANDARD.encode(image_data)
    }
}

#[async_trait]
impl LLMProvider for ClaudeProvider {
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String> {
        let messages = vec![ClaudeMessage {
            role: "user".to_string(),
            content: vec![ContentBlock::Text {
                text: user_prompt.to_string(),
            }],
        }];

        self.call_claude(system_prompt, messages).await
    }

    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        screenshot_base64: &str,
    ) -> Result<String> {
        // Detect media type from base64 prefix (JPEG starts with /9j/, PNG with iVBORw0KGgo)
        let media_type = if screenshot_base64.starts_with("/9j/") {
            "image/jpeg"
        } else {
            "image/png"
        };
        
        let messages = vec![ClaudeMessage {
            role: "user".to_string(),
            content: vec![
                ContentBlock::Image {
                    source: ImageSource {
                        source_type: "base64".to_string(),
                        media_type: media_type.to_string(),
                        data: screenshot_base64.to_string(),
                    },
                },
                ContentBlock::Text {
                    text: user_prompt.to_string(),
                },
            ],
        }];

        self.call_claude(system_prompt, messages).await
    }

    fn supports_vision(&self) -> bool {
        true
    }

    fn provider_name(&self) -> &str {
        "Claude/Anthropic"
    }
}

impl Default for ClaudeProvider {
    fn default() -> Self {
        Self::new().expect("Failed to create Claude provider")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encode_image() {
        let image_data = b"test image data";
        let encoded = ClaudeProvider::encode_image_to_base64(image_data);
        assert!(!encoded.is_empty());
    }
}
