#!/bin/bash

# Start Flask server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to the server directory
cd "$SCRIPT_DIR"

# Check if Python virtual environment exists, otherwise use system Python
if [ -d "../venv" ]; then
    source ../venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set Flask environment variables
export FLASK_APP=app.py
export FLASK_ENV=development

# Start Flask server in the background
echo "Starting Flask server on port 5001..."
python3 app.py > flask_server.log 2>&1 &

# Save the PID
echo $! > flask_server.pid

echo "Flask server started with PID $(cat flask_server.pid)"
echo "Logs available at: $SCRIPT_DIR/flask_server.log"

