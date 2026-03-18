"""
Authentication endpoints (Auth0 PKCE flow).
"""
import os
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

import requests as http_requests

from ..dependencies import auth_dao_dependency, get_db_path, get_encrypted_conn
from logger import get_logger

log = get_logger()
router = APIRouter()

# Auth0 config
AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com'
FLASK_PORT = int(os.environ.get('VITE_FLASK_PORT', '15001'))
AUTH0_CLIENT_ID = os.environ.get('VITE_AUTH0_CLIENT_ID', '')
AUTH0_REDIRECT_URI = f'http://localhost:{FLASK_PORT}/callback'


class AuthStartRequest(BaseModel):
    state: str
    code_verifier: str


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
async def get_session(auth_dao=Depends(auth_dao_dependency)):
    """
    Get the current user session.
    """
    session = auth_dao.get_current_session()
    if session:
        user_info = session.get("user_info")
        if isinstance(user_info, str):
            try:
                user_info = json.loads(user_info)
            except json.JSONDecodeError:
                pass
        
        return {
            "authenticated": True,
            "user_id": session.get("user_id"),
            "user_info": user_info,
            "expired": session.get("expired", False),
        }
    
    return {"authenticated": False, "user_id": None, "user_info": None}


@router.post("/logout")
async def logout(auth_dao=Depends(auth_dao_dependency)):
    """
    Log out the current user by clearing the session.
    """
    auth_dao.clear_current_session()
    log.info("🔐 User logged out")
    return {"ok": True}


@router.get("/poll/{state}")
async def auth_poll(
    state: str,
    auth_dao=Depends(auth_dao_dependency),
):
    """
    Poll for auth result after Auth0 callback.
    """
    pending = auth_dao.get_pending(state)
    if not pending:
        return {"status": "pending"}
    
    if pending.get("error"):
        return {
            "status": "error",
            "error": pending.get("error"),
            "error_description": pending.get("error_description"),
        }
    
    if pending.get("access_token"):
        # Session should already be created by callback
        session = auth_dao.get_current_session()
        return {
            "status": "success",
            "access_token": pending.get("access_token"),
            "user_info": session.get("user_info") if session else None,
        }
    
    return {"status": "pending"}


# Note: The actual /callback endpoint is handled at the app level
# because it may need to return HTML for browser redirect
