"""
Google OAuth 2.0 Installed App Flow Authentication.

Handles Google OAuth installed app flow (local server) to obtain and store credentials for API calls.
Provides get_stored_credentials() function for CalendarService.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    raise ImportError("Google auth libraries not installed. Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2")

load_dotenv()

# Required scopes for Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def load_oauth_secrets(secrets_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load OAuth secrets from oauth_secrets.json file.
    
    Args:
        secrets_path: Path to oauth_secrets.json (defaults to oauth_secrets.json in this directory)
    
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
    
    output =  {
        "client_id": client_info["client_id"],
        "client_secret": client_info["client_secret"],
        "project_id": secrets.get("project_id", ""),
    }

    return output


def get_stored_credentials(user_id: str = "default", credentials_path: Optional[Path] = None) -> Optional[Credentials]:
    """
    Get stored OAuth credentials for a user.
    
    This function is used by CalendarService to get credentials.
    
    Args:
        user_id: User identifier (default: "default")
        credentials_path: Path to store credentials (defaults to calendar_credentials.json in this directory)
    
    Returns:
        Credentials object if found and valid, None otherwise
    """
    if credentials_path is None:
        credentials_path = Path(__file__).parent / "calendar_credentials.json"
    
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
        
        return creds
    except Exception:
        return None


def store_credentials(creds: Credentials, credentials_path: Optional[Path] = None) -> None:
    """
    Store OAuth credentials to file.
    
    Args:
        creds: Credentials object to store
        credentials_path: Path to store credentials
    """
    if credentials_path is None:
        credentials_path = Path(__file__).parent / "calendar_credentials.json"
    
    credentials_path = Path(credentials_path)
    
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


class GoogleCalendarAuth:
    """
    Handles Google OAuth Installed App Flow authentication for Calendar API.
    
    Uses local server flow which automatically opens browser and captures OAuth callback.
    
    Usage:
        auth = GoogleCalendarAuth()
        creds = auth.get_credentials()
    """
    
    def __init__(self, secrets_path: Optional[Path] = None, credentials_path: Optional[Path] = None):
        """
        Initialize Google Calendar auth handler.
        
        Args:
            secrets_path: Path to oauth_secrets.json (defaults to oauth_secrets.json in this directory)
            credentials_path: Path to store credentials (defaults to calendar_credentials.json in this directory)
        """
        if secrets_path is None:
            secrets_path = Path(__file__).parent / "oauth_secrets.json"
        self.secrets_path = Path(secrets_path)
        
        if credentials_path is None:
            credentials_path = Path(__file__).parent / "calendar_credentials.json"
        self.credentials_path = Path(credentials_path)
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
    
    def get_credentials(self, user_id: str = "default") -> Credentials:
        """
        Get Google Calendar credentials via installed app flow (local server).
        
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
            return cached_creds
        
        # Start installed app flow
        if not self.secrets_path.exists():
            raise FileNotFoundError(
                f"OAuth secrets file not found: {self.secrets_path}\n"
                "Download it from Google Cloud Console and place it in this directory."
            )
        
        print("\n🔐 Google Calendar Authentication Required")
        print("   Opening browser for authorization...\n")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.secrets_path),
            SCOPES
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
        print("✅ Authorization successful! Credentials saved.")
        
        return creds
    
    def clear_credentials(self) -> None:
        """Clear stored credentials."""
        if self.credentials_path.exists():
            self.credentials_path.unlink()
