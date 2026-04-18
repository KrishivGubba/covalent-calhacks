"""Base provider contract for large context sync."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..models import ProviderFetchResult, ProviderRegistryInfo, ProviderSnapshot


class LargeContextProvider(ABC):
    provider_id: str
    display_name: str
    supports_live_sync: bool = True
    file_name: str
    integration_provider_key: Optional[str] = None

    def registry_info(self) -> ProviderRegistryInfo:
        return ProviderRegistryInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            supports_live_sync=self.supports_live_sync,
            file_name=self.file_name,
            integration_provider_key=self.integration_provider_key,
        )

    def is_connected(self, integration_dao) -> bool:
        if not self.integration_provider_key:
            return False
        return integration_dao.is_connected(self.integration_provider_key)

    @abstractmethod
    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        """Fetch provider records since the previous cursor/time window."""

    @abstractmethod
    def build_snapshot(
        self,
        fetch_result: ProviderFetchResult,
        previous_snapshot: Optional[ProviderSnapshot] = None,
    ) -> ProviderSnapshot:
        """Transform fetched records into the normalized provider snapshot."""

    def project_to_graph(self, snapshot: ProviderSnapshot, projector: Any, snapshot_path: str, run_id: str) -> None:
        projector.project_snapshot(snapshot, snapshot_path=snapshot_path, run_id=run_id)
