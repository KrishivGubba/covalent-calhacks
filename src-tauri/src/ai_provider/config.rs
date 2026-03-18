use std::collections::HashMap;
use std::env;
use std::path::PathBuf;
use serde::Deserialize;

// --- YAML deserialization structs matching model_config.yml ---

#[derive(Debug, Deserialize)]
struct ModelConfigFile {
    models: HashMap<String, ModelTaskConfig>,
    #[serde(default)]
    provider_settings: HashMap<String, ProviderSettingsEntry>,
}

#[derive(Debug, Deserialize)]
struct ModelTaskConfig {
    provider: String,
    model_name: String,
    #[serde(default)]
    api_key_env: Option<String>,
}

#[allow(dead_code)]
#[derive(Debug, Deserialize)]
struct ProviderSettingsEntry {
    #[serde(default = "default_timeout")]
    timeout: u64,
    #[serde(default)]
    base_url: Option<String>,
    #[serde(default)]
    api_key_env: Option<String>,
    #[serde(default)]
    gateway_url_env: Option<String>,
    #[serde(default)]
    access_token_env: Option<String>,
}

fn default_timeout() -> u64 {
    30
}

// ---------------------------------------------------------------------------
// Helper: decide if the Bedrock gateway should be active
// ---------------------------------------------------------------------------
//
// The gateway is disabled when any of the following are true:
//   • GATEWAY_URL is not set (`gateway_url_set` is false)
//   • GATEWAY_ENABLED=false  or  GATEWAY_ENABLED=0
//   • DEV=1  (convenience shorthand for local development)
//
// If none of those override flags are present, the gateway is enabled whenever
// GATEWAY_URL is set.  Note: AI_FALLBACK_CHAIN takes precedence at a higher
// level — if that var is set explicitly, its content is used verbatim and this
// function is not consulted.
fn gateway_enabled_from_env(gateway_url_set: bool) -> bool {
    if !gateway_url_set {
        return false;
    }
    // DEV=1 → skip gateway so local API keys are used directly
    if env::var("DEV").map(|v| v == "1").unwrap_or(false) {
        eprintln!("ℹ️  DEV=1 detected — Bedrock gateway disabled, using direct API keys");
        return false;
    }
    // GATEWAY_ENABLED=false or GATEWAY_ENABLED=0 → explicit opt-out
    match env::var("GATEWAY_ENABLED").as_deref() {
        Ok("false") | Ok("0") => {
            eprintln!("ℹ️  GATEWAY_ENABLED=false — Bedrock gateway disabled");
            false
        }
        _ => true,
    }
}

// --- Public config consumed by providers ---

/// Configuration for AI providers loaded from model_config.yml (source of truth)
/// with API keys resolved from the environment variables named in the YAML.
#[derive(Debug, Clone)]
pub struct ProviderConfig {
    pub provider: String,
    pub fallback_chain: Vec<String>,
    pub anthropic_api_key: Option<String>,
    pub anthropic_model: String,
    pub anthropic_timeout: u64,
    pub openai_api_key: Option<String>,
    pub openai_model: String,
    pub openai_timeout: u64,
    pub ollama_base_url: String,
    pub ollama_model: String,
    pub ollama_timeout: u64,
    /// URL of the Lambda/API-Gateway Bedrock gateway (e.g. `https://abc.execute-api.us-east-1.amazonaws.com`).
    /// When set and the user is authenticated, `GatewayProvider` is added first in the fallback chain.
    pub gateway_url: Option<String>,
    /// Bedrock inference-profile model ID to use via the gateway.
    /// Defaults to `us.anthropic.claude-sonnet-4-20250514-v1:0`.
    pub gateway_model: String,
    /// Whether the gateway is active.  False when disabled by DEV=1,
    /// GATEWAY_ENABLED=false, or an explicit AI_FALLBACK_CHAIN without "gateway".
    pub gateway_enabled: bool,
}

impl ProviderConfig {
    /// Load config from model_config.yml, falling back to env vars if YAML is not found.
    pub fn from_env() -> Self {
        // Load .env so API key env vars are available
        let _ = dotenvy::dotenv();

        match Self::from_yaml() {
            Ok(config) => {
                eprintln!("✓ Loaded provider config from model_config.yml");
                config
            }
            Err(e) => {
                eprintln!("⚠️  Could not load model_config.yml ({}), falling back to env vars", e);
                Self::from_env_only()
            }
        }
    }

