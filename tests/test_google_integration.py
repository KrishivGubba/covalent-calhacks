#!/usr/bin/env python3
"""
Test script to verify Google API integration is working.
Reads the access token from the integration_tokens table and tests Google API calls.
"""
import os
import sys
import json

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from server.integration_dao import IntegrationDAO

# Use urllib for HTTP calls (no extra dependencies)
import urllib.request
import urllib.error


def get_db_path():
    """Get the path to graph.db"""
    return os.path.join(PROJECT_ROOT, 'context-engine', 'graph.db')


def test_google_userinfo(access_token: str) -> dict:
    """Test Google userinfo endpoint."""
    print("\n--- Testing Google UserInfo API ---")
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ UserInfo: {data.get('email', 'unknown')}")
            print(f"  Name: {data.get('name', 'N/A')}")
            return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ UserInfo failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ UserInfo error: {e}")
        return {"success": False, "error": str(e)}


def test_google_calendar(access_token: str) -> dict:
    """Test Google Calendar API - list calendars."""
    print("\n--- Testing Google Calendar API ---")
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=5",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            calendars = data.get("items", [])
            print(f"✓ Found {len(calendars)} calendar(s)")
            for cal in calendars[:3]:
                print(f"  - {cal.get('summary', 'Untitled')}")
            return {"success": True, "count": len(calendars)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Calendar failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Calendar error: {e}")
        return {"success": False, "error": str(e)}


def test_google_gmail(access_token: str) -> dict:
    """Test Gmail API - list labels."""
    print("\n--- Testing Gmail API ---")
    try:
        req = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/labels",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            labels = data.get("labels", [])
            print(f"✓ Found {len(labels)} Gmail label(s)")
            system_labels = [l for l in labels if l.get("type") == "system"]
            print(f"  System labels: {len(system_labels)}")
            return {"success": True, "count": len(labels)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Gmail failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Gmail error: {e}")
        return {"success": False, "error": str(e)}


def test_google_drive(access_token: str) -> dict:
    """Test Google Drive API - list files."""
    print("\n--- Testing Google Drive API ---")
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/drive/v3/files?pageSize=5",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            files = data.get("files", [])
            print(f"✓ Found {len(files)} file(s) in Drive")
            for f in files[:3]:
                print(f"  - {f.get('name', 'Untitled')} ({f.get('mimeType', 'unknown')})")
            return {"success": True, "count": len(files)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Drive failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Drive error: {e}")
        return {"success": False, "error": str(e)}


def main():
    print("=" * 50)
    print("Google Integration Test")
    print("=" * 50)
    
    # Initialize DAO and get Google token
    db_path = get_db_path()
    print(f"\nDatabase path: {db_path}")
    
    dao = IntegrationDAO(db_path)
    
    # Check if Google is connected
    if not dao.is_connected("google"):
        print("\n✗ Google is not connected!")
        print("  Please connect Google from the Integrations page first.")
        return 1
    
    # Get token data
    token_data = dao.get_token("google")
    if not token_data:
        print("\n✗ No token data found for Google!")
        return 1
    
    access_token = token_data.get("access_token")
    expires_at = token_data.get("expires_at")
    scopes = token_data.get("scopes")
    metadata = token_data.get("provider_metadata")
    
    print(f"\n✓ Google token found!")
    print(f"  Email: {metadata.get('email', 'unknown') if metadata else 'unknown'}")
    print(f"  Expires at: {expires_at}")
    print(f"  Scopes: {scopes[:50]}..." if scopes and len(scopes) > 50 else f"  Scopes: {scopes}")
    
    # Run tests
    results = {}
    results["userinfo"] = test_google_userinfo(access_token)
    results["calendar"] = test_google_calendar(access_token)
    results["gmail"] = test_google_gmail(access_token)
    results["drive"] = test_google_drive(access_token)
    
    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    passed = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    
    if passed < total:
        print("\nFailed tests may indicate:")
        print("  - Token has expired (try refreshing)")
        print("  - Missing scopes")
        print("  - API not enabled in Google Cloud Console")
        return 1
    
    print("\n✓ All Google API tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
