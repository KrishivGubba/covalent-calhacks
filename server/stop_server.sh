#!/bin/bash

# Stop FastAPI server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default server port
SERVER_PORT=${VITE_FLASK_PORT:-15001}

# Kill server using PID file (check both new and old PID files)
for PID_FILE in "$SCRIPT_DIR/server.pid" "$SCRIPT_DIR/flask_server.pid"; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping server (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            sleep 1
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
        echo "Server stopped"
    fi
done

# Also kill any uvicorn processes for our app
pkill -f "uvicorn fastapi_app.main:app" 2>/dev/null || true

# Legacy: kill any old Flask processes
pkill -f "python app.py" 2>/dev/null || true

echo "Cleanup complete"

# Ensure nothing is still bound to the server port
if command -v lsof >/dev/null 2>&1; then
    PIDS_ON_PORT=$(lsof -ti:$SERVER_PORT 2>/dev/null)
    if [ -n "$PIDS_ON_PORT" ]; then
        echo "Killing process(es) on port $SERVER_PORT: $PIDS_ON_PORT"
        echo "$PIDS_ON_PORT" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "Port $SERVER_PORT cleared"
    fi
fi