    /// Parse model_config.yml and build ProviderConfig from it.
    fn from_yaml() -> Result<Self, String> {
        let yaml_path = Self::find_yaml_path()
            .ok_or_else(|| "model_config.yml not found".to_string())?;

        let contents = std::fs::read_to_string(&yaml_path)
            .map_err(|e| format!("Failed to read {}: {}", yaml_path.display(), e))?;

        let file: ModelConfigFile = serde_yaml::from_str(&contents)
            .map_err(|e| format!("Failed to parse model_config.yml: {}", e))?;

        // Collect the model name + api_key_env for each provider from the task configs.
        // We use the first task found per provider (priority: action_creation > others).
        let mut anthropic_model = String::new();
        let mut anthropic_key_env = String::from("ANTHROPIC_API_KEY");
        let mut openai_model = String::new();
        let mut openai_key_env = String::from("OPENAI_API_KEY");
        let mut bedrock_model = String::new();
        let mut has_bedrock_tasks = false;

        // Prioritized task order: action_creation first, then others alphabetically
        let priority_tasks = ["action_creation", "data_condensation", "graph_operations",
                              "traversal", "fit_validation", "embedding"];

        for task_name in &priority_tasks {
            if let Some(task) = file.models.get(*task_name) {
                match task.provider.as_str() {
                    "anthropic" if anthropic_model.is_empty() => {
                        anthropic_model = task.model_name.clone();
                        if let Some(ref key_env) = task.api_key_env {
                            anthropic_key_env = key_env.clone();
                        }
                    }
                    "bedrock" => {
                        has_bedrock_tasks = true;
                        if bedrock_model.is_empty() {
                            bedrock_model = task.model_name.clone();
                        }
                    }
                    "openai" if openai_model.is_empty() => {
                        openai_model = task.model_name.clone();
                        if let Some(ref key_env) = task.api_key_env {
                            openai_key_env = key_env.clone();
                        }
                    }
                    _ => {}
                }
            }
        }

        // Also scan any remaining tasks not in our priority list
        for (_task_name, task) in &file.models {
            match task.provider.as_str() {
                "anthropic" if anthropic_model.is_empty() => {
                    anthropic_model = task.model_name.clone();
                    if let Some(ref key_env) = task.api_key_env {
                        anthropic_key_env = key_env.clone();
                    }
                }
                "bedrock" if bedrock_model.is_empty() => {
                    has_bedrock_tasks = true;
                    bedrock_model = task.model_name.clone();
                }
                "openai" if openai_model.is_empty() => {
                    openai_model = task.model_name.clone();
                    if let Some(ref key_env) = task.api_key_env {
                        openai_key_env = key_env.clone();
                    }
                }
                _ => {}
            }
        }

        // Defaults if a provider wasn't referenced by any task
        if anthropic_model.is_empty() {
            anthropic_model = "claude-sonnet-4-5-20250929".to_string();
        }
        if openai_model.is_empty() {
            openai_model = "gpt-4o".to_string();
        }

        // Resolve API keys from the env var names specified in YAML
        let anthropic_api_key = env::var(&anthropic_key_env)
            .or_else(|_| env::var("CLAUDE_API_KEY"))
            .ok();
        let openai_api_key = env::var(&openai_key_env).ok();

        // Timeouts from provider_settings
        let anthropic_timeout = file.provider_settings.get("anthropic")
            .map(|s| s.timeout).unwrap_or(30);
        let openai_timeout = file.provider_settings.get("openai")
            .map(|s| s.timeout).unwrap_or(30);
        let ollama_timeout = file.provider_settings.get("ollama")
            .map(|s| s.timeout).unwrap_or(30);

        // Ollama settings: check provider_settings in YAML, then env vars
        let ollama_base_url = file.provider_settings.get("ollama")
            .and_then(|s| s.base_url.clone())
            .or_else(|| env::var("OLLAMA_BASE_URL").ok())
            .unwrap_or_else(|| "http://localhost:11434".to_string());

        let ollama_model = env::var("OLLAMA_MODEL")
            .unwrap_or_else(|_| "qwen2.5-coder:3b".to_string());

        // Determine primary provider — prefer gateway/bedrock when configured
        let provider = if has_bedrock_tasks {
            "gateway".to_string()
        } else if anthropic_api_key.is_some() {
            "claude".to_string()
        } else if openai_api_key.is_some() {
            "openai".to_string()
        } else {
            "ollama".to_string()
        };

        // Gateway config: resolve URL from bedrock provider_settings or env var
        let bedrock_settings = file.provider_settings.get("bedrock");
        let gateway_url_env = bedrock_settings
            .and_then(|s| s.gateway_url_env.clone())
            .unwrap_or_else(|| "GATEWAY_URL".to_string());
        let gateway_url = env::var(&gateway_url_env).ok();

        // Use bedrock model from YAML tasks, then GATEWAY_MODEL env, then default
        let gateway_model = if !bedrock_model.is_empty() {
            bedrock_model
        } else {
            env::var("GATEWAY_MODEL").unwrap_or_else(|_| {
                "us.anthropic.claude-sonnet-4-20250514-v1:0".to_string()
            })
        };

        // Gateway is active when: bedrock tasks in YAML + GATEWAY_URL set,
        // or legacy env-var based check. Disabled by DEV=1 or GATEWAY_ENABLED=false.
        let gateway_enabled = gateway_enabled_from_env(gateway_url.is_some())
            || (has_bedrock_tasks && gateway_url.is_some());

        // Build fallback chain.
        // Priority: explicit AI_FALLBACK_CHAIN env var > dynamic construction.
        // When bedrock tasks are configured, gateway leads the chain.
        let fallback_chain = if let Ok(chain) = env::var("AI_FALLBACK_CHAIN") {
            chain
                .split(',')
                .map(|s| s.trim().to_lowercase())
                .collect()
        } else {
            let mut chain = Vec::new();
            if gateway_enabled {
                chain.push("gateway".to_string());
            }
            if anthropic_api_key.is_some() {
                chain.push("claude".to_string());
            }
            if openai_api_key.is_some() {
                chain.push("openai".to_string());
            }
            chain.push("ollama".to_string());
            chain
        };

        Ok(Self {
            provider,
            fallback_chain,
            anthropic_api_key,
            anthropic_model,
            anthropic_timeout,
            openai_api_key,
            openai_model,
            openai_timeout,
            ollama_base_url,
            ollama_model,
            ollama_timeout,
            gateway_url,
            gateway_model,
            gateway_enabled,
        })
    }

