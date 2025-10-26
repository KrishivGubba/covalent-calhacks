use reqwest;
use serde::{Deserialize, Serialize};
use anyhow::{Result, Context as AnyhowContext};
use crate::screen_context::{RawContext, ContextType, DevelopmentType, CommunicationType, 
                             ResearchType, CreativeType, DataWorkType, AdministrationType, ActivityLevel};

const FLASK_API_URL: &str = "http://127.0.0.1:5001";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextPayload {
    pub description: String,
    pub data: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextResponse {
    pub message: String,
    pub written: String,
}

/// HTTP client for sending context data to Flask API
pub struct ContextApiClient {
    client: reqwest::Client,
    base_url: String,
}

impl ContextApiClient {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(10))
                .build()
                .unwrap_or_else(|_| reqwest::Client::new()),
            base_url: FLASK_API_URL.to_string(),
        }
    }

    pub fn with_base_url(base_url: String) -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(10))
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

    /// Send context data to the Flask API
    pub async fn send_context(&self, description: String, data: String) -> Result<ContextResponse> {
        let url = format!("{}/screen", self.base_url);
        
        let payload = ContextPayload { description, data };
        
        let response = self.client
            .post(&url)
            .json(&payload)
            .send()
            .await
            .context("Failed to send request to Flask API")?;

        if response.status().is_success() {
            let context_response: ContextResponse = response
                .json()
                .await
                .context("Failed to parse response from Flask API")?;
            
            Ok(context_response)
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

    /// Send raw context data after generating a description
    pub async fn send_raw_context(&self, context: &RawContext, context_type: &ContextType) -> Result<ContextResponse> {
        let description = self.generate_description(context, context_type);
        let data = serde_json::to_string(context)
            .context("Failed to serialize context data")?;
        
        self.send_context(description, data).await
    }

    /// Generate a human-readable description from context
    fn generate_description(&self, context: &RawContext, context_type: &ContextType) -> String {
        let app_name = &context.app_info.name;
        let window_title = context.app_info.window_title
            .as_ref()
            .map(|t| format!(" - {}", t))
            .unwrap_or_default();
        
        let context_type_str = match context_type {
            ContextType::Development(dev_type) => {
                match dev_type {
                    DevelopmentType::Frontend => "developing frontend",
                    DevelopmentType::Backend => "developing backend",
                    DevelopmentType::Database => "working with database",
                    DevelopmentType::DevOps => "DevOps work",
                    DevelopmentType::Debugging => "debugging",
                    DevelopmentType::CodeReview => "reviewing code",
                    DevelopmentType::Documentation => "writing documentation",
                }
            }
            ContextType::Communication(comm_type) => {
                match comm_type {
                    CommunicationType::VideoMeeting => "in video meeting",
                    CommunicationType::AudioCall => "on audio call",
                    CommunicationType::InstantMessaging => "messaging",
                    CommunicationType::EmailDrafting => "writing email",
                    CommunicationType::SlackDiscussion => "discussing on Slack",
                }
            }
            ContextType::Research(research_type) => {
                match research_type {
                    ResearchType::TechnicalResearch => "technical research",
                    ResearchType::MarketResearch => "market research",
                    ResearchType::AcademicReading => "academic reading",
                    ResearchType::APIDocumentation => "reading API docs",
                }
            }
            ContextType::Creative(creative_type) => {
                match creative_type {
                    CreativeType::UIDesign => "designing UI",
                    CreativeType::GraphicDesign => "graphic design",
                    CreativeType::VideoEditing => "editing video",
                    CreativeType::ContentWriting => "writing content",
                    CreativeType::Presentation => "creating presentation",
                }
            }
            ContextType::DataWork(data_type) => {
                match data_type {
                    DataWorkType::Spreadsheet => "working on spreadsheet",
                    DataWorkType::DataVisualization => "visualizing data",
                    DataWorkType::SQLQuerying => "querying SQL",
                    DataWorkType::DataCleaning => "cleaning data",
                }
            }
            ContextType::Administration(admin_type) => {
                match admin_type {
                    AdministrationType::TaskManagement => "managing tasks",
                    AdministrationType::Calendar => "managing calendar",
                    AdministrationType::PasswordManager => "managing passwords",
                    AdministrationType::SystemSettings => "changing settings",
                }
            }
            ContextType::Multitasking(_) => "multitasking",
            ContextType::Unknown => "using app",
        };

        let activity_level = match context.activity_metrics.activity_level {
            ActivityLevel::Idle => "idle",
            ActivityLevel::Low => "low activity",
            ActivityLevel::Medium => "medium activity",
            ActivityLevel::High => "high activity",
        };

        format!(
            "User {} in {}{} ({})",
            context_type_str, app_name, window_title, activity_level
        )
    }
}

impl Default for ContextApiClient {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_health_check() {
        let client = ContextApiClient::new();
        // This will fail if Flask server is not running, which is expected in tests
        let _result = client.health_check().await;
    }

    #[test]
    fn test_generate_description() {
        let client = ContextApiClient::new();
        let context = RawContext::default();
        let context_type = ContextType::Unknown;
        
        let description = client.generate_description(&context, &context_type);
        assert!(!description.is_empty());
    }
}

