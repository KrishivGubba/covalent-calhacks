#!/usr/bin/env python3
"""
Test script to verify GitHub API integration is working.
Reads the access token from the integration_tokens table and tests GitHub API calls.
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


def test_github_user(access_token: str) -> dict:
    """Test GitHub user endpoint."""
    print("\n--- Testing GitHub User API ---")
    try:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ User: {data.get('login', 'unknown')}")
            print(f"  Name: {data.get('name', 'N/A')}")
            print(f"  Email: {data.get('email', 'N/A')}")
            return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ User failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ User error: {e}")
        return {"success": False, "error": str(e)}


def test_github_repos(access_token: str) -> dict:
    """Test GitHub repos endpoint - list user's repos."""
    print("\n--- Testing GitHub Repos API ---")
    try:
        req = urllib.request.Request(
            "https://api.github.com/user/repos?per_page=5&sort=updated",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ Found {len(data)} repo(s) (showing first 5)")
            for repo in data[:5]:
                visibility = "private" if repo.get("private") else "public"
                print(f"  - {repo.get('full_name', 'Untitled')} ({visibility})")
            return {"success": True, "count": len(data)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Repos failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Repos error: {e}")
        return {"success": False, "error": str(e)}


def test_github_issues(access_token: str) -> dict:
    """Test GitHub issues endpoint - list user's issues."""
    print("\n--- Testing GitHub Issues API ---")
    try:
        req = urllib.request.Request(
            "https://api.github.com/user/issues?per_page=5&state=all",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ Found {len(data)} issue(s) (showing first 5)")
            for issue in data[:5]:
                print(f"  - #{issue.get('number')}: {issue.get('title', 'Untitled')[:50]} ({issue.get('state')})")
            return {"success": True, "count": len(data)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Issues failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Issues error: {e}")
        return {"success": False, "error": str(e)}


def test_github_notifications(access_token: str) -> dict:
    """Test GitHub notifications endpoint."""
    print("\n--- Testing GitHub Notifications API ---")
    try:
        req = urllib.request.Request(
            "https://api.github.com/notifications?per_page=5",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ Found {len(data)} notification(s)")
            for notif in data[:3]:
                print(f"  - {notif.get('subject', {}).get('title', 'Untitled')[:50]}")
            return {"success": True, "count": len(data)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Notifications failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"✗ Notifications error: {e}")
        return {"success": False, "error": str(e)}


def main():
    print("=" * 50)
    print("GitHub Integration Test")
    print("=" * 50)
    
    # Initialize DAO and get GitHub token
    db_path = get_db_path()
    print(f"\nDatabase path: {db_path}")
    
    dao = IntegrationDAO(db_path)
    
    # Check if GitHub is connected
    if not dao.is_connected("github"):
        print("\n✗ GitHub is not connected!")
        print("  Please connect GitHub from the Integrations page first.")
        return 1
    
    # Get token data
    token_data = dao.get_token("github")
    if not token_data:
        print("\n✗ No token data found for GitHub!")
        return 1
    
    access_token = token_data.get("access_token")
    scopes = token_data.get("scopes")
    metadata = token_data.get("provider_metadata")
    
    print(f"\n✓ GitHub token found!")
    print(f"  Username: {metadata.get('username', 'unknown') if metadata else 'unknown'}")
    print(f"  Scopes: {scopes}")
    print(f"  Note: GitHub tokens don't expire")
    
    # Run tests
    results = {}
    results["user"] = test_github_user(access_token)
    results["repos"] = test_github_repos(access_token)
    results["issues"] = test_github_issues(access_token)
    results["notifications"] = test_github_notifications(access_token)
    
    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    passed = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    
    if passed < total:
        print("\nFailed tests may indicate:")
        print("  - Token was revoked")
        print("  - Missing scopes")
        print("  - Rate limiting")
        return 1
    
    print("\n✓ All GitHub API tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
