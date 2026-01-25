"""
Unified LLM Client - Single interface for all LLM providers.

Usage:
    from llm_interactions import LLMClient
    
    client = LLMClient()
    response = client.generate("What is the weather?")
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Lazy imports for providers (only import what's needed)
_openai_client = None
_anthropic_client = None


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


def _get_anthropic_client():
    """Lazy import Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        try:
            from anthropic import Anthropic
            _anthropic_client = Anthropic
        except ImportError:
            raise ImportError("Anthropic package not installed. Install with: pip install anthropic")
    return _anthropic_client


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
        
        #TODO: MAYBE change this such that the config stuff is read at "runtime" ie when the method is actually called?
        # Find config file
        if config_path is None:
            # Default to llm-interactions/llm_config.json
            config_path = Path(__file__).parent / "llm_config.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        if self.config.get("provider"):
            self.provider = self.config.get("provider")
        else: raise ValueError("Provider not found in config. Must be specified in config or environment variable LLM_PROVIDER.")

        
        if self.provider not in ["openai", "anthropic"]:
            raise ValueError(f"Unsupported provider: {self.provider}. Supported: openai, anthropic")
    
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
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt, system_prompt, model, max_tokens, temperature, **kwargs)
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
    
    def _call_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """Private method to call Anthropic API."""
        Anthropic = _get_anthropic_client()
        
        # Get Anthropic config
        anthropic_config = self.config.get("anthropic", {})
        api_key = os.getenv(anthropic_config.get("api_key_env", "ANTHROPIC_API_KEY"))
        if not api_key:
            raise ValueError(f"API key not found. Set {anthropic_config.get('api_key_env', 'ANTHROPIC_API_KEY')} environment variable.")
        
        client = Anthropic(api_key=api_key)
        model = model or anthropic_config.get("model", "claude-sonnet-4-5-20250929")
        
        # Build request
        request_params = {
            "model": model,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature if temperature is not None else 0.7,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs
        }
        
        if system_prompt:
            request_params["system"] = system_prompt
        
        # Call API
        try:
            response = client.messages.create(**request_params)
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}")
