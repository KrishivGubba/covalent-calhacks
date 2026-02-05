#!/usr/bin/env python3
"""
Test script to verify Notion API integration is working.
Reads the access token from the integration_tokens table and tests Notion API calls.
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

NOTION_API_VERSION = "2022-06-28"


def get_db_path():
    """Get the path to graph.db"""
    return os.path.join(PROJECT_ROOT, 'context-engine', 'graph.db')


def notion_request(endpoint: str, access_token: str, method: str = "GET", data=None) -> dict:
    """Make an authenticated request to Notion API."""
    url = f"https://api.notion.com/v1{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_notion_me(access_token: str) -> dict:
    """Test Notion bot user endpoint."""
    print("\n--- Testing Notion Bot User (me) ---")
    try:
        data = notion_request("/users/me", access_token)
        print(f"  Bot name: {data.get('name', 'N/A')}")
        bot = data.get("bot", {})
        owner = bot.get("owner", {})
        if owner.get("type") == "user":
            user = owner.get("user", {})
            print(f"  Owner: {user.get('name', 'N/A')} ({user.get('person', {}).get('email', 'N/A')})")
        return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  Bot user failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"  Bot user error: {e}")
        return {"success": False, "error": str(e)}


def test_notion_users(access_token: str) -> dict:
    """Test Notion list users endpoint."""
    print("\n--- Testing Notion List Users ---")
    try:
        data = notion_request("/users?page_size=10", access_token)
        users = data.get("results", [])
        print(f"  Found {len(users)} user(s)")
        for user in users[:5]:
            print(f"  - {user.get('name', 'N/A')} ({user.get('type', 'unknown')})")
        return {"success": True, "count": len(users)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  List users failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"  List users error: {e}")
        return {"success": False, "error": str(e)}


def test_notion_search(access_token: str) -> dict:
    """Test Notion search endpoint."""
    print("\n--- Testing Notion Search ---")
    try:
        data = notion_request("/search", access_token, method="POST", data={"page_size": 5})
        results = data.get("results", [])
        print(f"  Found {len(results)} result(s)")
        for item in results[:5]:
            obj_type = item.get("object", "unknown")
            title = _extract_title(item)
            print(f"  - [{obj_type}] {title}")
        return {"success": True, "count": len(results)}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  Search failed: {e.code} - {error_body}")
        return {"success": False, "error": error_body}
    except Exception as e:
        print(f"  Search error: {e}")
        return {"success": False, "error": str(e)}


def _extract_title(obj: dict) -> str:
    """Extract title from a Notion page or database object."""
    properties = obj.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_items = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_items)
    
    title_array = obj.get("title", [])
    if isinstance(title_array, list) and title_array:
        return "".join(t.get("plain_text", "") for t in title_array)
    
    return "Untitled"


def main():
    print("=" * 50)
    print("Notion Integration Test")
    print("=" * 50)
    
    # Initialize DAO and get Notion token
    db_path = get_db_path()
    print(f"\nDatabase path: {db_path}")
    
    dao = IntegrationDAO(db_path)
    
    # Check if Notion is connected
    if not dao.is_connected("notion"):
        print("\n  Notion is not connected!")
        print("  Please connect Notion from the Integrations page first.")
        return 1
    
    # Get token data
    token_data = dao.get_token("notion")
    if not token_data:
        print("\n  No token data found for Notion!")
        return 1
    
    access_token = token_data.get("access_token")
    metadata = token_data.get("provider_metadata")
    
    print(f"\n  Notion token found!")
    print(f"  Workspace: {metadata.get('workspace_name', 'unknown') if metadata else 'unknown'}")
    print(f"  Note: Notion tokens don't expire")
    
    # Run tests
    results = {}
    results["me"] = test_notion_me(access_token)
    results["users"] = test_notion_users(access_token)
    results["search"] = test_notion_search(access_token)
    
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
        print("  - Integration not shared with pages")
        print("  - API version mismatch")
        return 1
    
    print("\n  All Notion API tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
