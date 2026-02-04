use anyhow::Result;
use async_trait::async_trait;

/// Trait defining the interface for all LLM providers
#[async_trait]
pub trait LLMProvider: Send + Sync {
    /// Generate text response from system and user prompts
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String>;
    
    /// Generate response with image input (vision models)
    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        image_base64: &str,
    ) -> Result<String>;
    
    /// Check if this provider supports vision/image input
    fn supports_vision(&self) -> bool;
    
    /// Get the name of this provider for logging
    fn provider_name(&self) -> &str;
}
