"""
AI Gateway Lambda - Routes LLM requests to AWS Bedrock and handles OAuth token exchange.

This Lambda serves as a secure gateway for the desktop app to access
Bedrock models and exchange OAuth tokens without exposing credentials on the client side.

Endpoints:
    POST /invoke - Invoke a Bedrock model (Claude, etc.)
    POST /converse - Use Bedrock's Converse API for chat
    POST /embed - Generate text embeddings via Bedrock (Titan Embed V2)
    GET /health - Health check (no auth required)
    
    Google OAuth (protected by Auth0 JWT):
    POST /integrations/google/exchange - Exchange auth code for tokens
    POST /integrations/google/refresh - Refresh access token
    
    GitHub OAuth (protected by Auth0 JWT):
    POST /integrations/github/exchange - Exchange auth code for tokens
    
    Notion OAuth (protected by Auth0 JWT):
    POST /integrations/notion/exchange - Exchange auth code for tokens
    POST /integrations/notion/refresh - Refresh access token

Expected request body for /invoke:
{
    "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",  # Bedrock inference profile ID
    "messages": [{"role": "user", "content": "Hello!"}],
    "system": "You are a helpful assistant.",  # optional
    "max_tokens": 4096,  # optional
    "temperature": 0.7  # optional
}

Expected request body for /embed:
{
    "text": "single text to embed",            # for single embedding
    "texts": ["text1", "text2"],               # for batch embeddings (use text OR texts)
    "model": "amazon.titan-embed-text-v2:0",   # optional, defaults to Titan Embed V2
    "dimensions": 1024,                         # optional, defaults to 1024
    "normalize": true                           # optional, defaults to true
}

Authentication:
    All endpoints except /health require a valid Auth0 JWT in the Authorization header.
    Set AUTH0_DOMAIN and AUTH0_AUDIENCE environment variables.
"""

import base64
import http.client
import json
import logging
import os
import ssl
import urllib.request
import urllib.parse
import urllib.error
from decimal import Decimal
from typing import Any, Dict, Optional
from functools import lru_cache

from budget_metadata import get_or_create_budget_row_minimal, sync_budget_user_row

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

# Budget tracking configuration
BUDGET_TABLE_NAME = os.environ.get("BUDGET_TABLE_NAME", "")
DEFAULT_BUDGET_LIMIT = float(os.environ.get("DEFAULT_BUDGET_LIMIT", "10.00"))

