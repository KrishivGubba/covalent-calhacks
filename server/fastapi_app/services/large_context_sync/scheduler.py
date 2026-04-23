"""Background scheduler for large context sync."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from logger import get_logger

from .engine import LargeContextSyncBusyError
from .integration_groups import build_live_integration_provider_map, compute_next_run_at

log = get_logger()


class LargeContextSyncScheduler:
    """Owns the background loop that periodically runs large context sync."""

    def __init__(self, *, dao, engine, providers, integration_dao):
        self.dao = dao
        self.engine = engine
        self.providers = list(providers)
        self.integration_dao = integration_dao
        self.integration_provider_map = build_live_integration_provider_map(self.providers)
        self.provider_lookup = {provider.provider_id: provider for provider in self.providers}
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self.next_run_at: Optional[str] = None
        self.last_started_at: Optional[str] = None
        self.last_completed_at: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._wake_event.clear()
            self._task = asyncio.create_task(self._run_forever(), name="LargeContextSyncScheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._wake_event.set()
        try:
            await self._task
        finally:
            self._task = None
            self.next_run_at = None

    def notify_config_changed(self) -> None:
        self._wake_event.set()

    async def _run_forever(self) -> None:
        log.info("Large context sync scheduler started")
        while not self._stop_event.is_set():
            config = self.dao.get_config()
            heartbeat = datetime.now(timezone.utc).isoformat()
            self.dao.touch_scheduler_heartbeat(heartbeat)

            if not config.enabled:
                self.next_run_at = None
                await self._wait_for_wake(timeout_seconds=5)
                continue

            now = datetime.now(timezone.utc)
            due_integration_ids, next_run_at = self._resolve_due_integrations(now)
            self.next_run_at = next_run_at.isoformat() if next_run_at else None

            if due_integration_ids:
                provider_ids = [
                    provider_id
                    for integration_id in due_integration_ids
                    for provider_id in self.integration_provider_map.get(integration_id, [])
                ]
                self.last_started_at = now.isoformat()
                log.info(
                    "Large context sync scheduled run starting at "
                    f"{self.last_started_at} for integrations={','.join(due_integration_ids)}"
                )
                try:
                    await asyncio.to_thread(self.engine.sync_once, provider_ids, False)
                except LargeContextSyncBusyError:
                    log.info("Large context sync scheduler skipped because another run is already active")
                except Exception as exc:
                    log.error(f"Large context scheduler run failed: {exc}")
                self.last_completed_at = datetime.now(timezone.utc).isoformat()
                log.info(f"Large context sync scheduled run completed at {self.last_completed_at}")
                continue

            timeout_seconds = 5.0
            if next_run_at is not None:
                timeout_seconds = max((next_run_at - now).total_seconds(), 0.0)
            log.info(
                "Large context sync waiting for next due integration run "
                f"at {self.next_run_at or 'none'}"
            )
            woke_early = await self._wait_for_wake(timeout_seconds=timeout_seconds or 0.1)
            if woke_early:
                log.info("Large context sync scheduler woke early due to config change or shutdown")

        log.info("Large context sync scheduler stopped")

    async def _wait_for_wake(self, timeout_seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout_seconds)
            self._wake_event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    def _resolve_due_integrations(self, now: datetime) -> tuple[list[str], Optional[datetime]]:
        controls = self.dao.get_integration_controls()
        due: list[str] = []
        next_run_at: Optional[datetime] = None

        for integration_id, provider_ids in self.integration_provider_map.items():
            control = controls.get(integration_id)
            if control is None or not control.enabled:
                continue
            providers = [self.provider_lookup[provider_id] for provider_id in provider_ids if provider_id in self.provider_lookup]
            if not providers or not any(provider.is_connected(self.integration_dao) for provider in providers):
                continue
            candidate = compute_next_run_at(
                control.last_completed_at,
                control.interval_minutes,
                now=now,
            )
            if candidate <= now:
                due.append(integration_id)
            if next_run_at is None or candidate < next_run_at:
                next_run_at = candidate

        return due, next_run_at
