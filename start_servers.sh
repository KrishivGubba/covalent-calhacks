#!/bin/bash
# Start both the MCP server and the Flask server.
# Stops any running instances first, then starts fresh.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Stopping servers ==="
bash "$SCRIPT_DIR/server/stop_flask.sh"
bash "$SCRIPT_DIR/covalent_mcp/stop_mcp.sh"
sleep 1

echo ""
echo "=== Starting MCP server ==="
bash "$SCRIPT_DIR/covalent_mcp/start_mcp.sh"

sleep 2

echo ""
echo "=== Starting Flask server ==="
bash "$SCRIPT_DIR/server/start_flask.sh"

echo ""
echo "=== Both servers started ==="
