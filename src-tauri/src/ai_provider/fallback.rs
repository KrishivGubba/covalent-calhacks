use anyhow::Result;
use async_trait::async_trait;
use std::sync::Arc;

use super::claude::ClaudeProvider;
use super::config::ProviderConfig;
use super::gateway::GatewayProvider;
use super::ollama::OllamaProvider;
use super::openai::OpenAIProvider;
use super::traits::LLMProvider;

/// FallbackProvider chains multiple providers with automatic failover
pub struct FallbackProvider {
    providers: Vec<Arc<dyn LLMProvider>>,
}

impl FallbackProvider {
    /// Creates provider chain based on configuration
    /// Default: Claude -> OpenAI -> Ollama
    pub fn new() -> Result<Self> {
        let config = ProviderConfig::from_env();
        Self::new_with_config(&config)
    }

    /// Creates provider chain from a specific config
    pub fn new_with_config(config: &ProviderConfig) -> Result<Self> {
        let mut providers: Vec<Arc<dyn LLMProvider>> = Vec::new();

        // Build providers based on fallback chain
        for provider_name in &config.fallback_chain {
            match provider_name.as_str() {
                "gateway" => {
                    match GatewayProvider::new_with_config(config) {
                        Ok(gateway) => {
                            println!("✓ Gateway/Bedrock provider initialized (JWT fetched per-request)");
                            providers.push(Arc::new(gateway));
                        }
                        Err(e) => {
                            eprintln!("⚠️  Gateway provider unavailable ({})", e);
                        }
                    }
                }
                "claude" | "anthropic" => {
                    if let Ok(claude) = ClaudeProvider::new_with_config(config) {
                        println!("✓ Claude provider initialized");
                        providers.push(Arc::new(claude));
                    } else {
                        eprintln!("⚠️  Claude provider unavailable (missing API key)");
                    }
                }
                "openai" => {
                    if let Ok(openai) = OpenAIProvider::new_with_config(config) {
                        println!("✓ OpenAI provider initialized");
                        providers.push(Arc::new(openai));
                    } else {
                        eprintln!("⚠️  OpenAI provider unavailable (missing API key)");
                    }
                }
                "ollama" => {
                    if let Ok(ollama) = OllamaProvider::new_with_config(config) {
                        println!("✓ Ollama provider initialized");
                        providers.push(Arc::new(ollama));
                    } else {
                        eprintln!("⚠️  Ollama provider unavailable (server not running?)");
                    }
                }
                _ => {
                    eprintln!("⚠️  Unknown provider in fallback chain: {}", provider_name);
                }
            }
        }

        if providers.is_empty() {
            return Err(anyhow::anyhow!(
                "No AI providers available. Please configure at least one provider with valid credentials."
            ));
        }

        println!(
            "🔗 Fallback chain initialized with {} provider(s)",
            providers.len()
        );

        Ok(Self { providers })
    }

    /// Get the number of available providers
    pub fn provider_count(&self) -> usize {
        self.providers.len()
    }

    /// Get names of all available providers
    pub fn available_providers(&self) -> Vec<String> {
        self.providers
            .iter()
            .map(|p| p.provider_name().to_string())
            .collect()
    }
}

#[async_trait]
impl LLMProvider for FallbackProvider {
    async fn generate(&self, system_prompt: &str, user_prompt: &str) -> Result<String> {
        let mut last_error = None;

        for (i, provider) in self.providers.iter().enumerate() {
            let provider_name = provider.provider_name();
            
            if i == 0 {
                eprintln!("🤖 Trying primary provider: {}", provider_name);
            } else {
                eprintln!("🔄 Falling back to: {}", provider_name);
            }

            match provider.generate(system_prompt, user_prompt).await {
                Ok(response) => {
                    if i > 0 {
                        eprintln!("✓ Fallback successful with {}", provider_name);
                    }
                    return Ok(response);
                }
                Err(e) => {
                    eprintln!(
                        "⚠️  Provider {} failed: {}, trying next...",
                        provider_name, e
                    );
                    last_error = Some(e);
                }
            }
        }

        Err(last_error.unwrap_or_else(|| {
            anyhow::anyhow!("All providers failed and no error was captured")
        }))
    }

    async fn generate_with_image(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        image_base64: &str,
    ) -> Result<String> {
        let mut last_error = None;

        // Only try providers that support vision
        let vision_providers: Vec<_> = self
            .providers
            .iter()
            .filter(|p| p.supports_vision())
            .collect();

        if vision_providers.is_empty() {
            return Err(anyhow::anyhow!(
                "No vision-capable providers available in fallback chain"
            ));
        }

        for (i, provider) in vision_providers.iter().enumerate() {
            let provider_name = provider.provider_name();
            
            if i == 0 {
                eprintln!("🤖 Trying primary vision provider: {}", provider_name);
            } else {
                eprintln!("🔄 Falling back to vision provider: {}", provider_name);
            }

            match provider
                .generate_with_image(system_prompt, user_prompt, image_base64)
                .await
            {
                Ok(response) => {
                    if i > 0 {
                        eprintln!("✓ Vision fallback successful with {}", provider_name);
                    }
                    return Ok(response);
                }
                Err(e) => {
                    eprintln!(
                        "⚠️  Vision provider {} failed: {}, trying next...",
                        provider_name, e
                    );
                    last_error = Some(e);
                }
            }
        }

        Err(last_error.unwrap_or_else(|| {
            anyhow::anyhow!("All vision providers failed and no error was captured")
        }))
    }

    fn supports_vision(&self) -> bool {
        // Support vision if at least one provider supports it
        self.providers.iter().any(|p| p.supports_vision())
    }

    fn provider_name(&self) -> &str {
        "FallbackProvider"
    }
}

impl Default for FallbackProvider {
    fn default() -> Self {
        Self::new().expect("Failed to create FallbackProvider")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fallback_provider_creation() {
        // This will fail if no providers are available, which is expected in CI
        let _ = FallbackProvider::new();
    }
}
