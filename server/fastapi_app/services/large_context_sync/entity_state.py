"""Helpers for normalized large-context entity state comparison."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import SnapshotEntity


ACTIVE_TTL_HOURS = 72


def normalize_snapshot_entity(entity: SnapshotEntity, *, provider_id: str) -> dict[str, Any]:
    """Convert a snapshot entity into a canonical dict for hashing and retrieval."""
    canonical_extra = {
        key: _canonicalize_value(value)
        for key, value in sorted(entity.extra_fields.items())
    }
    return {
        "provider_id": provider_id,
        "entity_type": entity.entity_type,
        "external_id": entity.external_id,
        "container_id": entity.container_id,
        "title": (entity.title or "").strip(),
        "summary": (entity.summary or "").strip(),
        "status": (entity.status or "").strip(),
        "project": (entity.project or "").strip(),
        "feature_tags": sorted(_stable_strings(entity.feature_tags)),
        "people": sorted(_stable_strings(entity.people)),
        "related_entities": sorted(_stable_strings(entity.related_entities)),
        "updated_at": entity.updated_at or "",
        "source_url": entity.source_url or "",
        "extra_fields": canonical_extra,
    }


def fingerprint_normalized_entity(normalized: dict[str, Any]) -> str:
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_deleted_entity_key(raw_value: str) -> tuple[str, str]:
    entity_type, _, external_id = raw_value.partition("|")
    if not entity_type or not external_id:
        raise ValueError(f"Invalid deleted entity key: {raw_value}")
    return entity_type, external_id


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_recent_iso(value: str | None, *, hours: int = 24) -> bool:
    if not value:
        return False
    try:
        parsed = _parse_iso(value)
    except ValueError:
        return False
    return parsed >= datetime.now(timezone.utc) - timedelta(hours=hours)


def compute_active_expiry(last_active_at: str | None) -> str | None:
    if not last_active_at:
        return None
    try:
        return (_parse_iso(last_active_at) + timedelta(hours=ACTIVE_TTL_HOURS)).isoformat()
    except ValueError:
        return None


def is_active_expired(last_active_at: str | None, *, now: datetime | None = None) -> bool:
    if not last_active_at:
        return True
    current_time = now or datetime.now(timezone.utc)
    try:
        active_at = _parse_iso(last_active_at)
    except ValueError:
        return True
    return active_at + timedelta(hours=ACTIVE_TTL_HOURS) <= current_time


def _stable_strings(values: list[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_value(item) for item in value]
    if value is None:
        return ""
    return value


def _parse_iso(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
