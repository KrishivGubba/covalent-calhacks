"""
LLM Interactions - Unified interface for interacting with different LLM providers.

This module provides a single entry point for all LLM interactions across the codebase.

Usage:
    # Direct API calls (requires API keys)
    from llm_interactions import LLMClient
    client = LLMClient()
    response = client.generate("Hello!")
    
    # Via Lambda Gateway (no API keys needed on client)
    from llm_interactions import GatewayClient
    client = GatewayClient()
    response = client.generate("Hello!")
"""

import importlib.util
from pathlib import Path

# Load llm_client module directly (handles hyphenated directory name)
_spec = importlib.util.spec_from_file_location(
    "llm_client",
    Path(__file__).parent / "llm_client.py"
)
_llm_client_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_llm_client_module)

# Load gateway_client module
_gw_spec = importlib.util.spec_from_file_location(
    "gateway_client",
    Path(__file__).parent / "gateway_client.py"
)
_gateway_client_module = importlib.util.module_from_spec(_gw_spec)
_gw_spec.loader.exec_module(_gateway_client_module)

# Export classes
LLMClient = _llm_client_module.LLMClient
GatewayClient = _gateway_client_module.GatewayClient
GatewayResponse = _gateway_client_module.GatewayResponse
GatewayError = _gateway_client_module.GatewayError
MODELS = _gateway_client_module.MODELS
quick_generate = _gateway_client_module.quick_generate

__all__ = [
    "LLMClient",
    "GatewayClient", 
    "GatewayResponse",
    "GatewayError",
    "MODELS",
    "quick_generate",
]
