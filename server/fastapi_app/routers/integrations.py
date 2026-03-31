"""
Integration management endpoints (Google, GitHub, Notion, Filesystem).
"""
import os
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

import requests as http_requests

from ..dependencies import integration_dao_dependency, auth_dao_dependency
from logger import get_logger

log = get_logger()
router = APIRouter()

FLASK_PORT = int(os.environ.get('VITE_FLASK_PORT', '15001'))

# Google OAuth config
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_REDIRECT_URI = f'http://127.0.0.1:{FLASK_PORT}/integrations/google/callback'
GOOGLE_SCOPES = 'openid https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email'

# GitHub OAuth config
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_REDIRECT_URI = f'http://127.0.0.1:{FLASK_PORT}/integrations/github/callback'
GITHUB_SCOPES = 'repo read:user'

# Notion OAuth config
NOTION_CLIENT_ID = os.environ.get('NOTION_CLIENT_ID', '')
NOTION_REDIRECT_URI = f'http://localhost:{FLASK_PORT}/integrations/notion/callback'

# Lambda Gateway URL
LAMBDA_GATEWAY_URL = os.environ.get('LAMBDA_GATEWAY_URL', 'https://gtfrn4otol.execute-api.us-east-1.amazonaws.com')

# In-memory storage for pending OAuth
google_auth_pending = {}
github_auth_pending = {}
notion_auth_pending = {}


def _get_filesystem_description(integration_dao) -> str:
    """Build a filesystem description with configured root path (Flask parity)."""
    root = integration_dao.get_filesystem_root()
    if root:
        display_path = root
        if len(display_path) > 50:
            display_path = "..." + display_path[-47:]
        return f"Access local files and directories ({display_path})"
    return "Access local files and directories"


class FilesystemConnectRequest(BaseModel):
    root_path: Optional[str] = None


class FilesystemUpdateRequest(BaseModel):
    root_path: Optional[str] = None


@router.get("/status")
async def get_integrations_status(integration_dao=Depends(integration_dao_dependency)):
    """
    Get the connection status of all integrations.
    """
    statuses = integration_dao.get_all_statuses()
    
    integrations = [
        {
            "id": "filesystem",
            "name": "Filesystem",
            "description": _get_filesystem_description(integration_dao),
            "icon": "📁",
            "connected": statuses.get("filesystem", False),
        },
        {
            "id": "github",
            "name": "GitHub",
            "description": "Access repositories, issues, and pull requests",
            "icon": "🐙",
            "connected": statuses.get("github", False),
        },
        {
            "id": "perplexity",
            "name": "Perplexity Search",
            "connected": True,
            "description": "AI-powered web search",
            "icon": "🔍",
            "included": True,
        },
        {
            "id": "notion",
            "name": "Notion",
            "description": "Access Notion workspaces and pages",
            "icon": "📝",
            "connected": statuses.get("notion", False),
        },
        {
            "id": "google",
            "name": "Google Workspace",
            "description": "Calendar, Drive, Mail",
            "icon": "🔷",
            "connected": statuses.get("google", False),
        },
    ]
    
    return {"integrations": integrations}


# ==================== Filesystem ====================

