// AI Provider module - Modular AI model abstraction layer
pub mod traits;
pub mod config;
pub mod claude;
pub mod openai;
pub mod ollama;
pub mod fallback;
pub mod auth;
pub mod gateway;

// Re-export main types for easier access
pub use traits::LLMProvider;
pub use config::ProviderConfig;
pub use claude::ClaudeProvider;
pub use openai::OpenAIProvider;
pub use ollama::OllamaProvider;
pub use fallback::FallbackProvider;
pub use gateway::GatewayProvider;

use anyhow::Result;
use std::sync::Arc;

/// Factory function to create the default provider (with fallback chain)
pub fn create_default_provider() -> Result<Arc<dyn LLMProvider>> {
    let provider = FallbackProvider::new()?;
    Ok(Arc::new(provider))
}

/// Factory function to create a provider from config
pub fn create_provider_from_config(config: &ProviderConfig) -> Result<Arc<dyn LLMProvider>> {
    let provider = FallbackProvider::new_with_config(config)?;
    Ok(Arc::new(provider))
}

/// Factory function to create a specific provider by name
pub fn create_single_provider(provider_name: &str) -> Result<Arc<dyn LLMProvider>> {
    match provider_name.to_lowercase().as_str() {
        "claude" | "anthropic" => {
            let provider = ClaudeProvider::new()?;
            Ok(Arc::new(provider))
        }
        "openai" => {
            let provider = OpenAIProvider::new()?;
            Ok(Arc::new(provider))
        }
        "ollama" => {
            let provider = OllamaProvider::new()?;
            Ok(Arc::new(provider))
        }
        _ => Err(anyhow::anyhow!("Unknown provider: {}", provider_name)),
    }
}
