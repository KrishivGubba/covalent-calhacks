#!/bin/bash
# Start the FastAPI server (and optionally the separate MCP server).
# Stops any running instances first, then starts fresh.
#
# Usage:
#   ./start_servers.sh           # Merged mode: MCP mounted in FastAPI at /mcp (single process)
#   ./start_servers.sh --split   # Split mode: Separate MCP server on port 8001

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check for --split flag
SPLIT_MODE=false
if [ "$1" = "--split" ]; then
    SPLIT_MODE=true
fi

echo "=== Stopping servers ==="
bash "$SCRIPT_DIR/server/stop_server.sh"
bash "$SCRIPT_DIR/covalent_mcp/stop_mcp.sh"
sleep 1

if [ "$SPLIT_MODE" = true ]; then
    echo ""
    echo "=== Starting MCP server (split mode) ==="
    export MOUNT_MCP_SERVER=false
    bash "$SCRIPT_DIR/covalent_mcp/start_mcp.sh"
    sleep 2
else
    echo ""
    echo "=== MCP server will be mounted in FastAPI (merged mode) ==="
    export MOUNT_MCP_SERVER=true
fi

echo ""
echo "=== Starting FastAPI server ==="
bash "$SCRIPT_DIR/server/start_server.sh"

echo ""
if [ "$SPLIT_MODE" = true ]; then
    echo "=== Both servers started (split mode) ==="
    echo "    FastAPI: http://localhost:${VITE_FLASK_PORT:-15001}"
    echo "    MCP:     http://localhost:${MCP_PORT:-8001}"
else
    echo "=== FastAPI server started with MCP mounted (merged mode) ==="
    echo "    FastAPI: http://localhost:${VITE_FLASK_PORT:-15001}"
    echo "    MCP:     http://localhost:${VITE_FLASK_PORT:-15001}/mcp"
fi
