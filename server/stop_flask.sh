#!/bin/bash

# Stop Flask server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default Flask port
FLASK_PORT=${VITE_FLASK_PORT:-15001}

# Kill Flask server using PID file
if [ -f "$SCRIPT_DIR/flask_server.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/flask_server.pid")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping Flask server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$SCRIPT_DIR/flask_server.pid"
    echo "Flask server stopped"
else
    echo "No PID file found, checking for running Flask processes..."
    pkill -f "python app.py" 2>/dev/null || true
    echo "Cleanup complete"
fi

# Ensure nothing is still bound to the Flask port
if command -v lsof >/dev/null 2>&1; then
    PIDS_ON_PORT=$(lsof -ti:$FLASK_PORT 2>/dev/null)
    if [ -n "$PIDS_ON_PORT" ]; then
        echo "Killing process(es) on port $FLASK_PORT: $PIDS_ON_PORT"
        echo "$PIDS_ON_PORT" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "Port $FLASK_PORT cleared"
    fi
fi
