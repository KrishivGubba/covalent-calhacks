"""
FastAPI Application Entry Point for Covalent Context Engine.

This replaces the Flask server (app.py) with a FastAPI-based server.
Optionally mounts the MCP server at /mcp for single-process deployment.
"""
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load .env - in dev mode load from project root; in frozen mode env vars are set by Tauri
if not getattr(sys, 'frozen', False):
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
else:
    load_dotenv()

# Add project paths
_project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(_project_root))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'context-engine'))

from logger import get_logger
log = get_logger()

from .dependencies import get_db_path, get_encrypted_conn, get_tree, get_auth_dao, get_integration_dao
from init_db import create_schema, ensure_parent_dir

# Import routers
from .routers import health, graph, screen, actions, tab_completion, auth, integrations, mcp as mcp_router

# Check if MCP should be mounted (controlled by env var, default: enabled)
MOUNT_MCP = os.environ.get('MOUNT_MCP_SERVER', 'true').lower() in ('true', '1', 'yes')


def create_mcp_server():
    """Create and configure the MCP server for mounting."""
    try:
        from fastmcp import FastMCP
        from covalent_mcp.tools import register_tools
        
        mcp_server = FastMCP("Covalent MCP Server")
        register_tools(mcp_server)
        log.info("✅ MCP server created and tools registered")
        return mcp_server
    except ImportError as e:
        log.warning(f"⚠️ Could not import MCP dependencies: {e}")
        return None
    except Exception as e:
        log.warning(f"⚠️ Failed to create MCP server: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown events.
    """
    # Startup
    log.info("🚀 FastAPI application starting up...")
    
    # Initialize database schema
    db_path = get_db_path()
    ensure_parent_dir(db_path)
    with get_encrypted_conn() as conn:
        create_schema(conn)
        conn.execute("DELETE FROM integration_tokens WHERE provider = 'filesystem' AND provider_metadata = '{\"type\": \"local_filesystem\"}'")
        conn.commit()
    log.info(f"✅ Database schema ensured at: {db_path}")
    os.environ.setdefault('GRAPH_DB_PATH', db_path)
    
    # Pre-initialize DAOs (lightweight)
    get_auth_dao()
    get_integration_dao()
    
    # Note: Tree is NOT initialized here - it's lazy-loaded on first request
    # This enables sub-second startup times
    
    if MOUNT_MCP:
        log.info("✅ MCP server mounted at /mcp")
    else:
        log.info("ℹ️ MCP server not mounted (MOUNT_MCP_SERVER=false)")
    
    log.info("✅ FastAPI application ready to serve requests")
    
    yield
    
    # Shutdown
    log.info("👋 FastAPI application shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Covalent Context Engine",
    description="API server for Covalent proactive AI agent",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add X-Process-Time header to all responses."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.3f}s"
    log.info(f"Request {request.method} {request.url.path} completed in {process_time * 1000:.3f}ms")
    return response


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(graph.router, prefix="/graph", tags=["Graph"])
app.include_router(screen.router, tags=["Screen Context"])
app.include_router(actions.router, tags=["Actions"])
app.include_router(tab_completion.router, tags=["Tab Completion"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
app.include_router(mcp_router.router, tags=["MCP"])

# Optionally mount MCP server at /mcp
if MOUNT_MCP:
    mcp_server = create_mcp_server()
    if mcp_server:
        try:
            # Mount the MCP HTTP app - this enables MCP protocol at /mcp
            mcp_http_app = mcp_server.http_app(path="/mcp")
            app.mount("/mcp", mcp_http_app)
        except Exception as e:
            log.warning(f"⚠️ Failed to mount MCP server: {e}")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception: {exc}")
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )


def run_server():
    """Run the FastAPI server using uvicorn."""
    import uvicorn
    
    port = int(os.environ.get('VITE_FLASK_PORT', '15001'))
    log.info(f"🚀 Starting FastAPI server on port {port}")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