@router.post("/filesystem/connect")
async def filesystem_connect(
    body: FilesystemConnectRequest,
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Connect filesystem integration by setting the root path.
    """
    if not body.root_path:
        return JSONResponse(status_code=400, content={"ok": False, "error": "root_path is required"})
    
    if not os.path.isdir(body.root_path):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Path does not exist or is not a directory"},
        )
    
    integration_dao.save_token(
        provider="filesystem",
        access_token="local",
        scopes="read_write",
        provider_metadata={"type": "local_filesystem", "root_path": body.root_path},
    )
    log.info(f"📁 Filesystem connected: {body.root_path}")
    
    return {"ok": True, "root_path": body.root_path}


@router.post("/filesystem/disconnect")
@router.delete("/filesystem/disconnect")
async def filesystem_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect filesystem integration.
    """
    deleted = integration_dao.delete_token("filesystem")
    log.info("📁 Filesystem disconnected")
    return {"ok": True, "deleted": deleted > 0}


@router.get("/filesystem/root")
async def filesystem_get_root(integration_dao=Depends(integration_dao_dependency)):
    """
    Get the current filesystem root path.
    """
    root_path = integration_dao.get_filesystem_root()
    return {"connected": root_path is not None, "root_path": root_path}


@router.put("/filesystem/root")
async def filesystem_update_root(
    body: FilesystemUpdateRequest,
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Update the filesystem root path.
    """
    if not body.root_path:
        return JSONResponse(status_code=400, content={"ok": False, "error": "root_path is required"})
    
    if not os.path.isdir(body.root_path):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Path does not exist or is not a directory"},
        )
    
    integration_dao.save_token(
        provider="filesystem",
        access_token="local",
        scopes="read_write",
        provider_metadata={"type": "local_filesystem", "root_path": body.root_path},
    )
    log.info(f"📁 Filesystem root updated: {body.root_path}")
    
    return {"ok": True, "root_path": body.root_path}


# ==================== Google ====================

class GoogleStartRequest(BaseModel):
    state: Optional[str] = None
    code_verifier: Optional[str] = None
    auth_token: Optional[str] = None


@router.post("/google/start")
async def google_start(body: GoogleStartRequest):
    """
    Called by frontend before opening Google OAuth.
    Stores the code_verifier and auth token so backend can exchange via Lambda.
    """
    if not body.state or not body.code_verifier:
        return JSONResponse(status_code=400, content={"error": "state and code_verifier are required"})
    if not body.auth_token:
        return JSONResponse(
            status_code=400,
            content={"error": "auth_token is required (user must be logged in)"},
        )

    google_auth_pending[body.state] = {
        "code_verifier": body.code_verifier,
        "auth_token": body.auth_token,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    log.info(f"🔷 Google auth start: stored code_verifier for state={body.state[:8]}...")
    return {"ok": True}


@router.get("/google/callback")
async def google_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Google OAuth redirect target. Exchanges code for tokens via Lambda.
    """
    def render_error(message: str, status_code: int = 200) -> HTMLResponse:
        return HTMLResponse(content=f"""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444;">Google Login Failed</h1>
                    <p style="color: #a1a1aa;">{message}</p>
                </div>
            </body></html>
        """, status_code=status_code)

    if not state:
        return render_error("Missing state parameter", status_code=400)

    if state not in google_auth_pending:
        return render_error("Invalid or expired state. Please try again.", status_code=400)

    if error:
        google_auth_pending[state] = {
            "status": "error",
            "error": error,
            "error_description": error_description or error,
        }
        return render_error(error_description or error)

    if not code:
        google_auth_pending[state] = {
            "status": "error",
            "error": "no_code",
            "error_description": "No authorization code received",
        }
        return render_error("No authorization code received")

    pending = google_auth_pending[state]
    code_verifier = pending.get("code_verifier")
    auth_token = pending.get("auth_token")

    if not code_verifier:
        google_auth_pending[state] = {
            "status": "error",
            "error": "no_verifier",
            "error_description": "Code verifier not found",
        }
        return render_error("Session expired. Please try again.")

    if not auth_token:
        google_auth_pending[state] = {
            "status": "error",
            "error": "no_auth_token",
            "error_description": "Auth token not found - user must be logged in",
        }
        return render_error("Please log in first.")

    try:
        log.info(f"🔷 Exchanging Google code via Lambda (state={state[:8]}...)...")
        resp = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/google/exchange",
            json={
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": GOOGLE_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            timeout=15,
        )

        token_data = resp.json()
        if not resp.ok or "error" in token_data:
            err = token_data.get("error", "token_exchange_failed")
            err_desc = token_data.get("error_description", "Token exchange failed")
            google_auth_pending[state] = {
                "status": "error",
                "error": err,
                "error_description": err_desc,
            }
            log.error(f"🔷 Google token exchange failed: {err} - {err_desc}")
            return render_error(err_desc)

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        scope = token_data.get("scope", GOOGLE_SCOPES)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        user_email = None
        try:
            userinfo_response = http_requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
            if userinfo_response.ok:
                user_email = userinfo_response.json().get("email")
        except Exception as e:
            log.warning(f"🔷 Failed to fetch Google user info: {e}")

        integration_dao.save_token(
            provider="google",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scope,
            provider_metadata={"email": user_email} if user_email else None,
        )

        google_auth_pending[state] = {"status": "ready", "email": user_email}
        log.info(f"✅ Google connected successfully (email={user_email})")

        return HTMLResponse(content="""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #C5F467;">Google Connected!</h1>
                    <p style="color: #a1a1aa;">You can close this window and return to Covalent.</p>
                </div>
            </body></html>
        """)

    except Exception as e:
        log.error(f"Google OAuth error: {e}")
        google_auth_pending[state] = {
            "status": "error",
            "error": "exception",
            "error_description": str(e),
        }
        return render_error(f"An error occurred: {e}")


@router.get("/google/check")
async def google_check(state: Optional[str] = Query(None)):
    """
    Polled by frontend after starting Google OAuth.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    if not state:
        return JSONResponse(status_code=400, content={"status": "error", "error": "missing state"})

    if state not in google_auth_pending:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_state"})

    pending = google_auth_pending[state]
    status = pending.get("status", "pending")

    if status == "ready":
        email = pending.get("email")
        del google_auth_pending[state]
        return {"status": "ready", "email": email}
    if status == "error":
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del google_auth_pending[state]
        return {"status": "error", "error": error, "error_description": error_desc}
    return {"status": "pending"}


@router.post("/google/disconnect")
@router.delete("/google/disconnect")
async def google_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect Google integration.
    """
    deleted = integration_dao.delete_token("google")
    log.info("🔌 Google disconnected")
    return {"ok": True, "deleted": deleted > 0}


# ==================== GitHub ====================

class GitHubStartRequest(BaseModel):
    state: Optional[str] = None
    code_verifier: Optional[str] = None
    auth_token: Optional[str] = None


@router.post("/github/start")
async def github_start(body: GitHubStartRequest):
    """
    Called by frontend before opening GitHub OAuth.
    Stores the code_verifier and auth token so backend can do token exchange later via Lambda.
    """
    if not body.state or not body.code_verifier:
        return JSONResponse(status_code=400, content={"error": "state and code_verifier are required"})
    
    if not body.auth_token:
        return JSONResponse(
            status_code=400,
            content={"error": "auth_token is required (user must be logged in)"},
        )
    
    github_auth_pending[body.state] = {
        "code_verifier": body.code_verifier,
        "auth_token": body.auth_token,
        "status": "pending",
    }
    log.info(f"🔷 GitHub auth start: stored code_verifier for state={body.state[:8]}...")
    return {"ok": True}


@router.get("/github/callback")
async def github_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    GitHub OAuth redirect target. Exchanges code for tokens using PKCE via Lambda.
    """
    def render_error(message: str, status_code: int = 200) -> HTMLResponse:
        return HTMLResponse(content=f"""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444;">GitHub Login Failed</h1>
                    <p style="color: #a1a1aa;">{message}</p>
                </div>
            </body></html>
        """, status_code=status_code)
    
    if not state:
        return render_error("Missing state parameter", status_code=400)
    
    if state not in github_auth_pending:
        return render_error("Invalid or expired state. Please try again.", status_code=400)
    
    if error:
        github_auth_pending[state] = {"status": "error", "error": error, "error_description": error_description}
        log.error(f"🔷 GitHub callback error: {error} - {error_description}")
        return render_error(error_description or error)
    
    if not code:
        github_auth_pending[state] = {"status": "error", "error": "no_code", "error_description": "No authorization code received"}
        return render_error("No authorization code received")
    
    pending = github_auth_pending[state]
    code_verifier = pending.get("code_verifier")
    auth_token = pending.get("auth_token")
    
    try:
        log.info(f"🔷 Exchanging GitHub code via Lambda (state={state[:8]}...)...")
        resp = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/github/exchange",
            json={
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            timeout=15,
        )
        
        if resp.status_code != 200:
            err_text = resp.text
            github_auth_pending[state] = {"status": "error", "error": "exchange_failed", "error_description": err_text}
            log.error(f"🔷 GitHub token exchange failed: {err_text}")
            return render_error(f"Token exchange failed: {err_text}")
        
        tokens = resp.json()
        access_token = tokens.get("access_token")
        
        # Fetch user info to get username
        username = None
        try:
            user_resp = http_requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
                timeout=10,
            )
            if user_resp.ok:
                username = user_resp.json().get("login")
        except Exception as e:
            log.warning(f"🔷 Failed to fetch GitHub username: {e}")
        
        integration_dao.save_token(
            provider="github",
            access_token=access_token,
            refresh_token=None,
            expires_at=None,
            scopes=GITHUB_SCOPES,
        )
        
        github_auth_pending[state] = {"status": "ready", "username": username}
        log.info(f"✅ GitHub connected successfully (username={username})")
        
        return HTMLResponse(content="""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #C5F467;">GitHub Connected!</h1>
                    <p style="color: #a1a1aa;">You can close this window and return to Covalent.</p>
                </div>
            </body></html>
        """)
        
    except Exception as e:
        log.error(f"GitHub OAuth error: {e}")
        import traceback
        traceback.print_exc()
        github_auth_pending[state] = {"status": "error", "error": "exception", "error_description": str(e)}
        return render_error(f"An error occurred: {e}")


@router.get("/github/check")
async def github_check(state: Optional[str] = Query(None)):
    """
    Polled by frontend after starting GitHub OAuth.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    if not state:
        return JSONResponse(status_code=400, content={"status": "error", "error": "missing state"})
    if state not in github_auth_pending:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_state"})
    
    pending = github_auth_pending[state]
    status = pending.get("status", "pending")
    
    if status == "ready":
        username = pending.get("username")
        del github_auth_pending[state]
        return {"status": "ready", "username": username}
    elif status == "error":
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del github_auth_pending[state]
        return {"status": "error", "error": error, "error_description": error_desc}
    else:
        return {"status": "pending"}


@router.post("/github/disconnect")
async def github_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect GitHub integration.
    """
    deleted = integration_dao.delete_token("github")
    log.info(f"🔌 GitHub disconnected (deleted={deleted})")
    return {"ok": True, "deleted": deleted > 0}


# ==================== Notion ====================

class NotionStartRequest(BaseModel):
    state: Optional[str] = None
    auth_token: Optional[str] = None


@router.post("/notion/start")
async def notion_start(body: NotionStartRequest):
    """
    Called by frontend before opening Notion OAuth.
    Stores the state and auth token so backend can do token exchange later via Lambda.
    Note: Notion OAuth does NOT use PKCE, so no code_verifier needed.
    """
    if not body.state:
        return JSONResponse(status_code=400, content={"error": "state is required"})
    
    if not body.auth_token:
        return JSONResponse(
            status_code=400,
            content={"error": "auth_token is required (user must be logged in)"},
        )
    
    notion_auth_pending[body.state] = {
        "auth_token": body.auth_token,
        "status": "pending",
    }
    log.info(f"🔷 Notion auth start: stored state={body.state[:8]}...")
    return {"ok": True}


@router.get("/notion/callback")
async def notion_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Notion OAuth redirect target. Exchanges code for tokens via Lambda.
    """
    def render_error(message: str, status_code: int = 200) -> HTMLResponse:
        return HTMLResponse(content=f"""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444;">Notion Login Failed</h1>
                    <p style="color: #a1a1aa;">{message}</p>
                </div>
            </body></html>
        """, status_code=status_code)
    
    if not state:
        return render_error("Missing state parameter", status_code=400)
    
    if state not in notion_auth_pending:
        return render_error("Invalid or expired state. Please try again.", status_code=400)
    
    if error:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = error
        notion_auth_pending[state]["error_description"] = error_description or error
        log.error(f"🔷 Notion callback error: {error}")
        return render_error(error_description or error)
    
    if not code:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "no_code"
        notion_auth_pending[state]["error_description"] = "No authorization code received"
        return render_error("No authorization code received")
    
    auth_token = notion_auth_pending[state].get("auth_token")
    
    if not auth_token:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "no_auth_token"
        notion_auth_pending[state]["error_description"] = "Auth token not found - user must be logged in"
        return render_error("Please log in first.")
    
    try:
        log.info(f"🔷 Exchanging Notion code for tokens via Lambda (state={state[:8]}...)...")
        token_response = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/notion/exchange",
            json={
                "code": code,
                "redirect_uri": NOTION_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            timeout=15,
        )
        token_data = token_response.json()
        
        if not token_response.ok or "error" in token_data:
            err = token_data.get("error", "token_exchange_failed")
            err_desc = token_data.get("error_description", "Token exchange failed")
            notion_auth_pending[state]["status"] = "error"
            notion_auth_pending[state]["error"] = err
            notion_auth_pending[state]["error_description"] = err_desc
            log.error(f"🔷 Notion token exchange failed: {err} - {err_desc}")
            return render_error(err_desc)
        
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        workspace_name = token_data.get("workspace_name")
        workspace_id = token_data.get("workspace_id")
        bot_id = token_data.get("bot_id")
        
        integration_dao.save_token(
            provider="notion",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=None,
            scopes=None,
            provider_metadata={
                "workspace_name": workspace_name,
                "workspace_id": workspace_id,
                "bot_id": bot_id,
            },
        )
        
        notion_auth_pending[state]["status"] = "ready"
        notion_auth_pending[state]["workspace_name"] = workspace_name
        
        log.info(f"🔷 Notion auth complete: workspace={workspace_name}")
        
        return HTMLResponse(content="""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #C5F467;">Notion Connected!</h1>
                    <p style="color: #a1a1aa;">You can close this window and return to Covalent.</p>
                </div>
            </body></html>
        """)
        
    except Exception as e:
        log.error(f"Notion OAuth error: {e}")
        import traceback
        traceback.print_exc()
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "exception"
        notion_auth_pending[state]["error_description"] = str(e)
        return render_error(f"An error occurred: {e}")


@router.get("/notion/check")
async def notion_check(state: Optional[str] = Query(None)):
    """
    Polled by frontend after starting Notion OAuth.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    if not state:
        return JSONResponse(status_code=400, content={"status": "error", "error": "missing state"})
    if state not in notion_auth_pending:
        return JSONResponse(status_code=400, content={"status": "error", "error": "invalid_state"})
    
    pending = notion_auth_pending[state]
    status = pending.get("status", "pending")
    
    if status == "ready":
        workspace_name = pending.get("workspace_name")
        del notion_auth_pending[state]
        return {"status": "ready", "workspace_name": workspace_name}
    elif status == "error":
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del notion_auth_pending[state]
        return {"status": "error", "error": error, "error_description": error_desc}
    else:
        return {"status": "pending"}


@router.post("/notion/disconnect")
async def notion_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect Notion integration.
    """
    deleted = integration_dao.delete_token("notion")
    log.info(f"🔌 Notion disconnected (deleted={deleted})")
    return {"ok": True, "deleted": deleted > 0}


class TokenRefreshRequest(BaseModel):
    auth_token: Optional[str] = None


@router.post("/google/refresh")
async def google_refresh_token(
    body: TokenRefreshRequest,
    integration_dao=Depends(integration_dao_dependency),
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Refresh Google access token using the refresh token via Lambda.
    Body: { "auth_token": "..." } - Auth0 token to authenticate with Lambda.
    """
    auth_token = body.auth_token
    if not auth_token:
        sessions = auth_dao.get_all_sessions()
        if sessions:
            session = auth_dao.get_session(sessions[0]["user_id"])
            if session:
                auth_token = session.get("access_token")

    if not auth_token:
        return JSONResponse(
            status_code=400,
            content={"error": "auth_token is required and no active session found"},
        )

    token_data = integration_dao.get_token("google")
    if not token_data:
        return JSONResponse(status_code=404, content={"error": "Google not connected"})

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return JSONResponse(status_code=400, content={"error": "No refresh token available"})

    try:
        token_response = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/google/refresh",
            json={"refresh_token": refresh_token},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            timeout=15,
        )
        new_token_data = token_response.json()

        if not token_response.ok or "error" in new_token_data:
            err = new_token_data.get("error", "refresh_failed")
            err_desc = new_token_data.get("error_description", "Token refresh failed")
            return JSONResponse(
                status_code=400,
                content={"error": err, "error_description": err_desc},
            )

        new_access_token = new_token_data.get("access_token")
        expires_in = new_token_data.get("expires_in", 3600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        integration_dao.update_access_token("google", new_access_token, expires_at)
        return {"access_token": new_access_token, "expires_at": expires_at}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "exception", "error_description": str(e)},
        )


@router.post("/notion/refresh")
async def notion_refresh_token(
    body: TokenRefreshRequest,
    integration_dao=Depends(integration_dao_dependency),
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Refresh Notion access token using the refresh token via Lambda.
    Body: { "auth_token": "..." } - Auth0 token to authenticate with Lambda.
    """
    auth_token = body.auth_token
    if not auth_token:
        sessions = auth_dao.get_all_sessions()
        if sessions:
            session = auth_dao.get_session(sessions[0]["user_id"])
            if session:
                auth_token = session.get("access_token")

    if not auth_token:
        return JSONResponse(
            status_code=400,
            content={"error": "auth_token is required and no active session found"},
        )

    token_data = integration_dao.get_token("notion")
    if not token_data:
        return JSONResponse(status_code=404, content={"error": "Notion not connected"})

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return JSONResponse(status_code=400, content={"error": "No refresh token available"})

    try:
        token_response = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/notion/refresh",
            json={"refresh_token": refresh_token},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            timeout=15,
        )
        new_token_data = token_response.json()

        if not token_response.ok or "error" in new_token_data:
            err = new_token_data.get("error", "refresh_failed")
            err_desc = new_token_data.get("error_description", "Token refresh failed")
            return JSONResponse(
                status_code=400,
                content={"error": err, "error_description": err_desc},
            )

        new_access_token = new_token_data.get("access_token")
        new_refresh_token = new_token_data.get("refresh_token")
        expires_in = new_token_data.get("expires_in", 3600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        integration_dao.update_access_token("notion", new_access_token, expires_at)
        if new_refresh_token and new_refresh_token != refresh_token:
            integration_dao.save_token(
                provider="notion",
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_at=expires_at,
            )

        return {"access_token": new_access_token, "expires_at": expires_at}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "exception", "error_description": str(e)},
        )
