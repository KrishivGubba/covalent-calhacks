#!/bin/bash

# Stop standalone MCP server processes (legacy mode).
# In the current architecture, MCP is mounted inside FastAPI at /mcp.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="$SCRIPT_DIR/mcp_server.pid"
STOPPED=0

if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping standalone MCP server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
        STOPPED=1
    fi
    rm -f "$PID_FILE"
fi

# Best-effort cleanup for older standalone invocation patterns.
pkill -f "python -m covalent_mcp.server_http" 2>/dev/null && STOPPED=1 || true
pkill -f "python -m covalent_mcp.server" 2>/dev/null && STOPPED=1 || true
pkill -f "mcp-server" 2>/dev/null && STOPPED=1 || true

if [ "$STOPPED" -eq 1 ]; then
    echo "Standalone MCP cleanup complete"
else
    echo "No standalone MCP process found (mounted MCP is stopped with FastAPI)"
fi
