use reqwest;
use serde::{Deserialize, Serialize};
use anyhow::{Result, Context};

const FLASK_API_URL: &str = "http://127.0.0.1:5001";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictionRequest {
    pub app_name: String,
    pub text_buffer: String,
    pub context_type: String,
    pub activity_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictionResponse {
    pub prediction: String,
    #[serde(default)]
    pub confidence: Option<f32>,
    #[serde(default)]
    pub suggested_actions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextUpdateRequest {
    pub app_name: String,
    pub activity_id: String,
    pub context_data: String,
    pub activity_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextUpdateResponse {
    pub message: String,
    pub node_id: Option<String>,
}

/// Request for sending decline feedback (negative signal for learning)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeclineFeedbackRequest {
    pub app_name: String,
    pub activity_id: String,
    pub declined_prediction: String,
    pub typed_text: String,
    pub chars_after: String,
    pub time_to_decline_ms: u64,
    pub signal: String, // "negative" for declines
}

/// Response from decline feedback endpoint
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeclineFeedbackResponse {
    pub message: String,
    #[serde(default)]
    pub acknowledged: bool,
}

/// HTTP client for tab completion predictions and context updates
pub struct TabCompletionApiClient {
    client: reqwest::Client,
    base_url: String,
}

impl TabCompletionApiClient {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .unwrap_or_else(|_| reqwest::Client::new()),
            base_url: FLASK_API_URL.to_string(),
        }
    }

    pub fn with_base_url(base_url: String) -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .unwrap_or_else(|_| reqwest::Client::new()),
            base_url,
        }
    }

    /// Check if the Flask server is healthy
    pub async fn health_check(&self) -> Result<bool> {
        let url = format!("{}/health", self.base_url);
        
        match self.client.get(&url).send().await {
            Ok(response) => Ok(response.status().is_success()),
            Err(_) => Ok(false),
        }
    }

    /// Get prediction from server (L2 cache - graph.db query)
    pub async fn get_prediction(&self, request: PredictionRequest) -> Result<PredictionResponse> {
        let url = format!("{}/tab_predict", self.base_url);
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send prediction request to Flask API")?;

        if response.status().is_success() {
            let prediction_response: PredictionResponse = response
                .json()
                .await
                .context("Failed to parse prediction response from Flask API")?;
            
            Ok(prediction_response)
        } else {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            Err(anyhow::anyhow!(
                "Flask API returned error status {}: {}",
                status,
                error_text
            ))
        }
    }

    /// Update context in graph.db (background operation)
    pub async fn update_context(&self, request: ContextUpdateRequest) -> Result<ContextUpdateResponse> {
        let url = format!("{}/tab_context", self.base_url);

        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send context update to Flask API")?;

        if response.status().is_success() {
            let context_response: ContextUpdateResponse = response
                .json()
                .await
                .context("Failed to parse context update response from Flask API")?;

            Ok(context_response)
        } else {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            Err(anyhow::anyhow!(
                "Flask API context update returned error status {}: {}",
                status,
                error_text
            ))
        }
    }

    /// Send decline feedback for learning (negative signal)
    /// This is fire-and-forget - we don't wait for or require a successful response
    pub async fn send_decline_feedback(&self, request: DeclineFeedbackRequest) -> Result<DeclineFeedbackResponse> {
        let url = format!("{}/tab_feedback", self.base_url);

        let response = self.client
            .post(&url)
            .json(&request)
            .timeout(std::time::Duration::from_secs(5)) // Short timeout for feedback
            .send()
            .await
            .context("Failed to send decline feedback to Flask API")?;

        if response.status().is_success() {
            let feedback_response: DeclineFeedbackResponse = response
                .json()
                .await
                .unwrap_or(DeclineFeedbackResponse {
                    message: "Feedback acknowledged".to_string(),
                    acknowledged: true,
                });

            Ok(feedback_response)
        } else {
            // Don't fail on error - feedback is best-effort
            Ok(DeclineFeedbackResponse {
                message: "Feedback sent (response not parsed)".to_string(),
                acknowledged: false,
            })
        }
    }
}

impl Default for TabCompletionApiClient {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_health_check() {
        let client = TabCompletionApiClient::new();
        let _result = client.health_check().await;
    }
}

