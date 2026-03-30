"""
Authentication endpoints (Auth0 PKCE flow).
"""
import os
import sys
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

import requests as http_requests

from ..dependencies import auth_dao_dependency, integration_dao_dependency
from logger import get_logger

log = get_logger()
router = APIRouter()

# Auth0 config
AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com'
FLASK_PORT = int(os.environ.get('VITE_FLASK_PORT', '15001'))
AUTH0_CLIENT_ID = os.environ.get('VITE_AUTH0_CLIENT_ID', '')
AUTH0_REDIRECT_URI = f'http://localhost:{FLASK_PORT}/callback'

# HTML templates directory (PyInstaller uses sys._MEIPASS for bundled data)
if getattr(sys, 'frozen', False):
    HTML_TEMPLATES_DIR = os.path.join(sys._MEIPASS, 'server', 'htmlstuff')
else:
    HTML_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'htmlstuff')


def load_html_template(filename: str, replacements: dict = None) -> str:
    """Load an HTML template from htmlstuff/ and optionally replace placeholders."""
    filepath = os.path.join(HTML_TEMPLATES_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if replacements:
        for key, value in replacements.items():
            content = content.replace(key, value)
    return content


class AuthStartRequest(BaseModel):
    state: str
    code_verifier: str


class LogoutRequest(BaseModel):
    user_id: Optional[str] = None


class SessionResponse(BaseModel):
    authenticated: bool
    user_id: Optional[str] = None
    user_info: Optional[dict] = None


@router.post("/start")
async def auth_start(
    body: AuthStartRequest,
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Called by frontend before opening Auth0 login.
    Stores the code_verifier so the backend can do the token exchange later.
    """
    if not body.state or not body.code_verifier:
        raise HTTPException(status_code=400, detail="state and code_verifier are required")
    
    auth_dao.save_code_verifier(body.state, body.code_verifier)
    log.info(f"🔐 Auth start: stored code_verifier for state={body.state[:8]}...")
    return {"ok": True}


@router.get("/session")
async def get_session(
    user_id: Optional[str] = Query(None),
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Get a user session by user_id.
    Returns session info and whether the token has expired.
    """
    if not user_id:
        return {"session": None, "expired": False}
    
    session = auth_dao.get_session(user_id)
    if session:
        user_info = session.get("user_info")
        if isinstance(user_info, str):
            try:
                user_info = json.loads(user_info)
            except json.JSONDecodeError:
                pass
            session["user_info"] = user_info
        
        # Check if token has expired
        expired = False
        expires_at = session.get("expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                expired = datetime.utcnow() > exp_dt.replace(tzinfo=None)
            except (ValueError, TypeError):
                pass
        
        return {
            "session": session,
            "expired": expired,
        }
    
    return {"session": None, "expired": False}


@router.post("/session/refresh")
async def refresh_session(
    request: Request,
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Refresh an expired access token using the stored refresh_token.
    """
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    session = auth_dao.get_session(user_id)
    if not session or not session.get("refresh_token"):
        raise HTTPException(status_code=401, detail="No refresh token available")
    
    try:
        token_response = http_requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": AUTH0_CLIENT_ID,
                "refresh_token": session["refresh_token"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        token_data = token_response.json()
        
        if not token_response.ok or "error" in token_data:
            log.error(f"🔐 Token refresh failed: {token_data}")
            raise HTTPException(status_code=401, detail="Token refresh failed")
        
        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 86400)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        auth_dao.update_access_token(user_id, new_access_token, expires_at)
        log.info(f"🔐 Token refreshed for user={user_id}")
        
        return {"access_token": new_access_token, "expires_at": expires_at}
        
    except http_requests.RequestException as e:
        log.error(f"🔐 Token refresh request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout(
    request: Request,
    auth_dao=Depends(auth_dao_dependency),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Log out a user by deleting their session.
    """
    try:
        body = await request.json()
        user_id = body.get("user_id")
    except Exception:
        user_id = None
    
    if user_id:
        auth_dao.delete_session(user_id)
        log.info(f"🔐 User {user_id} logged out")
    else:
        log.info("🔐 Logout called without user_id")

    # Match Flask behavior: clear OAuth integrations on logout
    for provider in ("google", "github", "notion"):
        try:
            integration_dao.delete_token(provider)
        except Exception as e:
            log.warning(f"⚠️ Failed to delete integration token for {provider}: {e}")
    
    return {"ok": True}


@router.get("/check")
async def auth_check(
    state: str = Query(...),
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Polled by frontend after starting Auth0 login.
    Returns: { "status": "pending" | "ready" | "error", tokens/user if ready, error info if error }.
    When status is "ready", tokens are returned once and then removed.
    """
    result = auth_dao.get_and_consume_pending_auth(state)
    return result


@router.get("/current")
async def get_current_session(auth_dao=Depends(auth_dao_dependency)):
    """
    Return the active Auth0 session for the logged-in desktop user.

    Single-user desktop app: returns the most recently updated session, or
    unauthenticated if none exist.
    """
    sessions = auth_dao.get_all_sessions()
    if not sessions:
        return {
            "authenticated": False,
            "access_token": None,
            "user_id": None,
            "user_info": None,
            "expired": False,
        }

    sessions_sorted = sorted(
        sessions,
        key=lambda s: s.get("updated_at") or "",
        reverse=True,
    )
    latest_user_id = sessions_sorted[0].get("user_id")
    if not latest_user_id:
        return {
            "authenticated": False,
            "access_token": None,
            "user_id": None,
            "user_info": None,
            "expired": False,
        }

    session = auth_dao.get_session(latest_user_id)
    if not session:
        return {
            "authenticated": False,
            "access_token": None,
            "user_id": None,
            "user_info": None,
            "expired": False,
        }

    expired = False
    expires_at = session.get("expires_at")
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
            expired = datetime.utcnow() > expires
        except ValueError:
            pass

    return {
        "authenticated": True,
        "expired": expired,
        "access_token": session.get("access_token"),
        "user_id": session.get("user_id"),
        "user_info": session.get("user_info"),
    }
