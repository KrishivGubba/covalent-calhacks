"""
Covalent MCP Server (HTTP transport).

Run with:
  python -m covalent_mcp.server_http

Then use the test script with:
  python -m covalent_mcp.toolclasses.test_all_modules --connect-url http://127.0.0.1:8000/mcp
"""
from fastmcp import FastMCP

from covalent_mcp.tools import register_tools

mcp = FastMCP("Covalent MCP Server")
register_tools(mcp)

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        path="/mcp",
    )
