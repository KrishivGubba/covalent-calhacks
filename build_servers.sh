#!/bin/bash
# Build standalone executables for the FastAPI and MCP servers using PyInstaller.
# Run from the project root with the venv activated.
# Output goes to dist-servers/ (dist/ is reserved for Vite frontend build).

set -e

DIST_DIR="dist-servers"

echo "=== Building FastAPI server ==="
pyinstaller server/run_fastapi.py \
  --noconfirm \
  --name flask-server \
  --distpath "$DIST_DIR" \
  --paths=context-engine \
  --paths=server \
  --paths=llm-interactions \
  --paths=. \
  --hidden-import=server.auth_dao \
  --hidden-import=server.integration_dao \
  --hidden-import=server.fastapi_app \
  --hidden-import=server.fastapi_app.main \
  --hidden-import=server.fastapi_app.dependencies \
  --hidden-import=server.fastapi_app.routers \
  --hidden-import=server.fastapi_app.routers.health \
  --hidden-import=server.fastapi_app.routers.graph \
  --hidden-import=server.fastapi_app.routers.screen \
  --hidden-import=server.fastapi_app.routers.actions \
  --hidden-import=server.fastapi_app.routers.tab_completion \
  --hidden-import=server.fastapi_app.routers.auth \
  --hidden-import=server.fastapi_app.routers.integrations \
  --hidden-import=server.fastapi_app.routers.mcp \
  --hidden-import=fastapi \
  --hidden-import=uvicorn \
  --hidden-import=uvicorn.logging \
  --hidden-import=uvicorn.loops \
  --hidden-import=uvicorn.loops.auto \
  --hidden-import=uvicorn.protocols \
  --hidden-import=uvicorn.protocols.http \
  --hidden-import=uvicorn.protocols.http.auto \
  --hidden-import=uvicorn.protocols.websockets \
  --hidden-import=uvicorn.protocols.websockets.auto \
  --hidden-import=uvicorn.lifespan \
  --hidden-import=uvicorn.lifespan.on \
  --hidden-import=starlette \
  --hidden-import=starlette.routing \
  --hidden-import=starlette.middleware \
  --hidden-import=starlette.middleware.cors \
  --hidden-import=pydantic \
  --hidden-import=google.generativeai \
  --hidden-import=anthropic \
  --hidden-import=openai \
  --hidden-import=langchain_mcp_adapters \
  --hidden-import=langchain_mcp_adapters.client \
  --hidden-import=pypdf \
  --hidden-import=googleapiclient.discovery \
  --hidden-import=google.auth.transport.requests \
  --hidden-import=posthog \
  --add-data="server/htmlstuff:server/htmlstuff" \
  --add-data="model_config.yml:." \
  --copy-metadata=fastmcp \
  --copy-metadata=anthropic \
  --copy-metadata=langchain \
  --copy-metadata=langchain-core \
  --copy-metadata=langchain-openai \
  --copy-metadata=openai \
  --collect-submodules=rich

echo ""
echo "=== Build complete ==="
echo "FastAPI server (with MCP mounted at /mcp): $DIST_DIR/flask-server/flask-server"
