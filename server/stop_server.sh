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

