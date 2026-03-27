"""
MCP Tools Registry.

This module imports all tool modules and registers them with the MCP server.
It also builds a global display-schema registry used by the Flask server to
resolve human-readable approval UIs for tool calls.

To add a new tool module:
  1. Copy toolclasses/_template.py → toolclasses/my_tool.py
  2. Implement your tool class (inherit from MCPToolModule)
  3. Create module instance: module = MyToolModule()
  4. Import in toolclasses/__init__.py: from .my_tool import module as my_tool_module
  5. Add to __all__ in toolclasses/__init__.py
  6. Import here: from mcp.toolclasses import my_tool_module
  7. Add to TOOL_MODULES list below
"""
import sys
from pathlib import Path
from typing import Dict, Optional

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()
from covalent_mcp.toolclasses.base import MCPToolModule, ToolDisplaySchema
from fastmcp import FastMCP


# Add new tool modules here - each must be an instance of MCPToolModule
from covalent_mcp.toolclasses import (
    github_module,
    calendar_module,
    gmail_module,
    drive_module,
    docs_module,
    filesystem_module,
    perplexity_search_module,
    notion_module,
)

TOOL_MODULES: list[MCPToolModule] = [
    github_module,
    calendar_module,
    gmail_module,
    drive_module,
    docs_module,
    filesystem_module,
    perplexity_search_module,
    notion_module,
]


# =============================================================================
# DISPLAY SCHEMA REGISTRY
# =============================================================================

# Global registry: tool_name -> ToolDisplaySchema
# Built once at import time by collecting schemas from all modules.
_DISPLAY_SCHEMA_REGISTRY: Dict[str, ToolDisplaySchema] = {}


def _build_display_schema_registry() -> Dict[str, ToolDisplaySchema]:
    """Collect display schemas from all tool modules into a single dict."""
    registry: Dict[str, ToolDisplaySchema] = {}
    for tool_module in TOOL_MODULES:
        if not isinstance(tool_module, MCPToolModule):
            continue
        try:
            schemas = tool_module.get_display_schemas()
            for tool_name, schema in schemas.items():
                if tool_name in registry:
                    log.warning(
                        f"Warning: duplicate display schema for '{tool_name}', "
                        f"overwritten by {tool_module.__class__.__name__}"
                    )
                registry[tool_name] = schema
        except Exception as e:
            log.warning(f"Warning: failed to get display schemas from {tool_module.__class__.__name__}: {e}")
    return registry


def get_display_schema(tool_name: str) -> Optional[ToolDisplaySchema]:
    """
    Look up the display schema for a given tool name.

    Returns None if no schema is registered (caller should fall back to raw params).
    """
    global _DISPLAY_SCHEMA_REGISTRY
    if not _DISPLAY_SCHEMA_REGISTRY:
        _DISPLAY_SCHEMA_REGISTRY = _build_display_schema_registry()
    return _DISPLAY_SCHEMA_REGISTRY.get(tool_name)


def get_all_display_schemas() -> Dict[str, ToolDisplaySchema]:
    """Return the full display schema registry (tool_name -> schema)."""
    global _DISPLAY_SCHEMA_REGISTRY
    if not _DISPLAY_SCHEMA_REGISTRY:
        _DISPLAY_SCHEMA_REGISTRY = _build_display_schema_registry()
    return _DISPLAY_SCHEMA_REGISTRY


# =============================================================================
# PASSABLE OUTPUTS REGISTRY
# =============================================================================

def get_passable_outputs(tool_name: str) -> list:
    """
    Get the passable outputs for a given tool.
    
    Returns a list of PassableOutput objects (or empty list if none declared).
    """
    schema = get_display_schema(tool_name)
    if schema is None:
        return []
    return schema.passable_outputs or []


def get_all_passable_outputs() -> Dict[str, list]:
    """
    Get all passable outputs across all tools.
    
    Returns a dict: tool_name -> list of PassableOutput objects.
    Only includes tools that have passable outputs declared.
    """
    all_schemas = get_all_display_schemas()
    result = {}
    for tool_name, schema in all_schemas.items():
        if schema.passable_outputs:
            result[tool_name] = schema.passable_outputs
    return result


def format_passable_outputs_for_prompt() -> str:
    """
    Format all passable outputs as a string for the LLM planning prompt.
    
    Returns a formatted string like:
    - create_document: id (The unique document ID), webViewLink (URL to view the document)
    - create_event: id (The event ID), htmlLink (URL to view the event)
    """
    all_outputs = get_all_passable_outputs()
    if not all_outputs:
        return "(No tools have passable outputs declared)"
    
    lines = []
    for tool_name, outputs in sorted(all_outputs.items()):
        output_strs = [f"{o.key} ({o.description})" for o in outputs]
        lines.append(f"- {tool_name}: {', '.join(output_strs)}")
    
    return "\n".join(lines)


# =============================================================================
# TOOL REGISTRATION
# =============================================================================

def register_tools(mcp: FastMCP) -> None:
    """
    Register all tools and resources from TOOL_MODULES with the MCP server.
    
    This will call register(mcp) on each module, which must be implemented
    (enforced by MCPToolModule abstract base class).
    It will also call register_resources(mcp) if the module provides resources.
    
    Args:
        mcp: The FastMCP server instance
    
    Raises:
        TypeError: If a module doesn't inherit from MCPToolModule
        NotImplementedError: If a module doesn't implement register()
    """
    for tool_module in TOOL_MODULES:
        # Verify it's a proper tool module
        if not isinstance(tool_module, MCPToolModule):
            raise TypeError(
                f"Tool module {tool_module} must inherit from MCPToolModule"
            )
        
        # Register tools (will raise NotImplementedError if not implemented)
        tool_module.register(mcp)
        
        # Register resources (optional - default implementation does nothing)
        tool_module.register_resources(mcp)

    # Eagerly build the display schema registry so it's ready for the server
    global _DISPLAY_SCHEMA_REGISTRY
    _DISPLAY_SCHEMA_REGISTRY = _build_display_schema_registry()
    log.info(f"📋 Display schemas registered for {len(_DISPLAY_SCHEMA_REGISTRY)} tools: {list(_DISPLAY_SCHEMA_REGISTRY.keys())}")