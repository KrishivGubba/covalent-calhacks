#!/bin/bash

# Start Flask server and MCP server for Covalent

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Navigate to project root
cd "$PROJECT_ROOT"

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Initialize database
echo "=== Initializing database ==="
python context-engine/init_db.py

# Start both servers
echo ""
bash "$PROJECT_ROOT/start_servers.sh"
