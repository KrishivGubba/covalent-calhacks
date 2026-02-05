from flask import Flask, request, jsonify, g
import sqlite3
import os
import sys
import time
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



app = Flask(__name__)
CORS(app)

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

# Lambda Gateway URL for secure token exchange
LAMBDA_GATEWAY_URL = os.environ.get('LAMBDA_GATEWAY_URL', 'https://gtfrn4otol.execute-api.us-east-1.amazonaws.com')

# In-memory storage for pending Google OAuth (state -> {code_verifier, result, ...})
# Short-lived, cleared after auth completes
google_auth_pending = {}

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
        
        
        
        # Convert the entire body to JSON string for storage
        import json
        data_str = json.dumps(body)
        
        # Call learn function - returns dict with structure info and actions
        print(f"\n📍 DEBUG: Calling tree.learn_with_structure()...")
        result = tree.learn_with_structure(enhanced_description, data_str)
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
    Body: { "user_id": "..." }
    """
    body = request.get_json() or {}
    user_id = body.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    deleted = auth_dao.delete_session(user_id)
    print(f"🔐 Logged out user={user_id} (deleted={deleted})")
    return jsonify({"ok": True, "deleted": deleted > 0}), 200


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
    Body: { "auth_token": "..." } - Auth0 token to authenticate with Lambda
    """
    body = request.get_json() or {}
    auth_token = body.get("auth_token")
    
    if not auth_token:
        return jsonify({"error": "auth_token is required"}), 400
    
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


@app.route("/trigger_action", methods=["POST"])
def trigger_action():
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        action = body.get("action", "")
        action_override = body.get("action_override")
        
        effective_action = None
        if action_override:
            action_data = tree.dao.get_action_by_id(action_uuid)
            if action_data:
                _, action_name, action_plan, action_prompt, _ = action_data
                effective_action = {
                    "action_name": action_override.get("action_name") or action_name,
                    "action_plan": action_override.get("action_plan") or action_plan,
                    "action_prompt": action_override.get("action_prompt") or action_prompt
                }
            else:
                effective_action = action_override

        result = tree.trigger_action(action_uuid, action_override=action_override)
        
        # result is a tuple: (action_text, collected_data_string, graph_output)
        if result and len(result) >= 3:
            action_text, collected_data, graph_output = result
            
            # Convert graph_output to JSON-serializable format
            serializable_output = {}
            if graph_output:
                for key, value in graph_output.items():
                    # Handle Pydantic models and other non-serializable objects
                    if hasattr(value, 'dict'):
                        serializable_output[key] = value.dict()
                    elif hasattr(value, '__dict__'):
                        serializable_output[key] = value.__dict__
                    elif isinstance(value, list):
                        serializable_output[key] = [
                            item.dict() if hasattr(item, 'dict') else 
                            item.__dict__ if hasattr(item, '__dict__') else 
                            str(item) for item in value
                        ]
                    else:
                        serializable_output[key] = str(value)
            
            return jsonify({
                "message": "Action triggered successfully",
                "action_text": action_text,
                "graph_output": serializable_output,
                "effective_action": effective_action
            }), 200
        else:
            return jsonify({"message": "Action triggered but no result returned"}), 200
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

        if not action_uuid:
            return jsonify({"error": "action_uuid is required"}), 400

        if "action_prompt" in action_override and not action_override.get("action_prompt"):
            return jsonify({"error": "action_prompt cannot be empty"}), 400

        action_data = tree.dao.get_action_by_id(action_uuid)
        if not action_data:
            return jsonify({"error": "action not found"}), 404

        _, action_name, action_plan, action_prompt, _ = action_data

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
