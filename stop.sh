#!/bin/bash

# Stop FastAPI server and MCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=== Stopping FastAPI server ==="
bash "$SCRIPT_DIR/server/stop_server.sh"

echo ""
echo "=== Stopping MCP server ==="
bash "$SCRIPT_DIR/covalent_mcp/stop_mcp.sh"

echo ""
echo "=== All servers stopped ==="
