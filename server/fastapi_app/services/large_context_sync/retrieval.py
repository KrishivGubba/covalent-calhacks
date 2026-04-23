"""Active-context retrieval helpers."""

from __future__ import annotations

import re
from typing import Any

from .dao import LargeContextSyncDAO
from .models import LargeContextEntityState


class ActiveContextRetriever:
    """Ranks active large-context entities for the current query."""

    def __init__(self, dao: LargeContextSyncDAO):
        self.dao = dao

    def get_active_context(self, query_text: str, limit: int = 10) -> list[dict[str, Any]]:
        candidates = self.dao.list_active_entities(limit=max(limit * 3, limit))
        if not candidates:
            return []

        query_terms = self._terms(query_text)
        ranked = sorted(
            (
                (
                    self._rank_candidate(candidate, query_terms),
                    candidate,
                )
                for candidate in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        results: list[dict[str, Any]] = []
        for score, candidate in ranked[:limit]:
            normalized = candidate.normalized_json
            results.append(
                {
                    "provider_id": candidate.provider_id,
                    "entity_type": candidate.entity_type,
                    "external_id": candidate.external_id,
                    "title": candidate.title or normalized.get("title") or candidate.external_id,
                    "project": normalized.get("project") or "",
                    "summary": normalized.get("summary") or "",
                    "why_active": list(candidate.active_reasons),
                    "freshness": candidate.source_updated_at or candidate.last_active_at or candidate.last_seen_at,
                    "source_url": candidate.source_url,
                    "related_entities": normalized.get("related_entities") or [],
                    "people": normalized.get("people") or [],
                    "score": score,
                }
            )
        return results

    def _rank_candidate(self, candidate: LargeContextEntityState, query_terms: set[str]) -> float:
        score = float(candidate.active_score)
        if not query_terms:
            return score

        haystack = " ".join(
            [
                candidate.title or "",
                candidate.entity_type,
                str(candidate.normalized_json.get("summary") or ""),
                str(candidate.normalized_json.get("project") or ""),
                " ".join(candidate.normalized_json.get("people") or []),
                " ".join(candidate.normalized_json.get("related_entities") or []),
            ]
        )
        overlap = len(query_terms & self._terms(haystack))
        return score + (overlap * 0.5)

    def _terms(self, value: str) -> set[str]:
        return {token for token in re.split(r"[^a-zA-Z0-9_#:/.-]+", value.lower()) if token}
