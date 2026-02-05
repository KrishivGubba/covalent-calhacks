"""
AI Gateway Lambda - Routes LLM requests to AWS Bedrock.

This Lambda serves as a secure gateway for the desktop app to access
Bedrock models without exposing credentials on the client side.

Endpoints:
    POST /invoke - Invoke a Bedrock model (Claude, etc.)
    POST /converse - Use Bedrock's Converse API for chat
    GET /health - Health check (no auth required)

Expected request body for /invoke:
{
    "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",  # Bedrock inference profile ID
    "messages": [{"role": "user", "content": "Hello!"}],
    "system": "You are a helpful assistant.",  # optional
    "max_tokens": 4096,  # optional
    "temperature": 0.7  # optional
}

Authentication:
    All endpoints except /health require a valid Auth0 JWT in the Authorization header.
    Set AUTH0_DOMAIN and AUTH0_AUDIENCE environment variables.
"""

import json
import logging
import os
from typing import Any, Dict, Optional
from functools import lru_cache

import boto3
from botocore.config import Config
import jwt
from jwt import PyJWKClient

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Bedrock client configuration
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "us.anthropic.claude-sonnet-4-20250514-v1:0")
DEFAULT_MAX_TOKENS = int(os.environ.get("DEFAULT_MAX_TOKENS", "4096"))
DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.7"))

# Auth0 JWT verification configuration
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")  # e.g., "dev-abc123.us.auth0.com"
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")  # e.g., "https://dev-abc123.us.auth0.com/api/v2/"
AUTH0_ALGORITHMS = ["RS256"]

# Cache the JWKS client (reused across invocations)
_jwks_client = None


def get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client for Auth0."""
    global _jwks_client
    if _jwks_client is None and AUTH0_DOMAIN:
        jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def verify_jwt(token: str) -> Dict[str, Any]:
    """
    Verify an Auth0 JWT and return the decoded payload.
    
    Raises:
        jwt.exceptions.InvalidTokenError: If token is invalid
    """
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise ValueError("AUTH0_DOMAIN and AUTH0_AUDIENCE must be configured")
    
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=AUTH0_ALGORITHMS,
        audience=AUTH0_AUDIENCE,
        issuer=f"https://{AUTH0_DOMAIN}/",
    )
    
    return payload


def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract the Bearer token from the Authorization header."""
    headers = event.get("headers", {}) or {}
    
    # Headers might be lowercase (API Gateway v2) or mixed case (v1)
    auth_header = headers.get("Authorization") or headers.get("authorization", "")
    
    if auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    
    return None


def authenticate_request(event: Dict[str, Any]) -> tuple[Optional[Dict], Optional[Dict]]:
    """
    Authenticate the request and return (user_payload, error_response).
    
    If authentication succeeds, returns (payload, None).
    If authentication fails, returns (None, error_response).
    """
    # Check if auth is configured
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        logger.warning("Auth0 not configured - allowing unauthenticated access")
        return ({"sub": "anonymous"}, None)
    
    token = extract_token(event)
    if not token:
        return (None, create_response(401, {"error": "Missing Authorization header"}))
    
    try:
        payload = verify_jwt(token)
        logger.info(f"Authenticated user: {payload.get('sub', 'unknown')}")
        return (payload, None)
    except jwt.ExpiredSignatureError:
        return (None, create_response(401, {"error": "Token has expired"}))
    except jwt.InvalidAudienceError:
        return (None, create_response(401, {"error": "Invalid token audience"}))
    except jwt.InvalidIssuerError:
        return (None, create_response(401, {"error": "Invalid token issuer"}))
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT validation failed: {e}")
        return (None, create_response(401, {"error": "Invalid token"}))
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return (None, create_response(500, {"error": "Authentication error"}))

# Allowed models (security: only allow specific models)
# Use inference profile format (us. prefix) for newer models
ALLOWED_MODELS = {
    # Claude 4.5 (inference profiles)
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # Claude 4 (inference profiles)
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    # Claude 3.5 (inference profiles)
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    # Claude 3.5 (on-demand - still works)
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    # Claude 3 models
    "anthropic.claude-3-opus-20240229-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    # Claude Instant
    "anthropic.claude-instant-v1",
    # Amazon Titan
    "amazon.titan-text-express-v1",
    "amazon.titan-text-lite-v1",
}

# Initialize Bedrock client (reused across invocations)
bedrock_config = Config(
    region_name=BEDROCK_REGION,
    retries={"max_attempts": 3, "mode": "adaptive"},
)
bedrock_runtime = boto3.client("bedrock-runtime", config=bedrock_config)


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a properly formatted API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # TODO: Restrict in production
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        },
        "body": json.dumps(body),
    }


def handle_options() -> Dict[str, Any]:
    """Handle CORS preflight requests."""
    return create_response(200, {"message": "OK"})


def handle_health() -> Dict[str, Any]:
    """Health check endpoint."""
    return create_response(200, {
        "status": "healthy",
        "region": BEDROCK_REGION,
        "default_model": DEFAULT_MODEL,
    })


