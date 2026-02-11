#!/bin/bash

# Start Flask server and MCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to project root
cd "$SCRIPT_DIR"

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Initialize database
echo "=== Initializing database ==="
python context-engine/init_db.py

# Start both servers
echo ""
bash "$SCRIPT_DIR/start_servers.sh"
