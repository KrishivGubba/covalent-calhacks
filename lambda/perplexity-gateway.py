"""
Perplexity Gateway Lambda - Proxies Perplexity API requests securely.

This Lambda serves as a secure gateway for the desktop app to access
Perplexity Search API without exposing the API key on the client side.

Endpoints:
    POST /search - Perform a Perplexity search
    GET /health - Health check (no auth required)

Authentication:
    All endpoints except /health require a valid Auth0 JWT in the Authorization header.
    Set AUTH0_DOMAIN and AUTH0_AUDIENCE environment variables.
"""

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from functools import lru_cache

import jwt
from jwt import PyJWKClient

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Perplexity API configuration
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/search"

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
    if jwks_client is None:
        raise ValueError("Failed to initialize JWKS client")
    
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    
    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=AUTH0_ALGORITHMS,
        audience=AUTH0_AUDIENCE,
        issuer=f"https://{AUTH0_DOMAIN}/",
    )
    
    return decoded


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Lambda response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        },
        "body": json.dumps(body),
    }


def handle_health() -> Dict[str, Any]:
    """Health check endpoint - no auth required."""
    return create_response(200, {
        "status": "healthy",
        "service": "perplexity-gateway",
        "perplexity_configured": bool(PERPLEXITY_API_KEY),
        "auth0_configured": bool(AUTH0_DOMAIN and AUTH0_AUDIENCE),
    })


def handle_search(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a Perplexity search.
    
    Body: {
        "query": "search query" or ["query1", "query2"],
        "max_results": 10,
        "max_tokens": 25000,
        "max_tokens_per_page": 2048,
        "country": "US",
        "search_domain_filter": ["domain1.com", "-excluded.com"],
        "search_language_filter": ["en", "fr"],
        "search_mode": "web" | "academic" | "sec",
        "search_recency_filter": "hour" | "day" | "week" | "month" | "year",
        "search_after_date_filter": "YYYY-MM-DD",
        "search_before_date_filter": "YYYY-MM-DD",
        "last_updated_after_filter": "YYYY-MM-DD",
        "last_updated_before_filter": "YYYY-MM-DD"
    }
    """
    if not PERPLEXITY_API_KEY:
        return create_response(500, {"error": "Perplexity API key not configured"})
    
    query = body.get("query")
    if not query:
        return create_response(400, {"error": "query is required"})
    
    # Build request payload for Perplexity API
    payload = {
        "query": query,
        "max_results": body.get("max_results", 10),
        "max_tokens_per_page": body.get("max_tokens_per_page", 2048),
    }
    
    # Add optional parameters if provided
    optional_params = [
        "max_tokens", "country", "search_domain_filter", "search_language_filter",
        "search_mode", "search_recency_filter", "search_after_date_filter",
        "search_before_date_filter", "last_updated_after_filter", "last_updated_before_filter"
    ]
    
    for param in optional_params:
        if param in body and body[param] is not None:
            payload[param] = body[param]
    
    try:
        # Call Perplexity API
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            PERPLEXITY_API_URL,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        logger.info(f"Perplexity search successful for query: {query[:50] if isinstance(query, str) else query}")
        
        # Return the raw Perplexity response
        return create_response(200, result)
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Perplexity API error: {e.code} - {error_body}")
        try:
            error_json = json.loads(error_body)
            return create_response(e.code, {
                "error": error_json.get("error", "perplexity_api_error"),
                "error_description": error_json.get("message", error_body),
            })
        except json.JSONDecodeError:
            return create_response(e.code, {
                "error": "perplexity_api_error",
                "error_description": error_body,
            })
    except Exception as e:
        logger.error(f"Perplexity search error: {e}")
        return create_response(500, {"error": "internal_error", "error_description": str(e)})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler.
    
    Routes requests based on path and method.
    """
    logger.info(f"Received event: {json.dumps(event)[:500]}")
    
    # Handle API Gateway v2 format
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    method = http.get("method", event.get("httpMethod", ""))
    path = http.get("path", event.get("path", ""))
    
    # Handle CORS preflight
    if method == "OPTIONS":
        return create_response(200, {"message": "CORS OK"})
    
    # Health check - no auth required
    if path == "/health" or path.endswith("/health"):
        return handle_health()
    
    # All other endpoints require Auth0 JWT
    auth_header = event.get("headers", {}).get("authorization", "")
    if not auth_header.startswith("Bearer "):
        auth_header = event.get("headers", {}).get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        return create_response(401, {"error": "Missing or invalid Authorization header"})
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    try:
        decoded_token = verify_jwt(token)
        logger.info(f"Authenticated user: {decoded_token.get('sub', 'unknown')}")
    except jwt.exceptions.InvalidTokenError as e:
        logger.warning(f"JWT verification failed: {e}")
        return create_response(401, {"error": "Invalid token", "details": str(e)})
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return create_response(401, {"error": "Authentication failed", "details": str(e)})
    
    # Parse request body
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            return create_response(400, {"error": "Invalid JSON body"})
    
    # Route to handler
    if (path == "/search" or path.endswith("/search")) and method == "POST":
        return handle_search(body)
    
    return create_response(404, {"error": "Not found", "path": path, "method": method})
