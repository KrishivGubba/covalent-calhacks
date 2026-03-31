"""
Authentication endpoints (Auth0 PKCE flow).
"""
import os
import sys
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
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
    state: Optional[str] = None
    code_verifier: Optional[str] = None


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
        return JSONResponse(
            status_code=400,
            content={"error": "state and code_verifier are required"},
        )
    
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
        return JSONResponse(status_code=400, content={"error": "user_id is required"})
    
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
    
    return {"session": None}


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
        return JSONResponse(status_code=400, content={"error": "user_id is required"})
    
    session = auth_dao.get_session(user_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    if not session.get("refresh_token"):
        return JSONResponse(status_code=400, content={"error": "No refresh token available"})
    
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
            err = token_data.get("error", "refresh_failed")
            err_desc = token_data.get("error_description", "Token refresh failed")
            log.error(f"🔐 Token refresh failed: {token_data}")
            return JSONResponse(
                status_code=400,
                content={"error": err, "error_description": err_desc},
            )
        
        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 86400)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        auth_dao.update_access_token(user_id, new_access_token, expires_at)
        log.info(f"🔐 Token refreshed for user={user_id}")
        
        return {"access_token": new_access_token, "expires_at": expires_at}
        
    except http_requests.RequestException as e:
        log.error(f"🔐 Token refresh request failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "exception", "error_description": str(e)},
        )


@router.post("/logout")
async def logout(
    request: Request,
    auth_dao=Depends(auth_dao_dependency),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Log out a user by deleting their session.
    """
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    session_deleted = auth_dao.delete_session(user_id)
    google_deleted = integration_dao.delete_token("google")
    github_deleted = integration_dao.delete_token("github")
    notion_deleted = integration_dao.delete_token("notion")
    tokens_deleted = google_deleted + github_deleted + notion_deleted

    log.info(
        f"🔐 Logged out user={user_id} "
        f"(session={session_deleted}, google={google_deleted}, github={github_deleted}, notion={notion_deleted})"
    )

    return {
        "ok": True,
        "deleted": session_deleted > 0,
        "integrations_deleted": tokens_deleted,
    }


@router.get("/check")
async def auth_check(
    state: Optional[str] = Query(None),
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Polled by frontend after starting Auth0 login.
    Returns: { "status": "pending" | "ready" | "error", tokens/user if ready, error info if error }.
    When status is "ready", tokens are returned once and then removed.
    """
    if not state:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": "missing state"},
        )

    result = auth_dao.get_and_consume_pending_auth(state)
    if not result:
        return {"status": "pending"}
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
