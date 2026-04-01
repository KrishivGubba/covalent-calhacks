#!/bin/bash

# Stop Covalent API stack (FastAPI + mounted MCP)

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=== Stopping FastAPI server (includes mounted MCP) ==="
bash "$SCRIPT_DIR/server/stop_server.sh"

echo ""
echo "=== Stopping standalone MCP server (legacy, if running) ==="
bash "$SCRIPT_DIR/covalent_mcp/stop_mcp.sh"

echo ""
echo "=== Shutdown complete ==="
