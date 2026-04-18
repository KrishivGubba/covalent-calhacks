"""Background scheduler for large context sync."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from logger import get_logger

log = get_logger()


class LargeContextSyncScheduler:
    """Owns the background loop that periodically runs large context sync."""

    def __init__(self, *, dao, engine):
        self.dao = dao
        self.engine = engine
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
            interval_seconds = max(config.interval_minutes, 30) * 60
            self.next_run_at = (now + timedelta(seconds=interval_seconds)).isoformat()
            woke_early = await self._wait_for_wake(timeout_seconds=interval_seconds)
            if woke_early:
                continue

            self.last_started_at = datetime.now(timezone.utc).isoformat()
            try:
                await asyncio.to_thread(self.engine.sync_once)
            except Exception as exc:
                log.error(f"Large context scheduler run failed: {exc}")
            self.last_completed_at = datetime.now(timezone.utc).isoformat()

        log.info("Large context sync scheduler stopped")

    async def _wait_for_wake(self, timeout_seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout_seconds)
            self._wake_event.clear()
            return True
        except asyncio.TimeoutError:
            return False
