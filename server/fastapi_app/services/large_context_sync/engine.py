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
from .models import LargeContextRunSummary
from .storage import LargeContextSnapshotStorage

log = get_logger()


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

    def sync_once(self, provider_subset: Optional[list[str]] = None) -> LargeContextRunSummary:
        with self._run_lock:
            config = self.dao.get_config()
            provider_lookup = {provider.provider_id: provider for provider in self.providers}
            if provider_subset:
                unknown = sorted(set(provider_subset) - set(provider_lookup))
                if unknown:
                    raise ValueError(f"Unknown providers requested: {', '.join(unknown)}")
                providers = [provider_lookup[provider_id] for provider_id in provider_subset]
            else:
                providers = list(self.providers)

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
