#!/usr/bin/env python3
"""
Test script to verify Jira API integration is working.
Reads the access token from the integration_tokens table and tests Jira API calls.
"""
import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from server.integration_dao import IntegrationDAO

import urllib.request
import urllib.error


def get_db_path():
    return os.path.join(PROJECT_ROOT, "context-engine", "graph.db")


def jira_request(url: str, access_token: str, method: str = "GET", data=None) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    print("=" * 50)
    print("Jira Integration Test")
    print("=" * 50)

    dao = IntegrationDAO(get_db_path())
    if not dao.is_connected("jira"):
        print("\n✗ Jira is not connected!")
        print("  Please connect Jira from the Integrations page first.")
        return 1

    token_data = dao.get_token("jira")
    metadata = token_data.get("provider_metadata") or {}
    cloud_id = metadata.get("cloud_id")
    site_url = metadata.get("site_url")
    if not cloud_id or not site_url:
        print("\n✗ Jira is connected but not configured!")
        print("  Select a Jira site and project allowlist from the Integrations page.")
        return 1

    access_token = token_data.get("access_token")
    resources = jira_request(
        "https://api.atlassian.com/oauth/token/accessible-resources",
        access_token,
    )
    projects = jira_request(
        f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project/search?maxResults=5",
        access_token,
    )
    issue_types = jira_request(
        f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issuetype",
        access_token,
    )

    print(f"\n✓ Jira token found for {site_url}")
    print(f"  Accessible sites: {len(resources)}")
    print(f"  Projects returned: {len(projects.get('values', []))}")
    print(f"  Issue types returned: {len(issue_types)}")
    print("\n✓ Jira API smoke test passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
