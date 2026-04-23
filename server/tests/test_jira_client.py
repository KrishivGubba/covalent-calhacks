from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from covalent_mcp.toolclasses.jira.jira_client import JiraClient


def test_search_issues_uses_enhanced_jql_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        content = b'{"issues":[]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"issues": []}

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("covalent_mcp.toolclasses.jira.jira_client.requests.request", fake_request)

    client = JiraClient(access_token="token", cloud_id="cloud-1")
    client.search_issues(
        'project = "PROJ" ORDER BY updated DESC',
        max_results=50,
        fields=["summary", "status"],
        expand=["names"],
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.atlassian.com/ex/jira/cloud-1/rest/api/3/search/jql"
    assert captured["headers"] == {
        "Authorization": "Bearer token",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == 20
    assert captured["kwargs"] == {
        "json": {
            "jql": 'project = "PROJ" ORDER BY updated DESC',
            "maxResults": 50,
            "fields": ["summary", "status"],
            "expand": "names",
        }
    }
