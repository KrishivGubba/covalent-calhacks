"""
FastMCP Server - Main MCP server implementation.

Run this file to start the MCP server:
    python -m mcp.server
"""
from fastmcp import FastMCP
from tools import register_tools

# Create the MCP server
mcp = FastMCP("Covalent MCP Server")

# Register all tools
register_tools(mcp)

# Run the server
if __name__ == "__main__":
    mcp.run()
