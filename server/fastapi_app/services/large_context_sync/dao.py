"""Database access for large context sync config, state, and run history."""

from __future__ import annotations

import json
from contextlib import closing
from typing import Any, Dict, Iterable, Optional

from .models import (
    LargeContextEntityState,
    LargeContextIntegrationSyncState,
    LargeContextProviderState,
    LargeContextRunSummary,
    LargeContextSyncConfig,
    ProviderRegistryInfo,
)


class LargeContextSyncDAO:
    """DAO for large context sync tables."""

    def __init__(self, db_path: str, conn_factory):
        self.db_path = db_path
        self._conn_factory = conn_factory

    def _conn(self):
        return self._conn_factory(self.db_path)

    def _row_to_entity_state(self, row) -> LargeContextEntityState:
        return LargeContextEntityState(
            provider_id=row[0],
            entity_type=row[1],
            external_id=row[2],
            container_id=row[3],
            title=row[4],
            source_url=row[5],
            source_updated_at=row[6],
            first_seen_at=row[7],
            last_seen_at=row[8],
            last_changed_at=row[9],
            fingerprint=row[10],
            normalized_json=json.loads(row[11]) if row[11] else {},
            durable_node_uuid=row[12],
            active_node_uuid=row[13],
            is_active=bool(row[14]),
            active_score=float(row[15] or 0.0),
            active_reasons=json.loads(row[16]) if row[16] else [],
            last_active_at=row[17],
        )

    def initialize(self, markdown_root: str, providers: Iterable[ProviderRegistryInfo]) -> None:
        providers = list(providers)
        with closing(self._conn()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS large_context_integration_controls (
                    integration_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    interval_minutes INTEGER NOT NULL DEFAULT 60,
                    status TEXT NOT NULL DEFAULT 'idle',
                    last_started_at TEXT,
                    last_completed_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO large_context_sync_config
                    (id, enabled, interval_minutes, projection_mode, markdown_root)
                VALUES (1, 1, 60, 'provider_subtree', ?)
                """,
                (markdown_root,),
            )
            conn.execute(
                """
                UPDATE large_context_sync_config
                SET markdown_root = COALESCE(markdown_root, ?)
                WHERE id = 1
                """,
                (markdown_root,),
            )
            config_row = conn.execute(
                """
                SELECT enabled, interval_minutes
                FROM large_context_sync_config
                WHERE id = 1
                """
            ).fetchone()
            default_enabled = bool(config_row[0]) if config_row else True
            default_interval = config_row[1] if config_row else 60
            for provider in providers:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO large_context_provider_state
                        (provider, supports_live_sync, status)
                    VALUES (?, ?, 'idle')
                    """,
                    (provider.provider_id, int(provider.supports_live_sync)),
                )
            live_integrations = sorted(
                {
                    provider.integration_provider_key
                    for provider in providers
                    if provider.supports_live_sync and provider.integration_provider_key
                }
            )
            for integration_id in live_integrations:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO large_context_integration_controls
                        (integration_id, enabled, interval_minutes, status)
                    VALUES (?, ?, ?, 'idle')
                    """,
                    (integration_id, int(default_enabled), default_interval),
                )
            conn.commit()

    def get_config(self) -> LargeContextSyncConfig:
        with closing(self._conn()) as conn:
            row = conn.execute(
                """
                SELECT enabled, interval_minutes, projection_mode, markdown_root, last_scheduler_heartbeat
                FROM large_context_sync_config
                WHERE id = 1
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("large_context_sync_config row missing")
        return LargeContextSyncConfig(
            enabled=bool(row[0]),
            interval_minutes=row[1],
            projection_mode=row[2],
            markdown_root=row[3],
            last_scheduler_heartbeat=row[4],
        )

    def update_config(self, *, enabled: bool, interval_minutes: int, markdown_root: Optional[str] = None) -> LargeContextSyncConfig:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_sync_config
                SET enabled = ?, interval_minutes = ?, markdown_root = COALESCE(?, markdown_root)
                WHERE id = 1
                """,
                (int(enabled), interval_minutes, markdown_root),
            )
            conn.commit()
        return self.get_config()

    def get_integration_controls(self) -> Dict[str, LargeContextIntegrationSyncState]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                """
                SELECT integration_id, enabled, interval_minutes, status, last_started_at,
                       last_completed_at, last_success_at, last_error
                FROM large_context_integration_controls
                """
            ).fetchall()
        return {
            row[0]: LargeContextIntegrationSyncState(
                integration_id=row[0],
                enabled=bool(row[1]),
                interval_minutes=row[2],
                status=row[3],
                last_started_at=row[4],
                last_completed_at=row[5],
                last_success_at=row[6],
                last_error=row[7],
            )
            for row in rows
        }

    def update_integration_control(
        self,
        integration_id: str,
        *,
        enabled: bool,
        interval_minutes: int,
    ) -> LargeContextIntegrationSyncState:
        with closing(self._conn()) as conn:
            cursor = conn.execute(
                """
                UPDATE large_context_integration_controls
                SET enabled = ?, interval_minutes = ?
                WHERE integration_id = ?
                """,
                (int(enabled), interval_minutes, integration_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Unknown large-context integration: {integration_id}")
        return self.get_integration_controls()[integration_id]

    def bulk_update_integration_controls(self, *, enabled: bool, interval_minutes: int) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_integration_controls
                SET enabled = ?, interval_minutes = ?
                """,
                (int(enabled), interval_minutes),
            )
            conn.commit()

    def touch_scheduler_heartbeat(self, heartbeat_at: str) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_sync_config
                SET last_scheduler_heartbeat = ?
                WHERE id = 1
                """,
                (heartbeat_at,),
            )
            conn.commit()

    def mark_integration_started(self, integration_id: str, *, started_at: str) -> None:
        with closing(self._conn()) as conn:
            cursor = conn.execute(
                """
                UPDATE large_context_integration_controls
                SET last_started_at = ?, status = 'running', last_error = NULL
                WHERE integration_id = ?
                """,
                (started_at, integration_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Unknown large-context integration: {integration_id}")

    def mark_integration_completed(
        self,
        integration_id: str,
        *,
        completed_at: str,
        status: str,
        last_error: Optional[str] = None,
        mark_success: bool = False,
    ) -> None:
        with closing(self._conn()) as conn:
            cursor = conn.execute(
                """
                UPDATE large_context_integration_controls
                SET last_completed_at = ?,
                    last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                    last_error = ?,
                    status = ?
                WHERE integration_id = ?
                """,
                (
                    completed_at,
                    int(mark_success),
                    completed_at,
                    last_error,
                    status,
                    integration_id,
                ),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Unknown large-context integration: {integration_id}")

    def get_provider_states(self) -> Dict[str, LargeContextProviderState]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                """
                SELECT provider, supports_live_sync, cursor_json, last_started_at, last_completed_at,
                       last_success_at, last_error, status, last_snapshot_path
                FROM large_context_provider_state
                """
            ).fetchall()
        return {
            row[0]: LargeContextProviderState(
                provider=row[0],
                supports_live_sync=bool(row[1]),
                cursor_json=json.loads(row[2]) if row[2] else None,
                last_started_at=row[3],
                last_completed_at=row[4],
                last_success_at=row[5],
                last_error=row[6],
                status=row[7],
                last_snapshot_path=row[8],
            )
            for row in rows
        }

    def mark_provider_started(self, provider: str, *, supports_live_sync: bool, started_at: str) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                INSERT INTO large_context_provider_state
                    (provider, supports_live_sync, last_started_at, status)
                VALUES (?, ?, ?, 'running')
                ON CONFLICT(provider) DO UPDATE SET
                    supports_live_sync = excluded.supports_live_sync,
                    last_started_at = excluded.last_started_at,
                    last_error = NULL,
                    status = 'running'
                """,
                (provider, int(supports_live_sync), started_at),
            )
            conn.commit()

    def mark_provider_completed(
        self,
        provider: str,
        *,
        supports_live_sync: bool,
        completed_at: str,
        status: str,
        cursor_json: Optional[Dict[str, Any]] = None,
        last_error: Optional[str] = None,
        last_snapshot_path: Optional[str] = None,
        mark_success: bool = False,
    ) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                INSERT INTO large_context_provider_state
                    (provider, supports_live_sync, cursor_json, last_completed_at, last_success_at, last_error, status, last_snapshot_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    supports_live_sync = excluded.supports_live_sync,
                    cursor_json = COALESCE(excluded.cursor_json, large_context_provider_state.cursor_json),
                    last_completed_at = excluded.last_completed_at,
                    last_success_at = CASE WHEN ? THEN excluded.last_completed_at ELSE large_context_provider_state.last_success_at END,
                    last_error = excluded.last_error,
                    status = excluded.status,
                    last_snapshot_path = COALESCE(excluded.last_snapshot_path, large_context_provider_state.last_snapshot_path)
                """,
                (
                    provider,
                    int(supports_live_sync),
                    json.dumps(cursor_json) if cursor_json is not None else None,
                    completed_at,
                    completed_at if mark_success else None,
                    last_error,
                    status,
                    last_snapshot_path,
                    int(mark_success),
                ),
            )
            conn.commit()

    def create_run(self, run: LargeContextRunSummary) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                INSERT INTO large_context_sync_runs
                    (run_id, started_at, completed_at, status, providers_attempted, providers_succeeded, providers_failed, error_json, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.started_at,
                    run.completed_at,
                    run.status,
                    json.dumps(run.providers_attempted),
                    json.dumps(run.providers_succeeded),
                    json.dumps(run.providers_failed),
                    json.dumps(run.error_json) if run.error_json is not None else None,
                    json.dumps(run.metrics_json) if run.metrics_json is not None else None,
                ),
            )
            conn.commit()

    def update_run(self, run: LargeContextRunSummary) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_sync_runs
                SET completed_at = ?, status = ?, providers_attempted = ?, providers_succeeded = ?,
                    providers_failed = ?, error_json = ?, metrics_json = ?
                WHERE run_id = ?
                """,
                (
                    run.completed_at,
                    run.status,
                    json.dumps(run.providers_attempted),
                    json.dumps(run.providers_succeeded),
                    json.dumps(run.providers_failed),
                    json.dumps(run.error_json) if run.error_json is not None else None,
                    json.dumps(run.metrics_json) if run.metrics_json is not None else None,
                    run.run_id,
                ),
            )
            conn.commit()

    def get_latest_run(self) -> Optional[LargeContextRunSummary]:
        with closing(self._conn()) as conn:
            row = conn.execute(
                """
                SELECT run_id, started_at, completed_at, status, providers_attempted, providers_succeeded, providers_failed, error_json, metrics_json
                FROM large_context_sync_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return LargeContextRunSummary(
            run_id=row[0],
            started_at=row[1],
            completed_at=row[2],
            status=row[3],
            providers_attempted=json.loads(row[4]) if row[4] else [],
            providers_succeeded=json.loads(row[5]) if row[5] else [],
            providers_failed=json.loads(row[6]) if row[6] else [],
            error_json=json.loads(row[7]) if row[7] else None,
            metrics_json=json.loads(row[8]) if row[8] else {},
        )

    def get_entity_state(
        self,
        provider_id: str,
        entity_type: str,
        external_id: str,
    ) -> Optional[LargeContextEntityState]:
        with closing(self._conn()) as conn:
            row = conn.execute(
                """
                SELECT provider_id, entity_type, external_id, container_id, title, source_url,
                       source_updated_at, first_seen_at, last_seen_at, last_changed_at,
                       fingerprint, normalized_json, durable_node_uuid, active_node_uuid,
                       is_active, active_score, active_reasons_json, last_active_at
                FROM large_context_entity_state
                WHERE provider_id = ? AND entity_type = ? AND external_id = ?
                """,
                (provider_id, entity_type, external_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity_state(row)

    def get_entity_states_for_provider(self, provider_id: str) -> Dict[tuple[str, str], LargeContextEntityState]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                """
                SELECT provider_id, entity_type, external_id, container_id, title, source_url,
                       source_updated_at, first_seen_at, last_seen_at, last_changed_at,
                       fingerprint, normalized_json, durable_node_uuid, active_node_uuid,
                       is_active, active_score, active_reasons_json, last_active_at
                FROM large_context_entity_state
                WHERE provider_id = ?
                """,
                (provider_id,),
            ).fetchall()
        return {
            (row[1], row[2]): self._row_to_entity_state(row)
            for row in rows
        }

    def upsert_entity_state(self, state: LargeContextEntityState) -> LargeContextEntityState:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                INSERT INTO large_context_entity_state (
                    provider_id, entity_type, external_id, container_id, title, source_url,
                    source_updated_at, first_seen_at, last_seen_at, last_changed_at,
                    fingerprint, normalized_json, durable_node_uuid, active_node_uuid,
                    is_active, active_score, active_reasons_json, last_active_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, entity_type, external_id) DO UPDATE SET
                    container_id = excluded.container_id,
                    title = excluded.title,
                    source_url = excluded.source_url,
                    source_updated_at = excluded.source_updated_at,
                    first_seen_at = large_context_entity_state.first_seen_at,
                    last_seen_at = excluded.last_seen_at,
                    last_changed_at = excluded.last_changed_at,
                    fingerprint = excluded.fingerprint,
                    normalized_json = excluded.normalized_json,
                    durable_node_uuid = COALESCE(excluded.durable_node_uuid, large_context_entity_state.durable_node_uuid),
                    active_node_uuid = COALESCE(excluded.active_node_uuid, large_context_entity_state.active_node_uuid),
                    is_active = excluded.is_active,
                    active_score = excluded.active_score,
                    active_reasons_json = excluded.active_reasons_json,
                    last_active_at = COALESCE(excluded.last_active_at, large_context_entity_state.last_active_at)
                """,
                (
                    state.provider_id,
                    state.entity_type,
                    state.external_id,
                    state.container_id,
                    state.title,
                    state.source_url,
                    state.source_updated_at,
                    state.first_seen_at,
                    state.last_seen_at,
                    state.last_changed_at,
                    state.fingerprint,
                    json.dumps(state.normalized_json),
                    state.durable_node_uuid,
                    state.active_node_uuid,
                    int(state.is_active),
                    state.active_score,
                    json.dumps(state.active_reasons),
                    state.last_active_at,
                ),
            )
            conn.commit()
        return self.get_entity_state(state.provider_id, state.entity_type, state.external_id)  # type: ignore[return-value]

    def delete_entity_state(self, provider_id: str, entity_type: str, external_id: str) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                DELETE FROM large_context_entity_state
                WHERE provider_id = ? AND entity_type = ? AND external_id = ?
                """,
                (provider_id, entity_type, external_id),
            )
            conn.commit()

    def mark_entity_active(
        self,
        provider_id: str,
        entity_type: str,
        external_id: str,
        *,
        active_node_uuid: Optional[str],
        active_score: float,
        active_reasons: list[str],
        last_active_at: str,
    ) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_entity_state
                SET active_node_uuid = ?,
                    is_active = 1,
                    active_score = ?,
                    active_reasons_json = ?,
                    last_active_at = ?
                WHERE provider_id = ? AND entity_type = ? AND external_id = ?
                """,
                (
                    active_node_uuid,
                    active_score,
                    json.dumps(active_reasons),
                    last_active_at,
                    provider_id,
                    entity_type,
                    external_id,
                ),
            )
            conn.commit()

    def mark_entity_inactive(self, provider_id: str, entity_type: str, external_id: str) -> None:
        with closing(self._conn()) as conn:
            conn.execute(
                """
                UPDATE large_context_entity_state
                SET active_node_uuid = NULL,
                    is_active = 0,
                    active_score = 0,
                    active_reasons_json = '[]'
                WHERE provider_id = ? AND entity_type = ? AND external_id = ?
                """,
                (provider_id, entity_type, external_id),
            )
            conn.commit()

    def list_active_entities(
        self,
        *,
        provider_id: Optional[str] = None,
        limit: int = 25,
    ) -> list[LargeContextEntityState]:
        params: list[Any] = []
        query = """
            SELECT provider_id, entity_type, external_id, container_id, title, source_url,
                   source_updated_at, first_seen_at, last_seen_at, last_changed_at,
                   fingerprint, normalized_json, durable_node_uuid, active_node_uuid,
                   is_active, active_score, active_reasons_json, last_active_at
            FROM large_context_entity_state
            WHERE is_active = 1
        """
        if provider_id:
            query += " AND provider_id = ?"
            params.append(provider_id)
        query += " ORDER BY active_score DESC, COALESCE(last_active_at, last_seen_at) DESC LIMIT ?"
        params.append(limit)
        with closing(self._conn()) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_entity_state(row) for row in rows]
