#!/bin/bash
# Start the FastAPI server with MCP mounted at /mcp (single process).
# Stops any running instances first, then starts fresh.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Stopping any running servers ==="
bash "$SCRIPT_DIR/server/stop_server.sh"
sleep 1

echo ""
echo "=== Starting FastAPI server (MCP mounted at /mcp) ==="
export MOUNT_MCP_SERVER=true
bash "$SCRIPT_DIR/server/start_server.sh"

echo ""
echo "=== Server started ==="
echo "    API:  http://localhost:${VITE_FLASK_PORT:-15001}"
echo "    MCP:  http://localhost:${VITE_FLASK_PORT:-15001}/mcp"
