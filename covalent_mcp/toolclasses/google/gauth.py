"""
Google OAuth 2.0 Authentication.

Provides utilities for Google API authentication:
- get_credentials_from_db(): Get credentials from the integration_tokens database (preferred).
  Automatically refreshes expired tokens via the Lambda gateway (which holds the client_secret).
- GoogleAuth: Legacy installed app flow (for standalone use only)

Architecture:
  - Client side (MCP/desktop) NEVER holds the client_secret.
  - Access tokens + refresh tokens are stored in graph.db (integration_tokens table).
  - When the access token expires, refresh happens via:
      gauth.py -> Lambda (has client_secret) -> Google token endpoint
  - The Lambda call is authenticated with the user's Auth0 JWT (read from user_sessions table).
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dotenv import load_dotenv

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    raise ImportError("Google auth libraries not installed. Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2")

load_dotenv()

# Add project root for logger
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()

# Google token endpoint
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Default scopes for Google APIs
# Can be extended when initializing GoogleAuth
# Note: 'openid' is automatically added by Google when using 'userinfo.email',
# but we include it explicitly to avoid scope mismatch warnings
DEFAULT_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Lambda Gateway URL for secure token operations (client_secret lives here)
LAMBDA_GATEWAY_URL = os.getenv("LAMBDA_GATEWAY_URL", "https://gtfrn4otol.execute-api.us-east-1.amazonaws.com")


def _get_db_path() -> Path:
    """Get path to the graph.db database."""
    # Prefer GRAPH_DB_PATH env var (set by Tauri in production)
    if os.getenv("GRAPH_DB_PATH"):
        db_path = Path(os.getenv("GRAPH_DB_PATH"))
        if db_path.exists():
            return db_path

    # Fall back to dev-relative path
    db_path = Path(__file__).parent.parent.parent.parent / "context-engine" / "graph.db"
    if db_path.exists():
        return db_path
    
    raise FileNotFoundError(
        "Database not found. Ensure graph.db exists in context-engine/ "
        "or set GRAPH_DB_PATH environment variable."
    )


def _is_token_expired(expires_at: Optional[str]) -> bool:
    """
    Check if a token is expired (with 5-minute buffer for safety).
    
    Returns True if the token is expired or will expire within 5 minutes.
    Returns False if no expiry info is available (optimistic).
    """
    if not expires_at:
        return False  # No expiry info — assume still valid
    try:
        expires = datetime.fromisoformat(expires_at)
        return datetime.utcnow() > (expires - timedelta(minutes=5))
    except (ValueError, TypeError):
        return False


def _get_auth0_jwt() -> Optional[str]:
    """
    Get the Auth0 access token (JWT) from the user_sessions table.
    
    This is a single-user desktop app, so we grab the first available session.
    The JWT is needed to authenticate calls to the Lambda gateway.
    """
    from server.auth_dao import AuthDAO
    
    db_path = _get_db_path()
    auth_dao = AuthDAO(str(db_path))
    
    sessions = auth_dao.get_all_sessions()
    if not sessions:
        return None
    
    # get_all_sessions returns limited fields; use get_session for full data
    user_id = sessions[0]["user_id"]
    session = auth_dao.get_session(user_id)
    if not session:
        return None
    
    return session.get("access_token")


def _refresh_google_token_via_lambda(integration_dao=None) -> str:
    """
    Refresh the Google access token by calling the Lambda gateway.
    
    Flow:
      1. Read refresh_token from integration_tokens DB
      2. Read Auth0 JWT from user_sessions DB (to authenticate with Lambda)
      3. POST to Lambda /integrations/google/refresh (Lambda has the client_secret)
      4. Lambda calls Google's token endpoint and returns new access_token
      5. Update integration_tokens DB with the new access_token + expires_at
    
    Returns:
        The new access_token string.
    
    Raises:
        RuntimeError: If refresh fails for any reason.
    """
    import requests as http_requests
    
    if integration_dao is None:
        from server.integration_dao import IntegrationDAO
        db_path = _get_db_path()
        integration_dao = IntegrationDAO(str(db_path))
    
    # 1. Get refresh token from DB
    token_data = integration_dao.get_token("google")
    if not token_data:
        raise RuntimeError("Google not connected. Please authenticate via the server's OAuth flow first.")
    
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "No Google refresh token available. "
            "Please disconnect and re-authenticate Google to get a new refresh token."
        )
    
    # 2. Get Auth0 JWT for Lambda authentication
    auth_jwt = _get_auth0_jwt()
    if not auth_jwt:
        raise RuntimeError(
            "No Auth0 session found. Please log in first so we can "
            "authenticate the token refresh request."
        )
    
    # 3. Call Lambda to refresh the token (client_secret is in Lambda's env)
    try:
        response = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/google/refresh",
            json={"refresh_token": refresh_token},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_jwt}",
            },
            timeout=15,
        )
        result = response.json()
    except Exception as e:
        raise RuntimeError(f"Failed to call Lambda for Google token refresh: {e}")
    
    if not response.ok or "error" in result:
        err = result.get("error", "refresh_failed")
        err_desc = result.get("error_description", "Token refresh failed")
        raise RuntimeError(f"Google token refresh failed: {err} - {err_desc}")
    
    # 4. Extract new token data
    new_access_token = result.get("access_token")
    if not new_access_token:
        raise RuntimeError("Lambda returned success but no access_token in response")
    
    expires_in = result.get("expires_in", 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    
    # 5. Update DB with new access token
    integration_dao.update_access_token("google", new_access_token, expires_at)
    log.info(f"Google access token refreshed successfully (expires in {expires_in}s)")
    
    return new_access_token


def get_credentials_from_db() -> Credentials:
    """
    Get Google credentials from the integration_tokens database.
    
    This is the preferred method for MCP tools. The server manages the OAuth flow
    and stores tokens in the database. If the access token is expired, it is
    automatically refreshed via the Lambda gateway (which holds the client_secret
    securely — no secrets are stored client-side).
    
    Returns:
        Credentials object ready for use with Google APIs
        
    Raises:
        RuntimeError: If no Google token found in database or refresh fails
        FileNotFoundError: If database not found
    """
    # Import here to avoid circular imports
    from server.integration_dao import IntegrationDAO
    
    db_path = _get_db_path()
    dao = IntegrationDAO(str(db_path))
    
    # Get token from database
    token_data = dao.get_token("google")
    if not token_data:
        raise RuntimeError(
            "No Google token found in database. "
            "Please authenticate via the server's OAuth flow first."
        )
    
    access_token = token_data.get("access_token")
    
    if not access_token:
        raise RuntimeError("Google access_token not found in database")
    
    # Check if token is expired and refresh if needed
    expires_at = token_data.get("expires_at")
    if _is_token_expired(expires_at):
        log.info("Google access token expired or expiring soon, refreshing via Lambda...")
        access_token = _refresh_google_token_via_lambda(dao)
    
    # Create Credentials object with just the access token.
    # No client_id/client_secret — refresh is handled by our Lambda pipeline,
    # not by the google-auth library's built-in refresh mechanism.
    creds = Credentials(token=access_token)
    
    return creds


# =============================================================================
# LEGACY: File-based credential helpers (for standalone/local dev use only)
# =============================================================================

def load_oauth_secrets(secrets_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load OAuth secrets from oauth_secrets.json file.
    
    LEGACY: Only used by GoogleAuth installed app flow for local development.
    Production code uses get_credentials_from_db() which never touches secrets.
    
    Args:
        secrets_path: Path to oauth_secrets.json (defaults to oauth_secrets.json in google/ directory)
    
    Returns:
        Dict with client_id, client_secret, etc.
    """
    if secrets_path is None:
        secrets_path = Path(__file__).parent / "oauth_secrets.json"
    
    secrets_path = Path(secrets_path)
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"OAuth secrets file not found: {secrets_path}\n"
            "Download it from Google Cloud Console and place it in this directory."
        )
    
    with open(secrets_path, 'r') as f:
        secrets = json.load(f)

    # Handle both "installed" and "web" client types
    if "installed" in secrets:
        client_info = secrets["installed"]
    elif "web" in secrets:
        client_info = secrets["web"]
    else:
        raise ValueError("Invalid oauth_secrets.json format. Expected 'installed' or 'web' key.")
    
    return {
        "client_id": client_info["client_id"],
        "client_secret": client_info["client_secret"],
        "project_id": secrets.get("project_id", ""),
    }


