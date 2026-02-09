from flask import Flask, request, jsonify, g
import sqlite3
import os
import sys
import time
import asyncio
import json
from datetime import datetime, timedelta

from flask_cors import CORS
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Add context-engine to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'context-engine'))
from graph import Tree
from auth_dao import AuthDAO
from integration_dao import IntegrationDAO

# Import action executor for MCP integration
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from action_executor import (
    plan_action, 
    execute_action, 
    gather_context,
    research_and_plan,
    health_check as mcp_health_check
)

# Import display schema registry for tool approval UI
from covalent_mcp.tools import get_display_schema
from covalent_mcp.toolclasses.base import resolve_display_fields


# =============================================================================
# DISPLAY SCHEMA RESOLUTION HELPER
# =============================================================================

def _resolve_tool_display(proposed_action: dict, loop=None) -> dict:
    """
    Given a proposed_action dict (with tool_name and parameters), resolve the
    display schema so the frontend can render a human-readable approval card.

    Returns a dict with:
      - "display_name": human-readable tool name
      - "description": short blurb
      - "fields": list of field dicts with values populated
      - "has_schema": True if a display schema exists, False for fallback

    If no schema is registered for the tool, returns a fallback that shows
    every parameter as an editable text field.
    """
    tool_name = proposed_action.get("tool_name", "")
    parameters = proposed_action.get("parameters", {})

    schema = get_display_schema(tool_name)

    if schema is None:
        # Fallback: show all params as editable text fields
        fallback_fields = []
        for key, value in parameters.items():
            fallback_fields.append({
                "key": key,
                "label": key.replace("_", " ").title(),
                "source": "param",
                "editable": True,
                "widget": "text_input",
                "required": False,
                "value": value,
            })
        return {
            "display_name": tool_name.replace("_", " ").title(),
            "description": "",
            "fields": fallback_fields,
            "has_schema": False,
        }

    # Schema exists - resolve it (may call external APIs)
    _loop = loop or asyncio.new_event_loop()
    _owns_loop = loop is None
    if _owns_loop:
        asyncio.set_event_loop(_loop)
    try:
        display_info = _loop.run_until_complete(
            resolve_display_fields(schema, parameters)
        )
    finally:
        if _owns_loop:
            _loop.close()

    display_info["has_schema"] = True
    return display_info


app = Flask(__name__)
CORS(app)
print("Starting Flask app")
print("hello krishvi gubba")
print("random startup log")

@app.before_request
def start_timer():
    g.start_time = time.perf_counter()

@app.after_request
def log_request(response):
    if hasattr(g, "start_time"):
        duration = time.perf_counter() - g.start_time
        app.logger.info("Request %s %s completed in %.3f ms", request.method, request.path, duration * 1000)
        response.headers["X-Process-Time"] = f"{duration:.3f}s"
    return response

# Connect to SQLite Database
db_path = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')

tree = Tree(db_path)


import requests as http_requests  # for server-side HTTP calls to Auth0

# Auth0 config (must match frontend)
AUTH0_DOMAIN = 'dev-sb3sx3jnljwod4ab.us.auth0.com'
AUTH0_CLIENT_ID = os.environ.get('VITE_AUTH0_CLIENT_ID', '')
AUTH0_REDIRECT_URI = 'http://localhost:5001/callback'

# Google OAuth config (token exchange happens via Lambda to keep secret secure)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_REDIRECT_URI = 'http://127.0.0.1:5001/integrations/google/callback'
GOOGLE_SCOPES = 'openid https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email'

# GitHub OAuth config (token exchange via Lambda to keep client_secret secure)
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_REDIRECT_URI = 'http://127.0.0.1:5001/integrations/github/callback'
GITHUB_SCOPES = 'repo read:user'  # repo = full repo access (repos, issues, PRs), read:user = user profile

# Notion OAuth config (token exchange via Lambda to keep client_secret secure)
NOTION_CLIENT_ID = os.environ.get('NOTION_CLIENT_ID', '')
NOTION_REDIRECT_URI = 'http://localhost:5001/integrations/notion/callback'

# Lambda Gateway URL for secure token exchange
LAMBDA_GATEWAY_URL = os.environ.get('LAMBDA_GATEWAY_URL', 'https://gtfrn4otol.execute-api.us-east-1.amazonaws.com')

# In-memory storage for pending OAuth (state -> {code_verifier, result, ...})
# Short-lived, cleared after auth completes
google_auth_pending = {}
github_auth_pending = {}
notion_auth_pending = {}

# HTML templates directory
HTML_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'htmlstuff')


