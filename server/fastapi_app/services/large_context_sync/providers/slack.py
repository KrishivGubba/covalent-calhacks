"""Slack placeholder provider for large context sync."""

from __future__ import annotations

from ..models import ProviderFetchResult, ProviderSnapshot
from .base import LargeContextProvider


class SlackLargeContextProvider(LargeContextProvider):
    provider_id = "slack"
    display_name = "Slack"
    supports_live_sync = False
    file_name = "slack.md"
    integration_provider_key = "slack"

    def fetch_delta(self, cursor, since_ts: str) -> ProviderFetchResult:
        return ProviderFetchResult(records=[], next_cursor=cursor, metadata={"status": "not_supported_yet"})

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        raise RuntimeError("Slack large context sync is not supported yet")
