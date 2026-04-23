"""Core large context sync orchestration."""

from __future__ import annotations

import traceback
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from logger import get_logger

from .dao import LargeContextSyncDAO
from .entity_state import (
    compute_active_expiry,
    fingerprint_normalized_entity,
    is_active_expired,
    is_recent_iso,
    normalize_snapshot_entity,
    parse_deleted_entity_key,
)
from .graph_projection import LargeContextGraphProjector
from .integration_groups import build_live_integration_provider_map
from .models import LargeContextEntityState, LargeContextRunSummary, ProviderSnapshot, SnapshotEntity
from .storage import LargeContextSnapshotStorage

log = get_logger()


class LargeContextSyncBusyError(RuntimeError):
    """Raised when a large-context sync is already running."""


class LargeContextSyncEngine:
    """Runs a large context sync across the provider registry."""

    INITIAL_BACKFILL_DAYS = 14
    ACTIVE_SCORE_THRESHOLD = 1.25

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
                self.dao.mark_integration_started(integration_id, started_at=run.started_at)

            for provider in providers:
                run.providers_attempted.append(provider.provider_id)
                started_at = datetime.now(timezone.utc).isoformat()
                self.dao.mark_provider_started(
                    provider.provider_id,
                    supports_live_sync=provider.supports_live_sync,
                    started_at=started_at,
                )

                if not provider.supports_live_sync:
                    completed_at = datetime.now(timezone.utc).isoformat()
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
                    fetch_result = provider.fetch_delta(cursor, since_ts)
                    snapshot = provider.build_snapshot(fetch_result)
                    provider_metrics = self._process_provider_snapshot(snapshot, run.run_id, fetch_result.metadata)
                    completed_at = datetime.now(timezone.utc).isoformat()
                    next_cursor = dict(fetch_result.next_cursor or snapshot.cursor or {})
                    next_cursor["last_success_at"] = completed_at

                    self.dao.mark_provider_completed(
                        provider.provider_id,
                        supports_live_sync=True,
                        completed_at=completed_at,
                        status="synced",
                        cursor_json=next_cursor,
                        last_snapshot_path=None,
                        mark_success=True,
                    )
                    run.providers_succeeded.append(provider.provider_id)
                    run.metrics_json[provider.provider_id] = provider_metrics
                    any_success = True
                    self._record_integration_result(integration_attempts, provider.provider_id, "success")
                except Exception as exc:
                    completed_at = datetime.now(timezone.utc).isoformat()
                    message = f"{exc.__class__.__name__}: {exc}"
                    errors[provider.provider_id] = message
                    log.error(
                        f"Large context sync failed for provider {provider.provider_id}: "
                        f"{message}\n{traceback.format_exc()}"
                    )
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
            return run
        finally:
            self._run_lock.release()

    def _process_provider_snapshot(
        self,
        snapshot: ProviderSnapshot,
        run_id: str,
        fetch_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        existing_states = self.dao.get_entity_states_for_provider(snapshot.provider_id)
        touched_keys: set[tuple[str, str]] = set()
        generated_at = snapshot.generated_at
        metrics = {
            "fetched_candidates": int(fetch_metadata.get("fetched_candidates") or len(snapshot.entities)),
            "new_entities": 0,
            "changed_entities": 0,
            "unchanged_entities": 0,
            "deleted_entities": 0,
            "active_promoted": 0,
            "active_retained": 0,
            "active_demoted": 0,
            "anomaly_backfill_used": bool(fetch_metadata.get("anomaly_backfill_used")),
        }

        for entity in snapshot.entities:
            key = (entity.entity_type, entity.external_id)
            touched_keys.add(key)
            previous_state = existing_states.get(key)
            normalized = normalize_snapshot_entity(entity, provider_id=snapshot.provider_id)
            fingerprint = fingerprint_normalized_entity(normalized)
            changed = previous_state is None or previous_state.fingerprint != fingerprint
            is_new = previous_state is None

            if is_new:
                metrics["new_entities"] += 1
            elif changed:
                metrics["changed_entities"] += 1
            else:
                metrics["unchanged_entities"] += 1

            state = LargeContextEntityState(
                provider_id=snapshot.provider_id,
                entity_type=entity.entity_type,
                external_id=entity.external_id,
                container_id=entity.container_id,
                title=entity.title,
                source_url=entity.source_url,
                source_updated_at=entity.updated_at,
                first_seen_at=previous_state.first_seen_at if previous_state else generated_at,
                last_seen_at=generated_at,
                last_changed_at=generated_at if changed else (previous_state.last_changed_at if previous_state else generated_at),
                fingerprint=fingerprint,
                normalized_json=normalized,
                durable_node_uuid=previous_state.durable_node_uuid if previous_state else None,
                active_node_uuid=previous_state.active_node_uuid if previous_state else None,
                is_active=previous_state.is_active if previous_state else False,
                active_score=previous_state.active_score if previous_state else 0.0,
                active_reasons=list(previous_state.active_reasons) if previous_state else [],
                last_active_at=previous_state.last_active_at if previous_state else None,
            )

            if changed:
                state.durable_node_uuid = self.projector.upsert_durable_entity(
                    snapshot,
                    entity,
                    run_id=run_id,
                    snapshot_path="",
                )

            active_score, active_reasons = self._score_entity_for_activity(
                entity,
                normalized,
                changed=changed,
            )
            if active_score >= self.ACTIVE_SCORE_THRESHOLD:
                state.last_active_at = generated_at
                state.active_score = active_score
                state.active_reasons = active_reasons
                state.is_active = True
                state.active_node_uuid = self.projector.upsert_active_entity(
                    snapshot,
                    entity,
                    active_score=active_score,
                    active_reasons=active_reasons,
                    promoted_at=generated_at,
                    expires_at=compute_active_expiry(generated_at),
                )
                if previous_state and previous_state.is_active:
                    metrics["active_retained"] += 1
                else:
                    metrics["active_promoted"] += 1
            elif previous_state and previous_state.is_active and not is_active_expired(previous_state.last_active_at):
                state.is_active = True
                state.active_node_uuid = previous_state.active_node_uuid
                state.active_score = previous_state.active_score
                state.active_reasons = list(previous_state.active_reasons)
                state.last_active_at = previous_state.last_active_at
                metrics["active_retained"] += 1
            else:
                if previous_state and previous_state.is_active:
                    self.projector.remove_active_entity(
                        snapshot.provider_id,
                        entity.entity_type,
                        entity.external_id,
                        node_uuid=previous_state.active_node_uuid,
                    )
                    metrics["active_demoted"] += 1
                state.is_active = False
                state.active_node_uuid = None
                state.active_score = 0.0
                state.active_reasons = []

            persisted = self.dao.upsert_entity_state(state)
            existing_states[key] = persisted

        for raw_deleted in snapshot.deleted_entities:
            entity_type, external_id = parse_deleted_entity_key(raw_deleted)
            previous_state = existing_states.get((entity_type, external_id))
            if previous_state is None:
                continue
            self.projector.delete_entity(
                provider_id=snapshot.provider_id,
                entity_type=entity_type,
                external_id=external_id,
                durable_node_uuid=previous_state.durable_node_uuid,
                active_node_uuid=previous_state.active_node_uuid,
            )
            self.dao.delete_entity_state(snapshot.provider_id, entity_type, external_id)
            metrics["deleted_entities"] += 1

        for key, previous_state in existing_states.items():
            if key in touched_keys or not previous_state.is_active:
                continue
            if is_active_expired(previous_state.last_active_at):
                self.projector.remove_active_entity(
                    snapshot.provider_id,
                    previous_state.entity_type,
                    previous_state.external_id,
                    node_uuid=previous_state.active_node_uuid,
                )
                self.dao.mark_entity_inactive(
                    snapshot.provider_id,
                    previous_state.entity_type,
                    previous_state.external_id,
                )
                metrics["active_demoted"] += 1

        return metrics

    def _score_entity_for_activity(
        self,
        entity: SnapshotEntity,
        normalized: dict[str, Any],
        *,
        changed: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        if changed:
            score += 1.0
            reasons.append("changed_this_sync")

        urgency_score, urgency_reasons = self._urgency_score(entity)
        score += urgency_score
        reasons.extend(urgency_reasons)

        if normalized.get("related_entities"):
            score += 0.25
            reasons.append("linked_work")
        if is_recent_iso(entity.updated_at, hours=72):
            score += 0.25
            reasons.append("fresh")

        return score, reasons

    def _urgency_score(self, entity: SnapshotEntity) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0
        extra = entity.extra_fields or {}

        if entity.entity_type == "email_thread":
            labels = {str(label) for label in extra.get("labels", [])}
            participants = [str(person) for person in extra.get("participants", [])]
            account_email = str(extra.get("account_email") or "").lower()
            account_domain = account_email.split("@", 1)[1] if "@" in account_email else ""
            external = any(
                "@" in person and person.lower().split("@", 1)[1] != account_domain
                for person in participants
                if "@" in person and person.lower() != account_email
            )
            if entity.status == "unread" and external:
                score += 1.0
                reasons.append("unread_external_thread")
            if ("IMPORTANT" in labels or "STARRED" in labels) and self._is_aging(entity.updated_at, hours=48):
                score += 1.0
                reasons.append("important_unread_aging")

        if entity.entity_type in {"drive_file", "doc"} and entity.related_entities:
            score += 1.0
            reasons.append("drive_artifact_linked_to_active_work")

        if entity.entity_type == "calendar_event":
            if self._is_upcoming(extra.get("start_at"), within_days=7) and not entity.related_entities:
                score += 1.0
                reasons.append("upcoming_meeting_missing_linked_work")
            if self._is_upcoming(extra.get("start_at"), within_hours=24) and entity.related_entities:
                score += 1.0
                reasons.append("upcoming_meeting_with_linked_work")

        return score, reasons

    def _is_aging(self, value: str | None, *, hours: int) -> bool:
        if not value:
            return False
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - parsed.astimezone(timezone.utc) >= timedelta(hours=hours)

    def _is_upcoming(self, value: str | None, *, within_days: int | None = None, within_hours: int | None = None) -> bool:
        if not value:
            return False
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if parsed < now:
            return False
        if within_hours is not None:
            return parsed <= now + timedelta(hours=within_hours)
        if within_days is not None:
            return parsed <= now + timedelta(days=within_days)
        return False

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
