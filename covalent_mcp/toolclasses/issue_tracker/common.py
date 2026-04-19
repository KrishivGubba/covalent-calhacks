"""Shared helpers for issue-tracker providers and tools."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
DB_PATH = os.environ.get(
    "GRAPH_DB_PATH",
    os.path.join(PROJECT_ROOT, "context-engine", "graph.db"),
)

sys.path.insert(0, PROJECT_ROOT)


def get_integration_dao(db_path: str = DB_PATH):
    from server.integration_dao import IntegrationDAO

    return IntegrationDAO(db_path)


def get_auth0_jwt(db_path: str = DB_PATH) -> Optional[str]:
    try:
        from server.auth_dao import AuthDAO

        auth_dao = AuthDAO(db_path)
        sessions = auth_dao.get_all_sessions()
        if not sessions:
            return None
        user_id = sessions[0]["user_id"]
        session = auth_dao.get_session(user_id)
        return session.get("access_token") if session else None
    except Exception:
        return None


def is_token_expired(expires_at: Optional[str], *, buffer_minutes: int = 5) -> bool:
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return False
    return datetime.utcnow() > (expiry - timedelta(minutes=buffer_minutes))


def merge_provider_metadata(provider: str, updates: Dict[str, Any], *, integration_dao=None) -> Dict[str, Any]:
    dao = integration_dao or get_integration_dao()
    token_data = dao.get_token(provider)
    if not token_data:
        raise RuntimeError(f"{provider} integration is not connected")

    metadata = dict(token_data.get("provider_metadata") or {})
    metadata.update(updates)
    dao.save_token(
        provider=provider,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_at=token_data.get("expires_at"),
        scopes=token_data.get("scopes"),
        provider_metadata=metadata,
    )
    return metadata


GITHUB_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?:issues|pull)/(?P<number>\d+)"
)
GITHUB_SHORTHAND_RE = re.compile(
    r"\b(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<number>\d+)\b"
)
JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
SLACK_URL_RE = re.compile(r"https?://[\w.-]+\.slack\.com/archives/(?P<channel>[A-Z0-9]+)/p(?P<ts>\d{10,})")
NOTION_URL_RE = re.compile(r"https?://(?:www\.)?notion\.so/[\w-]*?(?P<id>[a-fA-F0-9]{32})")


def normalize_notion_id(value: str) -> str:
    return value.replace("-", "").lower()


def _normalize_slack_ts(raw_ts: str) -> str:
    if len(raw_ts) <= 6:
        return raw_ts
    return f"{raw_ts[:-6]}.{raw_ts[-6:]}"


def extract_external_references(texts: Iterable[str], *, current_jira_key: str | None = None) -> Dict[str, list[str]]:
    references = {"github": [], "jira": [], "slack": [], "notion": []}
    seen = {key: set() for key in references}

    def add(kind: str, value: str) -> None:
        if value not in seen[kind]:
            seen[kind].add(value)
            references[kind].append(value)

    for text in texts:
        if not text:
            continue

        for match in GITHUB_URL_RE.finditer(text):
            owner = match.group("owner")
            repo = match.group("repo")
            number = match.group("number")
            add("github", f"github:{owner}/{repo}#{number}")

        for match in GITHUB_SHORTHAND_RE.finditer(text):
            owner = match.group("owner")
            repo = match.group("repo")
            number = match.group("number")
            add("github", f"github:{owner}/{repo}#{number}")

        for match in JIRA_KEY_RE.finditer(text):
            key = match.group(1)
            if key != current_jira_key:
                add("jira", f"jira:{key}")

        for match in SLACK_URL_RE.finditer(text):
            add("slack", f"slack:{match.group('channel')}:{_normalize_slack_ts(match.group('ts'))}")

        for match in NOTION_URL_RE.finditer(text):
            add("notion", f"notion:{normalize_notion_id(match.group('id'))}")

    return references
