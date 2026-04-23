"""Core large context sync orchestration."""

from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timedelta, timezone
import threading
from typing import Iterable, Optional

from logger import get_logger

from .dao import LargeContextSyncDAO
from .graph_projection import LargeContextGraphProjector
from .integration_groups import build_live_integration_provider_map
from .models import LargeContextRunSummary
from .storage import LargeContextSnapshotStorage

log = get_logger()


class LargeContextSyncBusyError(RuntimeError):
    """Raised when a large-context sync is already running."""


class LargeContextSyncEngine:
    """Runs a large context sync across the provider registry."""

    INITIAL_BACKFILL_DAYS = 14

    def __init__(
        self,
        *,
        dao: LargeContextSyncDAO,
        integration_dao,
        storage: LargeContextSnapshotStorage,
        projector: LargeContextGraphProjector,
        providers: Iterable,
    ):
        self.dao = dao
        self.integration_dao = integration_dao
        self.storage = storage
        self.projector = projector
        self.providers = list(providers)
        self._run_lock = threading.Lock()
        self.integration_provider_map = build_live_integration_provider_map(self.providers)
        self.provider_integration_map = {
            provider_id: integration_id
            for integration_id, provider_ids in self.integration_provider_map.items()
            for provider_id in provider_ids
        }

    @property
    def is_running(self) -> bool:
        return self._run_lock.locked()

    def sync_once(
        self,
        provider_subset: Optional[list[str]] = None,
        blocking: bool = True,
    ) -> LargeContextRunSummary:
        acquired = self._run_lock.acquire(blocking=blocking)
        if not acquired:
            raise LargeContextSyncBusyError("Large context sync is already running")
        try:
            config = self.dao.get_config()
            provider_lookup = {provider.provider_id: provider for provider in self.providers}
            if provider_subset:
                unknown = sorted(set(provider_subset) - set(provider_lookup))
                if unknown:
                    raise ValueError(f"Unknown providers requested: {', '.join(unknown)}")
                providers = [provider_lookup[provider_id] for provider_id in provider_subset]
            else:
                providers = list(self.providers)
            integration_attempts: dict[str, dict[str, list[str]]] = {}
            for provider in providers:
                integration_id = self.provider_integration_map.get(provider.provider_id)
                if not integration_id:
                    continue
                integration_attempts.setdefault(
                    integration_id,
                    {"success": [], "failure": [], "disconnected": []},
                )

            run = LargeContextRunSummary(
                run_id=str(uuid.uuid4()),
                started_at=datetime.now(timezone.utc).isoformat(),
                status="running",
            )
            self.dao.create_run(run)
            log.info(
                f"Large context sync run {run.run_id} starting "
                f"(providers={','.join(provider.provider_id for provider in providers)}, "
                f"interval_minutes={config.interval_minutes})"
            )
            provider_states = self.dao.get_provider_states()
            any_success = False
            errors: dict[str, str] = {}
            for integration_id in integration_attempts:
                self.dao.mark_integration_started(
                    integration_id,
                    started_at=run.started_at,
                )

            for provider in providers:
                run.providers_attempted.append(provider.provider_id)
                started_at = datetime.now(timezone.utc).isoformat()
                log.info(f"Large context sync provider {provider.provider_id} starting")
                self.dao.mark_provider_started(
                    provider.provider_id,
                    supports_live_sync=provider.supports_live_sync,
                    started_at=started_at,
                )

                if not provider.supports_live_sync:
                    completed_at = datetime.now(timezone.utc).isoformat()
                    log.info(
                        f"Large context sync provider {provider.provider_id} skipped "
                        "(placeholder adapter)"
                    )
                    self.dao.mark_provider_completed(
                        provider.provider_id,
                        supports_live_sync=False,
                        completed_at=completed_at,
                        status="not_supported_yet",
                        last_error="Provider adapter is a placeholder in v1",
                    )
                    continue

                if not provider.is_connected(self.integration_dao):
                    completed_at = datetime.now(timezone.utc).isoformat()
                    log.info(
                        f"Large context sync provider {provider.provider_id} skipped "
                        "(integration disconnected or not configured)"
                    )
                    self.dao.mark_provider_completed(
                        provider.provider_id,
                        supports_live_sync=True,
                        completed_at=completed_at,
                        status="disconnected",
                        last_error="Integration is not connected",
                    )
                    self._record_integration_result(integration_attempts, provider.provider_id, "disconnected")
                    continue

                try:
                    state = provider_states.get(provider.provider_id)
                    cursor = state.cursor_json if state else None
                    since_ts = (cursor or {}).get("since") or (
                        datetime.now(timezone.utc) - timedelta(days=self.INITIAL_BACKFILL_DAYS)
                    ).isoformat()
                    log.info(
                        f"Large context sync provider {provider.provider_id} fetching delta "
                        f"since {since_ts}"
                    )
                    fetch_result = provider.fetch_delta(cursor, since_ts)
                    snapshot = provider.build_snapshot(fetch_result)
                    snapshot_path = self.storage.write_snapshot(
                        snapshot,
                        provider.file_name,
                        markdown_root=config.markdown_root,
                    )
                    log.info(
                        f"Large context sync provider {provider.provider_id} wrote snapshot "
                        f"to {snapshot_path} "
                        f"(containers={len(snapshot.containers)}, entities={len(snapshot.entities)}, "
                        f"people={len(snapshot.relevant_people)}, links={len(snapshot.cross_links)})"
                    )
                    provider.project_to_graph(snapshot, self.projector, snapshot_path, run.run_id)
                    log.info(
                        f"Large context sync provider {provider.provider_id} projected snapshot "
                        f"to graph from {snapshot_path}"
                    )
                    completed_at = datetime.now(timezone.utc).isoformat()
                    self.dao.mark_provider_completed(
                        provider.provider_id,
                        supports_live_sync=True,
                        completed_at=completed_at,
                        status="synced",
                        cursor_json=fetch_result.next_cursor or snapshot.cursor,
                        last_snapshot_path=snapshot_path,
                        mark_success=True,
                    )
                    run.providers_succeeded.append(provider.provider_id)
                    any_success = True
                    self._record_integration_result(integration_attempts, provider.provider_id, "success")
                    log.info(f"Large context sync provider {provider.provider_id} completed successfully")
                except Exception as exc:
                    completed_at = datetime.now(timezone.utc).isoformat()
                    message = f"{exc.__class__.__name__}: {exc}"
                    errors[provider.provider_id] = message
                    log.error(f"Large context sync failed for provider {provider.provider_id}: {message}\n{traceback.format_exc()}")
                    self.dao.mark_provider_completed(
                        provider.provider_id,
                        supports_live_sync=provider.supports_live_sync,
                        completed_at=completed_at,
                        status="error",
                        last_error=message,
                    )
                    run.providers_failed.append(provider.provider_id)
                    self._record_integration_result(integration_attempts, provider.provider_id, "failure")

            self._mark_integrations_completed(
                integration_attempts,
                completed_at=datetime.now(timezone.utc).isoformat(),
                errors=errors,
            )

            run.completed_at = datetime.now(timezone.utc).isoformat()
            if run.providers_failed and not any_success:
                run.status = "error"
            elif run.providers_failed:
                run.status = "partial_success"
            else:
                run.status = "completed"
            if errors:
                run.error_json = errors
            self.dao.update_run(run)
            log.info(
                f"Large context sync run {run.run_id} finished with status={run.status} "
                f"(attempted={len(run.providers_attempted)}, "
                f"succeeded={len(run.providers_succeeded)}, failed={len(run.providers_failed)})"
            )
            return run
        finally:
            self._run_lock.release()

    def _record_integration_result(
        self,
        integration_attempts: dict[str, dict[str, list[str]]],
        provider_id: str,
        result_key: str,
    ) -> None:
        integration_id = self.provider_integration_map.get(provider_id)
        if not integration_id or integration_id not in integration_attempts:
            return
        integration_attempts[integration_id][result_key].append(provider_id)

    def _mark_integrations_completed(
        self,
        integration_attempts: dict[str, dict[str, list[str]]],
        *,
        completed_at: str,
        errors: dict[str, str],
    ) -> None:
        for integration_id, attempt in integration_attempts.items():
            if attempt["success"] and attempt["failure"]:
                status = "partial_success"
                last_error = "; ".join(
                    f"{provider_id}: {errors.get(provider_id, 'Unknown error')}"
                    for provider_id in attempt["failure"]
                )
            elif attempt["success"]:
                status = "synced"
                last_error = None
            elif attempt["failure"]:
                status = "error"
                last_error = "; ".join(
                    f"{provider_id}: {errors.get(provider_id, 'Unknown error')}"
                    for provider_id in attempt["failure"]
                )
            elif attempt["disconnected"]:
                status = "disconnected"
                last_error = "Integration is not connected"
            else:
                status = "idle"
                last_error = None

            self.dao.mark_integration_completed(
                integration_id,
                completed_at=completed_at,
                status=status,
                last_error=last_error,
                mark_success=bool(attempt["success"]),
            )
