# LLM Interactions

Unified interface for interacting with different LLM providers (OpenAI, Anthropic, etc.).

## Usage

```python
import sys
from pathlib import Path

# Add project root to path (required because directory name has hyphen)
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_interactions import LLMClient

# Initialize client (reads from llm_config.json)
client = LLMClient()

# Generate a response
response = client.generate("What is the weather in San Francisco?")
print(response)

# With system prompt
response = client.generate(
    prompt="Explain quantum computing",
    system_prompt="You are a helpful physics teacher.",
    temperature=0.5
)
```

## Configuration

Configuration is stored in `llm_config.json`:

```json
{
  "provider": "openai",
  "openai": {
    "model": "gpt-4-turbo",
    "api_key_env": "OPENAI_API_KEY"
  },
  "anthropic": {
    "model": "claude-sonnet-4-5-20250929",
    "api_key_env": "ANTHROPIC_API_KEY"
  },
  "defaults": {
    "max_tokens": 4096,
    "temperature": 0.7
  }
}
```

### Changing Providers

To switch providers, change the `"provider"` field in `llm_config.json`:
- `"openai"` - Uses OpenAI GPT models
- `"anthropic"` - Uses Anthropic Claude models

### Provider-Specific Settings

Each provider can have its own settings:
- `model`: Default model name for that provider
- `api_key_env`: Environment variable name for API key
- Any other provider-specific parameters

### Environment Variable Fallback

If `llm_config.json` doesn't exist, the client falls back to:
- `LLM_PROVIDER` environment variable (defaults to "openai")
- Provider-specific env vars for models

## API

### `LLMClient.generate(prompt, **kwargs)`

**Public method** - The only method you need to call.

**Parameters:**
- `prompt` (str, required): User query/prompt
- `system_prompt` (str, optional): System prompt
- `model` (str, optional): Override default model
- `max_tokens` (int, optional): Override default max tokens
- `temperature` (float, optional): Override default temperature
- `**kwargs`: Additional provider-specific parameters

**Returns:**
- `str`: Generated response text

**Example:**
```python
client = LLMClient()

# Simple query
response = client.generate("Hello!")

# With all parameters
response = client.generate(
    prompt="Write a poem",
    system_prompt="You are a creative writer",
    model="gpt-4",
    max_tokens=500,
    temperature=0.9
)
```

## Adding New Providers

To add a new provider:

1. Add provider config to `llm_config.json`:
```json
{
  "provider": "new_provider",
  "new_provider": {
    "model": "model-name",
    "api_key_env": "NEW_PROVIDER_API_KEY"
  }
}
```

2. Add private method to `LLMClient`:
```python
def _call_new_provider(self, prompt, system_prompt, model, max_tokens, temperature, **kwargs):
    # Implementation
    pass
```

3. Update router in `generate()` method:
```python
if self.provider == "new_provider":
    return self._call_new_provider(...)
```
