"""
Unified LLM Client - Single interface for all LLM providers.

Usage:
    from llm_interactions import LLMClient
    
    client = LLMClient()
    response = client.generate("What is the weather?")
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Add context-engine to path for model_interface
_project_root = Path(__file__).resolve().parent.parent
_context_engine_path = _project_root / "context-engine"
if str(_context_engine_path) not in sys.path:
    sys.path.insert(0, str(_context_engine_path))

# Lazy imports for providers (only import what's needed)
_openai_client = None
_model_factory = None

# Bedrock model ID mapping
BEDROCK_MODELS = {
    "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-3-5-sonnet-20241022": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-7-sonnet-20250219": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
}


def _get_openai_client():
    """Lazy import OpenAI client."""
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI
        except ImportError:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")
    return _openai_client


def _get_model_factory():
    """Lazy import and cache ModelFactory for bedrock/anthropic providers."""
    global _model_factory
    if _model_factory is None:
        from model_interface import ModelFactory
        _model_factory = ModelFactory()
    return _model_factory


class LLMClient:
    """
    Unified LLM client that routes requests to different providers based on config.
    
    Configuration is loaded from:
    1. llm_config.json (in llm-interactions directory)
    2. Falls back to LLM_PROVIDER environment variable
    
    Public API:
        generate(prompt, system_prompt=None, **kwargs) -> str
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize LLM client with configuration.
        
        Args:
            config_path: Optional path to config JSON file. 
                        Defaults to llm-interactions/llm_config.json
        """
        load_dotenv()
        
        # Find config file
        if config_path is None:
            # Default to llm-interactions/llm_config.json
            config_path = Path(__file__).parent / "llm_config.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        if self.config.get("provider"):
            self.provider = self.config.get("provider")
        else:
            raise ValueError("Provider not found in config. Must be specified in config or environment variable LLM_PROVIDER.")

        # "anthropic" is now an alias for "bedrock" - routes through the gateway
        if self.provider not in ["openai", "anthropic", "bedrock"]:
            raise ValueError(f"Unsupported provider: {self.provider}. Supported: openai, anthropic, bedrock")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file. Config file is required."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"LLM config file not found at: {self.config_path}. "
                f"Create it (or pass config_path=...) and include at least a 'provider' key."
            )

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {self.config_path}: {e}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Generate a response from the configured LLM provider.
        
        This is the ONLY public method - all LLM calls go through here.
        
        Args:
            prompt: User prompt/query
            system_prompt: Optional system prompt
            model: Optional model override (uses config default if not provided)
            max_tokens: Optional max tokens (uses config default if not provided)
            temperature: Optional temperature (uses config default if not provided)
            **kwargs: Additional provider-specific parameters
        
        Returns:
            str: Generated response text
        
        Raises:
            ValueError: If provider is not supported
            RuntimeError: If API call fails
        """
        # Get defaults from config
        defaults = self.config.get("defaults", {})
        max_tokens = max_tokens or defaults.get("max_tokens", 4096)
        temperature = temperature if temperature is not None else defaults.get("temperature", 0.7)
        
        # Route to appropriate provider
        if self.provider == "openai":
            return self._call_openai(prompt, system_prompt, model, max_tokens, temperature, **kwargs)
        elif self.provider in ["anthropic", "bedrock"]:
            # Both "anthropic" and "bedrock" route through the Bedrock gateway
            return self._call_bedrock(prompt, system_prompt, model, max_tokens, temperature, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _call_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """Private method to call OpenAI API."""
        OpenAI = _get_openai_client()
        
        # Get OpenAI config
        openai_config = self.config.get("openai", {})
        api_key = os.getenv(openai_config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            raise ValueError(f"API key not found. Set {openai_config.get('api_key_env', 'OPENAI_API_KEY')} environment variable.")
        
        client = OpenAI(api_key=api_key)
        model = model or openai_config.get("model", "gpt-4-turbo")
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Call API
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}")
    
    def _call_bedrock(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Private method to call Bedrock via the model_interface.py ChatModel.
        
        Routes through the GatewayClient -> Lambda -> Bedrock path.
        """
        factory = _get_model_factory()
        chat_model = factory.get_chat_model("action_creation")
        
        # Get model from config if not provided
        if model is None:
            # Check anthropic config for backward compatibility
            anthropic_config = self.config.get("anthropic", {})
            model = anthropic_config.get("model", "claude-sonnet-4-5-20250929")
        
        # Map Anthropic model name to Bedrock ID if needed
        bedrock_model = BEDROCK_MODELS.get(model, model)
        
        # Call API via model_interface
        try:
            response = chat_model.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model=bedrock_model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response
        except Exception as e:
            raise RuntimeError(f"Bedrock API call failed: {e}")