def load_html_template(filename, replacements=None):
    """Load an HTML template from htmlstuff/ and optionally replace placeholders."""
    filepath = os.path.join(HTML_TEMPLATES_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if replacements:
        for key, value in replacements.items():
            content = content.replace(key, value)
    return content


def _ensure_auth_table_schema():
    """Ensure auth_pending table has all required columns (migration for existing DBs)."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        cursor = conn.execute("PRAGMA table_info(auth_pending)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        needed = [
            ("code_verifier", "TEXT"),
            ("access_token", "TEXT"),
            ("id_token", "TEXT"),
            ("refresh_token", "TEXT"),
            ("user_info", "TEXT"),
        ]
        for col_name, col_type in needed:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE auth_pending ADD COLUMN {col_name} {col_type}")
                print(f"🔧 Added column {col_name} to auth_pending table")
        conn.commit()
    except Exception as e:
        print(f"⚠️  Failed to migrate auth_pending table: {e}")
    finally:
        conn.close()


# Run migration on startup, then instantiate DAOs
_ensure_auth_table_schema()
auth_dao = AuthDAO(db_path)
auth_dao.ensure_sessions_table()  # Create user_sessions table if needed

integration_dao = IntegrationDAO(db_path)
integration_dao.ensure_table()  # Create integration_tokens table if needed


@app.route("/screen", methods=["POST"])
def screen():
    try:
        body = request.get_json()
        
        # The body is already parsed JSON from the Rust code
        # Extract fields directly from the JSON object
        description = body.get("description", "")
        app_name = body.get("app_name", "Unknown")
        context_type = body.get("context_type", {})
        activity_level = body.get("activity_level", "Unknown")
        workflow_stage = body.get("workflow_stage", "Unknown")
        
        # Format context_type properly (it's a nested object like {"Development": "DevOps"})
        context_type_str = "Unknown"
        if isinstance(context_type, dict) and context_type:
            # Get the first key-value pair from the context_type dict
            for key, value in context_type.items():
                context_type_str = f"{key}({value})" if value else key
                break
        
        # Enhance description with app context for better action generation
        enhanced_description = f"Current App: {app_name} | Context: {context_type_str} | Activity: {activity_level} | Stage: {workflow_stage} | {description}"
        
        print(f"Enhanced description: {enhanced_description}")
        
        # Get MCP integration statuses (so LLM knows which actions are available)
        statuses = integration_dao.get_all_statuses()
        
        # Build list of available MCPs
        available_mcps = [
            {
                "id": "filesystem",
                "name": "Filesystem",
                "description": "Access local files and directories",
                "connected": True,
            },
            {
                "id": "github",
                "name": "GitHub",
                "description": "Access repositories, issues, and pull requests",
                "connected": statuses.get("github", False),
            },
            {
                "id": "perplexity",
                "name": "Perplexity Search",
                "description": "AI-powered web search",
                "connected": True,
            },
            {
                "id": "notion",
                "name": "Notion",
                "description": "Access Notion workspaces and pages",
                "connected": statuses.get("notion", False),
            },
            {
                "id": "google",
                "name": "Google Workspace",
                "description": "Calendar, Drive, Mail",
                "connected": statuses.get("google", False),
            },
        ]
        
        # Filter to only connected MCPs
        connected_mcps = [mcp for mcp in available_mcps if mcp["connected"]]
        
        print(f"Available MCPs: {[mcp['name'] for mcp in connected_mcps]}")
        
        # Convert the entire body to JSON string for storage
        import json
        data_str = json.dumps(body)
        
        # Call learn function - returns dict with structure info and actions
        print(f"\n📍 DEBUG: Calling tree.learn_with_structure()...")
        result = tree.learn_with_structure(enhanced_description, data_str, available_mcps=connected_mcps)
        print(f"📍 DEBUG: Operation: {result['operation']}, Confidence: {result['confidence']}")
        
        # Extract recent actions from the result
        recent_actions = result.get("actions", [])
        print(f"📍 DEBUG: Got {len(recent_actions)} recent actions")

        # Format actions for frontend
        actions_list = []
        for action in recent_actions:
            uuid, name, plan, prompt, node_uuid, last_selected = action
            actions_list.append({
                "action_uuid": str(uuid),
                "action_name": name,
                "action_plan": plan,
                "action_prompt": prompt,
                "last_selected": last_selected
            })

        # Get the most recent action (first in list) for legacy compatibility
        primary_action = actions_list[0] if actions_list else None

        # Return all recent actions to the frontend
        return jsonify({
            "message": f"Context processed successfully. {len(actions_list)} recent actions available.",
            "primary_action": primary_action,
            "recent_actions": actions_list,
            # Legacy fields for backward compatibility
            "action_name": primary_action["action_name"] if primary_action else None,
            "action_plan": primary_action["action_plan"] if primary_action else None,
            "action_prompt": primary_action["action_prompt"] if primary_action else None,
            "action_uuid": primary_action["action_uuid"] if primary_action else None
        }), 200
    except Exception as e:
        print(f"Error in /screen endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "covalent-context-engine"}), 200


@app.route("/auth/start", methods=["POST"])
def auth_start():
    """
    Called by frontend before opening Auth0 login.
    Stores the code_verifier so the backend can do the token exchange later.
    Body: { "state": "...", "code_verifier": "..." }
    """
    body = request.get_json() or {}
    state = body.get("state")
    code_verifier = body.get("code_verifier")
    if not state or not code_verifier:
        return jsonify({"error": "state and code_verifier are required"}), 400
    auth_dao.save_code_verifier(state, code_verifier)
    print(f"🔐 Auth start: stored code_verifier for state={state[:8]}...")
    return jsonify({"ok": True}), 200


@app.route("/callback", methods=["GET", "POST"])
def auth_callback():
    """
    Auth0 redirect target. Performs server-side token exchange and stores result for frontend to poll.
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    error_description = request.args.get("error_description")

    def render_error(message):
        return load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': message})

    if not state:
        return render_error("Missing state parameter"), 400

    # If Auth0 returned an error
    if error:
        auth_dao.save_auth_result(state, error=error, error_description=error_description)
        print(f"🔐 Auth callback error: {error} - {error_description}")
        return render_error(error_description or error), 200

    if not code:
        auth_dao.save_auth_result(state, error="no_code", error_description="No authorization code received")
        return render_error("No authorization code received"), 200

    # Retrieve the code_verifier
    code_verifier = auth_dao.get_code_verifier(state)
    if not code_verifier:
        auth_dao.save_auth_result(state, error="no_verifier", error_description="Code verifier not found - session may have expired")
        return render_error("Session expired. Please try again."), 200

    # Exchange code for tokens (server-side, no CORS issues)
    try:
        print(f"🔐 Exchanging code for tokens (state={state[:8]}...)...")
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
            print(f"🔐 Token exchange failed: {err} - {err_desc}")
            return render_error(err_desc), 200

        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 86400)  # Default 24 hours

        print(f"🔐 Tokens received. Fetching user info...")

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
                print(f"🔐 User info: {user_info.get('email', user_info.get('sub', 'unknown'))}")
        except Exception as e:
            print(f"🔐 Failed to fetch user info: {e}")

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
            print(f"🔐 Saved persistent session for user={user_info['sub']}")

        print(f"🔐 Auth complete for state={state[:8]}...")
        return load_html_template('auth_success.html'), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        auth_dao.save_auth_result(state, error="exception", error_description=str(e))
        return render_error(f"An error occurred: {e}"), 200


@app.route("/auth/check", methods=["GET"])
def auth_check():
    """
    Polled by frontend after starting Auth0 login. Query param: state.
    Returns: { "status": "pending" | "ready" | "error", tokens/user if ready, error info if error }.
    When status is "ready", tokens are returned once and then removed.
    """
    state = request.args.get("state")
    if not state:
        return jsonify({"status": "pending", "error": "missing state"}), 400
    result = auth_dao.get_and_consume_pending_auth(state)
    return jsonify(result), 200


