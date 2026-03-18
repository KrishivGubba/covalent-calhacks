/// GatewayProvider: routes LLM requests through the AWS Lambda → Bedrock gateway.
///
/// When the user is authenticated (Auth0 JWT stored in the Flask session DB), this
/// provider is preferred over direct Anthropic/OpenAI calls.  It:
///   1. Fetches the current JWT from the local Flask server (`/auth/current`).
///   2. POSTs to `GATEWAY_URL/invoke` with `Authorization: Bearer <jwt>`.
///   3. Returns the Bedrock/Claude response.
///
/// If no JWT is available (user not logged in) or the gateway returns an error, the
/// `FallbackProvider` will automatically try the next provider in the chain.
use anyhow::{Context, Result};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use super::auth;
use super::config::ProviderConfig;
use super::traits::LLMProvider;

const GATEWAY_TIMEOUT_SECS: u64 = 90;

// ---------------------------------------------------------------------------
// Bedrock model ID mapping
// ---------------------------------------------------------------------------
// model_config.yml uses short Anthropic model names; Bedrock inference profiles
// use the `us.anthropic.*` prefix.  Add entries here as new models ship.

fn map_to_bedrock_model(model: &str) -> &str {
    match model {
        "claude-sonnet-4-5-20250929" => "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "claude-haiku-4-5-20251001" => "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "claude-sonnet-4-20250514" => "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "claude-3-5-sonnet-20241022" => "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "claude-3-5-haiku-20241022" => "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "claude-3-opus-20240229" => "anthropic.claude-3-opus-20240229-v1:0",
        "claude-3-sonnet-20240229" => "anthropic.claude-3-sonnet-20240229-v1:0",
        "claude-3-haiku-20240307" => "anthropic.claude-3-haiku-20240307-v1:0",
        other => other, // pass through — already a full Bedrock ID or unknown
    }
}

// ---------------------------------------------------------------------------
// Request / response shapes (must match lambda/ai-gateway.py)
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
struct GatewayMessage {
    role: String,
    content: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct GatewayRequest {
    model: String,
    messages: Vec<GatewayMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<String>,
    max_tokens: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    use_converse: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct GatewayResponse {
    content: String,
    #[allow(dead_code)]
    model: Option<String>,
    #[allow(dead_code)]
    stop_reason: Option<String>,
}

// ---------------------------------------------------------------------------
// Provider struct
// ---------------------------------------------------------------------------

pub struct GatewayProvider {
    client: reqwest::Client,
    /// Full URL for the Lambda/API-Gateway endpoint, e.g.
    /// `https://abc123.execute-api.us-east-1.amazonaws.com`
    gateway_url: String,
    /// Base URL of the local Flask server used to fetch the JWT.
    flask_base_url: String,
    /// Bedrock inference-profile ID to send to the gateway.
    bedrock_model: String,
}

impl GatewayProvider {
    pub fn new_with_config(config: &ProviderConfig) -> Result<Self> {
        let gateway_url = config
            .gateway_url
            .clone()
            .ok_or_else(|| anyhow::anyhow!("GATEWAY_URL is not configured"))?;

        let flask_base_url = auth::flask_base_url();

        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(GATEWAY_TIMEOUT_SECS))
            .build()
            .context("Failed to build HTTP client for GatewayProvider")?;

        Ok(Self {
            client,
            gateway_url,
            flask_base_url,
            bedrock_model: config.gateway_model.clone(),
        })
    }

    // -----------------------------------------------------------------------
    // Core HTTP call
    // -----------------------------------------------------------------------

    async fn call_gateway(
        &self,
        system_prompt: &str,
        messages: Vec<GatewayMessage>,
        use_converse: Option<bool>,
    ) -> Result<String> {
        // Require a live JWT — no JWT means the user is not logged in.
        let jwt = auth::fetch_current_jwt(&self.flask_base_url)
            .await
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "GatewayProvider: no active user session; user must be logged in to use the Bedrock gateway"
                )
            })?;

        let invoke_url = format!("{}/invoke", self.gateway_url.trim_end_matches('/'));

        let system = if system_prompt.is_empty() {
            None
        } else {
            Some(system_prompt.to_string())
        };

        let request = GatewayRequest {
            model: self.bedrock_model.clone(),
            messages,
            system,
            max_tokens: 4096,
            use_converse,
        };

        let response = self
            .client
            .post(&invoke_url)
            .header("Authorization", format!("Bearer {}", jwt))
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to Bedrock gateway")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "Bedrock gateway returned error {}: {}",
                status,
                body
            ));
        }

        let gateway_response: GatewayResponse = response
            .json()
            .await
            .context("Failed to parse Bedrock gateway response")?;

        Ok(gateway_response.content)
    }
}

// ---------------------------------------------------------------------------
// LLMProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl LLMProvider for GatewayProvider {
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String> {
        let messages = vec![GatewayMessage {
            role: "user".to_string(),
            content: serde_json::Value::String(user_prompt.to_string()),
        }];
        self.call_gateway(system_prompt, messages, None).await
    }

    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        image_base64: &str,
    ) -> Result<String> {
        // Detect media type from base64 prefix
        let media_type = if image_base64.starts_with("/9j/") {
            "image/jpeg"
        } else {
            "image/png"
        };

        // Construct Anthropic-format multi-part content with base64 image.
        // use_converse=false routes through the Lambda's invoke_bedrock_raw path,
        // which natively handles Anthropic-format base64 images.
        let content = serde_json::json!([
            {"type": "text", "text": user_prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_base64
                }
            }
        ]);

        let messages = vec![GatewayMessage {
            role: "user".to_string(),
            content,
        }];

        self.call_gateway(system_prompt, messages, Some(false)).await
    }

    fn supports_vision(&self) -> bool {
        true
    }

    fn provider_name(&self) -> &str {
        "Gateway/Bedrock"
    }
}

// ---------------------------------------------------------------------------
// Utility: build a GatewayProvider from a model name (maps to Bedrock ID)
// ---------------------------------------------------------------------------

/// Create a GatewayProvider from a ProviderConfig, mapping the stored
/// `anthropic_model` name to the corresponding Bedrock inference-profile ID if
/// needed.  The `gateway_model` field in config takes priority.
pub fn build_gateway_model_id(config: &ProviderConfig) -> String {
    if !config.gateway_model.is_empty() {
        return config.gateway_model.clone();
    }
    map_to_bedrock_model(&config.anthropic_model).to_string()
}
