#!/bin/bash

# Stop FastMCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default port
MCP_PORT=${MCP_PORT:-8001}

# Kill MCP server using PID file
if [ -f "$SCRIPT_DIR/mcp_server.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/mcp_server.pid")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping FastMCP server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$SCRIPT_DIR/mcp_server.pid"
    echo "FastMCP server stopped"
else
    echo "No PID file found, checking for running MCP processes..."
    pkill -f "covalent_mcp.server" 2>/dev/null || true
    echo "Cleanup complete"
fi

# Ensure nothing is still bound to the MCP port
if command -v lsof >/dev/null 2>&1; then
    PIDS_ON_PORT=$(lsof -ti:$MCP_PORT 2>/dev/null)
    if [ -n "$PIDS_ON_PORT" ]; then
        echo "Killing process(es) on port $MCP_PORT: $PIDS_ON_PORT"
        echo "$PIDS_ON_PORT" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "Port $MCP_PORT cleared"
    fi
fi
