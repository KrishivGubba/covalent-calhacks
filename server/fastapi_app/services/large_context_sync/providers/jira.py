"""Jira placeholder provider for large context sync."""

from __future__ import annotations

from ..models import ProviderFetchResult, ProviderSnapshot
from .base import LargeContextProvider


class JiraLargeContextProvider(LargeContextProvider):
    provider_id = "jira"
    display_name = "Jira"
    supports_live_sync = False
    file_name = "jira.md"
    integration_provider_key = "jira"

    def fetch_delta(self, cursor, since_ts: str) -> ProviderFetchResult:
        return ProviderFetchResult(records=[], next_cursor=cursor, metadata={"status": "not_supported_yet"})

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        raise RuntimeError("Jira large context sync is not supported yet")
