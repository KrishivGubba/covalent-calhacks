"""
GitHub OAuth Device Flow Authentication.

Handles GitHub device flow to obtain access tokens for API calls.
"""
import os
import time
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# GitHub Device Flow endpoints
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubAuth:
    """
    Handles GitHub OAuth Device Flow authentication.
    
    Usage:
        auth = GitHubAuth(client_id="...", client_secret="...")
        token = auth.get_access_token(scope="repo")
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_storage_path: Optional[Path] = None
    ):
        """
        Initialize GitHub auth handler.
        
        Args:
            client_id: GitHub OAuth App Client ID (or from GITHUB_CLIENT_ID env var)
            client_secret: GitHub OAuth App Client Secret (or from GITHUB_CLIENT_SECRET env var)
            token_storage_path: Path to store access token (defaults to github_token.json in this directory)
        """
        self.client_id = client_id or os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GITHUB_CLIENT_SECRET")
        
        if not self.client_id:
            raise ValueError("GitHub Client ID required. Set GITHUB_CLIENT_ID env var or pass client_id.")
        if not self.client_secret:
            raise ValueError("GitHub Client Secret required. Set GITHUB_CLIENT_SECRET env var or pass client_secret.")
        
        # Default token storage location (in same directory as this module)
        if token_storage_path is None:
            token_storage_path = Path(__file__).parent / "github_token.json"
        
        self.token_storage_path = Path(token_storage_path)
        self.token_storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def get_access_token(self, scope: str = "repo") -> str:
        """
        Get GitHub access token via device flow.
        
        If token already exists and is valid, returns cached token.
        Otherwise, initiates device flow and polls for token.
        
        Args:
            scope: OAuth scope to request (default: "repo" for full repo access)
        
        Returns:
            str: Access token
        
        Raises:
            RuntimeError: If device flow fails or times out
        """
        # Check for existing token
        cached_token = self._load_cached_token()
        if cached_token:
            return cached_token
        
        # Start device flow
        device_code_data = self._request_device_code(scope)
        user_code = device_code_data["user_code"]
        device_code = device_code_data["device_code"]
        verification_uri = device_code_data["verification_uri"]
        interval = device_code_data.get("interval", 5)  # Polling interval in seconds
        
        # Display instructions to user
        print(f"\n🔐 GitHub Authentication Required")
        print(f"   1. Visit: {verification_uri}")
        print(f"   2. Enter code: {user_code}")
        print(f"   3. Authorize the application\n")
        print("⏳ Waiting for authorization...")
        
        # Poll for access token
        expires_in = device_code_data.get("expires_in", 900)  # Default 15 minutes
        start_time = time.time()
        
        while time.time() - start_time < expires_in:
            time.sleep(interval)
            
            token_response = self._poll_for_token(device_code)
            
            if "access_token" in token_response:
                access_token = token_response["access_token"]
                # Cache the token
                self._save_token(access_token)
                print("✅ Authorization successful! Token saved.")
                return access_token
            
            elif token_response.get("error") == "authorization_pending":
                print(".", end="", flush=True)  # Show progress
                continue
            elif token_response.get("error") == "slow_down":
                interval += 5  # Increase polling interval
                continue
            else:
                error = token_response.get("error", "unknown")
                error_desc = token_response.get("error_description", "")
                raise RuntimeError(f"Device flow failed: {error} - {error_desc}")
        
        raise RuntimeError("Device flow timed out. Please try again.")
    
    def _request_device_code(self, scope: str) -> Dict[str, Any]:
        """Request device code from GitHub."""
        response = requests.post(
            DEVICE_CODE_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": self.client_id,
                "scope": scope
            }
        )
        response.raise_for_status()
        return response.json()
    
    def _poll_for_token(self, device_code: str) -> Dict[str, Any]:
        """Poll GitHub for access token."""
        response = requests.post(
            ACCESS_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            }
        )
        response.raise_for_status()
        return response.json()
    
    def _load_cached_token(self) -> Optional[str]:
        """Load cached access token if it exists."""
        if not self.token_storage_path.exists():
            return None
        
        try:
            with open(self.token_storage_path, 'r') as f:
                data = json.load(f)
                return data.get("access_token")
        except (json.JSONDecodeError, KeyError):
            return None
    
    def _save_token(self, token: str) -> None:
        """Save access token to cache."""
        data = {"access_token": token}
        with open(self.token_storage_path, 'w') as f:
            json.dump(data, f)
        # Set restrictive permissions (owner read/write only)
        self.token_storage_path.chmod(0o600)
    
    def clear_token(self) -> None:
        """Clear cached access token."""
        if self.token_storage_path.exists():
            self.token_storage_path.unlink()