# Per-token pricing (USD) for each model — used to calculate request cost.
# Prices are per token (not per 1K). Multiply by token count to get cost.
# Source: AWS Bedrock pricing as of 2025. Update when pricing changes.
MODEL_PRICING = {
    # Claude 4.5 (inference profiles)
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0":  {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    # Claude 4 (inference profiles)
    "us.anthropic.claude-sonnet-4-20250514-v1:0":   {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    # Claude 3.5 (inference profiles)
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "us.anthropic.claude-3-5-haiku-20241022-v1:0":  {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    # Claude 3.5 (on-demand)
    "anthropic.claude-3-5-sonnet-20241022-v2:0":    {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "anthropic.claude-3-5-haiku-20241022-v1:0":     {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    # Claude 3 models
    "anthropic.claude-3-opus-20240229-v1:0":        {"input": 15.00 / 1_000_000, "output": 75.00 / 1_000_000},
    "anthropic.claude-3-sonnet-20240229-v1:0":      {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "anthropic.claude-3-haiku-20240307-v1:0":       {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
    # Claude Instant
    "anthropic.claude-instant-v1":                  {"input": 0.80 / 1_000_000, "output": 2.40 / 1_000_000},
    # Amazon Titan (text)
    "amazon.titan-text-express-v1":                 {"input": 0.20 / 1_000_000, "output": 0.60 / 1_000_000},
    "amazon.titan-text-lite-v1":                    {"input": 0.15 / 1_000_000, "output": 0.20 / 1_000_000},
    # Amazon Titan (embeddings) — output is a vector, not tokens, so output cost is 0
    "amazon.titan-embed-text-v2:0":                 {"input": 0.02 / 1_000_000, "output": 0.0},
    "amazon.titan-embed-text-v1":                   {"input": 0.10 / 1_000_000, "output": 0.0},
}

# Google OAuth configuration (for token exchange - secret stored securely here)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# GitHub OAuth configuration (for token exchange - using Lambda for consistency with Google)
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Notion OAuth configuration (for token exchange - uses Basic Auth with client_id:client_secret)
NOTION_CLIENT_ID = os.environ.get("NOTION_CLIENT_ID", "")
NOTION_CLIENT_SECRET = os.environ.get("NOTION_CLIENT_SECRET", "")

# GitHub PAT for proxying private release assets to the Tauri updater
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "hem8705/covalent-calhacks")
GITHUB_API_BASE = "https://api.github.com"

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

# Allowed embedding models
DEFAULT_EMBEDDING_MODEL = os.environ.get("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
DEFAULT_EMBEDDING_DIMENSIONS = int(os.environ.get("DEFAULT_EMBEDDING_DIMENSIONS", "1024"))
ALLOWED_EMBEDDING_MODELS = {
    "amazon.titan-embed-text-v2:0",
    "amazon.titan-embed-text-v1",
}

# Initialize Bedrock client (reused across invocations)
bedrock_config = Config(
    region_name=BEDROCK_REGION,
    retries={"max_attempts": 3, "mode": "adaptive"},
)
bedrock_runtime = boto3.client("bedrock-runtime", config=bedrock_config)

# Initialize DynamoDB client for budget tracking
_dynamodb = None


def get_dynamodb_table():
    """Get the DynamoDB table resource for budget tracking."""
    global _dynamodb
    if _dynamodb is None and BUDGET_TABLE_NAME:
        _dynamodb = boto3.resource("dynamodb").Table(BUDGET_TABLE_NAME)
    return _dynamodb


def calculate_request_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the USD cost of a Bedrock request from token counts."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        logger.warning(f"No pricing info for model {model}, using Sonnet pricing as fallback")
        pricing = {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000}
    return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])


def get_user_budget(
    user_id: str, jwt_payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fetch the user's budget record from DynamoDB.

    For authenticated users (non-anonymous), refreshes human-readable JWT metadata
    on the row (display name, email, picture, etc.) and returns spend/limit.
    """
    table = get_dynamodb_table()
    if not table:
        logger.warning("Budget table not configured — skipping budget check")
        return {"total_spend": 0.0, "budget_limit": float("inf")}

    try:
        if user_id != "anonymous":
            return sync_budget_user_row(
                table, user_id, jwt_payload or {}, DEFAULT_BUDGET_LIMIT
            )
        return get_or_create_budget_row_minimal(
            table, user_id, DEFAULT_BUDGET_LIMIT
        )
    except Exception as e:
        logger.error(f"DynamoDB get_user_budget error: {e}")
        # Fail open — don't block requests if DynamoDB is down
        return {"total_spend": 0.0, "budget_limit": float("inf")}


def record_spend(user_id: str, cost: float) -> None:
    """Atomically increment the user's total_spend in DynamoDB."""
    table = get_dynamodb_table()
    if not table or cost <= 0:
        return

    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET total_spend = if_not_exists(total_spend, :zero) + :cost",
            ExpressionAttributeValues={
                ":cost": Decimal(str(round(cost, 8))),
                ":zero": Decimal("0"),
            },
        )
        logger.info(f"Recorded ${cost:.6f} spend for user {user_id}")
    except Exception as e:
        logger.error(f"DynamoDB record_spend error: {e}")


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


def handle_invoke(
    body: Dict[str, Any],
    user_id: str = "anonymous",
    jwt_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle the /invoke endpoint with budget enforcement."""
    # Validate request
    error = validate_request(body)
    if error:
        return create_response(400, {"error": error})
    
    # --- Budget pre-check: reject if user is already over budget ---
    budget = get_user_budget(user_id, jwt_payload)
    remaining = budget["budget_limit"] - budget["total_spend"]
    if remaining <= 0:
        logger.warning(f"User {user_id} over budget: spent ${budget['total_spend']:.4f} / ${budget['budget_limit']:.2f}")
        return create_response(429, {
            "error": "Budget exceeded",
            "total_spend": round(budget["total_spend"], 6),
            "budget_limit": round(budget["budget_limit"], 2),
            "remaining": 0.0,
        })
    
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
        
        # --- Budget post-call: calculate actual cost and record spend ---
        input_tokens = result.get("usage", {}).get("input_tokens", 0)
        output_tokens = result.get("usage", {}).get("output_tokens", 0)
        cost = calculate_request_cost(model, input_tokens, output_tokens)
        record_spend(user_id, cost)
        
        # Include cost info in the response so the client can display it
        result["cost"] = {
            "request_cost": round(cost, 8),
            "total_spend": round(budget["total_spend"] + cost, 6),
            "budget_limit": round(budget["budget_limit"], 2),
            "remaining": round(max(0, remaining - cost), 6),
        }
        
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


# ========================
# Embedding Handler
# ========================

def handle_embed(
    body: Dict[str, Any],
    user_id: str = "anonymous",
    jwt_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Handle the /embed endpoint with budget enforcement.
    
    Supports single text or batch embedding via Bedrock Titan Embed V2.
    
    Single: {"text": "hello"} -> {"embedding": [...], ...}
    Batch:  {"texts": ["hello", "world"]} -> {"embeddings": [[...], [...]], ...}
    """
    if not body:
        return create_response(400, {"error": "Request body is required"})
    
    # Determine single vs batch
    single_text = body.get("text")
    batch_texts = body.get("texts")
    
    if single_text is None and batch_texts is None:
        return create_response(400, {"error": "Either 'text' (string) or 'texts' (list of strings) is required"})
    
    if single_text is not None and batch_texts is not None:
        return create_response(400, {"error": "Provide either 'text' or 'texts', not both"})
    
    # --- Budget pre-check: reject if user is already over budget ---
    budget = get_user_budget(user_id, jwt_payload)
    remaining = budget["budget_limit"] - budget["total_spend"]
    if remaining <= 0:
        logger.warning(f"User {user_id} over budget: spent ${budget['total_spend']:.4f} / ${budget['budget_limit']:.2f}")
        return create_response(429, {
            "error": "Budget exceeded",
            "total_spend": round(budget["total_spend"], 6),
            "budget_limit": round(budget["budget_limit"], 2),
            "remaining": 0.0,
        })
    
    model = body.get("model", DEFAULT_EMBEDDING_MODEL)
    if model not in ALLOWED_EMBEDDING_MODELS:
        return create_response(400, {
            "error": f"Embedding model '{model}' is not allowed. Allowed: {list(ALLOWED_EMBEDDING_MODELS)}"
        })
    
    dimensions = body.get("dimensions", DEFAULT_EMBEDDING_DIMENSIONS)
    normalize = body.get("normalize", True)
    
    # Build list of texts to embed
    if single_text is not None:
        texts_to_embed = [single_text]
    else:
        if not isinstance(batch_texts, list) or not batch_texts:
            return create_response(400, {"error": "'texts' must be a non-empty list of strings"})
        if len(batch_texts) > 100:
            return create_response(400, {"error": "'texts' list cannot exceed 100 items"})
        texts_to_embed = batch_texts
    
    try:
        all_embeddings = []
        total_input_tokens = 0
        
        for text in texts_to_embed:
            if not isinstance(text, str) or not text.strip():
                return create_response(400, {"error": "Each text must be a non-empty string"})
            
            payload = {
                "inputText": text,
                "dimensions": dimensions,
                "normalize": normalize,
            }
            
            response = bedrock_runtime.invoke_model(
                modelId=model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
            
            response_body = json.loads(response["body"].read())
            all_embeddings.append(response_body.get("embedding", []))
            total_input_tokens += response_body.get("inputTextTokenCount", 0)
        
        # --- Budget post-call: calculate actual cost and record spend ---
        cost = calculate_request_cost(model, total_input_tokens, 0)
        record_spend(user_id, cost)
        
        cost_info = {
            "request_cost": round(cost, 8),
            "total_spend": round(budget["total_spend"] + cost, 6),
            "budget_limit": round(budget["budget_limit"], 2),
            "remaining": round(max(0, remaining - cost), 6),
        }
        
        # Return single vs batch format
        if single_text is not None:
            return create_response(200, {
                "embedding": all_embeddings[0],
                "model": model,
                "dimensions": dimensions,
                "input_tokens": total_input_tokens,
                "cost": cost_info,
            })
        else:
            return create_response(200, {
                "embeddings": all_embeddings,
                "model": model,
                "dimensions": dimensions,
                "input_tokens": total_input_tokens,
                "cost": cost_info,
            })
    
    except bedrock_runtime.exceptions.ValidationException as e:
        logger.error(f"Bedrock embedding validation error: {e}")
        return create_response(400, {"error": f"Validation error: {str(e)}"})
    
    except bedrock_runtime.exceptions.ThrottlingException as e:
        logger.error(f"Bedrock embedding throttling: {e}")
        return create_response(429, {"error": "Rate limit exceeded. Please retry later."})
    
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return create_response(500, {"error": f"Embedding error: {str(e)}"})


# ========================
# Google OAuth Handlers
# ========================

def handle_google_exchange(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exchange Google auth code for tokens.
    
    Body: {
        "code": "auth_code_from_google",
        "code_verifier": "pkce_verifier",
        "redirect_uri": "http://127.0.0.1:{FLASK_PORT}/integrations/google/callback"
    }
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return create_response(500, {"error": "Google OAuth not configured on server"})
    
    code = body.get("code")
    code_verifier = body.get("code_verifier")
    redirect_uri = body.get("redirect_uri")
    
    if not code or not code_verifier or not redirect_uri:
        return create_response(400, {"error": "code, code_verifier, and redirect_uri are required"})
    
    # Exchange code for tokens
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    
    try:
        encoded_data = urllib.parse.urlencode(token_data).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        logger.info("Google token exchange successful")
        return create_response(200, {
            "access_token": result.get("access_token"),
            "refresh_token": result.get("refresh_token"),
            "expires_in": result.get("expires_in"),
            "scope": result.get("scope"),
            "token_type": result.get("token_type"),
        })
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Google token exchange failed: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(400, {
                "error": error_json.get("error", "token_exchange_failed"),
                "error_description": error_json.get("error_description", "Token exchange failed"),
            })
        except json.JSONDecodeError:
            return create_response(400, {"error": "token_exchange_failed", "error_description": error_body})
    except Exception as e:
        logger.error(f"Google token exchange error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


def handle_google_refresh(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refresh Google access token.
    
    Body: {
        "refresh_token": "the_refresh_token"
    }
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return create_response(500, {"error": "Google OAuth not configured on server"})
    
    refresh_token = body.get("refresh_token")
    
    if not refresh_token:
        return create_response(400, {"error": "refresh_token is required"})
    
    # Refresh the token
    token_data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    
    try:
        encoded_data = urllib.parse.urlencode(token_data).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        logger.info("Google token refresh successful")
        return create_response(200, {
            "access_token": result.get("access_token"),
            "expires_in": result.get("expires_in"),
            "scope": result.get("scope"),
            "token_type": result.get("token_type"),
        })
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Google token refresh failed: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(400, {
                "error": error_json.get("error", "refresh_failed"),
                "error_description": error_json.get("error_description", "Token refresh failed"),
            })
        except json.JSONDecodeError:
            return create_response(400, {"error": "refresh_failed", "error_description": error_body})
    except Exception as e:
        logger.error(f"Google token refresh error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


def handle_github_exchange(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exchange GitHub auth code for access token.
    
    Body: {
        "code": "auth_code_from_github",
        "code_verifier": "pkce_verifier",
        "redirect_uri": "http://127.0.0.1:{FLASK_PORT}/integrations/github/callback"
    }
    
    Note: GitHub OAuth Apps require both client_id and client_secret for token exchange.
    """
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return create_response(500, {"error": "GitHub OAuth not configured on server (missing client_id or client_secret)"})
    
    code = body.get("code")
    code_verifier = body.get("code_verifier")
    redirect_uri = body.get("redirect_uri")
    
    if not code or not code_verifier or not redirect_uri:
        return create_response(400, {"error": "code, code_verifier, and redirect_uri are required"})
    
    # Exchange code for tokens
    # GitHub's token endpoint accepts form-encoded data
    # Note: GitHub OAuth Apps require client_secret for token exchange
    token_data = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    
    try:
        encoded_data = urllib.parse.urlencode(token_data).encode("utf-8")
        req = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=encoded_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",  # GitHub returns form-encoded by default, request JSON
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        # Check for error in response (GitHub returns 200 even on errors)
        if "error" in result:
            logger.error(f"GitHub token exchange error: {result}")
            return create_response(400, {
                "error": result.get("error"),
                "error_description": result.get("error_description", result.get("error")),
            })
        
        logger.info("GitHub token exchange successful")
        return create_response(200, {
            "access_token": result.get("access_token"),
            "token_type": result.get("token_type"),
            "scope": result.get("scope"),
        })
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"GitHub token exchange failed: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(400, {
                "error": error_json.get("error", "token_exchange_failed"),
                "error_description": error_json.get("error_description", "Token exchange failed"),
            })
        except json.JSONDecodeError:
            return create_response(400, {"error": "token_exchange_failed", "error_description": error_body})
    except Exception as e:
        logger.error(f"GitHub token exchange error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


def handle_notion_exchange(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exchange Notion auth code for access token.
    
    Body: {
        "code": "auth_code_from_notion",
        "redirect_uri": "http://localhost:{FLASK_PORT}/integrations/notion/callback"
    }
    
    Note: Notion uses Basic Auth (base64 of client_id:client_secret) for token exchange.
    """
    if not NOTION_CLIENT_ID or not NOTION_CLIENT_SECRET:
        return create_response(500, {"error": "Notion OAuth not configured on server (missing client_id or client_secret)"})
    
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    
    if not code or not redirect_uri:
        return create_response(400, {"error": "code and redirect_uri are required"})
    
    # Exchange code for token
    # Notion requires Basic Auth: base64(client_id:client_secret)
    token_data = json.dumps({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")
    
    credentials = base64.b64encode(f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()).decode()
    
    try:
        req = urllib.request.Request(
            "https://api.notion.com/v1/oauth/token",
            data=token_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credentials}",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        # Check for error in response
        if "error" in result:
            logger.error(f"Notion token exchange error: {result}")
            return create_response(400, {
                "error": result.get("error"),
                "error_description": result.get("error", "Token exchange failed"),
            })
        
        logger.info("Notion token exchange successful")
        return create_response(200, {
            "access_token": result.get("access_token"),
            "refresh_token": result.get("refresh_token"),  # Notion provides refresh tokens
            "token_type": result.get("token_type"),
            "bot_id": result.get("bot_id"),
            "workspace_id": result.get("workspace_id"),
            "workspace_name": result.get("workspace_name"),
            "workspace_icon": result.get("workspace_icon"),
            "duplicated_template_id": result.get("duplicated_template_id"),
            "owner": result.get("owner"),
        })
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Notion token exchange failed: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(400, {
                "error": error_json.get("error", "token_exchange_failed"),
                "error_description": error_json.get("message", "Token exchange failed"),
            })
        except json.JSONDecodeError:
            return create_response(400, {"error": "token_exchange_failed", "error_description": error_body})
    except Exception as e:
        logger.error(f"Notion token exchange error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


def handle_notion_refresh(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refresh Notion access token using the refresh token.
    
    Body: {
        "refresh_token": "the_refresh_token"
    }
    
    Note: Notion uses Basic Auth (base64 of client_id:client_secret) for token refresh,
    same as token exchange.
    """
    if not NOTION_CLIENT_ID or not NOTION_CLIENT_SECRET:
        return create_response(500, {"error": "Notion OAuth not configured on server (missing client_id or client_secret)"})
    
    refresh_token = body.get("refresh_token")
    
    if not refresh_token:
        return create_response(400, {"error": "refresh_token is required"})
    
    # Refresh the token
    # Notion requires Basic Auth: base64(client_id:client_secret)
    token_data = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")
    
    credentials = base64.b64encode(f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()).decode()
    
    try:
        req = urllib.request.Request(
            "https://api.notion.com/v1/oauth/token",
            data=token_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credentials}",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        # Check for error in response
        if "error" in result:
            logger.error(f"Notion token refresh error: {result}")
            return create_response(400, {
                "error": result.get("error", "refresh_failed"),
                "error_description": result.get("message", "Token refresh failed"),
            })
        
        logger.info("Notion token refresh successful")
        return create_response(200, {
            "access_token": result.get("access_token"),
            "refresh_token": result.get("refresh_token"),  # Notion may rotate refresh tokens
            "expires_in": result.get("expires_in"),
            "token_type": result.get("token_type"),
            "bot_id": result.get("bot_id"),
            "workspace_id": result.get("workspace_id"),
        })
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Notion token refresh failed: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(400, {
                "error": error_json.get("error", "refresh_failed"),
                "error_description": error_json.get("message", "Token refresh failed"),
            })
        except json.JSONDecodeError:
            return create_response(400, {"error": "refresh_failed", "error_description": error_body})
    except Exception as e:
        logger.error(f"Notion token refresh error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


# ========================
# App Update Proxy
# ========================

def _get_temp_download_url(asset_api_url: str, pat: str) -> Optional[str]:
    """
    Get a temporary public download URL for a GitHub release asset.

    GitHub responds with a 302 redirect to a time-limited S3 URL when
    a release asset is requested with Accept: application/octet-stream.
    We capture that redirect URL instead of following it.
    """
    parsed = urllib.parse.urlparse(asset_api_url)
    conn = http.client.HTTPSConnection(parsed.hostname, context=ssl.create_default_context())
    conn.request("GET", parsed.path, headers={
        "Accept": "application/octet-stream",
        "Authorization": f"token {pat}",
        "User-Agent": "Covalent-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    resp = conn.getresponse()
    location = resp.getheader("Location") if resp.status in (301, 302, 303, 307) else None
    conn.close()
    return location


def handle_updates_latest() -> Dict[str, Any]:
    """
    Proxy the Tauri updater's latest.json from a private GitHub release.

    1. Fetches the latest release metadata from the GitHub API.
    2. Downloads the latest.json asset from that release.
    3. Rewrites the platform download URLs to temporary public S3 URLs
       so the Tauri updater can download the binary without auth.
    4. Returns the modified latest.json.
    """
    if not GITHUB_PAT:
        return create_response(500, {"error": "GitHub PAT not configured"})

    github_headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Covalent-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        # 1. Fetch latest release metadata
        release_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(release_url, headers=github_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            release = json.loads(response.read().decode("utf-8"))

        assets = release.get("assets", [])
        if not assets:
            return create_response(404, {"error": "No assets found in latest release"})

        # 2. Find the latest.json asset
        latest_json_asset = None
        for asset in assets:
            if asset["name"] == "latest.json":
                latest_json_asset = asset
                break

        if not latest_json_asset:
            return create_response(404, {"error": "latest.json not found in release assets"})

        # 3. Download latest.json content (urllib follows the S3 redirect automatically)
        download_headers = {
            "Authorization": f"token {GITHUB_PAT}",
            "Accept": "application/octet-stream",
            "User-Agent": "Covalent-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        req = urllib.request.Request(latest_json_asset["url"], headers=download_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            latest_json = json.loads(response.read().decode("utf-8"))

        # 4. Build name -> asset lookup
        asset_by_name = {a["name"]: a for a in assets}

        # 5. Rewrite each platform's download URL to a temporary public URL
        platforms = latest_json.get("platforms", {})
        for platform_key, platform_data in platforms.items():
            url = platform_data.get("url", "")
            if not url:
                continue

            filename = url.split("/")[-1]
            asset = asset_by_name.get(filename)
            if not asset:
                logger.warning(f"Asset '{filename}' not found in release for platform {platform_key}")
                continue

            temp_url = _get_temp_download_url(asset["url"], GITHUB_PAT)
            if temp_url:
                platform_data["url"] = temp_url
                logger.info(f"Rewrote download URL for {platform_key}")
            else:
                logger.warning(f"Could not get temp URL for {filename}")

        # 6. Return the modified latest.json
        return create_response(200, latest_json)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"GitHub API error: {e.code} - {error_body}")
        if e.code == 404:
            return create_response(404, {"error": "No releases found"})
        return create_response(502, {"error": "GitHub API error", "details": error_body})
    except Exception as e:
        logger.error(f"Update proxy error: {e}")
        return create_response(500, {"error": f"Update proxy error: {str(e)}"})


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
    
    user_id = user_payload.get("sub", "anonymous")

    # App update check (returns modified latest.json with temporary download URLs)
    if path == "/updates/latest" or path.endswith("/updates/latest"):
        if http_method != "GET":
            return create_response(405, {"error": "Method not allowed. Use GET."})
        return handle_updates_latest()

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
        
        return handle_invoke(body, user_id=user_id, jwt_payload=user_payload)
    
    # Embedding endpoint
    if path == "/embed" or path.endswith("/embed"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_embed(body, user_id=user_id, jwt_payload=user_payload)
    
    # Google OAuth token exchange
    if path == "/integrations/google/exchange" or path.endswith("/integrations/google/exchange"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_google_exchange(body)
    
    # Google OAuth token refresh
    if path == "/integrations/google/refresh" or path.endswith("/integrations/google/refresh"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_google_refresh(body)
    
    # GitHub OAuth token exchange
    if path == "/integrations/github/exchange" or path.endswith("/integrations/github/exchange"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_github_exchange(body)
    
    # Notion OAuth token exchange
    if path == "/integrations/notion/exchange" or path.endswith("/integrations/notion/exchange"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_notion_exchange(body)
    
    # Notion OAuth token refresh
    if path == "/integrations/notion/refresh" or path.endswith("/integrations/notion/refresh"):
        if http_method != "POST":
            return create_response(405, {"error": "Method not allowed. Use POST."})
        
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        
        return handle_notion_refresh(body)
    
    # Default: treat as invoke for backward compatibility
    if http_method == "POST":
        body = event.get("body", "{}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {"error": "Invalid JSON in request body"})
        return handle_invoke(body, user_id=user_id, jwt_payload=user_payload)
    
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
