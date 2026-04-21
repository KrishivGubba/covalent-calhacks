"""Manual run selector normalization for large context sync."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from .models import ManualRunRequest


@dataclass(frozen=True)
class ResolvedManualRunSelection:
    provider_ids: Optional[list[str]]
    selection_mode: str


def resolve_manual_run_selection(
    request: ManualRunRequest | None,
    *,
    providers: Iterable,
    integration_dao,
) -> ResolvedManualRunSelection:
    providers = list(providers)
    provider_lookup = {provider.provider_id: provider for provider in providers}
    integration_lookup: dict[str, list[str]] = defaultdict(list)
    for provider in providers:
        if provider.integration_provider_key:
            integration_lookup[provider.integration_provider_key].append(provider.provider_id)

    if request is None:
        return ResolvedManualRunSelection(provider_ids=None, selection_mode="all_registry")

    explicit_modes = sum(
        1
        for enabled in [
            request.mode is not None,
            bool(request.provider_ids),
            bool(request.integration_ids),
            bool(request.providers),
        ]
        if enabled
    )
    if explicit_modes == 0:
        return ResolvedManualRunSelection(provider_ids=None, selection_mode="all_registry")

    if request.providers and (request.provider_ids or request.integration_ids):
        raise ValueError("Use either legacy providers or provider_ids/integration_ids, not both")

    if request.mode == "all_connected_live":
        if request.provider_ids or request.integration_ids or request.providers:
            raise ValueError("mode='all_connected_live' cannot be combined with provider_ids, integration_ids, or providers")
        return ResolvedManualRunSelection(
            provider_ids=_connected_live_provider_ids(providers, integration_dao),
            selection_mode="all_connected_live",
        )

    if request.mode == "providers":
        raw_ids = request.provider_ids or request.providers or []
        if not raw_ids or request.integration_ids:
            raise ValueError("mode='providers' requires provider_ids (or legacy providers) and no integration_ids")
        return ResolvedManualRunSelection(
            provider_ids=_resolve_provider_ids(raw_ids, provider_lookup),
            selection_mode="providers",
        )

    if request.mode == "integrations":
        raw_ids = request.integration_ids
        if not raw_ids or request.provider_ids or request.providers:
            raise ValueError("mode='integrations' requires integration_ids and no provider_ids/providers")
        return ResolvedManualRunSelection(
            provider_ids=_resolve_integration_ids(raw_ids, integration_lookup),
            selection_mode="integrations",
        )

    if request.mode is not None:
        raise ValueError(f"Unsupported manual run mode: {request.mode}")

    if request.provider_ids:
        return ResolvedManualRunSelection(
            provider_ids=_resolve_provider_ids(request.provider_ids, provider_lookup),
            selection_mode="providers",
        )

    if request.integration_ids:
        return ResolvedManualRunSelection(
            provider_ids=_resolve_integration_ids(request.integration_ids, integration_lookup),
            selection_mode="integrations",
        )

    legacy_selectors = request.providers or []
    if not legacy_selectors:
        return ResolvedManualRunSelection(provider_ids=None, selection_mode="all_registry")

    # Backward compatibility for older clients that manually trigger only ["github"]
    # as a proxy for "sync the connected live set". Keep this transition localized
    # here so the engine remains provider-ID only.
    if legacy_selectors == ["github"]:
        return ResolvedManualRunSelection(
            provider_ids=_connected_live_provider_ids(providers, integration_dao),
            selection_mode="legacy_all_connected_live",
        )

    resolved = _resolve_legacy_selectors(
        legacy_selectors,
        provider_lookup=provider_lookup,
        integration_lookup=integration_lookup,
    )
    return ResolvedManualRunSelection(provider_ids=resolved, selection_mode="legacy_selectors")


def _connected_live_provider_ids(providers: Iterable, integration_dao) -> list[str]:
    return [
        provider.provider_id
        for provider in providers
        if provider.supports_live_sync and provider.is_connected(integration_dao)
    ]


def _resolve_provider_ids(raw_ids: list[str], provider_lookup: dict[str, object]) -> list[str]:
    unknown = sorted({raw_id for raw_id in raw_ids if raw_id not in provider_lookup})
    if unknown:
        raise ValueError(f"Unknown providers requested: {', '.join(unknown)}")
    seen: set[str] = set()
    resolved: list[str] = []
    for raw_id in raw_ids:
        if raw_id not in seen:
            resolved.append(raw_id)
            seen.add(raw_id)
    return resolved


def _resolve_integration_ids(raw_ids: list[str], integration_lookup: dict[str, list[str]]) -> list[str]:
    unknown = sorted({raw_id for raw_id in raw_ids if raw_id not in integration_lookup})
    if unknown:
        raise ValueError(f"Unknown integrations requested: {', '.join(unknown)}")
    seen: set[str] = set()
    resolved: list[str] = []
    for raw_id in raw_ids:
        for provider_id in integration_lookup[raw_id]:
            if provider_id not in seen:
                resolved.append(provider_id)
                seen.add(provider_id)
    return resolved


def _resolve_legacy_selectors(
    legacy_selectors: list[str],
    *,
    provider_lookup: dict[str, object],
    integration_lookup: dict[str, list[str]],
) -> list[str]:
    seen: set[str] = set()
    resolved: list[str] = []
    unknown: list[str] = []

    for raw_id in legacy_selectors:
        if raw_id in provider_lookup:
            if raw_id not in seen:
                resolved.append(raw_id)
                seen.add(raw_id)
            continue

        integration_matches = integration_lookup.get(raw_id) or []
        if integration_matches:
            for provider_id in integration_matches:
                if provider_id not in seen:
                    resolved.append(provider_id)
                    seen.add(provider_id)
            continue

        unknown.append(raw_id)

    if unknown:
        raise ValueError(f"Unknown providers requested: {', '.join(sorted(set(unknown)))}")

    return resolved
