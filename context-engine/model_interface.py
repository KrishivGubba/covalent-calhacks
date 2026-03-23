"""
Model Interface for Context Engine
Provides a unified interface to switch between different LLM providers (Claude, OpenAI, Qwen, Google, Bedrock)
"""

import os
import sys
import base64
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# Add llm-interactions to path for GatewayClient
_llm_interactions_path = _project_root / "llm-interactions"
if str(_llm_interactions_path) not in sys.path:
    sys.path.insert(0, str(_llm_interactions_path))

from logger import get_logger
log = get_logger()
import yaml
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List


class ModelConfig:
    """Loads and manages model configuration from YAML file"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # Default to model_config.yml in repo root (or bundle root when frozen)
            if getattr(sys, 'frozen', False):
                repo_root = Path(sys._MEIPASS)
            else:
                repo_root = Path(__file__).parent.parent
            config_path = repo_root / "model_config.yml"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Model config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def get_model_config(self, task: str) -> Dict[str, Any]:
        """Get configuration for a specific task"""
        if task not in self.config['models']:
            raise ValueError(f"Task '{task}' not found in model config. Available tasks: {list(self.config['models'].keys())}")
        
        return self.config['models'][task]
    
    def get_provider_settings(self, provider: str) -> Dict[str, Any]:
        """Get provider-specific settings"""
        return self.config.get('provider_settings', {}).get(provider, {})


class EmbeddingModel:
    """Unified interface for embedding models"""
    
    def __init__(self, config: ModelConfig, task: str = "embedding"):
        self.config = config.get_model_config(task)
        self.provider = self.config['provider']
        self.model_name = self.config['model_name']
        self.api_key = os.getenv(self.config['api_key_env'])
        
        if not self.api_key:
            raise ValueError(f"API key not found in environment: {self.config['api_key_env']}")
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client based on provider"""
        if self.provider == "google":
            import google.genai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            raise ValueError("Anthropic does not provide embedding models. Use Google or OpenAI for embeddings.")
        elif self.provider == "qwen":
            from openai import OpenAI
            provider_settings = ModelConfig().get_provider_settings("qwen")
            base_url = provider_settings.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")
    
    def embed(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text"""
        if not text:
            return None
        
        try:
            if self.provider == "google":
                result = self.client.embed_content(
                    model=self.model_name,
                    content=text,
                )
                embedding = np.array(result['embedding']).reshape(1, -1)
                return embedding
            
            elif self.provider in ["openai", "qwen"]:
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=text
                )
                embedding = np.array(response.data[0].embedding).reshape(1, -1)
                return embedding
            
        except Exception as e:
            log.error(f"Error generating embedding with {self.provider}: {e}")
            return None


class ChatModel:
    """Unified interface for chat/completion models"""
    
    def __init__(self, config: ModelConfig, task: str):
        self.model_config = config
        self.config = config.get_model_config(task)
        self.provider = self.config['provider']
        self.model_name = self.config['model_name']
        self.max_tokens = self.config.get('max_tokens', 2048)
        
        # Bedrock uses GatewayClient with env vars, not an API key
        if self.provider == "bedrock":
            self.api_key = None
        else:
            self.api_key = os.getenv(self.config.get('api_key_env', ''))
            if not self.api_key:
                raise ValueError(f"API key not found in environment: {self.config.get('api_key_env')}")
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client based on provider"""
        if self.provider == "google":
            import google.gen as genai
            genai.configure(api_key=self.api_key)
            self.client = genai
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
        elif self.provider == "qwen":
            from openai import OpenAI
            provider_settings = ModelConfig().get_provider_settings("qwen")
            base_url = provider_settings.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        elif self.provider == "bedrock":
            from gateway_client import GatewayClient
            provider_settings = self.model_config.get_provider_settings("bedrock")
            gateway_url = os.getenv(provider_settings.get("gateway_url_env", "GATEWAY_URL"))
            access_token = os.getenv(provider_settings.get("access_token_env", "GATEWAY_ACCESS_TOKEN"))
            timeout = provider_settings.get("timeout", 60)
            
            if not gateway_url:
                raise ValueError("GATEWAY_URL environment variable not set for bedrock provider")
            
            # If no static env-var token, fetch from the local Flask auth endpoint
            if not access_token:
                access_token = self._fetch_flask_access_token()
            
            self.client = GatewayClient(
                url=gateway_url,
                access_token=access_token,
                timeout=timeout,
                default_model=self.model_name,
            )
        else:
            raise ValueError(f"Unsupported chat provider: {self.provider}")
    
    def _fetch_flask_access_token(self) -> Optional[str]:
        """Fetch the current Auth0 access token from the local Flask /auth/current endpoint."""
        import requests as _requests
        flask_port = os.getenv("VITE_FLASK_PORT", "15001")
        try:
            resp = _requests.get(
                f"http://127.0.0.1:{flask_port}/auth/current", timeout=5
            )
            if resp.ok:
                data = resp.json()
                if data.get("authenticated") and not data.get("expired"):
                    return data.get("access_token")
        except Exception:
            pass
        return None

    def generate(self, prompt: str, system_prompt: Optional[str] = None, 
                 model: Optional[str] = None, max_tokens: Optional[int] = None,
                 temperature: Optional[float] = None) -> str:
        """Generate completion for prompt"""
        try:
            if self.provider == "bedrock":
                token = self._fetch_flask_access_token()
                if token:
                    self.client.set_access_token(token)

            if self.provider == "google":
                model_obj = self.client.GenerativeModel(self.model_name)
                response = model_obj.generate_content(prompt)
                return response.text
            
            elif self.provider == "anthropic":
                messages = [{"role": "user", "content": prompt}]
                response = self.client.messages.create(
                    model=model or self.model_name,
                    max_tokens=max_tokens or self.max_tokens,
                    messages=messages
                )
                return response.content[0].text
            
            elif self.provider == "bedrock":
                response = self.client.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model or self.model_name,
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=temperature,
                )
                return response.content
            
            elif self.provider in ["openai", "qwen"]:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                # Newer OpenAI models (o1, o3, gpt-5 series) use max_completion_tokens
                # Older models (gpt-4, gpt-3.5) use max_tokens
                # Check model name to determine which parameter to use
                actual_model = model or self.model_name
                uses_completion_tokens = any(prefix in actual_model.lower() 
                                            for prefix in ["o1", "o3", "gpt-5"])
                
                if uses_completion_tokens:
                    response = self.client.chat.completions.create(
                        model=actual_model,
                        messages=messages,
                        max_completion_tokens=max_tokens or self.max_tokens
                    )
                else:
                    response = self.client.chat.completions.create(
                        model=actual_model,
                        messages=messages,
                        max_tokens=max_tokens or self.max_tokens
                    )
                return response.choices[0].message.content
            
        except Exception as e:
            log.error(f"Error generating completion with {self.provider}: {e}")
            raise
    
    def generate_with_vision(self, prompt: str, image_path: str,
                             system_prompt: Optional[str] = None,
                             model: Optional[str] = None,
                             max_tokens: Optional[int] = None,
                             temperature: Optional[float] = None) -> str:
        """
        Generate completion with vision (image) input.
        
        Currently only supported for bedrock provider via the gateway's raw API.
        
        Args:
            prompt: Text prompt
            image_path: Path to image file (PNG, JPG, etc.)
            system_prompt: Optional system prompt
            model: Optional model override (must be a vision-capable model)
            max_tokens: Optional max tokens override
            temperature: Optional temperature override
            
        Returns:
            str: Generated response text
        """
        if self.provider != "bedrock":
            raise NotImplementedError(f"generate_with_vision not implemented for provider: {self.provider}")
        
        token = self._fetch_flask_access_token()
        if token:
            self.client.set_access_token(token)
        
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # Determine media type from file extension
        ext = Path(image_path).suffix.lower()
        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(ext, "image/png")
        
        img_b64 = base64.b64encode(image_data).decode()
        
        # Construct Anthropic-format message with image
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    }
                }
            ]
        }]
        
        # Use invoke with use_converse=False to route through invoke_bedrock_raw
        # which natively handles Anthropic-format base64 images
        response = self.client.invoke(
            messages=messages,
            model=model or self.model_name,
            system=system_prompt,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            use_converse=False,
        )
        return response.content


class ModelFactory:
    """Factory class to create model instances for different tasks"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.model_config = ModelConfig(config_path)
        self._embedding_cache = {}
        self._chat_cache = {}
    
    def get_embedding_model(self, task: str = "embedding") -> EmbeddingModel:
        """Get embedding model for a specific task"""
        if task not in self._embedding_cache:
            self._embedding_cache[task] = EmbeddingModel(self.model_config, task)
        return self._embedding_cache[task]
    
    def get_chat_model(self, task: str) -> ChatModel:
        """Get chat model for a specific task"""
        if task not in self._chat_cache:
            self._chat_cache[task] = ChatModel(self.model_config, task)
        return self._chat_cache[task]
    
    def reload_config(self):
        """Reload configuration from file"""
        self.model_config = ModelConfig(self.model_config.config_path)
        self._embedding_cache.clear()
        self._chat_cache.clear()