@app.route("/auth/session", methods=["GET"])
def get_session():
    """
    Retrieve a persistent user session by user_id.
    Query param: user_id (the Auth0 sub claim).
    Returns session data if found, or null.
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    session = auth_dao.get_session(user_id)
    if not session:
        return jsonify({"session": None}), 200
    
    # Check if token is expired
    if session.get("expires_at"):
        try:
            expires = datetime.fromisoformat(session["expires_at"])
            if datetime.utcnow() > expires:
                # Token expired - frontend should refresh
                return jsonify({
                    "session": session,
                    "expired": True,
                }), 200
        except ValueError:
            pass
    
    return jsonify({"session": session, "expired": False}), 200


@app.route("/auth/session/refresh", methods=["POST"])
def refresh_session():
    """
    Refresh an expired access token using the refresh token.
    Body: { "user_id": "..." }
    """
    body = request.get_json() or {}
    user_id = body.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    session = auth_dao.get_session(user_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "No refresh token available"}), 400
    
    try:
        # Use refresh token to get new access token
        token_response = http_requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": AUTH0_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        token_data = token_response.json()

        if not token_response.ok or "error" in token_data:
            err = token_data.get("error", "refresh_failed")
            err_desc = token_data.get("error_description", "Token refresh failed")
            print(f"🔐 Token refresh failed: {err} - {err_desc}")
            return jsonify({"error": err, "error_description": err_desc}), 400

        new_access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 86400)
        new_refresh_token = token_data.get("refresh_token")  # Auth0 may rotate

        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        # Update session with new tokens
        if new_refresh_token:
            # If Auth0 rotated the refresh token, save the new one
            auth_dao.save_session(
                user_id=user_id,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_at=expires_at,
            )
        else:
            auth_dao.update_access_token(user_id, new_access_token, expires_at)

        print(f"🔐 Refreshed access token for user={user_id}")
        
        return jsonify({
            "access_token": new_access_token,
            "expires_at": expires_at,
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "exception", "error_description": str(e)}), 500


@app.route("/auth/logout", methods=["POST"])
def logout():
    """
    Delete a user session (logout).
    Also deletes OAuth integration tokens (Google, GitHub, Notion).
    Body: { "user_id": "..." }
    """
    body = request.get_json() or {}
    user_id = body.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    # Delete user session
    session_deleted = auth_dao.delete_session(user_id)
    
    # Delete OAuth integration tokens individually (not "included" ones like filesystem)
    google_deleted = integration_dao.delete_token("google")
    github_deleted = integration_dao.delete_token("github")
    notion_deleted = integration_dao.delete_token("notion")
    
    tokens_deleted = google_deleted + github_deleted + notion_deleted
    
    print(f"🔐 Logged out user={user_id} (session={session_deleted}, google={google_deleted}, github={github_deleted}, notion={notion_deleted})")
    return jsonify({"ok": True, "deleted": session_deleted > 0, "integrations_deleted": tokens_deleted}), 200


# ========================
# Integrations Endpoints
# ========================

@app.route("/integrations/status", methods=["GET"])
def integrations_status():
    """
    Get status of all integrations.
    Returns: { "integrations": [ { "id": "google", "name": "...", "connected": true/false }, ... ] }
    """
    # Get connection status from DB (single-user desktop app, no user_id needed)
    statuses = integration_dao.get_all_statuses()
    
    # Build the full integrations list with metadata
    # "included" means it's built-in and always connected (no OAuth needed)
    integrations = [
        {
            "id": "filesystem",
            "name": "Filesystem",
            "description": "Access local files and directories",
            "icon": "📁",
            "connected": True,  # Always connected - uses local filesystem
            "included": True,
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
            "description": "AI-powered web search",
            "icon": "🔍",
            "connected": True,  # Always connected - uses API key
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
    
    return jsonify({"integrations": integrations}), 200


# ========================
# Google OAuth Endpoints
# ========================

@app.route("/integrations/google/start", methods=["POST"])
def google_auth_start():
    """
    Called by frontend before opening Google OAuth.
    Stores the code_verifier and auth token so backend can do token exchange later via Lambda.
    Body: { "state": "...", "code_verifier": "...", "auth_token": "..." }
    """
    body = request.get_json() or {}
    state = body.get("state")
    code_verifier = body.get("code_verifier")
    auth_token = body.get("auth_token")  # Auth0 access token for Lambda call
    
    if not state or not code_verifier:
        return jsonify({"error": "state and code_verifier are required"}), 400
    
    if not auth_token:
        return jsonify({"error": "auth_token is required (user must be logged in)"}), 400
    
    google_auth_pending[state] = {
        "code_verifier": code_verifier,
        "auth_token": auth_token,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    print(f"🔷 Google auth start: stored code_verifier for state={state[:8]}...")
    return jsonify({"ok": True}), 200


@app.route("/integrations/google/callback", methods=["GET"])
def google_auth_callback():
    """
    Google OAuth redirect target. Exchanges code for tokens using PKCE (no secret).
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    
    def render_error(message):
        return load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': f"Google: {message}"})
    
    if not state:
        return render_error("Missing state parameter"), 400
    
    if state not in google_auth_pending:
        return render_error("Invalid or expired state. Please try again."), 400
    
    # If Google returned an error
    if error:
        google_auth_pending[state]["status"] = "error"
        google_auth_pending[state]["error"] = error
        google_auth_pending[state]["error_description"] = request.args.get("error_description", error)
        print(f"🔷 Google callback error: {error}")
        return render_error(request.args.get("error_description", error)), 200
    
    if not code:
        google_auth_pending[state]["status"] = "error"
        google_auth_pending[state]["error"] = "no_code"
        google_auth_pending[state]["error_description"] = "No authorization code received"
        return render_error("No authorization code received"), 200
    
    code_verifier = google_auth_pending[state].get("code_verifier")
    auth_token = google_auth_pending[state].get("auth_token")
    
    if not code_verifier:
        google_auth_pending[state]["status"] = "error"
        google_auth_pending[state]["error"] = "no_verifier"
        google_auth_pending[state]["error_description"] = "Code verifier not found"
        return render_error("Session expired. Please try again."), 200
    
    if not auth_token:
        google_auth_pending[state]["status"] = "error"
        google_auth_pending[state]["error"] = "no_auth_token"
        google_auth_pending[state]["error_description"] = "Auth token not found - user must be logged in"
        return render_error("Please log in first."), 200
    
    # Exchange code for tokens via Lambda (keeps client_secret secure on server)
    try:
        print(f"🔷 Exchanging Google code for tokens via Lambda (state={state[:8]}...)...")
        token_response = http_requests.post(
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
        token_data = token_response.json()
        
        if not token_response.ok or "error" in token_data:
            err = token_data.get("error", "token_exchange_failed")
            err_desc = token_data.get("error_description", "Token exchange failed")
            google_auth_pending[state]["status"] = "error"
            google_auth_pending[state]["error"] = err
            google_auth_pending[state]["error_description"] = err_desc
            print(f"🔷 Google token exchange failed: {err} - {err_desc}")
            return render_error(err_desc), 200
        
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        scope = token_data.get("scope", "")
        
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        # Fetch user info from Google
        user_email = None
        try:
            userinfo_response = http_requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
            if userinfo_response.ok:
                user_info = userinfo_response.json()
                user_email = user_info.get("email")
                print(f"🔷 Google user: {user_email}")
        except Exception as e:
            print(f"🔷 Failed to fetch Google user info: {e}")
        
        # Save to integration_tokens table
        integration_dao.save_token(
            provider="google",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scope,
            provider_metadata={"email": user_email} if user_email else None,
        )
        
        # Mark as ready for frontend polling
        google_auth_pending[state]["status"] = "ready"
        google_auth_pending[state]["email"] = user_email
        
        print(f"🔷 Google auth complete for state={state[:8]}...")
        return load_html_template('auth_success.html'), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        google_auth_pending[state]["status"] = "error"
        google_auth_pending[state]["error"] = "exception"
        google_auth_pending[state]["error_description"] = str(e)
        return render_error(f"An error occurred: {e}"), 200


@app.route("/integrations/google/check", methods=["GET"])
def google_auth_check():
    """
    Polled by frontend after starting Google OAuth. Query param: state.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    state = request.args.get("state")
    if not state:
        return jsonify({"status": "error", "error": "missing state"}), 400
    
    if state not in google_auth_pending:
        return jsonify({"status": "error", "error": "invalid_state"}), 400
    
    pending = google_auth_pending[state]
    status = pending.get("status", "pending")
    
    if status == "ready":
        # Clean up and return success
        email = pending.get("email")
        del google_auth_pending[state]
        return jsonify({"status": "ready", "email": email}), 200
    elif status == "error":
        # Clean up and return error
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del google_auth_pending[state]
        return jsonify({"status": "error", "error": error, "error_description": error_desc}), 200
    else:
        return jsonify({"status": "pending"}), 200


@app.route("/integrations/google/disconnect", methods=["POST"])
def google_disconnect():
    """
    Disconnect Google integration (delete tokens).
    """
    deleted = integration_dao.delete_token("google")
    print(f"🔷 Google disconnected (deleted={deleted})")
    return jsonify({"ok": True, "deleted": deleted > 0}), 200


@app.route("/integrations/google/refresh", methods=["POST"])
def google_refresh_token():
    """
    Refresh Google access token using the refresh token via Lambda.
    Body: { "auth_token": "..." } - Auth0 token to authenticate with Lambda.
    
    If auth_token is not provided in the body, it will be auto-read from the
    user_sessions table in the database (single-user desktop app).
    """
    body = request.get_json() or {}
    auth_token = body.get("auth_token")
    
    # If no auth_token provided, try to read from user sessions DB
    if not auth_token:
        sessions = auth_dao.get_all_sessions()
        if sessions:
            session = auth_dao.get_session(sessions[0]["user_id"])
            if session:
                auth_token = session.get("access_token")
    
    if not auth_token:
        return jsonify({"error": "auth_token is required and no active session found"}), 400
    
    token_data = integration_dao.get_token("google")
    if not token_data:
        return jsonify({"error": "Google not connected"}), 404
    
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "No refresh token available"}), 400
    
    try:
        # Call Lambda to refresh the token (keeps client_secret secure)
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
            print(f"🔷 Google token refresh failed: {err} - {err_desc}")
            return jsonify({"error": err, "error_description": err_desc}), 400
        
        new_access_token = new_token_data.get("access_token")
        expires_in = new_token_data.get("expires_in", 3600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        integration_dao.update_access_token("google", new_access_token, expires_at)
        print(f"🔷 Google access token refreshed")
        
        return jsonify({
            "access_token": new_access_token,
            "expires_at": expires_at,
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "exception", "error_description": str(e)}), 500


# ============================================================================
# GitHub OAuth Integration (with PKCE, token exchange via Lambda)
# ============================================================================

@app.route("/integrations/github/start", methods=["POST"])
def github_auth_start():
    """
    Called by frontend before opening GitHub OAuth.
    Stores the code_verifier and auth token so backend can do token exchange later via Lambda.
    Body: { "state": "...", "code_verifier": "...", "auth_token": "..." }
    """
    body = request.get_json() or {}
    state = body.get("state")
    code_verifier = body.get("code_verifier")
    auth_token = body.get("auth_token")  # Auth0 access token for Lambda call
    
    if not state or not code_verifier:
        return jsonify({"error": "state and code_verifier are required"}), 400
    
    if not auth_token:
        return jsonify({"error": "auth_token is required (user must be logged in)"}), 400
    
    github_auth_pending[state] = {
        "code_verifier": code_verifier,
        "auth_token": auth_token,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    print(f"🔷 GitHub auth start: stored code_verifier for state={state[:8]}...")
    return jsonify({"ok": True}), 200


@app.route("/integrations/github/callback", methods=["GET"])
def github_auth_callback():
    """
    GitHub OAuth redirect target. Exchanges code for tokens using PKCE via Lambda.
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    error_description = request.args.get("error_description")
    
    def render_error(message):
        return load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': f"GitHub: {message}"})
    
    if not state:
        return render_error("Missing state parameter"), 400
    
    if state not in github_auth_pending:
        return render_error("Invalid or expired state. Please try again."), 400
    
    # If GitHub returned an error
    if error:
        github_auth_pending[state]["status"] = "error"
        github_auth_pending[state]["error"] = error
        github_auth_pending[state]["error_description"] = error_description or error
        print(f"🔷 GitHub callback error: {error}")
        return render_error(error_description or error), 200
    
    if not code:
        github_auth_pending[state]["status"] = "error"
        github_auth_pending[state]["error"] = "no_code"
        github_auth_pending[state]["error_description"] = "No authorization code received"
        return render_error("No authorization code received"), 200
    
    code_verifier = github_auth_pending[state].get("code_verifier")
    auth_token = github_auth_pending[state].get("auth_token")
    
    if not code_verifier:
        github_auth_pending[state]["status"] = "error"
        github_auth_pending[state]["error"] = "no_verifier"
        github_auth_pending[state]["error_description"] = "Code verifier not found"
        return render_error("Session expired. Please try again."), 200
    
    if not auth_token:
        github_auth_pending[state]["status"] = "error"
        github_auth_pending[state]["error"] = "no_auth_token"
        github_auth_pending[state]["error_description"] = "Auth token not found - user must be logged in"
        return render_error("Please log in first."), 200
    
    # Exchange code for tokens via Lambda
    try:
        print(f"🔷 Exchanging GitHub code for tokens via Lambda (state={state[:8]}...)...")
        token_response = http_requests.post(
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
        token_data = token_response.json()
        
        if not token_response.ok or "error" in token_data:
            err = token_data.get("error", "token_exchange_failed")
            err_desc = token_data.get("error_description", "Token exchange failed")
            github_auth_pending[state]["status"] = "error"
            github_auth_pending[state]["error"] = err
            github_auth_pending[state]["error_description"] = err_desc
            print(f"🔷 GitHub token exchange failed: {err} - {err_desc}")
            return render_error(err_desc), 200
        
        access_token = token_data.get("access_token")
        # GitHub classic OAuth tokens don't expire and don't have refresh tokens
        scope = token_data.get("scope", "")
        
        # Fetch user info from GitHub
        username = None
        user_email = None
        try:
            userinfo_response = http_requests.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=5,
            )
            if userinfo_response.ok:
                user_info = userinfo_response.json()
                username = user_info.get("login")
                user_email = user_info.get("email")
                print(f"🔷 GitHub user: {username} ({user_email})")
        except Exception as e:
            print(f"🔷 Failed to fetch GitHub user info: {e}")
        
        # Save to integration_tokens table
        # GitHub tokens don't expire, so expires_at is None
        integration_dao.save_token(
            provider="github",
            access_token=access_token,
            refresh_token=None,  # GitHub doesn't use refresh tokens
            expires_at=None,     # GitHub tokens don't expire
            scopes=scope,
            provider_metadata={"username": username, "email": user_email},
        )
        
        # Mark as ready for frontend polling
        github_auth_pending[state]["status"] = "ready"
        github_auth_pending[state]["username"] = username
        
        print(f"🔷 GitHub auth complete for state={state[:8]}...")
        return load_html_template('auth_success.html'), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        github_auth_pending[state]["status"] = "error"
        github_auth_pending[state]["error"] = "exception"
        github_auth_pending[state]["error_description"] = str(e)
        return render_error(f"An error occurred: {e}"), 200


@app.route("/integrations/github/check", methods=["GET"])
def github_auth_check():
    """
    Polled by frontend after starting GitHub OAuth. Query param: state.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    state = request.args.get("state")
    if not state:
        return jsonify({"status": "error", "error": "missing state"}), 400
    
    if state not in github_auth_pending:
        return jsonify({"status": "error", "error": "invalid_state"}), 400
    
    pending = github_auth_pending[state]
    status = pending.get("status", "pending")
    
    if status == "ready":
        # Clean up and return success
        username = pending.get("username")
        del github_auth_pending[state]
        return jsonify({"status": "ready", "username": username}), 200
    elif status == "error":
        # Clean up and return error
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del github_auth_pending[state]
        return jsonify({"status": "error", "error": error, "error_description": error_desc}), 200
    else:
        return jsonify({"status": "pending"}), 200


@app.route("/integrations/github/disconnect", methods=["POST"])
def github_disconnect():
    """
    Disconnect GitHub integration (delete tokens).
    """
    deleted = integration_dao.delete_token("github")
    print(f"🔷 GitHub disconnected (deleted={deleted})")
    return jsonify({"ok": True, "deleted": deleted > 0}), 200


# ============================================================================
# Notion OAuth Integration (token exchange via Lambda)
# ============================================================================

@app.route("/integrations/notion/start", methods=["POST"])
def notion_auth_start():
    """
    Called by frontend before opening Notion OAuth.
    Stores the state and auth token so backend can do token exchange later via Lambda.
    Body: { "state": "...", "auth_token": "..." }
    
    Note: Notion OAuth does NOT use PKCE, so no code_verifier needed.
    """
    body = request.get_json() or {}
    state = body.get("state")
    auth_token = body.get("auth_token")  # Auth0 access token for Lambda call
    
    if not state:
        return jsonify({"error": "state is required"}), 400
    
    if not auth_token:
        return jsonify({"error": "auth_token is required (user must be logged in)"}), 400
    
    notion_auth_pending[state] = {
        "auth_token": auth_token,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    print(f"🔷 Notion auth start: stored state={state[:8]}...")
    return jsonify({"ok": True}), 200


@app.route("/integrations/notion/callback", methods=["GET"])
def notion_auth_callback():
    """
    Notion OAuth redirect target. Exchanges code for tokens via Lambda.
    
    Notion sends: ?code=...&state=...
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    
    def render_error(message):
        return load_html_template('auth_error.html', {'{{ERROR_MESSAGE}}': f"Notion: {message}"})
    
    if not state:
        return render_error("Missing state parameter"), 400
    
    if state not in notion_auth_pending:
        return render_error("Invalid or expired state. Please try again."), 400
    
    # If Notion returned an error
    if error:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = error
        notion_auth_pending[state]["error_description"] = request.args.get("error_description", error)
        print(f"🔷 Notion callback error: {error}")
        return render_error(request.args.get("error_description", error)), 200
    
    if not code:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "no_code"
        notion_auth_pending[state]["error_description"] = "No authorization code received"
        return render_error("No authorization code received"), 200
    
    auth_token = notion_auth_pending[state].get("auth_token")
    
    if not auth_token:
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "no_auth_token"
        notion_auth_pending[state]["error_description"] = "Auth token not found - user must be logged in"
        return render_error("Please log in first."), 200
    
    # Exchange code for tokens via Lambda
    try:
        print(f"🔷 Exchanging Notion code for tokens via Lambda (state={state[:8]}...)...")
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
            print(f"🔷 Notion token exchange failed: {err} - {err_desc}")
            return render_error(err_desc), 200
        
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")  # Notion provides refresh tokens
        workspace_name = token_data.get("workspace_name")
        workspace_id = token_data.get("workspace_id")
        bot_id = token_data.get("bot_id")
        
        # Save to integration_tokens table
        # Note: Notion access tokens have an expiry; use refresh_token to renew
        integration_dao.save_token(
            provider="notion",
            access_token=access_token,
            refresh_token=refresh_token,  # Store refresh token for renewal
            expires_at=None,     # Notion doesn't return expires_in directly
            scopes=None,         # Notion doesn't use scopes in the same way
            provider_metadata={
                "workspace_name": workspace_name,
                "workspace_id": workspace_id,
                "bot_id": bot_id,
            },
        )
        
        # Mark as ready for frontend polling
        notion_auth_pending[state]["status"] = "ready"
        notion_auth_pending[state]["workspace_name"] = workspace_name
        
        print(f"🔷 Notion auth complete: workspace={workspace_name}")
        return load_html_template('auth_success.html'), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        notion_auth_pending[state]["status"] = "error"
        notion_auth_pending[state]["error"] = "exception"
        notion_auth_pending[state]["error_description"] = str(e)
        return render_error(f"An error occurred: {e}"), 200


@app.route("/integrations/notion/check", methods=["GET"])
def notion_auth_check():
    """
    Polled by frontend after starting Notion OAuth. Query param: state.
    Returns: { "status": "pending" | "ready" | "error", ... }
    """
    state = request.args.get("state")
    if not state:
        return jsonify({"status": "error", "error": "missing state"}), 400
    
    if state not in notion_auth_pending:
        return jsonify({"status": "error", "error": "invalid_state"}), 400
    
    pending = notion_auth_pending[state]
    status = pending.get("status", "pending")
    
    if status == "ready":
        workspace_name = pending.get("workspace_name")
        del notion_auth_pending[state]
        return jsonify({"status": "ready", "workspace_name": workspace_name}), 200
    elif status == "error":
        error = pending.get("error")
        error_desc = pending.get("error_description")
        del notion_auth_pending[state]
        return jsonify({"status": "error", "error": error, "error_description": error_desc}), 200
    else:
        return jsonify({"status": "pending"}), 200


@app.route("/integrations/notion/disconnect", methods=["POST"])
def notion_disconnect():
    """
    Disconnect Notion integration (delete tokens).
    """
    deleted = integration_dao.delete_token("notion")
    print(f"🔷 Notion disconnected (deleted={deleted})")
    return jsonify({"ok": True, "deleted": deleted > 0}), 200


@app.route("/integrations/notion/refresh", methods=["POST"])
def notion_refresh_token():
    """
    Refresh Notion access token using the refresh token via Lambda.
    Body: { "auth_token": "..." } - Auth0 token to authenticate with Lambda.
    
    If auth_token is not provided in the body, it will be auto-read from the
    user_sessions table in the database (single-user desktop app).
    """
    body = request.get_json() or {}
    auth_token = body.get("auth_token")
    
    # If no auth_token provided, try to read from user sessions DB
    if not auth_token:
        sessions = auth_dao.get_all_sessions()
        if sessions:
            session = auth_dao.get_session(sessions[0]["user_id"])
            if session:
                auth_token = session.get("access_token")
    
    if not auth_token:
        return jsonify({"error": "auth_token is required and no active session found"}), 400
    
    token_data = integration_dao.get_token("notion")
    if not token_data:
        return jsonify({"error": "Notion not connected"}), 404
    
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "No refresh token available"}), 400
    
    try:
        # Call Lambda to refresh the token (keeps client_secret secure)
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
            print(f"🔷 Notion token refresh failed: {err} - {err_desc}")
            return jsonify({"error": err, "error_description": err_desc}), 400
        
        new_access_token = new_token_data.get("access_token")
        new_refresh_token = new_token_data.get("refresh_token")  # Notion may rotate
        expires_in = new_token_data.get("expires_in", 3600)
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        # Update access token in DB
        integration_dao.update_access_token("notion", new_access_token, expires_at)
        
        # If Notion rotated the refresh token, update that too
        if new_refresh_token and new_refresh_token != refresh_token:
            integration_dao.save_token(
                provider="notion",
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_at=expires_at,
            )
        
        print(f"🔷 Notion access token refreshed")
        
        return jsonify({
            "access_token": new_access_token,
            "expires_at": expires_at,
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "exception", "error_description": str(e)}), 500


