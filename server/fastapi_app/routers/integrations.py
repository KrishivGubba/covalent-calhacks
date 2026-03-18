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
            f"{LAMBDA_GATEWAY_URL}/google/exchange",
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

@router.get("/github/connect")
async def github_connect():
    """
    Start GitHub OAuth flow.
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    github_auth_pending[state] = {"status": "pending"}
    
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": GITHUB_SCOPES,
        "state": state,
    }
    
    auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    
    return {"auth_url": auth_url, "state": state}


@router.get("/github/callback")
async def github_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Handle GitHub OAuth callback.
    """
    if error:
        if state and state in github_auth_pending:
            github_auth_pending[state] = {"status": "error", "error": error}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{error}</p></body></html>")
    
    if not code or not state:
        return HTMLResponse(content="<html><body><h1>Error</h1><p>Missing code or state</p></body></html>")
    
    try:
        # Exchange code for tokens via Lambda
        resp = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/github/exchange",
            json={"code": code, "redirect_uri": GITHUB_REDIRECT_URI},
            timeout=30,
        )
        
        if resp.status_code != 200:
            github_auth_pending[state] = {"status": "error", "error": resp.text}
            return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{resp.text}</p></body></html>")
        
        tokens = resp.json()
        
        integration_dao.save_token(
            provider="github",
            access_token=tokens.get("access_token"),
            refresh_token=None,
            expires_at=None,
            scopes=GITHUB_SCOPES,
        )
        
        github_auth_pending[state] = {"status": "success"}
        log.info("✅ GitHub connected successfully")
        
        return HTMLResponse(content="""
            <html><body>
                <h1>Success!</h1>
                <p>GitHub connected. You can close this window.</p>
                <script>window.close();</script>
            </body></html>
        """)
        
    except Exception as e:
        log.error(f"GitHub OAuth error: {e}")
        github_auth_pending[state] = {"status": "error", "error": str(e)}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>")


@router.get("/github/poll/{state}")
async def github_poll(state: str):
    """
    Poll for GitHub OAuth result.
    """
    if state not in github_auth_pending:
        return {"status": "not_found"}
    return github_auth_pending[state]


@router.delete("/github/disconnect")
async def github_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect GitHub integration.
    """
    integration_dao.delete_token("github")
    log.info("🔌 GitHub disconnected")
    return {"status": "success"}


# ==================== Notion ====================

@router.get("/notion/connect")
async def notion_connect():
    """
    Start Notion OAuth flow.
    """
    if not NOTION_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Notion OAuth not configured")
    
    state = secrets.token_urlsafe(32)
    notion_auth_pending[state] = {"status": "pending"}
    
    params = {
        "client_id": NOTION_CLIENT_ID,
        "redirect_uri": NOTION_REDIRECT_URI,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    
    auth_url = f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"
    
    return {"auth_url": auth_url, "state": state}


@router.get("/notion/callback")
async def notion_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Handle Notion OAuth callback.
    """
    if error:
        if state and state in notion_auth_pending:
            notion_auth_pending[state] = {"status": "error", "error": error}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{error}</p></body></html>")
    
    if not code or not state:
        return HTMLResponse(content="<html><body><h1>Error</h1><p>Missing code or state</p></body></html>")
    
    try:
        # Exchange code for tokens via Lambda
        resp = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/notion/exchange",
            json={"code": code, "redirect_uri": NOTION_REDIRECT_URI},
            timeout=30,
        )
        
        if resp.status_code != 200:
            notion_auth_pending[state] = {"status": "error", "error": resp.text}
            return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{resp.text}</p></body></html>")
        
        tokens = resp.json()
        
        integration_dao.save_token(
            provider="notion",
            access_token=tokens.get("access_token"),
            refresh_token=None,
            expires_at=None,
            scopes="all",
            provider_metadata=json.dumps({"workspace_id": tokens.get("workspace_id")}),
        )
        
        notion_auth_pending[state] = {"status": "success"}
        log.info("✅ Notion connected successfully")
        
        return HTMLResponse(content="""
            <html><body>
                <h1>Success!</h1>
                <p>Notion connected. You can close this window.</p>
                <script>window.close();</script>
            </body></html>
        """)
        
    except Exception as e:
        log.error(f"Notion OAuth error: {e}")
        notion_auth_pending[state] = {"status": "error", "error": str(e)}
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>")


@router.get("/notion/poll/{state}")
async def notion_poll(state: str):
    """
    Poll for Notion OAuth result.
    """
    if state not in notion_auth_pending:
        return {"status": "not_found"}
    return notion_auth_pending[state]


@router.delete("/notion/disconnect")
async def notion_disconnect(integration_dao=Depends(integration_dao_dependency)):
    """
    Disconnect Notion integration.
    """
    integration_dao.delete_token("notion")
    log.info("🔌 Notion disconnected")
    return {"status": "success"}
