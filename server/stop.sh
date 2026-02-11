#!/bin/bash

# Stop Flask server and MCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "=== Stopping Flask server ==="
bash "$SCRIPT_DIR/stop_flask.sh"

echo ""
echo "=== Stopping MCP server ==="
bash "$PROJECT_ROOT/covalent_mcp/stop_mcp.sh"

echo ""
echo "=== All servers stopped ==="
