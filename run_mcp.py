"""Entry point for PyInstaller to launch the MCP server.

This wrapper exists because covalent_mcp/server.py uses relative imports
(from .tools import ...) which only work when run as part of a package.
PyInstaller runs the entry point as __main__, so we need this top-level
script to import covalent_mcp as a proper package.
"""
import os
import sys
import logging

# Pre-configure logging BEFORE importing covalent_mcp modules.
# This prevents a RecursionError caused by Logger.py's stdout/stderr redirect
# when it runs during the toolclasses import chain.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    datefmt='%H:%M:%S',
)

from covalent_mcp.server import mcp

if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport='streamable-http', host='0.0.0.0', port=port)
