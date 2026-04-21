"""Helpers for grouping large-context providers by integration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional


def build_live_integration_provider_map(providers: Iterable) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for provider in providers:
        integration_id = getattr(provider, "integration_provider_key", None)
        if not integration_id or not getattr(provider, "supports_live_sync", False):
            continue
        grouped[integration_id].append(provider.provider_id)
    return dict(grouped)


def parse_iso_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compute_next_run_at(
    last_completed_at: str | None,
    interval_minutes: int,
    *,
    now: Optional[datetime] = None,
) -> datetime:
    current_time = now or datetime.now(timezone.utc)
    last_completed = parse_iso_datetime(last_completed_at)
    if last_completed is None:
        return current_time + timedelta(minutes=max(interval_minutes, 30))
    return last_completed.astimezone(timezone.utc) + timedelta(minutes=max(interval_minutes, 30))
