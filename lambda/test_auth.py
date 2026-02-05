"""
Test script for Lambda JWT authentication.

Usage:
    python test_auth.py

Tests:
    1. Request with valid access token from database
    2. Request with invalid/random token (should fail with 401)
"""

import os
import sys

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'llm-interactions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from gateway_client import GatewayClient, GatewayError
from auth_dao import AuthDAO


# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')


def get_current_access_token() -> tuple[str, str]:
    """
    Get the access token for the current user from the database.
    Returns (user_id, access_token) or raises if no session found.
    """
    auth_dao = AuthDAO(DB_PATH)
    
    # Get all sessions and use the most recent one
    sessions = auth_dao.get_all_sessions()
    
    if not sessions:
        raise ValueError("No user sessions found in database. Please log in first.")
    
    # Use the first (most recent) session
    user_id = sessions[0]["user_id"]
    session = auth_dao.get_session(user_id)
    
    if not session or not session.get("access_token"):
        raise ValueError(f"No access token found for user {user_id}")
    
    print(f"Found session for user: {user_id}")
    print(f"  Email: {session.get('user_info', {}).get('email', 'unknown')}")
    print(f"  Expires at: {session.get('expires_at', 'unknown')}")
    
    return user_id, session["access_token"]


def test_with_valid_token():
    """Test a request with the real access token from storage."""
    print("\n" + "="*60)
    print("TEST 1: Request with VALID access token")
    print("="*60)
    
    try:
        user_id, access_token = get_current_access_token()
        print(f"\nUsing token: {access_token[:20]}...{access_token[-10:]}")
        
        client = GatewayClient(access_token=access_token)
        print(f"\nClient: {client}")
        
        # Try health check first (no auth required)
        print("\n--- Health Check (no auth required) ---")
        try:
            health = client.health()
            print(f"  Status: {health.get('status')}")
            print(f"  Region: {health.get('region')}")
        except GatewayError as e:
            print(f"  Health check failed: {e.message}")
            print(f"  Status code: {e.status_code}")
        
        # Try an actual invoke (auth required)
        print("\n--- Invoke (auth required) ---")
        try:
            response = client.generate(
                "Say 'Auth working!' in exactly 2 words.",
                max_tokens=20,
            )
            print(f"  Response: {response.content}")
            print(f"  Tokens: {response.input_tokens} in, {response.output_tokens} out")
            print("\n✅ SUCCESS: Authenticated request worked!")
        except GatewayError as e:
            print(f"  ❌ FAILED: {e.message}")
            print(f"  Status code: {e.status_code}")
            if e.status_code == 401:
                print("  Token was rejected - may be expired or invalid")
            elif e.status_code == 500:
                print("  Server error - Lambda may be misconfigured or missing dependencies")
            
    except ValueError as e:
        print(f"\n⚠️  Cannot run test: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


def test_with_invalid_token():
    """Test a request with a random/invalid token (should fail)."""
    print("\n" + "="*60)
    print("TEST 2: Request with INVALID/random token")
    print("="*60)
    
    fake_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWtlMTIzIiwiYXVkIjoiZmFrZSIsImlzcyI6Imh0dHBzOi8vZmFrZS5hdXRoMC5jb20vIiwiZXhwIjoxNzA5MjUxMjAwfQ.fake_signature_here"
    
    print(f"\nUsing fake token: {fake_token[:30]}...")
    
    try:
        client = GatewayClient(access_token=fake_token)
        print(f"\nClient: {client}")
        
        # Try an invoke (should fail with 401)
        print("\n--- Invoke (should fail) ---")
        try:
            response = client.generate("Hello!", max_tokens=20)
            print(f"  ⚠️  UNEXPECTED SUCCESS: {response.content}")
            print("  This means auth is not being enforced!")
        except GatewayError as e:
            if e.status_code == 401:
                print(f"  ✅ EXPECTED: Got 401 Unauthorized")
                print(f"  Error message: {e.message}")
            else:
                print(f"  ❌ UNEXPECTED ERROR (status {e.status_code}):")
                print(f"  {e.message}")
                
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


def test_with_no_token():
    """Test a request with no token at all."""
    print("\n" + "="*60)
    print("TEST 3: Request with NO token")
    print("="*60)
    
    try:
        client = GatewayClient()  # No access_token
        print(f"\nClient: {client}")
        
        # Health check should still work
        print("\n--- Health Check (no auth required) ---")
        try:
            health = client.health()
            print(f"  ✅ Status: {health.get('status')}")
        except GatewayError as e:
            print(f"  Status {e.status_code}: {e.message}")
        
        # Invoke should fail
        print("\n--- Invoke (should fail) ---")
        try:
            response = client.generate("Hello!", max_tokens=20)
            print(f"  ⚠️  UNEXPECTED SUCCESS: {response.content}")
            print("  This means auth is not being enforced!")
        except GatewayError as e:
            if e.status_code == 401:
                print(f"  ✅ EXPECTED: Got 401 Unauthorized")
                print(f"  Error message: {e.message}")
            else:
                print(f"  Status {e.status_code}: {e.message}")
                
    except ValueError as e:
        # This happens if GATEWAY_URL is not set
        print(f"\n⚠️  Cannot run test: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    print("Lambda JWT Authentication Test")
    print("=" * 60)
    
    # Check if gateway URL is configured
    gateway_url = os.getenv("GATEWAY_URL")
    if not gateway_url:
        print("\n⚠️  GATEWAY_URL not set!")
        print("Set it with: export GATEWAY_URL='https://your-api.execute-api.us-east-1.amazonaws.com'")
        print("\nRunning in dry-run mode (just checking database)...\n")
        
        try:
            user_id, token = get_current_access_token()
            print(f"\n✅ Found valid token in database for user: {user_id}")
            print(f"   Token preview: {token[:30]}...")
        except ValueError as e:
            print(f"\n❌ {e}")
        
        sys.exit(0)
    
    print(f"Gateway URL: {gateway_url}")
    
    # Run tests
    test_with_valid_token()
    test_with_invalid_token()
    test_with_no_token()
    
    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)
