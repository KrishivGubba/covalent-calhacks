"""
Tool Modules - All MCP tool modules.

Each module must:
  1. Inherit from MCPToolModule
  2. Implement register(mcp) method
  3. Export a 'module' instance

Import modules here and add to __all__.
"""
from covalent_mcp.toolclasses.weather import module as weather_module
from covalent_mcp.toolclasses.email_tool import module as email_module

__all__ = ["weather_module", "email_module"]
