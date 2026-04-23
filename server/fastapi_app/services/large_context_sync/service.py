"""High-level service wrapper for large context sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from logger import get_logger
from server.fastapi_app.dependencies import get_data_dir, get_encrypted_conn, refresh_tree_from_db
from server.fastapi_app.services.integration_registry import get_provider_config

from .dao import LargeContextSyncDAO
from .engine import LargeContextSyncBusyError, LargeContextSyncEngine
from .graph_projection import LargeContextGraphProjector
from .integration_groups import build_live_integration_provider_map, compute_next_run_at
from .models import (
    LargeContextIntegrationConfigUpdate,
    LargeContextIntegrationStatus,
    ManualRunRequest,
)
from .providers import build_default_provider_registry
from .scheduler import LargeContextSyncScheduler
from .selection import resolve_manual_run_selection
from .storage import LargeContextSnapshotStorage

log = get_logger()


class LargeContextSyncService:
    """Coordinates config/state, engine runs, and the background scheduler."""

    def __init__(self, *, db_path: str, integration_dao, provider_registry: Optional[Iterable] = None):
        default_markdown_root = f"{get_data_dir()}/long_term_context"
        self.dao = LargeContextSyncDAO(db_path, get_encrypted_conn)
        self.integration_dao = integration_dao
        self.providers = list(provider_registry or build_default_provider_registry(integration_dao))
        self.integration_provider_map = build_live_integration_provider_map(self.providers)
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
        self.scheduler = LargeContextSyncScheduler(
            dao=self.dao,
            engine=self.engine,
            providers=self.providers,
            integration_dao=self.integration_dao,
        )

    async def start(self) -> None:
        self.scheduler.start()
        import asyncio

        await asyncio.sleep(0)

    async def stop(self) -> None:
        await self.scheduler.stop()

    async def run_now(self, request: ManualRunRequest | None = None):
        import asyncio

        selection = resolve_manual_run_selection(
            request,
            providers=self.providers,
            integration_dao=self.integration_dao,
        )
        log.info(
            f"Large context manual run selection resolved "
            f"(mode={selection.selection_mode}, providers={selection.provider_ids or 'all_registry'})"
        )
        return await asyncio.to_thread(self.engine.sync_once, selection.provider_ids, False)

    def get_config(self):
        return self.dao.get_config()

    def update_config(self, *, enabled: bool, interval_minutes: int):
        config = self.dao.update_config(enabled=enabled, interval_minutes=interval_minutes)
        self.dao.bulk_update_integration_controls(enabled=enabled, interval_minutes=interval_minutes)
        self.scheduler.notify_config_changed()
        return config

    def update_integration_config(self, integration_id: str, *, enabled: bool, interval_minutes: int):
        config = self.dao.update_integration_control(
            integration_id,
            enabled=enabled,
            interval_minutes=interval_minutes,
        )
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
        latest_run = self.dao.get_latest_run()
        integration_statuses = [status.model_dump() for status in self.list_integration_statuses()]
        return {
            "config": self.get_config().model_dump(),
            "scheduler": {
                "running": self.scheduler.running,
                "next_run_at": self.scheduler.next_run_at,
                "last_started_at": self.scheduler.last_started_at,
                "last_completed_at": self.scheduler.last_completed_at,
            },
            "integrations": integration_statuses,
            "providers": [state.model_dump() for state in self.dao.get_provider_states().values()],
            "last_run": latest_run.model_dump() if latest_run else None,
        }

    def list_integration_statuses(self) -> list[LargeContextIntegrationStatus]:
        controls = self.dao.get_integration_controls()
        global_config = self.get_config()
        provider_lookup = {provider.provider_id: provider for provider in self.providers}
        now = datetime.now(timezone.utc)
        statuses: list[LargeContextIntegrationStatus] = []

        for integration_id, provider_ids in self.integration_provider_map.items():
            control = controls.get(integration_id)
            if control is None:
                continue
            providers = [provider_lookup[provider_id] for provider_id in provider_ids if provider_id in provider_lookup]
            connected = any(provider.is_connected(self.integration_dao) for provider in providers)
            next_run_at = None
            if global_config.enabled and control.enabled and connected:
                next_run_at = compute_next_run_at(
                    control.last_completed_at,
                    control.interval_minutes,
                    now=now,
                ).isoformat()
            statuses.append(
                LargeContextIntegrationStatus(
                    integration_id=integration_id,
                    display_name=self._integration_display_name(integration_id, providers),
                    provider_ids=provider_ids,
                    connected=connected,
                    enabled=control.enabled,
                    interval_minutes=control.interval_minutes,
                    status=control.status,
                    last_started_at=control.last_started_at,
                    last_completed_at=control.last_completed_at,
                    last_success_at=control.last_success_at,
                    last_error=control.last_error,
                    next_run_at=next_run_at,
                )
            )

        return statuses

    def _integration_display_name(self, integration_id: str, providers: list) -> str:
        try:
            return get_provider_config(integration_id).name
        except KeyError:
            if providers:
                return providers[0].display_name
            return integration_id.replace("_", " ").title()
