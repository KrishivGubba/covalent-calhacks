"""
AI Gateway Client - Easy interface to call the Bedrock Lambda gateway.

Usage:
    from llm_interactions import GatewayClient
    
    client = GatewayClient()
    response = client.generate("What is 2+2?")
    
    # Or with more options
    response = client.generate(
        prompt="Explain quantum computing",
        system_prompt="You are a physics professor",
        model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        max_tokens=1000,
        temperature=0.5
    )
    
    # Health check
    health = client.health()
    
    # Chat with conversation history
    response = client.chat([
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What's your name?"}
    ])
"""

import os
import sys
import json
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


@dataclass
class GatewayResponse:
    """Response from the AI Gateway."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    def __str__(self) -> str:
        return self.content


@dataclass
class EmbeddingResponse:
    """Response from the AI Gateway /embed endpoint (single text)."""
    embedding: List[float]
    model: str
    dimensions: int
    input_tokens: int


@dataclass
class BatchEmbeddingResponse:
    """Response from the AI Gateway /embed endpoint (batch texts)."""
    embeddings: List[List[float]]
    model: str
    dimensions: int
    input_tokens: int


# Available models (for reference)
MODELS = {
    # Claude 4.5 (latest)
    "claude-4.5-sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-4.5-haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # Claude 4
    "claude-4-sonnet": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    # Claude 3.5
    "claude-3.5-sonnet": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3.5-haiku": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    # Claude 3
    "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
}


class GatewayError(Exception):
    """Exception raised when the gateway returns an error."""
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class GatewayClient:
    """
    Client for the AI Gateway Lambda.
    
    The gateway routes requests to AWS Bedrock, providing secure access
    to Claude and other models without exposing API keys on the client.
    
    Configuration:
        Set GATEWAY_URL environment variable, or pass url to constructor.
        Authentication requires an access_token (Auth0 JWT).
        
    Example:
        client = GatewayClient(access_token="eyJ...")
        response = client.generate("Hello!")
        print(response.content)
    """
    
    DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_TIMEOUT = 60  # seconds
    
    def __init__(
        self,
        url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        default_model: Optional[str] = None,
        default_max_tokens: Optional[int] = None,
        default_temperature: Optional[float] = None,
    ):
        """
        Initialize the Gateway client.
        
        Args:
            url: Gateway URL. Defaults to GATEWAY_URL env var.
            access_token: Auth0 JWT access token for authentication.
            timeout: Request timeout in seconds. Default 60.
            default_model: Default model to use. Can use alias from MODELS dict.
            default_max_tokens: Default max tokens.
            default_temperature: Default temperature.
        """
        load_dotenv()
        
        self.url = url or os.getenv("GATEWAY_URL")
        if not self.url:
            raise ValueError(
                "Gateway URL not configured. "
                "Set GATEWAY_URL environment variable or pass url parameter."
            )
        
        # Remove trailing slash
        self.url = self.url.rstrip("/")
        
        self.access_token = access_token
        self.timeout = timeout
        self.default_model = self._resolve_model(default_model) if default_model else self.DEFAULT_MODEL
        self.default_max_tokens = default_max_tokens or self.DEFAULT_MAX_TOKENS
        self.default_temperature = default_temperature if default_temperature is not None else self.DEFAULT_TEMPERATURE
        
        # Session for connection pooling
        self._session = requests.Session()
    
    def set_access_token(self, access_token: str) -> None:
        """Update the access token (e.g., after refresh)."""
        self.access_token = access_token
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for requests, including auth if available."""
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers
    
    def _resolve_model(self, model: str) -> str:
        """Resolve model alias to full model ID."""
        return MODELS.get(model, model)
    
    def _make_request(self, endpoint: str, method: str = "GET", json_data: Dict = None) -> Dict[str, Any]:
        """Make a request to the gateway."""
        url = f"{self.url}/{endpoint.lstrip('/')}"
        headers = self._get_headers()
        
        has_auth = "Authorization" in headers
        auth_preview = headers.get("Authorization", "")[:30] + "..." if has_auth else "(none)"
        payload_keys = list(json_data.keys()) if json_data else []
        print(f"🌐 Gateway {method} {url}")
        print(f"   Auth: {auth_preview}")
        print(f"   Payload keys: {payload_keys}")
        
        try:
            # #region agent log
            import time as _time_mod
            _dl_req_start = _time_mod.time()
            _dl_payload_size = len(json.dumps(json_data)) if json_data else 0
            _debug_log_path = "/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-4fb65e.log"
            try:
                with open(_debug_log_path, "a") as _dlf:
                    _dlf.write(json.dumps({"sessionId":"4fb65e","id":f"log_{int(_dl_req_start*1000)}_http_req","timestamp":int(_dl_req_start*1000),"location":"gateway_client.py:_make_request","message":"HTTP request starting","data":{"method":method,"endpoint":endpoint,"payload_bytes":_dl_payload_size,"timeout":self.timeout},"runId":"run1","hypothesisId":"H1,H4"}) + "\n")
            except: pass
            # #endregion
            
            if method == "GET":
                response = self._session.get(url, headers=headers, timeout=self.timeout)
            elif method == "POST":
                response = self._session.post(
                    url,
                    json=json_data,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # #region agent log
            _dl_req_end = _time_mod.time()
            _dl_req_duration_ms = int((_dl_req_end - _dl_req_start) * 1000)
            try:
                with open(_debug_log_path, "a") as _dlf:
                    _dlf.write(json.dumps({"sessionId":"4fb65e","id":f"log_{int(_dl_req_end*1000)}_http_resp","timestamp":int(_dl_req_end*1000),"location":"gateway_client.py:_make_request","message":"HTTP response received","data":{"status_code":response.status_code,"duration_ms":_dl_req_duration_ms,"response_len":len(response.text),"response_preview":response.text[:300]},"runId":"run1","hypothesisId":"H1,H2,H3,H4,H5"}) + "\n")
            except: pass
            # #endregion
            
            # Try to parse JSON, but capture raw text for error reporting
            raw_text = response.text
            try:
                data = response.json()
            except json.JSONDecodeError:
                # If not JSON, include raw response in error
                raise GatewayError(f"Invalid JSON response: {raw_text[:500]}", response.status_code)
            
            if response.status_code == 401:
                error_msg = data.get("error", "Unauthorized - invalid or missing access token")
                raise GatewayError(error_msg, 401)
            
            if response.status_code != 200:
                error_msg = data.get("error", raw_text[:500] if raw_text else f"HTTP {response.status_code}")
                error_detail = data.get("message", data.get("errorMessage", ""))
                if error_detail:
                    error_msg = f"{error_msg}: {error_detail}"
                raise GatewayError(error_msg, response.status_code)
            
            return data
            
        except requests.exceptions.Timeout:
            # #region agent log
            try:
                with open(_debug_log_path, "a") as _dlf:
                    _dl_to_ts = int(_time_mod.time() * 1000)
                    _dlf.write(json.dumps({"sessionId":"4fb65e","id":f"log_{_dl_to_ts}_timeout","timestamp":_dl_to_ts,"location":"gateway_client.py:_make_request","message":"Request timed out on client side","data":{"timeout":self.timeout,"endpoint":endpoint},"runId":"run1","hypothesisId":"H1"}) + "\n")
            except: pass
            # #endregion
            raise GatewayError("Request timed out", 504)
        except requests.exceptions.ConnectionError as e:
            # #region agent log
            try:
                with open(_debug_log_path, "a") as _dlf:
                    _dl_ce_ts = int(_time_mod.time() * 1000)
                    _dlf.write(json.dumps({"sessionId":"4fb65e","id":f"log_{_dl_ce_ts}_conn_err","timestamp":_dl_ce_ts,"location":"gateway_client.py:_make_request","message":"Connection error","data":{"error":str(e)[:200],"endpoint":endpoint},"runId":"run1","hypothesisId":"H5"}) + "\n")
            except: pass
            # #endregion
            raise GatewayError(f"Connection failed: {e}", 503)
    
    def health(self) -> Dict[str, Any]:
        """
        Check gateway health.
        
        Returns:
            dict: Health status including region and default model.
            
        Example:
            >>> client.health()
            {'status': 'healthy', 'region': 'us-east-1', 'default_model': 'us.anthropic.claude-sonnet-4-20250514-v1:0'}
        """
        return self._make_request("/health")
    
    def invoke(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> GatewayResponse:
        """
        Invoke the model with a list of messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Role must be 'user' or 'assistant'.
            model: Model ID or alias (e.g., 'claude-4-sonnet'). Uses default if not provided.
            system: Optional system prompt.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature (0-1).
            **kwargs: Additional parameters passed to the gateway (e.g., use_converse=False for vision).
            
        Returns:
            GatewayResponse: Response with content, usage stats, etc.
            
        Example:
            >>> response = client.invoke([
            ...     {"role": "user", "content": "Hello!"}
            ... ])
            >>> print(response.content)
            "Hello! How can I help you today?"
        """
        payload = {
            "messages": messages,
            "model": self._resolve_model(model) if model else self.default_model,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature if temperature is not None else self.default_temperature,
            **kwargs,
        }
        
        if system:
            payload["system"] = system
        
        data = self._make_request("/invoke", method="POST", json_data=payload)
        
        return GatewayResponse(
            content=data.get("content", ""),
            model=data.get("model", ""),
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            stop_reason=data.get("stop_reason", "unknown"),
        )
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> GatewayResponse:
        """
        Generate a response from a single prompt.
        
        This is a convenience method that wraps invoke() for simple use cases.
        
        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            model: Model ID or alias.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.
            
        Returns:
            GatewayResponse: Response with content, usage stats, etc.
            
        Example:
            >>> response = client.generate("What is 2+2?")
            >>> print(response)
            "2 + 2 = 4"
        """
        messages = [{"role": "user", "content": prompt}]
        return self.invoke(
            messages=messages,
            model=model,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> GatewayResponse:
        """
        Continue a conversation with message history.
        
        Alias for invoke() with a clearer name for chat use cases.
        
        Args:
            messages: Conversation history as list of message dicts.
            system_prompt: Optional system prompt.
            model: Model ID or alias.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.
            
        Returns:
            GatewayResponse: Response with content, usage stats, etc.
            
        Example:
            >>> messages = [
            ...     {"role": "user", "content": "My name is Alice"},
            ...     {"role": "assistant", "content": "Nice to meet you, Alice!"},
            ...     {"role": "user", "content": "What's my name?"}
            ... ]
            >>> response = client.chat(messages)
            >>> print(response.content)
            "Your name is Alice."
        """
        return self.invoke(
            messages=messages,
            model=model,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    
    # ========================
    # Embedding Methods
    # ========================
    
    def embed(
        self,
        text: str,
        model: Optional[str] = None,
        dimensions: int = 1024,
        normalize: bool = True,
    ) -> EmbeddingResponse:
        """
        Generate an embedding for a single text.
        
        Args:
            text: The text to embed.
            model: Embedding model ID. Defaults to Titan Embed V2.
            dimensions: Embedding dimensions (default 1024).
            normalize: Whether to normalize the embedding (default True).
            
        Returns:
            EmbeddingResponse with embedding vector and metadata.
            
        Example:
            >>> response = client.embed("Hello world")
            >>> print(len(response.embedding))
            1024
        """
        payload = {
            "text": text,
            "dimensions": dimensions,
            "normalize": normalize,
        }
        if model:
            payload["model"] = model
        
        data = self._make_request("/embed", method="POST", json_data=payload)
        
        return EmbeddingResponse(
            embedding=data.get("embedding", []),
            model=data.get("model", ""),
            dimensions=data.get("dimensions", dimensions),
            input_tokens=data.get("input_tokens", 0),
        )
    
    def embed_documents(
        self,
        texts: List[str],
        model: Optional[str] = None,
        dimensions: int = 1024,
        normalize: bool = True,
    ) -> BatchEmbeddingResponse:
        """
        Generate embeddings for multiple texts in a single request.
        
        Args:
            texts: List of texts to embed (max 100).
            model: Embedding model ID. Defaults to Titan Embed V2.
            dimensions: Embedding dimensions (default 1024).
            normalize: Whether to normalize embeddings (default True).
            
        Returns:
            BatchEmbeddingResponse with list of embedding vectors.
            
        Example:
            >>> response = client.embed_documents(["Hello", "World"])
            >>> print(len(response.embeddings))
            2
        """
        payload = {
            "texts": texts,
            "dimensions": dimensions,
            "normalize": normalize,
        }
        if model:
            payload["model"] = model
        
        data = self._make_request("/embed", method="POST", json_data=payload)
        
        return BatchEmbeddingResponse(
            embeddings=data.get("embeddings", []),
            model=data.get("model", ""),
            dimensions=data.get("dimensions", dimensions),
            input_tokens=data.get("input_tokens", 0),
        )
    
    def embed_query(
        self,
        query: str,
        model: Optional[str] = None,
        dimensions: int = 1024,
    ) -> List[float]:
        """
        Embed a single query and return just the vector.
        
        Convenience method that returns the raw embedding list,
        matching the interface expected by the ToolRouter.
        
        Args:
            query: The query text to embed.
            model: Embedding model ID. Defaults to Titan Embed V2.
            dimensions: Embedding dimensions (default 1024).
            
        Returns:
            List of floats representing the embedding vector.
        """
        response = self.embed(text=query, model=model, dimensions=dimensions)
        return response.embedding
    
    def __repr__(self) -> str:
        return f"GatewayClient(url='{self.url}', model='{self.default_model}')"


# Convenience function for quick one-off calls
def quick_generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> str:
    """
    Quick one-liner to generate a response.
    
    Creates a temporary client and generates a response.
    For multiple calls, create a GatewayClient instance instead.
    
    Args:
        prompt: The user prompt.
        system_prompt: Optional system prompt.
        model: Model ID or alias.
        **kwargs: Additional arguments passed to generate().
        
    Returns:
        str: The generated response content.
        
    Example:
        >>> from llm_interactions.gateway_client import quick_generate
        >>> print(quick_generate("What is 2+2?"))
        "2 + 2 = 4"
    """
    client = GatewayClient()
    response = client.generate(prompt, system_prompt=system_prompt, model=model, **kwargs)
    return response.content


if __name__ == "__main__":
    # Example usage
    import sys
    
    # Load .env from project root
    load_dotenv()
    
    # Check if URL is configured
    url = os.getenv("GATEWAY_URL")
    if not url:
        log.error("Set GATEWAY_URL environment variable first:")
        log.info("  export GATEWAY_URL='https://your-api-id.execute-api.us-east-1.amazonaws.com'")
        sys.exit(1)
    
    client = GatewayClient()
    log.info(f"Client: {client}")
    response = client.generate("Hello", model="claude-4.5-sonnet")
    log.info(f"Response: {response.content}, the big response")
    # Health check
    log.info("\n--- Health Check ---")
    try:
        health = client.health()
        log.info(f"Status: {health.get('status')}")
        log.info(f"Region: {health.get('region')}")
        log.info(f"Default Model: {health.get('default_model')}")
    except GatewayError as e:
        log.error(f"Health check failed: {e}")
        sys.exit(1)
    
    # Generate
    log.info("\n--- Generate ---")
    try:
        response = client.generate(
            "What is 2+2? Reply in one word.",
            system_prompt="You are a math tutor. Be concise.",
            max_tokens=50,
        )
        log.info(f"Response: {response.content}")
        log.info(f"Tokens: {response.input_tokens} in, {response.output_tokens} out")
        log.info(f"Stop reason: {response.stop_reason}")
    except GatewayError as e:
        log.error(f"Generate failed: {e}")
