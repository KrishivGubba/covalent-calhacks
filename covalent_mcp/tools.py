"""
MCP Tools Registry.

This module imports all tool modules and registers them with the MCP server.

To add a new tool module:
  1. Copy toolclasses/_template.py → toolclasses/my_tool.py
  2. Implement your tool class (inherit from MCPToolModule)
  3. Create module instance: module = MyToolModule()
  4. Import in toolclasses/__init__.py: from .my_tool import module as my_tool_module
  5. Add to __all__ in toolclasses/__init__.py
  6. Import here: from mcp.toolclasses import my_tool_module
  7. Add to TOOL_MODULES list below
"""
from covalent_mcp.toolclasses.base import MCPToolModule
from fastmcp import FastMCP


# Add new tool modules here - each must be an instance of MCPToolModule
from covalent_mcp.toolclasses import github_module, calendar_module, gmail_module, drive_module

TOOL_MODULES: list[MCPToolModule] = [
    github_module,
    calendar_module,
    gmail_module,
    drive_module,
]


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