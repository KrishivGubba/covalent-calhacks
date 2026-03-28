"""
Integration management endpoints (Google, GitHub, Notion, Filesystem).
"""
import os
import json
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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


class FilesystemConnectRequest(BaseModel):
    root_path: str


class FilesystemUpdateRequest(BaseModel):
    root_path: str


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
            "connected": statuses.get("filesystem", False),
            "description": "Access local files and directories",
        },
        {
            "id": "github",
            "name": "GitHub",
            "connected": statuses.get("github", False),
            "description": "Access repositories, issues, and pull requests",
        },
        {
            "id": "perplexity",
            "name": "Perplexity Search",
            "connected": True,
            "description": "AI-powered web search — included by default",
        },
        {
            "id": "notion",
            "name": "Notion",
            "connected": statuses.get("notion", False),
            "description": "Access Notion workspaces and pages",
        },
        {
            "id": "google",
            "name": "Google Workspace",
            "connected": statuses.get("google", False),
            "description": "Calendar, Drive, and Gmail integration",
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
        raise HTTPException(status_code=400, detail="root_path is required")
    
    if not os.path.isdir(body.root_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist or is not a directory: {body.root_path}")
    
    integration_dao.save_filesystem_root(body.root_path)
    log.info(f"📁 Filesystem connected: {body.root_path}")
    
    return {"status": "success", "root_path": body.root_path}


@router.delete("/filesystem/disconnect")
async def filesystem_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect filesystem integration.
    """
    integration_dao.delete_token("filesystem")
    log.info("📁 Filesystem disconnected")
    return {"status": "success"}


@router.get("/filesystem/root")
async def filesystem_get_root(integration_dao=Depends(integration_dao_dependency)):
    """
    Get the current filesystem root path.
    """
    root_path = integration_dao.get_filesystem_root()
    return {"root_path": root_path}


@router.put("/filesystem/root")
async def filesystem_update_root(
    body: FilesystemUpdateRequest,
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Update the filesystem root path.
    """
    if not body.root_path:
        raise HTTPException(status_code=400, detail="root_path is required")
    
    if not os.path.isdir(body.root_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist or is not a directory: {body.root_path}")
    
    integration_dao.save_filesystem_root(body.root_path)
    log.info(f"📁 Filesystem root updated: {body.root_path}")
    
    return {"status": "success", "root_path": body.root_path}


# ==================== Google ====================

@router.get("/google/connect")
async def google_connect():
    """
    Start Google OAuth flow. Returns the authorization URL.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    
    google_auth_pending[state] = {"status": "pending"}
    
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return {"auth_url": auth_url, "state": state}


@router.get("/google/callback")
async def google_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Handle Google OAuth callback.
    """
    if error:
        if state and state in google_auth_pending:
            google_auth_pending[state] = {"status": "error", "error": error}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{error}</p></body></html>")
    
    if not code or not state:
        return HTMLResponse(content="<html><body><h1>Error</h1><p>Missing code or state</p></body></html>")
    
    try:
        # Exchange code for tokens via Lambda
        resp = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/google/exchange",
            json={"code": code, "redirect_uri": GOOGLE_REDIRECT_URI},
            timeout=30,
        )
        
        if resp.status_code != 200:
            google_auth_pending[state] = {"status": "error", "error": resp.text}
            return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{resp.text}</p></body></html>")
        
        tokens = resp.json()
        
        integration_dao.save_token(
            provider="google",
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            expires_at=tokens.get("expires_at"),
            scopes=GOOGLE_SCOPES,
        )
        
        google_auth_pending[state] = {"status": "success"}
        log.info("✅ Google connected successfully")
        
        return HTMLResponse(content="""
            <html><body>
                <h1>Success!</h1>
                <p>Google Workspace connected. You can close this window.</p>
                <script>window.close();</script>
            </body></html>
        """)
        
    except Exception as e:
        log.error(f"Google OAuth error: {e}")
        google_auth_pending[state] = {"status": "error", "error": str(e)}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>")


@router.get("/google/poll/{state}")
async def google_poll(state: str):
    """
    Poll for Google OAuth result.
    """
    if state not in google_auth_pending:
        return {"status": "not_found"}
    return google_auth_pending[state]


@router.delete("/google/disconnect")
async def google_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect Google integration.
    """
    integration_dao.delete_token("google")
    log.info("🔌 Google disconnected")
    return {"status": "success"}


# ==================== GitHub ====================

class GitHubStartRequest(BaseModel):
    state: str
    code_verifier: str
    auth_token: str


@router.post("/github/start")
async def github_start(body: GitHubStartRequest):
    """
    Called by frontend before opening GitHub OAuth.
    Stores the code_verifier and auth token so backend can do token exchange later via Lambda.
    """
    if not body.state or not body.code_verifier:
        raise HTTPException(status_code=400, detail="state and code_verifier are required")
    
    if not body.auth_token:
        raise HTTPException(status_code=400, detail="auth_token is required (user must be logged in)")
    
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
    def render_error(message: str) -> HTMLResponse:
        return HTMLResponse(content=f"""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444;">GitHub Login Failed</h1>
                    <p style="color: #a1a1aa;">{message}</p>
                </div>
            </body></html>
        """)
    
    if not state:
        return render_error("Missing state parameter")
    
    if state not in github_auth_pending:
        return render_error("Invalid or expired state. Please try again.")
    
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
async def github_check(state: str = Query(...)):
    """
    Polled by frontend after starting GitHub OAuth.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    if state not in github_auth_pending:
        return {"status": "error", "error": "invalid_state"}
    
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
    state: str
    auth_token: str


@router.post("/notion/start")
async def notion_start(body: NotionStartRequest):
    """
    Called by frontend before opening Notion OAuth.
    Stores the state and auth token so backend can do token exchange later via Lambda.
    Note: Notion OAuth does NOT use PKCE, so no code_verifier needed.
    """
    if not body.state:
        raise HTTPException(status_code=400, detail="state is required")
    
    if not body.auth_token:
        raise HTTPException(status_code=400, detail="auth_token is required (user must be logged in)")
    
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
    def render_error(message: str) -> HTMLResponse:
        return HTMLResponse(content=f"""
            <html><body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fff;">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444;">Notion Login Failed</h1>
                    <p style="color: #a1a1aa;">{message}</p>
                </div>
            </body></html>
        """)
    
    if not state:
        return render_error("Missing state parameter")
    
    if state not in notion_auth_pending:
        return render_error("Invalid or expired state. Please try again.")
    
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
async def notion_check(state: str = Query(...)):
    """
    Polled by frontend after starting Notion OAuth.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    if state not in notion_auth_pending:
        return {"status": "error", "error": "invalid_state"}
    
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
