"""Slack Web API client.

Thin wrapper around the Slack Web API used by the large-context sync provider.
Accepts either a bot (``xoxb-``) or user (``xoxp-``) token. All responses that
come back with ``ok: false`` are raised as ``SlackAPIError`` so callers can
handle failure uniformly.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

import requests


class SlackAPIError(RuntimeError):
    """Raised when the Slack Web API returns ``ok: false``."""

    def __init__(self, method: str, error: str, response: Dict[str, Any]):
        super().__init__(f"Slack API {method} failed: {error}")
        self.method = method
        self.error = error
        self.response = response


class SlackClient:
    """Minimal Slack Web API client.

    Usage::

        client = SlackClient(access_token="xoxb-...")
        auth = client.auth_test()
        for user in client.iter_users():
            ...
    """

    BASE_URL = "https://slack.com/api"

    # Conservative page sizes — Slack's upper bounds are higher, but large page
    # requests are more prone to rate limiting and timeouts.
    USERS_PAGE_SIZE = 200
    CONVERSATIONS_PAGE_SIZE = 200
    HISTORY_PAGE_SIZE = 200
    REPLIES_PAGE_SIZE = 200

    # How many times we retry a 429 before giving up. Slack returns
    # ``Retry-After`` seconds on throttling; we clamp to a sane ceiling so a
    # misbehaving workspace can't stall sync indefinitely.
    MAX_RETRIES = 3
    MAX_RETRY_WAIT_SECONDS = 30.0

    def __init__(self, access_token: str, *, session: Optional[requests.Session] = None):
        if not access_token:
            raise ValueError("access_token must be provided")
        self.access_token = access_token
        self._session = session or requests.Session()

    def _request(self, method: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{method}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        attempts = 0
        while True:
            attempts += 1
            response = self._session.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 429 and attempts <= self.MAX_RETRIES:
                retry_after = float(response.headers.get("Retry-After", "1"))
                time.sleep(min(max(retry_after, 1.0), self.MAX_RETRY_WAIT_SECONDS))
                continue
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                error = str(payload.get("error") or "unknown_error")
                # Slack uses ``ratelimited`` in rare cases where the HTTP status
                # is 200 but throttling still applies. Retry once more.
                if error == "ratelimited" and attempts <= self.MAX_RETRIES:
                    time.sleep(min(float(payload.get("retry_after") or 1.0), self.MAX_RETRY_WAIT_SECONDS))
                    continue
                raise SlackAPIError(method, error, payload)
            return payload

    def _paginate(
        self,
        method: str,
        *,
        collection_key: str,
        params: Dict[str, Any],
    ) -> Iterator[Dict[str, Any]]:
        next_cursor: Optional[str] = None
        while True:
            call_params = dict(params)
            if next_cursor:
                call_params["cursor"] = next_cursor
            payload = self._request(method, params=call_params)
            for item in payload.get(collection_key) or []:
                yield item
            next_cursor = ((payload.get("response_metadata") or {}).get("next_cursor") or "").strip()
            if not next_cursor:
                return

    def auth_test(self) -> Dict[str, Any]:
        return self._request("auth.test")

    def team_info(self) -> Dict[str, Any]:
        payload = self._request("team.info")
        return payload.get("team") or {}

    def iter_users(self) -> Iterator[Dict[str, Any]]:
        yield from self._paginate(
            "users.list",
            collection_key="members",
            params={"limit": self.USERS_PAGE_SIZE},
        )

    def user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            payload = self._request("users.info", params={"user": user_id})
        except SlackAPIError as exc:
            if exc.error in {"user_not_found", "user_not_visible"}:
                return None
            raise
        return payload.get("user")

    def iter_conversations(
        self,
        *,
        types: Iterable[str] = ("public_channel", "private_channel", "mpim", "im"),
        exclude_archived: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        yield from self._paginate(
            "conversations.list",
            collection_key="channels",
            params={
                "types": ",".join(types),
                "exclude_archived": str(exclude_archived).lower(),
                "limit": self.CONVERSATIONS_PAGE_SIZE,
            },
        )

    def iter_history(
        self,
        channel_id: str,
        *,
        oldest: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "channel": channel_id,
            "limit": self.HISTORY_PAGE_SIZE,
        }
        if oldest:
            params["oldest"] = oldest
        count = 0
        for message in self._paginate("conversations.history", collection_key="messages", params=params):
            yield message
            count += 1
            if max_messages is not None and count >= max_messages:
                return

    def iter_replies(
        self,
        channel_id: str,
        thread_ts: str,
        *,
        oldest: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": self.REPLIES_PAGE_SIZE,
        }
        if oldest:
            params["oldest"] = oldest
        count = 0
        for message in self._paginate("conversations.replies", collection_key="messages", params=params):
            yield message
            count += 1
            if max_messages is not None and count >= max_messages:
                return

    def list_all_users(self) -> List[Dict[str, Any]]:
        return list(self.iter_users())

    def list_all_conversations(
        self,
        *,
        types: Iterable[str] = ("public_channel", "private_channel", "mpim", "im"),
        exclude_archived: bool = True,
    ) -> List[Dict[str, Any]]:
        return list(self.iter_conversations(types=types, exclude_archived=exclude_archived))
