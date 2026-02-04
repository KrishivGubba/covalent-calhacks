use std::env;

/// Configuration for AI providers loaded from environment variables
#[derive(Debug, Clone)]
pub struct ProviderConfig {
    pub provider: String,
    pub fallback_chain: Vec<String>,
    pub anthropic_api_key: Option<String>,
    pub anthropic_model: String,
    pub openai_api_key: Option<String>,
    pub openai_model: String,
    pub ollama_base_url: String,
    pub ollama_model: String,
}

impl ProviderConfig {
    pub fn from_env() -> Self {
        // Load .env file if present
        let _ = dotenvy::dotenv();
        
        // Primary provider (default: claude if ANTHROPIC_API_KEY is set)
        let provider = env::var("AI_PROVIDER").unwrap_or_else(|_| {
            if env::var("ANTHROPIC_API_KEY").is_ok() || env::var("CLAUDE_API_KEY").is_ok() {
                "claude".to_string()
            } else if env::var("OPENAI_API_KEY").is_ok() {
                "openai".to_string()
            } else {
                "ollama".to_string()
            }
        });
        
        // Fallback chain (default: claude,openai,ollama)
        let fallback_chain = env::var("AI_FALLBACK_CHAIN")
            .unwrap_or_else(|_| "claude,openai,ollama".to_string())
            .split(',')
            .map(|s| s.trim().to_lowercase())
            .collect();
        
        // Provider-specific configuration
        let anthropic_api_key = env::var("ANTHROPIC_API_KEY")
            .or_else(|_| env::var("CLAUDE_API_KEY"))
            .ok();
        
        let anthropic_model = env::var("ANTHROPIC_MODEL")
            .unwrap_or_else(|_| "claude-sonnet-4-20250514".to_string());
        
        let openai_api_key = env::var("OPENAI_API_KEY").ok();
        
        let openai_model = env::var("OPENAI_MODEL")
            .unwrap_or_else(|_| "gpt-4o".to_string());
        
        let ollama_base_url = env::var("OLLAMA_BASE_URL")
            .unwrap_or_else(|_| "http://localhost:11434".to_string());
        
        let ollama_model = env::var("OLLAMA_MODEL")
            .unwrap_or_else(|_| "qwen2.5-coder:3b".to_string());
        
        Self {
            provider,
            fallback_chain,
            anthropic_api_key,
            anthropic_model,
            openai_api_key,
            openai_model,
            ollama_base_url,
            ollama_model,
        }
    }
}

impl Default for ProviderConfig {
    fn default() -> Self {
        Self::from_env()
    }
}
