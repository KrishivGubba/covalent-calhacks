use anyhow::{Context, Result};
use async_trait::async_trait;
use reqwest;
use serde::{Deserialize, Serialize};

use super::config::ProviderConfig;
use super::traits::LLMProvider;

const OPENAI_API_URL: &str = "https://api.openai.com/v1/chat/completions";

#[derive(Debug, Clone, Serialize)]
struct OpenAIMessage {
    role: String,
    content: Vec<OpenAIContent>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type")]
enum OpenAIContent {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "image_url")]
    ImageUrl { image_url: ImageUrl },
}

#[derive(Debug, Clone, Serialize)]
struct ImageUrl {
    url: String,
}

#[derive(Debug, Serialize)]
struct OpenAIRequest {
    model: String,
    messages: Vec<OpenAIMessage>,
    max_completion_tokens: u32,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponse {
    choices: Vec<OpenAIChoice>,
}

#[derive(Debug, Deserialize)]
struct OpenAIChoice {
    message: OpenAIResponseMessage,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponseMessage {
    content: String,
}

pub struct OpenAIProvider {
    client: reqwest::Client,
    api_key: String,
    model: String,
}

impl OpenAIProvider {
    pub fn new() -> Result<Self> {
        let config = ProviderConfig::from_env();
        Self::new_with_config(&config)
    }

    pub fn new_with_config(config: &ProviderConfig) -> Result<Self> {
        let api_key = config.openai_api_key.clone()
            .ok_or_else(|| anyhow::anyhow!("OPENAI_API_KEY not available in config"))?;

        Ok(Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(config.openai_timeout))
                .build()?,
            api_key,
            model: config.openai_model.clone(),
        })
    }

    /// Internal method to call OpenAI API
    async fn call_openai(&self, messages: Vec<OpenAIMessage>) -> Result<String> {
        let request = OpenAIRequest {
            model: self.model.clone(),
            messages,
            max_completion_tokens: 1024,
        };

        let response = self
            .client
            .post(OPENAI_API_URL)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to OpenAI API")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "OpenAI API returned error status {}: {}",
                status,
                error_text
            ));
        }

        let openai_response: OpenAIResponse = response
            .json()
            .await
            .context("Failed to parse OpenAI API response")?;

        // Extract text from the first choice
        openai_response
            .choices
            .first()
            .map(|choice| choice.message.content.clone())
            .ok_or_else(|| anyhow::anyhow!("No choices in OpenAI response"))
    }
}

#[async_trait]
impl LLMProvider for OpenAIProvider {
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String> {
        let messages = vec![
            OpenAIMessage {
                role: "system".to_string(),
                content: vec![OpenAIContent::Text {
                    text: system_prompt.to_string(),
                }],
            },
            OpenAIMessage {
                role: "user".to_string(),
                content: vec![OpenAIContent::Text {
                    text: user_prompt.to_string(),
                }],
            },
        ];

        self.call_openai(messages).await
    }

    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        image_base64: &str,
    ) -> Result<String> {
        let messages = vec![
            OpenAIMessage {
                role: "system".to_string(),
                content: vec![OpenAIContent::Text {
                    text: system_prompt.to_string(),
                }],
            },
            OpenAIMessage {
                role: "user".to_string(),
                content: vec![
                    OpenAIContent::ImageUrl {
                        image_url: ImageUrl {
                            url: format!("data:image/png;base64,{}", image_base64),
                        },
                    },
                    OpenAIContent::Text {
                        text: user_prompt.to_string(),
                    },
                ],
            },
        ];

        self.call_openai(messages).await
    }

    fn supports_vision(&self) -> bool {
        // GPT-4 and GPT-5 Vision models support vision
        self.model.contains("gpt-4") || self.model.contains("gpt-5") || self.model.contains("vision")
    }

    fn provider_name(&self) -> &str {
        "OpenAI"
    }
}

impl Default for OpenAIProvider {
    fn default() -> Self {
        Self::new().expect("Failed to create OpenAI provider")
    }
}