def validate_request(body: Dict[str, Any]) -> Optional[str]:
    """Validate the request body. Returns error message if invalid, None if valid."""
    if not body:
        return "Request body is required"
    
    model = body.get("model", DEFAULT_MODEL)
    if model not in ALLOWED_MODELS:
        return f"Model '{model}' is not allowed. Allowed models: {list(ALLOWED_MODELS)}"
    
    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return "messages field is required and must be a list"
    
    for msg in messages:
        if not isinstance(msg, dict):
            return "Each message must be an object"
        if "role" not in msg or "content" not in msg:
            return "Each message must have 'role' and 'content' fields"
        if msg["role"] not in ["user", "assistant"]:
            return "Message role must be 'user' or 'assistant'"
    
    return None


def invoke_bedrock_converse(
    model: str,
    messages: list,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Dict[str, Any]:
    """
    Invoke Bedrock using the Converse API.
    
    This is the preferred API as it provides a unified interface
    across different model providers.
    """
    # Build the request
    request_params = {
        "modelId": model,
        "messages": [
            {
                "role": msg["role"],
                "content": [{"text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"],
            }
            for msg in messages
        ],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }
    
    # Add system prompt if provided
    if system:
        request_params["system"] = [{"text": system}]
    
    logger.info(f"Invoking Bedrock Converse API with model: {model}")
    
    response = bedrock_runtime.converse(**request_params)
    
    # Extract the response
    output = response.get("output", {})
    message = output.get("message", {})
    content = message.get("content", [])
    
    # Get text content
    text_content = ""
    for block in content:
        if "text" in block:
            text_content += block["text"]
    
    return {
        "content": text_content,
        "model": model,
        "usage": {
            "input_tokens": response.get("usage", {}).get("inputTokens", 0),
            "output_tokens": response.get("usage", {}).get("outputTokens", 0),
        },
        "stop_reason": response.get("stopReason", "unknown"),
    }


def invoke_bedrock_raw(
    model: str,
    messages: list,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Dict[str, Any]:
    """
    Invoke Bedrock using the raw InvokeModel API.
    
    This is a fallback for models that don't support Converse API.
    Currently configured for Anthropic Claude models.
    """
    # Build Claude-specific payload
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    
    if system:
        payload["system"] = system
    
    logger.info(f"Invoking Bedrock InvokeModel API with model: {model}")
    
    response = bedrock_runtime.invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(payload),
    )
    
    response_body = json.loads(response["body"].read())
    
    # Extract content from Claude response
    content = response_body.get("content", [])
    text_content = ""
    for block in content:
        if block.get("type") == "text":
            text_content += block.get("text", "")
    
    return {
        "content": text_content,
        "model": model,
        "usage": {
            "input_tokens": response_body.get("usage", {}).get("input_tokens", 0),
            "output_tokens": response_body.get("usage", {}).get("output_tokens", 0),
        },
        "stop_reason": response_body.get("stop_reason", "unknown"),
    }


def handle_invoke(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle the /invoke endpoint."""
    # Validate request
    error = validate_request(body)
    if error:
        return create_response(400, {"error": error})
    
    # Extract parameters
    model = body.get("model", DEFAULT_MODEL)
    messages = body["messages"]
    system = body.get("system")
    max_tokens = body.get("max_tokens", DEFAULT_MAX_TOKENS)
    temperature = body.get("temperature", DEFAULT_TEMPERATURE)
    
    # Use raw API for direct control (Converse API is the fallback)
    use_converse = body.get("use_converse", True)
    
    try:
        if use_converse:
            result = invoke_bedrock_converse(
                model=model,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            result = invoke_bedrock_raw(
                model=model,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        
        return create_response(200, result)
    
    except bedrock_runtime.exceptions.ValidationException as e:
        logger.error(f"Bedrock validation error: {e}")
        return create_response(400, {"error": f"Validation error: {str(e)}"})
    
    except bedrock_runtime.exceptions.ThrottlingException as e:
        logger.error(f"Bedrock throttling: {e}")
        return create_response(429, {"error": "Rate limit exceeded. Please retry later."})
    
    except bedrock_runtime.exceptions.ModelTimeoutException as e:
        logger.error(f"Bedrock timeout: {e}")
        return create_response(504, {"error": "Model invocation timed out."})
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_response(500, {"error": f"Internal server error: {str(e)}"})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler.
    
    Routes requests based on HTTP method and path.
    Authentication is required for all endpoints except /health and OPTIONS.
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Handle different event formats (API Gateway v1, v2, ALB)
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("path") or event.get("rawPath", "")
    
    # Handle CORS preflight (no auth required)
    if http_method == "OPTIONS":
        return handle_options()
    
    # Health check (no auth required)
    if path == "/health" or path.endswith("/health"):
        return handle_health()
    
    # --- All other endpoints require authentication ---
    user_payload, auth_error = authenticate_request(event)
    if auth_error:
        return auth_error
    
    # User is authenticated - user_payload contains JWT claims (sub, email, etc.)
    logger.info(f"Request authenticated for user: {user_payload.get('sub', 'unknown')}")
    
    if path == "/invoke" or path.endswith("/invoke"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        # Parse body
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_invoke(body)
    
    # Default: treat as invoke for backward compatibility
    if http_method == "POST":
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        return handle_invoke(body)
    
    return create_response(404, {"error": f"Not found: {path}"})


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "httpMethod": "POST",
        "path": "/invoke",
        "body": json.dumps({
            "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "messages": [{"role": "user", "content": "Hello! What's 2+2?"}],
            "system": "You are a helpful math assistant.",
            "max_tokens": 100,
        }),
    }
    
    # Note: This won't work without AWS credentials
    print("Test event:")
    print(json.dumps(test_event, indent=2))
