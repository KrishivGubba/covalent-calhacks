#!/bin/bash
# Build standalone executables for the Flask and MCP servers using PyInstaller.
# Run from the project root with the venv activated.
# Output goes to dist-servers/ (dist/ is reserved for Vite frontend build).

set -e

DIST_DIR="dist-servers"

echo "=== Building Flask server ==="
pyinstaller server/app.py \
  --name flask-server \
  --distpath "$DIST_DIR" \
  --paths=context-engine \
  --paths=server \
  --paths=llm-interactions \
  --paths=. \
  --hidden-import=server.auth_dao \
  --hidden-import=server.integration_dao \
  --hidden-import=google.generativeai \
  --hidden-import=anthropic \
  --hidden-import=openai \
  --hidden-import=langchain_mcp_adapters \
  --hidden-import=langchain_mcp_adapters.client \
  --hidden-import=pypdf \
  --hidden-import=googleapiclient.discovery \
  --hidden-import=google.auth.transport.requests \
  --add-data="server/htmlstuff:server/htmlstuff" \
  --add-data="model_config.yml:." \
  --copy-metadata=fastmcp \
  --copy-metadata=anthropic \
  --copy-metadata=langchain \
  --copy-metadata=langchain-core \
  --copy-metadata=langchain-openai \
  --copy-metadata=openai

echo ""
echo "=== Building MCP server ==="
pyinstaller run_mcp.py \
  --name mcp-server \
  --distpath "$DIST_DIR" \
  --paths=. \
  --paths=server \
  --hidden-import=server.auth_dao \
  --hidden-import=server.integration_dao \
  --hidden-import=auth_dao \
  --hidden-import=pypdf \
  --hidden-import=googleapiclient.discovery \
  --hidden-import=google.auth.transport.requests \
  --hidden-import=lupa.lua51 \
  --collect-all=fakeredis \
  --copy-metadata=fastmcp

echo ""
echo "=== Build complete ==="
echo "Flask server: $DIST_DIR/flask-server/flask-server"
echo "MCP server:   $DIST_DIR/mcp-server/mcp-server"