# ========================
# Graph Visualization & Reset Endpoints
# ========================

@app.route("/graph/data", methods=["GET"])
def graph_data():
    """
    Return full graph data (nodes, edges, actions, data entries) for UI visualization.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()

        # Get all nodes
        cursor.execute("SELECT UUID, Metadata, parent_uuid, children_uuid_arr FROM node_table")
        raw_nodes = cursor.fetchall()

        # Get all actions
        cursor.execute("SELECT UUID, Action_name, Node_UUID FROM action_table")
        raw_actions = cursor.fetchall()

        # Get all data entries
        cursor.execute("SELECT UUID, Node_UUID, key, type, category FROM data_table")
        raw_data = cursor.fetchall()

        conn.close()

        # Build actions-per-node lookup
        from collections import defaultdict
        actions_per_node = defaultdict(list)
        for action_uuid, action_name, node_uuid in raw_actions:
            actions_per_node[node_uuid].append({"uuid": action_uuid, "name": action_name})

        # Build data-per-node lookup
        data_per_node = defaultdict(list)
        for data_uuid, node_uuid, key, dtype, category in raw_data:
            data_per_node[node_uuid].append({
                "uuid": data_uuid,
                "key": key,
                "type": dtype,
                "category": category,
            })

        # Build depth lookup
        node_parent = {}
        for uuid, metadata, parent_uuid, children_arr in raw_nodes:
            node_parent[uuid] = parent_uuid

        def get_depth(uuid, depth=0):
            parent = node_parent.get(uuid)
            if parent is None:
                return depth
            return get_depth(parent, depth + 1)

        # Build node list and edge list
        nodes = []
        edges = []
        for uuid, metadata, parent_uuid, children_arr in raw_nodes:
            depth = get_depth(uuid)
            nodes.append({
                "id": uuid,
                "label": metadata or "Untitled",
                "parent_id": parent_uuid,
                "depth": depth,
                "actions": actions_per_node.get(uuid, []),
                "data": data_per_node.get(uuid, []),
            })
            if parent_uuid and parent_uuid in node_parent:
                edges.append({"from": parent_uuid, "to": uuid})

        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(raw_nodes),
                "total_actions": len(raw_actions),
                "total_data": len(raw_data),
            },
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/graph/reset", methods=["POST"])
def graph_reset():
    """
    Reset only the graph-related tables (node_table, action_table, data_table, node_counters).
    Preserves auth tables (auth_pending, user_sessions, integration_tokens).
    """
    global tree
    try:
        # Close the Tree's DAO connection so we can safely modify the tables
        try:
            tree.dao.close()
        except Exception:
            pass

        # Connect directly and clear only graph-related tables
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()

        # Delete all data from graph tables (order matters due to foreign keys)
        graph_tables = ["data_table", "action_table", "node_counters", "node_table"]
        for table in graph_tables:
            cursor.execute(f"DELETE FROM {table}")
            print(f"🗑️  Cleared table: {table}")

        conn.commit()
        conn.close()

        print("✅ Graph tables cleared (auth/integration tables preserved)")

        # Re-create the Tree object pointing at the DB
        tree = Tree(db_path)

        return jsonify({"message": "Graph reset successfully"}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Attempt to re-create tree even on error so the server stays functional
        try:
            tree = Tree(db_path)
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# DEPRECATED: /trigger_action endpoint is no longer used.
# New flow: frontend calls /plan_action -> user approves/edits -> /execute_action
# @app.route("/trigger_action", methods=["POST"])
# def trigger_action():
#     import json
#     start_time = time.perf_counter()
#     action_uuid = ""
#     action_type = "unknown"
#     effective_action = None
#     node_uuid = None
#     
#     try:
#         body = request.get_json()
#         action_uuid = body.get("action_uuid", "")
#         action = body.get("action", "")
#         action_override = body.get("action_override")
#         
#         # Get action data to determine type and node
#         action_data = tree.dao.get_action_by_id(action_uuid)
#         if action_data:
#             _, action_name, action_plan, action_prompt, fetched_node_uuid = action_data
#             node_uuid = fetched_node_uuid
#             action_type = action_name or "unknown"
#             
#             if action_override:
#                 effective_action = {
#                     "action_name": action_override.get("action_name") or action_name,
#                     "action_plan": action_override.get("action_plan") or action_plan,
#                     "action_prompt": action_override.get("action_prompt") or action_prompt
#                 }
#                 action_type = effective_action.get("action_name", action_type)
#             else:
#                 effective_action = {
#                     "action_name": action_name,
#                     "action_plan": action_plan,
#                     "action_prompt": action_prompt
#                 }
#         elif action_override:
#             effective_action = action_override
#             action_type = action_override.get("action_name", "unknown")
# 
#         result = tree.trigger_action(action_uuid, action_override=action_override)
#         
#         # Calculate duration
#         duration_ms = int((time.perf_counter() - start_time) * 1000)
#         
#         # result is a tuple: (action_text, collected_data_string, graph_output)
#         if result and len(result) >= 3:
#             action_text, collected_data, graph_output = result
#             
#             # Convert graph_output to JSON-serializable format
#             # graph_output may be a dict (real run) or a str (placeholder/error message)
#             serializable_output = {}
#             if graph_output:
#                 if isinstance(graph_output, dict):
#                     for key, value in graph_output.items():
#                         # Handle Pydantic models and other non-serializable objects
#                         if hasattr(value, 'dict'):
#                             serializable_output[key] = value.dict()
#                         elif hasattr(value, '__dict__'):
#                             serializable_output[key] = value.__dict__
#                         elif isinstance(value, list):
#                             serializable_output[key] = [
#                                 item.dict() if hasattr(item, 'dict') else 
#                                 item.__dict__ if hasattr(item, '__dict__') else 
#                                 str(item) for item in value
#                             ]
#                         else:
#                             serializable_output[key] = str(value)
#                 else:
#                     # Placeholder or string result (e.g. "MCP not set up yet")
#                     serializable_output["message"] = str(graph_output)
#             
#             # Log successful action to history
#             try:
#                 tree.dao.insert_action_history(
#                     action_uuid=action_uuid,
#                     action_type=action_type,
#                     action_data=json.dumps(effective_action) if effective_action else None,
#                     node_uuid=node_uuid,
#                     status="completed",
#                     result=json.dumps(serializable_output) if serializable_output else None,
#                     error_message=None,
#                     duration_ms=duration_ms
#                 )
#             except Exception as log_err:
#                 print(f"⚠️ Failed to log action history: {log_err}")
#             
#             return jsonify({
#                 "message": "Action triggered successfully",
#                 "action_text": action_text,
#                 "graph_output": serializable_output,
#                 "effective_action": effective_action
#             }), 200
#         else:
#             # Log action with no result
#             try:
#                 tree.dao.insert_action_history(
#                     action_uuid=action_uuid,
#                     action_type=action_type,
#                     action_data=json.dumps(effective_action) if effective_action else None,
#                     node_uuid=node_uuid,
#                     status="completed",
#                     result=None,
#                     error_message="No result returned",
#                     duration_ms=duration_ms
#                 )
#             except Exception as log_err:
#                 print(f"⚠️ Failed to log action history: {log_err}")
#             
#             return jsonify({"message": "Action triggered but no result returned"}), 200
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         
#         # Calculate duration even for failed actions
#         duration_ms = int((time.perf_counter() - start_time) * 1000)
#         
#         # Log failed action to history
#         try:
#             tree.dao.insert_action_history(
#                 action_uuid=action_uuid,
#                 action_type=action_type,
#                 action_data=json.dumps(effective_action) if effective_action else None,
#                 node_uuid=node_uuid,
#                 status="failed",
#                 result=None,
#                 error_message=str(e),
#                 duration_ms=duration_ms
#             )
#         except Exception as log_err:
#             print(f"⚠️ Failed to log action history: {log_err}")
#         
#         return jsonify({"error": str(e)}), 500


@app.route("/plan_action", methods=["POST"])
def plan_action_endpoint():
    """
    Research and plan an action using MCP tools - Phases 0+1 of three-phase execution.
    
    This endpoint:
    1. Takes action text and context from get_action_context (traverses tree, returns node data & parental chain)
    2. RESEARCH: Reads relevant resources to gather additional context
    3. PLANNING: Uses semantic tool routing to find relevant tools
    4. Has agent propose ONE tool call with parameters
    5. Returns proposed action for user approval/editing
    
    Body:
        {
            "action_uuid": "uuid-of-action",
            "action_override": {...} (optional),
            "skip_research": false (optional - skip resource reading)
        }
    
    Returns:
        {
            "status": "success" | "error",
            "research": {
                "resources_read": [...],
                "context_gathered": str
            },
            "proposed_action": {
                "tool_name": str,
                "parameters": dict,
                "reasoning": str
            },
            "action_text": str,
            "context_data": str
        }
    """
    start_time = time.perf_counter()
    
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        action_override = body.get("action_override")
        skip_research = body.get("skip_research", False)
        
        # Get action context (traverses tree and returns node data with parental chain)
        action_text, collected_data = tree.get_action_context(action_uuid, action_override=action_override)
        
        if not action_text:
            return jsonify({
                "status": "error",
                "error": "Failed to retrieve action details"
            }), 400
        
        print(f"📋 Planning action: {action_text[:100]}...")
        
        # Run the research + planning async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if skip_research:
                # Skip research phase, just plan directly
                plan_result = loop.run_until_complete(
                    plan_action(action_text, collected_data)
                )
                research_info = {"resources_read": [], "context_gathered": collected_data}
            else:
                # Full research + planning flow
                result = loop.run_until_complete(
                    research_and_plan(action_text, collected_data)
                )
                plan_result = {
                    "status": result["status"],
                    "proposed_action": result["proposed_action"],
                    "error": result.get("error")
                }
                research_info = result.get("research", {"resources_read": [], "context_gathered": collected_data})
        finally:
            loop.close()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if plan_result["status"] == "error":
            return jsonify({
                "status": "error",
                "error": plan_result["error"],
                "research": research_info,
                "duration_ms": duration_ms
            }), 500
        
        # Resolve display schema for the proposed tool call
        display_info = None
        if plan_result.get("proposed_action"):
            try:
                display_info = _resolve_tool_display(plan_result["proposed_action"])
            except Exception as display_err:
                print(f"Warning: display schema resolution failed: {display_err}")
        
        return jsonify({
            "status": "success",
            "research": research_info,
            "proposed_action": plan_result["proposed_action"],
            "display": display_info,
            "action_text": action_text,
            "context_data": research_info.get("context_gathered", collected_data),
            "duration_ms": duration_ms
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "duration_ms": duration_ms
        }), 500



#TODO and NOTE: this shit is ONLY for testing, please remove before prod.
@app.route("/plan_action_direct", methods=["POST"])
def plan_action_direct_endpoint():
    """
    Direct research and planning endpoint - bypasses action_uuid lookup.
    
    Use this for testing or when you have raw action text and context.
    
    Body:
        {
            "action_text": "Send an email to ritesh...",
            "context": "Ritesh's email is ritesh@example.com",
            "skip_research": false (optional)
        }
    
    Returns:
        {
            "status": "success" | "error",
            "research": {...},
            "proposed_action": {...}
        }
    """
    start_time = time.perf_counter()
    
    try:
        body = request.get_json()
        action_text = body.get("action_text", "")
        context = body.get("context", "")
        skip_research = body.get("skip_research", False)
        
        if not action_text:
            return jsonify({
                "status": "error",
                "error": "action_text is required"
            }), 400
        
        print(f"📋 Planning action (direct): {action_text[:100]}...")
        
        # Run the research + planning async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if skip_research:
                plan_result = loop.run_until_complete(
                    plan_action(action_text, context)
                )
                research_info = {"resources_read": [], "context_gathered": context}
            else:
                result = loop.run_until_complete(
                    research_and_plan(action_text, context)
                )
                plan_result = {
                    "status": result["status"],
                    "proposed_action": result["proposed_action"],
                    "error": result.get("error")
                }
                research_info = result.get("research", {"resources_read": [], "context_gathered": context})
        finally:
            loop.close()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if plan_result["status"] == "error":
            return jsonify({
                "status": "error",
                "error": plan_result["error"],
                "research": research_info,
                "duration_ms": duration_ms
            }), 500
        
        # Resolve display schema for the proposed tool call
        display_info = None
        if plan_result.get("proposed_action"):
            try:
                display_info = _resolve_tool_display(plan_result["proposed_action"])
            except Exception as display_err:
                print(f"Warning: display schema resolution failed: {display_err}")
        
        return jsonify({
            "status": "success",
            "research": research_info,
            "proposed_action": plan_result["proposed_action"],
            "display": display_info,
            "action_text": action_text,
            "context_data": research_info.get("context_gathered", context),
            "duration_ms": duration_ms
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "duration_ms": duration_ms
        }), 500


@app.route("/execute_action", methods=["POST"])
def execute_action_endpoint():
    """
    Execute an approved action - Phase 2 of two-phase execution.
    
    This endpoint:
    1. Takes user-approved/edited parameters
    2. Executes the tool via MCP
    3. Logs the execution to history
    4. Returns the result
    
    Body:
        {
            "action_uuid": "uuid-of-action",
            "tool_name": "send_email",
            "parameters": {
                "to": "user@example.com",
                "subject": "...",
                "body": "..."
            }
        }
    
    Returns:
        {
            "status": "success" | "error",
            "result": Any,
            "duration_ms": int
        }
    """
    start_time = time.perf_counter()
    action_uuid = ""
    tool_name = ""
    
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        tool_name = body.get("tool_name", "")
        parameters = body.get("parameters", {})
        
        if not tool_name or not parameters:
            return jsonify({
                "status": "error",
                "error": "Missing tool_name or parameters"
            }), 400
        
        print(f"🚀 Executing {tool_name} with parameters: {parameters}")
        
        # Get action data for logging
        action_data = tree.dao.get_action_by_id(action_uuid)
        node_uuid = action_data[4] if action_data else None
        
        # Run the execution async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            exec_result = loop.run_until_complete(
                execute_action(tool_name, parameters)
            )
        finally:
            loop.close()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if exec_result["status"] == "error":
            # Log failed execution
            try:
                tree.dao.insert_action_history(
                    action_uuid=action_uuid,
                    action_type=tool_name,
                    action_data=str(parameters),
                    node_uuid=node_uuid,
                    status="failed",
                    result=None,
                    error_message=exec_result["error"],
                    duration_ms=duration_ms
                )
            except Exception as log_err:
                print(f"⚠️ Failed to log action history: {log_err}")
            
            return jsonify({
                "status": "error",
                "error": exec_result["error"],
                "duration_ms": duration_ms
            }), 500
        
        # Log successful execution
        try:
            tree.dao.insert_action_history(
                action_uuid=action_uuid,
                action_type=tool_name,
                action_data=str(parameters),
                node_uuid=node_uuid,
                status="completed",
                result=str(exec_result["result"]),
                error_message=None,
                duration_ms=duration_ms
            )
        except Exception as log_err:
            print(f"⚠️ Failed to log action history: {log_err}")
        
        return jsonify({
            "status": "success",
            "result": exec_result["result"],
            "duration_ms": duration_ms
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Log failed execution
        try:
            tree.dao.insert_action_history(
                action_uuid=action_uuid,
                action_type=tool_name,
                action_data="execution_error",
                node_uuid=None,
                status="failed",
                result=None,
                error_message=str(e),
                duration_ms=duration_ms
            )
        except Exception as log_err:
            print(f"⚠️ Failed to log action history: {log_err}")
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "duration_ms": duration_ms
        }), 500


@app.route("/mcp_health", methods=["GET"])
def mcp_health_endpoint():
    """
    Check MCP server health and available tools.
    
    Returns:
        {
            "status": "healthy" | "unhealthy",
            "tools_count": int,
            "tool_names": list
        }
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            health_result = loop.run_until_complete(mcp_health_check())
        finally:
            loop.close()
        
        return jsonify(health_result), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@app.route("/action_history", methods=["GET"])
