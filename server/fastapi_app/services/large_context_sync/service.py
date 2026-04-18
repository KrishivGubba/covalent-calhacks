"""High-level service wrapper for large context sync."""

from __future__ import annotations

from typing import Iterable, Optional

from logger import get_logger
from server.fastapi_app.dependencies import get_data_dir, get_encrypted_conn, refresh_tree_from_db

from .dao import LargeContextSyncDAO
from .engine import LargeContextSyncEngine
from .graph_projection import LargeContextGraphProjector
from .providers import build_default_provider_registry
from .scheduler import LargeContextSyncScheduler
from .storage import LargeContextSnapshotStorage

log = get_logger()


class LargeContextSyncService:
    """Coordinates config/state, engine runs, and the background scheduler."""

    def __init__(self, *, db_path: str, integration_dao, provider_registry: Optional[Iterable] = None):
        default_markdown_root = f"{get_data_dir()}/long_term_context"
        self.dao = LargeContextSyncDAO(db_path, get_encrypted_conn)
        self.integration_dao = integration_dao
        self.providers = list(provider_registry or build_default_provider_registry(integration_dao))
        self.storage = LargeContextSnapshotStorage(default_markdown_root)
        self.dao.initialize(default_markdown_root, [provider.registry_info() for provider in self.providers])
        self.projector = LargeContextGraphProjector(db_path, refresh_tree_callback=refresh_tree_from_db)
        self.engine = LargeContextSyncEngine(
            dao=self.dao,
            integration_dao=self.integration_dao,
            storage=self.storage,
            projector=self.projector,
            providers=self.providers,
        )
        self.scheduler = LargeContextSyncScheduler(dao=self.dao, engine=self.engine)

    async def start(self) -> None:
        self.scheduler.start()

    async def stop(self) -> None:
        await self.scheduler.stop()

    async def run_now(self, provider_subset: Optional[list[str]] = None):
        import asyncio

        return await asyncio.to_thread(self.engine.sync_once, provider_subset)

    def get_config(self):
        return self.dao.get_config()

    def update_config(self, *, enabled: bool, interval_minutes: int):
        config = self.dao.update_config(enabled=enabled, interval_minutes=interval_minutes)
        self.scheduler.notify_config_changed()
        return config

    def list_providers(self) -> list[dict]:
        providers = []
        states = self.dao.get_provider_states()
        for provider in self.providers:
            info = provider.registry_info()
            state = states.get(provider.provider_id)
            providers.append({
                **info.model_dump(),
                "connected": provider.is_connected(self.integration_dao) if info.supports_live_sync else False,
                "mode": "live" if info.supports_live_sync else "placeholder",
                "status": state.status if state else "idle",
            })
        return providers

    def get_status(self) -> dict:
        return {
            "config": self.get_config().model_dump(),
            "scheduler": {
                "running": self.scheduler.running,
                "next_run_at": self.scheduler.next_run_at,
                "last_started_at": self.scheduler.last_started_at,
                "last_completed_at": self.scheduler.last_completed_at,
            },
            "providers": [state.model_dump() for state in self.dao.get_provider_states().values()],
            "last_run": self.dao.get_latest_run().model_dump() if self.dao.get_latest_run() else None,
        }