def get_stored_credentials(user_id: str = "default", credentials_path: Optional[Path] = None) -> Optional[Credentials]:
    """
    LEGACY: Get stored OAuth credentials from local file.
    Production code uses get_credentials_from_db() instead.
    """
    if credentials_path is None:
        credentials_path = Path(__file__).parent / "google_credentials.json"
    
    credentials_path = Path(credentials_path)
    
    if not credentials_path.exists():
        return None
    
    try:
        with open(credentials_path, 'r') as f:
            creds_data = json.load(f)
        
        # Create Credentials object from stored data
        creds = Credentials.from_authorized_user_info(creds_data)
        
        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed credentials
            store_credentials(creds, credentials_path)
        
        return creds
    except Exception:
        return None


def store_credentials(creds: Credentials, credentials_path: Optional[Path] = None) -> None:
    """
    LEGACY: Store OAuth credentials to local file.
    Production code uses the database (integration_tokens table) instead.
    """
    if credentials_path is None:
        credentials_path = Path(__file__).parent / "google_credentials.json"
    
    credentials_path = Path(credentials_path)
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(credentials_path, 'w') as f:
        json.dump({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'id_token': creds.id_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }, f)
    
    # Set restrictive permissions
    credentials_path.chmod(0o600)


class GoogleAuth:
    """
    Handles Google OAuth Installed App Flow authentication for Google APIs.
    
    Supports multiple scopes for Calendar, Gmail, and other Google services.
    Uses local server flow which automatically opens browser and captures OAuth callback.
    
    Usage:
        auth = GoogleAuth(scopes=["https://www.googleapis.com/auth/calendar.events"])
        creds = auth.get_credentials()
    """
    
    def __init__(
        self, 
        scopes: Optional[List[str]] = None,
        secrets_path: Optional[Path] = None, 
        credentials_path: Optional[Path] = None
    ):
        """
        Initialize Google auth handler.
        
        Args:
            scopes: List of OAuth scopes to request (defaults to DEFAULT_SCOPES)
            secrets_path: Path to oauth_secrets.json (defaults to oauth_secrets.json in google/ directory)
            credentials_path: Path to store credentials (defaults to google_credentials.json in google/ directory)
        """
        if scopes is None:
            scopes = DEFAULT_SCOPES.copy()
        self.scopes = scopes
        
        if secrets_path is None:
            secrets_path = Path(__file__).parent / "oauth_secrets.json"
        self.secrets_path = Path(secrets_path)
        
        if credentials_path is None:
            credentials_path = Path(__file__).parent / "google_credentials.json"
        self.credentials_path = Path(credentials_path)
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
    
    def get_credentials(self, user_id: str = "default") -> Credentials:
        """
        Get Google credentials via installed app flow (local server).
        
        If credentials already exist and are valid, returns cached credentials.
        Otherwise, starts a local server, opens browser for authorization, and captures the callback.
        
        Args:
            user_id: User identifier (for future multi-user support, currently unused)
        
        Returns:
            Credentials object
        
        Raises:
            FileNotFoundError: If oauth_secrets.json is not found
            RuntimeError: If authentication fails
        """
        # Check for existing credentials
        cached_creds = get_stored_credentials(user_id, self.credentials_path)
        if cached_creds and cached_creds.valid:
            # Check if cached credentials have all required scopes
            if set(self.scopes).issubset(set(cached_creds.scopes)):
                return cached_creds
            # If scopes have changed, need to re-authenticate
            log.warning("⚠️  Scopes have changed. Re-authentication required.")
        
        # Start installed app flow
        if not self.secrets_path.exists():
            raise FileNotFoundError(
                f"OAuth secrets file not found: {self.secrets_path}\n"
                "Download it from Google Cloud Console and place it in this directory."
            )
        
        log.info("\n🔐 Google Authentication Required")
        log.info(f"   Requesting scopes: {', '.join(self.scopes)}")
        log.info("   Opening browser for authorization...\n")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.secrets_path),
            self.scopes
        )
        
        # This will:
        # 1. Start a local server on a random port
        # 2. Open the browser
        # 3. Wait for user to authorize
        # 4. Capture the callback
        # 5. Return credentials
        creds = flow.run_local_server(port=0)
        
        # Store credentials for future use
        store_credentials(creds, self.credentials_path)
        log.info("✅ Authorization successful! Credentials saved.")
        
        return creds
    
    def clear_credentials(self) -> None:
        """Clear stored credentials."""
        if self.credentials_path.exists():
            self.credentials_path.unlink()
