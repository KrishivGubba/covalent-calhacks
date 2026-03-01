#!/bin/bash

# Start Flask server for Covalent

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

# Default Flask settings
export FLASK_APP=app.py
export FLASK_ENV=development
FLASK_PORT=${VITE_FLASK_PORT:-15001}

# Check if server is already running
if [ -f "$SCRIPT_DIR/flask_server.pid" ]; then
    OLD_PID=$(cat "$SCRIPT_DIR/flask_server.pid")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Flask server is already running with PID $OLD_PID"
        exit 0
    fi
fi

# Start Flask server in the background
echo "Starting Flask server on port $FLASK_PORT..."
python app.py > "$SCRIPT_DIR/flask_server.log" 2>&1 &

# Save the PID
echo $! > "$SCRIPT_DIR/flask_server.pid"

# Wait for server to start and verify it's running
echo "Waiting for server to start..."
for i in 1 2 3 4 5; do
    sleep 1
    # Check if the port is listening
    if lsof -ti:$FLASK_PORT > /dev/null 2>&1; then
        echo "Flask server started with PID $(cat "$SCRIPT_DIR/flask_server.pid")"
        echo "Server URL: http://localhost:$FLASK_PORT"
        echo "Logs available at: $SCRIPT_DIR/flask_server.log"
        exit 0
    fi
done

# If we get here, server failed to start
echo "Failed to start Flask server. Check logs at: $SCRIPT_DIR/flask_server.log"
tail -20 "$SCRIPT_DIR/flask_server.log"
rm -f "$SCRIPT_DIR/flask_server.pid"
exit 1
