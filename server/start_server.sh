#!/bin/bash

# Start FastAPI server for Covalent (uvicorn)

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Navigate to the server directory
cd "$SCRIPT_DIR"

# Check if Python virtual environment exists
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Default server port
SERVER_PORT=${VITE_FLASK_PORT:-15001}

# Check if server is already running
if [ -f "$SCRIPT_DIR/server.pid" ]; then
    OLD_PID=$(cat "$SCRIPT_DIR/server.pid")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "FastAPI server is already running with PID $OLD_PID"
        exit 0
    fi
fi

# Start FastAPI server with uvicorn in the background
echo "Starting FastAPI server on port $SERVER_PORT..."
python -m uvicorn fastapi_app.main:app --host 127.0.0.1 --port $SERVER_PORT > "$SCRIPT_DIR/server.log" 2>&1 &

# Save the PID
echo $! > "$SCRIPT_DIR/server.pid"

# Wait for server to start and verify it's running
echo "Waiting for server to start..."
for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    # Check if the port is listening
    if lsof -ti:$SERVER_PORT > /dev/null 2>&1; then
        echo "FastAPI server started with PID $(cat "$SCRIPT_DIR/server.pid")"
        echo "Server URL: http://localhost:$SERVER_PORT"
        echo "Logs available at: $SCRIPT_DIR/server.log"
        exit 0
    fi
done

# If we get here, server failed to start
echo "Failed to start FastAPI server. Check logs at: $SCRIPT_DIR/server.log"
tail -20 "$SCRIPT_DIR/server.log"
rm -f "$SCRIPT_DIR/server.pid"
exit 1
