#!/bin/bash

# Stop Flask server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to the server directory
cd "$SCRIPT_DIR"

# Kill Flask server using PID file
if [ -f "flask_server.pid" ]; then
    PID=$(cat flask_server.pid)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping Flask server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f flask_server.pid
    echo "Flask server stopped"
else
    echo "No PID file found, checking for running Flask processes..."
    pkill -f "python3 app.py" 2>/dev/null || true
    echo "Cleanup complete"
fi

# Ensure nothing is still bound to port 5001 (e.g. old server without correct PID file)
if command -v lsof >/dev/null 2>&1; then
    PIDS_ON_5001=$(lsof -ti:5001 2>/dev/null)
    if [ -n "$PIDS_ON_5001" ]; then
        echo "Killing process(es) on port 5001: $PIDS_ON_5001"
        echo "$PIDS_ON_5001" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "Port 5001 cleared"
    fi
fi

