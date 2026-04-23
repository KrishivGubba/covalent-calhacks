"""Jira Cloud REST client for OAuth-based MCP tools and sync."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import requests


class JiraClient:
    ATLASSIAN_API_BASE = "https://api.atlassian.com"

    def __init__(self, access_token: str, cloud_id: Optional[str] = None):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.cloud_id = cloud_id

    @staticmethod
    def adf_to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(filter(None, (JiraClient.adf_to_text(item) for item in value))).strip()
        if not isinstance(value, dict):
            return str(value)

        if value.get("type") == "text":
            return value.get("text", "")

        content = value.get("content")
        if isinstance(content, list):
            parts = [JiraClient.adf_to_text(item) for item in content]
            joined = "".join(part for part in parts if part)
            if value.get("type") in {"paragraph", "heading", "bulletList", "orderedList", "listItem"}:
                return joined + "\n"
            return joined

        return ""

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, url: str, **kwargs) -> Any:
        headers = self._headers(kwargs.pop("headers", None))
        response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _api_url(self, path: str, cloud_id: Optional[str] = None) -> str:
        resolved_cloud_id = cloud_id or self.cloud_id
        if not resolved_cloud_id:
            raise ValueError("cloud_id is required")
        return f"{self.ATLASSIAN_API_BASE}/ex/jira/{resolved_cloud_id}{path}"

    def get_accessible_resources(self) -> List[Dict[str, Any]]:
        return self._request("GET", f"{self.ATLASSIAN_API_BASE}/oauth/token/accessible-resources")

    def get_myself(self) -> Dict[str, Any]:
        return self._request("GET", f"{self.ATLASSIAN_API_BASE}/me")

    def list_projects(self, *, cloud_id: Optional[str] = None) -> List[Dict[str, Any]]:
        response = self._request(
            "GET",
            self._api_url("/rest/api/3/project/search", cloud_id=cloud_id),
            params={"maxResults": 100},
        )
        return response.get("values", [])

    def list_issue_types(self, *, cloud_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._request("GET", self._api_url("/rest/api/3/issuetype", cloud_id=cloud_id))

    def search_issues(
        self,
        jql: str,
        *,
        cloud_id: Optional[str] = None,
        max_results: int = 50,
        fields: Optional[Iterable[str]] = None,
        expand: Optional[Iterable[str] | str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max(1, min(max_results, 100)),
        }
        if fields is not None:
            payload["fields"] = list(fields)
        if expand:
            payload["expand"] = ",".join(expand) if not isinstance(expand, str) else expand
        return self._request(
            "POST",
            self._api_url("/rest/api/3/search/jql", cloud_id=cloud_id),
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    def get_issue(
        self,
        issue_key: str,
        *,
        cloud_id: Optional[str] = None,
        fields: Optional[Iterable[str]] = None,
        expand: Optional[Iterable[str] | str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if fields is not None:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand) if not isinstance(expand, str) else expand
        return self._request(
            "GET",
            self._api_url(f"/rest/api/3/issue/{issue_key}", cloud_id=cloud_id),
            params=params or None,
        )

    def create_issue(self, fields: Dict[str, Any], *, cloud_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            self._api_url("/rest/api/3/issue", cloud_id=cloud_id),
            json={"fields": fields},
            headers={"Content-Type": "application/json"},
        )

    def update_issue(self, issue_key: str, fields: Dict[str, Any], *, cloud_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request(
            "PUT",
            self._api_url(f"/rest/api/3/issue/{issue_key}", cloud_id=cloud_id),
            json={"fields": fields},
            headers={"Content-Type": "application/json"},
        )

    def assign_issue(self, issue_key: str, account_id: str, *, cloud_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request(
            "PUT",
            self._api_url(f"/rest/api/3/issue/{issue_key}/assignee", cloud_id=cloud_id),
            json={"accountId": account_id},
            headers={"Content-Type": "application/json"},
        )

    def add_comment(self, issue_key: str, body: Dict[str, Any], *, cloud_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            self._api_url(f"/rest/api/3/issue/{issue_key}/comment", cloud_id=cloud_id),
            json={"body": body},
            headers={"Content-Type": "application/json"},
        )

    def list_transitions(self, issue_key: str, *, cloud_id: Optional[str] = None) -> List[Dict[str, Any]]:
        response = self._request(
            "GET",
            self._api_url(f"/rest/api/3/issue/{issue_key}/transitions", cloud_id=cloud_id),
            params={"expand": "transitions.fields"},
        )
        return response.get("transitions", [])

    def transition_issue(self, issue_key: str, transition_id: str, *, cloud_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request(
            "POST",
            self._api_url(f"/rest/api/3/issue/{issue_key}/transitions", cloud_id=cloud_id),
            json={"transition": {"id": transition_id}},
            headers={"Content-Type": "application/json"},
        )

    @staticmethod
    def plain_text_to_adf(text: str) -> Dict[str, Any]:
        paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
        if not paragraphs:
            paragraphs = [text.strip()] if text.strip() else []
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": paragraph}],
                }
                for paragraph in paragraphs
            ],
        }
