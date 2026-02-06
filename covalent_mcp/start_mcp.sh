#!/bin/bash

# Start FastMCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Navigate to the project root (so module imports work)
cd "$PROJECT_ROOT"

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

# Load environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Default port
MCP_PORT=${MCP_PORT:-8001}

# Check if server is already running
if [ -f "$SCRIPT_DIR/mcp_server.pid" ]; then
    OLD_PID=$(cat "$SCRIPT_DIR/mcp_server.pid")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "MCP server is already running with PID $OLD_PID"
        exit 0
    fi
fi

# Start MCP server in the background
echo "Starting FastMCP server on port $MCP_PORT..."
python3 -c "
from covalent_mcp.server import mcp
mcp.run(transport='streamable-http', host='0.0.0.0', port=$MCP_PORT)
" > "$SCRIPT_DIR/mcp_server.log" 2>&1 &

# Save the PID
echo $! > "$SCRIPT_DIR/mcp_server.pid"

# Wait for server to start and verify it's running
echo "Waiting for server to start..."
for i in 1 2 3 4 5; do
    sleep 1
    # Check if the port is listening
    if lsof -ti:$MCP_PORT > /dev/null 2>&1; then
        echo "FastMCP server started with PID $(cat "$SCRIPT_DIR/mcp_server.pid")"
        echo "Server URL: http://localhost:$MCP_PORT/mcp"
        echo "Logs available at: $SCRIPT_DIR/mcp_server.log"
        exit 0
    fi
done

# If we get here, server failed to start
echo "Failed to start MCP server. Check logs at: $SCRIPT_DIR/mcp_server.log"
tail -20 "$SCRIPT_DIR/mcp_server.log"
rm -f "$SCRIPT_DIR/mcp_server.pid"
exit 1