    /// Pure env-var fallback (original behavior) used when YAML is unavailable.
    fn from_env_only() -> Self {
        let anthropic_api_key = env::var("ANTHROPIC_API_KEY")
            .or_else(|_| env::var("CLAUDE_API_KEY"))
            .ok();
        let openai_api_key = env::var("OPENAI_API_KEY").ok();
        let gateway_url = env::var("GATEWAY_URL").ok();

        let gateway_enabled = gateway_enabled_from_env(gateway_url.is_some());

        let provider = env::var("AI_PROVIDER").unwrap_or_else(|_| {
            if gateway_enabled {
                "gateway".to_string()
            } else if anthropic_api_key.is_some() {
                "claude".to_string()
            } else if openai_api_key.is_some() {
                "openai".to_string()
            } else {
                "ollama".to_string()
            }
        });

        // If AI_FALLBACK_CHAIN is explicitly set, honour it; otherwise build
        // dynamically so the gateway always leads when configured.
        let fallback_chain = if let Ok(chain) = env::var("AI_FALLBACK_CHAIN") {
            chain
                .split(',')
                .map(|s| s.trim().to_lowercase())
                .collect()
        } else {
            let mut chain = Vec::new();
            if gateway_enabled {
                chain.push("gateway".to_string());
            }
            if anthropic_api_key.is_some() {
                chain.push("claude".to_string());
            }
            if openai_api_key.is_some() {
                chain.push("openai".to_string());
            }
            chain.push("ollama".to_string());
            chain
        };

        let anthropic_model = env::var("ANTHROPIC_MODEL")
            .unwrap_or_else(|_| "claude-sonnet-4-5-20250929".to_string());

        let openai_model = env::var("OPENAI_MODEL")
            .unwrap_or_else(|_| "gpt-4o".to_string());

        let ollama_base_url = env::var("OLLAMA_BASE_URL")
            .unwrap_or_else(|_| "http://localhost:11434".to_string());

        let ollama_model = env::var("OLLAMA_MODEL")
            .unwrap_or_else(|_| "qwen2.5-coder:3b".to_string());

        let gateway_model = env::var("GATEWAY_MODEL")
            .unwrap_or_else(|_| "us.anthropic.claude-sonnet-4-20250514-v1:0".to_string());

        Self {
            provider,
            fallback_chain,
            anthropic_api_key,
            anthropic_model,
            anthropic_timeout: 30,
            openai_api_key,
            openai_model,
            openai_timeout: 30,
            ollama_base_url,
            ollama_model,
            ollama_timeout: 30,
            gateway_url,
            gateway_model,
            gateway_enabled,
        }
    }

    /// Search common locations for model_config.yml
    fn find_yaml_path() -> Option<PathBuf> {
        let candidates = [
            // Relative to CWD (covers both `src-tauri/` and project root)
            PathBuf::from("model_config.yml"),
            PathBuf::from("../model_config.yml"),
            // Relative to executable (for release builds)
            std::env::current_exe().ok()
                .and_then(|p| p.parent().map(|d| d.join("../../../model_config.yml")))
                .unwrap_or_default(),
        ];

        for path in &candidates {
            if path.exists() {
                return Some(path.clone());
            }
        }

        // Also check MODEL_CONFIG_PATH env var as explicit override
        if let Ok(explicit) = env::var("MODEL_CONFIG_PATH") {
            let p = PathBuf::from(&explicit);
            if p.exists() {
                return Some(p);
            }
        }

        None
    }
}

impl Default for ProviderConfig {
    fn default() -> Self {
        Self::from_env()
    }
}
