"""Filesystem storage for large context markdown snapshots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .models import ProviderSnapshot, SnapshotCrossLink, SnapshotEntity, SnapshotPerson


class LargeContextSnapshotStorage:
    """Writes provider snapshots as structured markdown files."""

    def __init__(self, default_root: str):
        self.default_root = default_root

    def resolve_root(self, markdown_root: Optional[str] = None) -> str:
        root = markdown_root or self.default_root
        os.makedirs(root, exist_ok=True)
        return root

    def write_snapshot(self, snapshot: ProviderSnapshot, file_name: str, markdown_root: Optional[str] = None) -> str:
        root = self.resolve_root(markdown_root)
        path = Path(root) / file_name
        temp_path = path.with_suffix(path.suffix + ".tmp")
        content = self.render_snapshot(snapshot)
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)
        return str(path)

    def render_snapshot(self, snapshot: ProviderSnapshot) -> str:
        lines: list[str] = [f"# {snapshot.provider_display_name} Context Snapshot", ""]
        lines.extend(self._render_mapping_section("Sync Metadata", {
            "provider_id": snapshot.provider_id,
            "generated_at": snapshot.generated_at,
            "cursor": snapshot.cursor or {},
            **snapshot.metadata,
        }))
        lines.extend(self._render_containers(snapshot))
        lines.extend(self._render_entities(snapshot))
        lines.extend(self._render_people(snapshot.relevant_people))
        lines.extend(self._render_cross_links(snapshot.cross_links))
        lines.extend(self._render_string_list_section("Open Questions / Watch Items", [
            *snapshot.open_questions,
            *snapshot.watch_items,
        ]))
        return "\n".join(lines).rstrip() + "\n"

    def _render_containers(self, snapshot: ProviderSnapshot) -> list[str]:
        lines = ["## Containers"]
        if not snapshot.containers:
            lines.extend(["- none", ""])
            return lines
        for container in snapshot.containers:
            lines.append(f"### {container.container_type}: {container.title}")
            lines.extend(self._render_mapping({
                "container_type": container.container_type,
                "container_id": container.container_id,
                "title": container.title,
                "summary": container.summary,
                "parent_id": container.parent_id,
                "source_url": container.source_url,
            }))
            lines.append("")
        return lines

    def _render_entities(self, snapshot: ProviderSnapshot) -> list[str]:
        lines = ["## Active Entities"]
        if not snapshot.entities:
            lines.extend(["- none", ""])
            return lines
        for entity in snapshot.entities:
            lines.append(f"### {entity.entity_type}: {entity.title}")
            ordered = {
                "entity_type": entity.entity_type,
                "external_id": entity.external_id,
                "title": entity.title,
                "status": entity.status,
                "summary": entity.summary,
                "project": entity.project,
                "feature_tags": entity.feature_tags,
                "people": entity.people,
                "related_entities": entity.related_entities,
                "updated_at": entity.updated_at,
                "source_url": entity.source_url,
            }
            ordered.update(entity.extra_fields)
            lines.extend(self._render_mapping(ordered))
            lines.append("")
        return lines

    def _render_people(self, people: Iterable[SnapshotPerson]) -> list[str]:
        people = list(people)
        lines = ["## Relevant People"]
        if not people:
            lines.extend(["- none", ""])
            return lines
        for person in people:
            lines.append(f"### {person.display_name}")
            lines.extend(self._render_mapping({
                "identifier": person.identifier,
                "display_name": person.display_name,
                "role": person.role,
                "related_entities": person.related_entities,
            }))
            lines.append("")
        return lines

    def _render_cross_links(self, links: Iterable[SnapshotCrossLink]) -> list[str]:
        links = list(links)
        lines = ["## Cross-Links"]
        if not links:
            lines.extend(["- none", ""])
            return lines
        for link in links:
            lines.append(f"### {link.source_entity_id} -> {link.target_entity_id}")
            lines.extend(self._render_mapping({
                "source_entity_id": link.source_entity_id,
                "target_entity_id": link.target_entity_id,
                "relationship": link.relationship,
                "note": link.note,
            }))
            lines.append("")
        return lines

    def _render_mapping_section(self, title: str, values: Dict[str, Any]) -> list[str]:
        return [f"## {title}", *self._render_mapping(values), ""]

    def _render_string_list_section(self, title: str, values: Iterable[str]) -> list[str]:
        values = [value for value in values if value]
        lines = [f"## {title}"]
        if not values:
            lines.extend(["- none", ""])
            return lines
        for value in values:
            lines.append(f"- {value}")
        lines.append("")
        return lines

    def _render_mapping(self, values: Dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for key, value in values.items():
            if value is None:
                continue
            rendered = self._render_value(value)
            lines.append(f"- {key}: {rendered}")
        if not lines:
            lines.append("- {}")
        return lines

    def _render_value(self, value: Any) -> str:
        if isinstance(value, dict):
            return "{ " + ", ".join(f"{key}: {self._render_value(item)}" for key, item in value.items()) + " }"
        if isinstance(value, list):
            return "[" + ", ".join(self._render_value(item) for item in value) + "]"
        return str(value)