def get_action_history():
    """
    Get action execution history.
    Query params:
        - limit: Max number of records (default: 50)
        - offset: Pagination offset (default: 0)
        - status: Filter by status (optional)
        - action_type: Filter by action type (optional)
    """
    try:
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        status = request.args.get("status")
        action_type = request.args.get("action_type")
        
        # Cap limit to prevent huge queries
        limit = min(limit, 200)
        
        records = tree.dao.get_action_history(
            limit=limit,
            offset=offset,
            status=status,
            action_type=action_type
        )
        
        # Convert tuples to dicts
        history = []
        for record in records:
            history.append({
                "id": record[0],
                "action_uuid": record[1],
                "action_type": record[2],
                "action_data": record[3],
                "creation_timestamp": record[4],
                "node_uuid": record[5],
                "status": record[6],
                "result": record[7],
                "error_message": record[8],
                "duration_ms": record[9],
            })
        
        return jsonify({"history": history, "count": len(history)}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/edit_action", methods=["POST"])
def edit_action():
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        action_override = body.get("action_override") or {}
        persist = bool(body.get("persist", False))

        # region agent log
        try:
            import json, time
            log_entry = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H1",
                "location": "server/app.py:1384",
                "message": "edit_action entry",
                "data": {
                    "action_uuid": action_uuid,
                    "has_override": bool(action_override),
                    "persist": persist
                },
                "timestamp": int(time.time() * 1000)
            }
            with open("/Users/Patron/Desktop/covalent-calhacks/.cursor/debug.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        # endregion

        if not action_uuid:
            return jsonify({"error": "action_uuid is required"}), 400

        if "action_prompt" in action_override and not action_override.get("action_prompt"):
            return jsonify({"error": "action_prompt cannot be empty"}), 400

        action_data = tree.dao.get_action_by_id(action_uuid)
        if not action_data:
            return jsonify({"error": "action not found"}), 404
        # region agent log
        try:
            import json, time
            log_entry = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H1",
                "location": "server/app.py:1396",
                "message": "edit_action fetched action_data",
                "data": {
                    "action_uuid": action_uuid,
                    "action_data_len": len(action_data) if action_data is not None else None,
                    "action_data_preview": list(action_data) if action_data is not None else None
                },
                "timestamp": int(time.time() * 1000)
            }
            with open("/Users/Patron/Desktop/covalent-calhacks/.cursor/debug.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        # endregion
        _, action_name, action_plan, action_prompt, _ = action_data

        

        # region agent log
        try:
            import json, time
            log_entry = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H2",
                "location": "server/app.py:1400",
                "message": "edit_action unpacked action_data",
                "data": {
                    "action_uuid": action_uuid,
                    "action_name": action_name,
                    "action_plan": action_plan,
                    "has_action_prompt": bool(action_prompt)
                },
                "timestamp": int(time.time() * 1000)
            }
            with open("/Users/Patron/Desktop/covalent-calhacks/.cursor/debug.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
        # endregion

        effective_action = {
            "action_name": action_override.get("action_name") or action_name,
            "action_plan": action_override.get("action_plan") or action_plan,
            "action_prompt": action_override.get("action_prompt") or action_prompt
        }

        if persist:
            tree.dao.update_action(
                action_uuid,
                effective_action["action_name"],
                effective_action["action_plan"],
                effective_action["action_prompt"]
            )

        return jsonify({
            "message": "Action edit processed",
            "persisted": persist,
            "effective_action": effective_action
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/tab_predict", methods=["POST"])
def tab_predict():
    """
    Get tab completion prediction using graph.db context
    Request body:
    {
        "app_name": "VSCode",
        "text_buffer": "import numpy as n",
        "context_type": "full_query",
        "activity_id": "abc123"
    }
    """
    try:
        body = request.get_json()
        app_name = body.get("app_name", "Unknown")
        text_buffer = body.get("text_buffer", "")
        context_type = body.get("context_type", "")
        activity_id = body.get("activity_id", "")
        
        if not text_buffer:
            return jsonify({"error": "text_buffer is required"}), 400
        
        # Use graph traversal to find relevant context
        # The graph.py traverse() method returns the most relevant node
        relevant_node = tree.traverse(f"App: {app_name} | Context: Typing '{text_buffer}'")
        
        # Get data from the relevant node and its ancestors
        # This gives us context about what the user is working on
        context_data = []
        if relevant_node:
            # Collect metadata chain for context
            metadata_chain = tree.get_parent_metadata(relevant_node)
            context_data.append(metadata_chain)
            
            # Get actions from this node (these are learned patterns)
            if relevant_node.actions:
                for action in relevant_node.actions[:3]:  # Top 3 actions
                    context_data.append(action.get('action_name', ''))
        
        # Generate prediction based on context
        # This is a simple completion - you could enhance with a local LLM call here
        prediction = generate_tab_prediction(text_buffer, context_data)
        
        return jsonify({
            "prediction": prediction,
            "confidence": 0.85,  # TODO: Calculate actual confidence
            "suggested_actions": [a.get('action_name', '') for a in (relevant_node.actions[:3] if relevant_node else [])]
        }), 200
        
    except Exception as e:
        print(f"Error in /tab_predict endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/tab_context", methods=["POST"])
def tab_context():
    """
    Update context in graph.db for tab completion learning
    Request body:
    {
        "app_name": "VSCode",
        "activity_id": "abc123",
        "context_data": "{json_serialized_context}",
        "activity_type": "Development::Backend"
    }
    """
    try:
        body = request.get_json()
        app_name = body.get("app_name", "Unknown")
        activity_id = body.get("activity_id", "")
        context_data = body.get("context_data", "")
        activity_type = body.get("activity_type", "Unknown")
        
        # Create a summary for graph traversal
        summary = f"Tab completion context update for {app_name} | Activity: {activity_type}"
        
        # Use tree.learn() to insert this context into the graph
        # This will find the right node and store the context there
        recent_actions = tree.learn(summary, context_data, key=f"tab_context_{activity_id}")

        # Get the node_id from the first action if available
        node_id = None
        if recent_actions:
            # Each action tuple is: (uuid, name, plan, prompt, node_uuid, last_selected)
            node_id = str(recent_actions[0][4]) if recent_actions[0][4] else None

        return jsonify({
            "message": "Context updated successfully",
            "node_id": node_id
        }), 200
        
    except Exception as e:
        print(f"Error in /tab_context endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def generate_tab_prediction(text_buffer, context_data):
    """
    Generate tab completion prediction based on text buffer and graph context.
    This is a simple heuristic - enhance with LLM for better results.
    """
    # Extract the last incomplete word or phrase
    last_line = text_buffer.split('\n')[-1] if '\n' in text_buffer else text_buffer
    words = last_line.split()
    
    if not words:
        return ""
    
    last_word = words[-1]
    
    # Simple pattern matching from context
    for context in context_data:
        if isinstance(context, str):
            # Look for common patterns in the context
            if last_word in context:
                # Find what typically follows this word in context
                context_words = context.split()
                for i, word in enumerate(context_words):
                    if word.startswith(last_word) and i + 1 < len(context_words):
                        return context_words[i + 1]
    
    # Fallback: basic Python/JS completions
    common_completions = {
        "import": "numpy as np",
        "from": "typing import",
        "def": "function_name():",
        "class": "ClassName:",
        "if": "__name__ == '__main__':",
        "for": "i in range():",
        "return": "None",
        "const": "variable = ",
        "let": "variable = ",
        "function": "name() {",
    }
    
    for keyword, completion in common_completions.items():
        if last_word.startswith(keyword) or keyword.startswith(last_word):
            return completion
    
    return ""


if __name__ == "__main__":
    print("Registered routes:", [r.rule for r in app.url_map.iter_rules()])
    app.run(host="127.0.0.1", port=5001, debug=False)
