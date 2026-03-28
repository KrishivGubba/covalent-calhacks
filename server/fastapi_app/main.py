"""
FastAPI Application Entry Point for Covalent Context Engine.

This replaces the Flask server (app.py) with a FastAPI-based server.
Optionally mounts the MCP server at /mcp for single-process deployment.
"""
import os
import sys
import time
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
import requests as http_requests

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


# Auth0 callback endpoint (at root level for redirect URI)
AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com'
FLASK_PORT = int(os.environ.get('VITE_FLASK_PORT', '15001'))
AUTH0_CLIENT_ID = os.environ.get('VITE_AUTH0_CLIENT_ID', '')
AUTH0_REDIRECT_URI = f'http://localhost:{FLASK_PORT}/callback'

# HTML templates directory (PyInstaller uses sys._MEIPASS for bundled data)
if getattr(sys, 'frozen', False):
    HTML_TEMPLATES_DIR = os.path.join(sys._MEIPASS, 'server', 'htmlstuff')
else:
    HTML_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'htmlstuff')


def load_html_template(filename: str, replacements: dict = None) -> str:
    """Load an HTML template from htmlstuff/ and optionally replace placeholders."""
    filepath = os.path.join(HTML_TEMPLATES_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if replacements:
        for key, value in replacements.items():
            content = content.replace(key, value)
    return content


@app.api_route("/callback", methods=["GET", "POST"], response_class=HTMLResponse)
async def auth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
):
    """
    Auth0 redirect target. Performs server-side token exchange and stores result for frontend to poll.
    """
    auth_dao = get_auth_dao()
    
    def render_error(message: str) -> HTMLResponse:
        return HTMLResponse(
            content=load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': message}),
            status_code=200
        )
    
    if not state:
        return HTMLResponse(
            content=load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': 'Missing state parameter'}),
            status_code=400
        )
    
    # If Auth0 returned an error
    if error:
        auth_dao.save_auth_result(state, error=error, error_description=error_description)
        log.error(f"🔐 Auth callback error: {error} - {error_description}")
        return render_error(error_description or error)
    
    if not code:
        auth_dao.save_auth_result(state, error="no_code", error_description="No authorization code received")
        return render_error("No authorization code received")
    
    # Retrieve the code_verifier
    code_verifier = auth_dao.get_code_verifier(state)
    if not code_verifier:
        auth_dao.save_auth_result(state, error="no_verifier", error_description="Code verifier not found - session may have expired")
        return render_error("Session expired. Please try again.")
    
    # Exchange code for tokens (server-side, no CORS issues)
    try:
        log.info(f"🔐 Exchanging code for tokens (state={state[:8]}...)...")
        token_response = http_requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": AUTH0_CLIENT_ID,
                "code_verifier": code_verifier,
                "code": code,
                "redirect_uri": AUTH0_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        token_data = token_response.json()
        
        if not token_response.ok or "error" in token_data:
            err = token_data.get("error", "token_exchange_failed")
            err_desc = token_data.get("error_description", "Token exchange failed")
            auth_dao.save_auth_result(state, error=err, error_description=err_desc)
            log.error(f"🔐 Token exchange failed: {err} - {err_desc}")
            return render_error(err_desc)
        
        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 86400)  # Default 24 hours
        
        log.info("🔐 Tokens received. Fetching user info...")
        
        # Fetch user info
        user_info = None
        try:
            userinfo_response = http_requests.get(
                f"https://{AUTH0_DOMAIN}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
            if userinfo_response.ok:
                user_info = userinfo_response.json()
                log.info(f"🔐 User info: {user_info.get('email', user_info.get('sub', 'unknown'))}")
        except Exception as e:
            log.error(f"🔐 Failed to fetch user info: {e}")
        
        auth_dao.save_auth_result(
            state,
            access_token=access_token,
            id_token=id_token,
            refresh_token=refresh_token,
            user_info=user_info,
        )
        
        # Save persistent session for future logins
        if user_info and user_info.get("sub"):
            expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
            auth_dao.save_session(
                user_id=user_info["sub"],
                access_token=access_token,
                refresh_token=refresh_token,
                id_token=id_token,
                expires_at=expires_at,
                user_info=user_info,
            )
            log.set_user_id(user_info["sub"])
            log.info(f"🔐 Saved persistent session for user={user_info['sub']}")
        
        log.info(f"🔐 Auth complete for state={state[:8]}...")
        return HTMLResponse(content=load_html_template('auth_success.html'), status_code=200)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        auth_dao.save_auth_result(state, error="exception", error_description=str(e))
        return render_error(f"An error occurred: {e}")

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
