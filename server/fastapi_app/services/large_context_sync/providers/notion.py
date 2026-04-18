"""Notion large-context provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from covalent_mcp.toolclasses.notion.notion import _get_notion_token
from covalent_mcp.toolclasses.notion.notion_client import NotionClient

from ..models import (
    ProviderFetchResult,
    ProviderSnapshot,
    SnapshotContainer,
    SnapshotEntity,
    SnapshotPerson,
)
from .base import LargeContextProvider


class NotionLargeContextProvider(LargeContextProvider):
    provider_id = "notion"
    display_name = "Notion"
    supports_live_sync = True
    file_name = "notion.md"
    integration_provider_key = "notion"

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        token = _get_notion_token()
        if not token:
            raise RuntimeError("Notion integration is not connected")
        client = NotionClient(token)
        search_results = client.search(query="", sort_direction="descending", page_size=20)
        records = []
        for result in search_results.get("results", []):
            if result.get("object") == "database":
                database_id = result.get("id")
                items = client.query_database(database_id, page_size=10).get("results", [])
                records.append({"type": "database", "object": result, "items": items})
            else:
                records.append({"type": "page", "object": result})
        return ProviderFetchResult(
            records=records,
            next_cursor={"since": datetime.now(timezone.utc).isoformat()},
            metadata={"backfill_since": (cursor or {}).get("since") or since_ts},
        )

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        people_map: Dict[str, SnapshotPerson] = {}
        containers = [SnapshotContainer(container_type="workspace", container_id="notion:workspace", title="Notion Workspace")]
        entities: list[SnapshotEntity] = []

        for record in fetch_result.records:
            item = record["object"]
            item_id = item.get("id")
            title = self._extract_title(item)
            last_editor = ((item.get("last_edited_by") or {}).get("id") or "")
            parent = item.get("parent") or {}
            parent_id = parent.get("database_id") or parent.get("page_id") or "notion:workspace"
            container_id = parent_id if parent_id != "notion:workspace" else "notion:workspace"

            if container_id != "notion:workspace":
                containers.append(
                    SnapshotContainer(
                        container_type="parent",
                        container_id=container_id,
                        title=parent.get("type", "parent"),
                        parent_id="notion:workspace",
                    )
                )

            if record["type"] == "database":
                database_title = title or item_id or "Database"
                database_container_id = f"database:{item_id}"
                containers.append(
                    SnapshotContainer(
                        container_type="database",
                        container_id=database_container_id,
                        title=database_title,
                        parent_id="notion:workspace",
                    )
                )
                for database_item in record.get("items", []):
                    entity_id = database_item.get("id")
                    item_title = self._extract_title(database_item)
                    people = [last_editor] if last_editor else []
                    entities.append(
                        SnapshotEntity(
                            entity_type="database_item",
                            external_id=f"notion:{entity_id}",
                            title=item_title or entity_id or "Database Item",
                            status=self._extract_status(database_item),
                            summary=item_title or "Notion database item",
                            project=database_title,
                            feature_tags=[],
                            people=people,
                            related_entities=[],
                            updated_at=database_item.get("last_edited_time"),
                            source_url=database_item.get("url"),
                            container_id=database_container_id,
                            extra_fields={
                                "page_id": entity_id,
                                "owner": "",
                                "last_editor": last_editor,
                                "database": database_title,
                                "status_field": self._extract_status(database_item),
                                "linked_github_ids": [],
                                "linked_jira_ids": [],
                            },
                        )
                    )
                    self._upsert_person(people_map, last_editor, f"notion:{entity_id}")
            else:
                entities.append(
                    SnapshotEntity(
                        entity_type="page",
                        external_id=f"notion:{item_id}",
                        title=title or item_id or "Notion Page",
                        status="active",
                        summary=title or "Notion page",
                        project=parent.get("type") or "notion",
                        feature_tags=[],
                        people=[last_editor] if last_editor else [],
                        related_entities=[],
                        updated_at=item.get("last_edited_time"),
                        source_url=item.get("url"),
                        container_id=container_id,
                        extra_fields={
                            "page_id": item_id,
                            "owner": "",
                            "last_editor": last_editor,
                            "database": "",
                            "status_field": "",
                            "linked_github_ids": [],
                            "linked_jira_ids": [],
                        },
                    )
                )
                self._upsert_person(people_map, last_editor, f"notion:{item_id}")

        unique_containers = {(container.container_type, container.container_id): container for container in containers}
        return ProviderSnapshot(
            provider_id=self.provider_id,
            provider_display_name=self.display_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cursor=fetch_result.next_cursor,
            metadata=fetch_result.metadata,
            containers=list(unique_containers.values()),
            entities=entities,
            relevant_people=sorted(people_map.values(), key=lambda person: person.display_name.lower()),
        )

    def _extract_title(self, obj: dict) -> str:
        title_items = obj.get("title")
        if isinstance(title_items, list) and title_items:
            return "".join(item.get("plain_text", "") for item in title_items).strip()

        properties = obj.get("properties") or {}
        for value in properties.values():
            title_prop = value.get("title")
            if isinstance(title_prop, list) and title_prop:
                return "".join(item.get("plain_text", "") for item in title_prop).strip()

        return ""

    def _extract_status(self, obj: dict) -> str:
        properties = obj.get("properties") or {}
        for value in properties.values():
            status = value.get("status")
            if isinstance(status, dict) and status.get("name"):
                return status["name"]
            select = value.get("select")
            if isinstance(select, dict) and select.get("name"):
                return select["name"]
        return "active"

    def _upsert_person(self, people_map: Dict[str, SnapshotPerson], identifier: str, related_entity: str) -> None:
        if not identifier:
            return
        person = people_map.get(identifier)
        if person is None:
            person = SnapshotPerson(identifier=identifier, display_name=identifier, role="notion_user", related_entities=[])
            people_map[identifier] = person
        if related_entity not in person.related_entities:
            person.related_entities.append(related_entity)
