#!/bin/bash

# Backward-compatible stop wrapper for Covalent API stack.
# Primary path is now FastAPI with MCP mounted at /mcp.

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "=== Stopping FastAPI server (includes mounted MCP) ==="
bash "$SCRIPT_DIR/stop_server.sh"

echo ""
echo "=== Stopping standalone MCP server (legacy, if running) ==="
bash "$PROJECT_ROOT/covalent_mcp/stop_mcp.sh"

echo ""
echo "=== Shutdown complete ==="
