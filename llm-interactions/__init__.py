"""
LLM Interactions - Unified interface for interacting with different LLM providers.

This module provides a single entry point for all LLM interactions across the codebase.

Usage:
    import sys
    sys.path.insert(0, 'path/to/project')
    from llm_interactions import LLMClient
    
    client = LLMClient()
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

LLMClient = _llm_client_module.LLMClient

__all__ = ["LLMClient"]
