"""
Base MCP Tool Module - Abstract base class for all tool modules.

All tool modules MUST inherit from this and implement the register() method.
This enforces the contract that every tool module must define how to register its tools.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for type-checking; avoid import-time dependency.
    from fastmcp import FastMCP


class MCPToolModule(ABC):
    """
    Abstract base class for MCP tool modules.
    
    Every tool module must inherit from this and implement register(mcp).
    Optionally, implement register_resources(mcp) to expose read-only resources.
    This ensures a consistent interface across all tool modules.
    
    Example:
        class MyToolModule(MCPToolModule):
            def register(self, mcp: FastMCP) -> None:
                @mcp.tool()
                def my_tool(param: str) -> str:
                    return f"Result: {param}"
            
            def register_resources(self, mcp: FastMCP) -> None:
                @mcp.resource()
                def my_resource(uri: str) -> str:
                    return "Resource content"
    """
    
    @abstractmethod
    def register(self, mcp: "FastMCP") -> None:
        """
        Register this module's tools with the MCP server.
        
        This method MUST be implemented by all tool modules.
        Use @mcp.tool() decorator to register each tool function.
        
        Args:
            mcp: The FastMCP server instance to register tools with
        
        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement register(mcp) method"
        )
    
    def register_resources(self, mcp: "FastMCP") -> None:
        """
        Register this module's resources with the MCP server.
        
        This method is OPTIONAL. Override it if your module provides resources.
        Use @mcp.resource() decorator to register each resource function.
        
        Resources are read-only data that clients can fetch for context.
        They are application-controlled (client decides when to load them),
        unlike tools which are model-controlled (model decides when to invoke).
        
        Args:
            mcp: The FastMCP server instance to register resources with
        
        Default implementation: Does nothing (no resources).
        """
        pass  # Default: no resources