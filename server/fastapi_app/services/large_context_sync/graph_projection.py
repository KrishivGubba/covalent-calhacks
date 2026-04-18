"""Graph projection for provider-owned large context subtrees."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.append(str(_PROJECT_ROOT / "context-engine"))

from graph_dao import GraphDAO  # type: ignore  # noqa: E402

from .models import ProviderSnapshot


class LargeContextGraphProjector:
    """Projects normalized provider snapshots into a dedicated graph subtree."""

    ROOT_NODE_LABEL = "Long Term Context"

    def __init__(self, db_path: str, refresh_tree_callback=None):
        self.db_path = db_path
        self._refresh_tree_callback = refresh_tree_callback

    def project_snapshot(self, snapshot: ProviderSnapshot, *, snapshot_path: str, run_id: str) -> None:
        dao = GraphDAO(self.db_path)
        try:
            graph_root_uuid = self._ensure_graph_root(dao)
            long_term_root_uuid = self._ensure_child_node(dao, graph_root_uuid, self.ROOT_NODE_LABEL)
            provider_uuid = self._ensure_child_node(dao, long_term_root_uuid, snapshot.provider_display_name)

            container_nodes: Dict[str, str] = {}
            for container in snapshot.containers:
                parent_uuid = provider_uuid
                if container.parent_id and container.parent_id in container_nodes:
                    parent_uuid = container_nodes[container.parent_id]
                container_nodes[container.container_id] = self._ensure_child_node(
                    dao,
                    parent_uuid,
                    container.title,
                )

            existing_entities = self._get_existing_entity_nodes(dao, snapshot.provider_id)
            seen_entity_keys: Set[Tuple[str, str]] = set()

            for entity in snapshot.entities:
                entity_key = (entity.entity_type, entity.external_id)
                seen_entity_keys.add(entity_key)
                container_uuid = container_nodes.get(entity.container_id, provider_uuid)
                node_uuid = existing_entities.get(entity_key)
                metadata = f"[{snapshot.provider_id}/{entity.entity_type}] {entity.external_id} - {entity.title}"
                if node_uuid is None:
                    node_uuid = dao.create_node(metadata, parent_uuid=container_uuid)
                    dao.add_child_to_node(container_uuid, node_uuid)
                else:
                    current_node = dao.get_node_by_id(node_uuid)
                    if current_node and current_node[4] != container_uuid:
                        dao.update_node_parent(node_uuid, container_uuid)
                    dao.update_node_metadata(node_uuid, metadata)

                self._replace_large_context_data(
                    dao,
                    node_uuid,
                    snapshot=snapshot,
                    entity_type=entity.entity_type,
                    external_id=entity.external_id,
                    container_id=entity.container_id,
                    title=entity.title,
                    summary=entity.summary,
                    status=entity.status,
                    project=entity.project,
                    feature_tags=entity.feature_tags,
                    people=entity.people,
                    related_entities=entity.related_entities,
                    updated_at=entity.updated_at,
                    source_url=entity.source_url,
                    snapshot_path=snapshot_path,
                    run_id=run_id,
                )

            for entity_key, node_uuid in existing_entities.items():
                if entity_key not in seen_entity_keys:
                    dao.delete_node(node_uuid, cascade=True)

            if self._refresh_tree_callback:
                self._refresh_tree_callback()
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def _ensure_graph_root(self, dao: GraphDAO) -> str:
        rows = dao.execute_query(
            """
            SELECT UUID
            FROM node_table
            WHERE parent_uuid IS NULL
            ORDER BY created ASC
            LIMIT 1
            """
        )
        if rows:
            return rows[0][0]
        return dao.create_node("Root", parent_uuid=None)

    def _ensure_child_node(self, dao: GraphDAO, parent_uuid: str, metadata: str) -> str:
        parent = dao.get_node_by_id(parent_uuid)
        if parent:
            try:
                child_ids = json.loads(parent[5]) if parent[5] else []
            except json.JSONDecodeError:
                child_ids = []
            for child_id in child_ids:
                child = dao.get_node_by_id(child_id)
                if child and child[1] == metadata:
                    return child[0]

        node_uuid = dao.create_node(metadata, parent_uuid=parent_uuid)
        dao.add_child_to_node(parent_uuid, node_uuid)
        return node_uuid

    def _get_existing_entity_nodes(self, dao: GraphDAO, provider_id: str) -> Dict[Tuple[str, str], str]:
        rows = dao.execute_query(
            """
            SELECT provider_data.Node_UUID, entity_data.info, external_data.info
            FROM data_table AS provider_data
            JOIN data_table AS entity_data ON provider_data.Node_UUID = entity_data.Node_UUID
            JOIN data_table AS external_data ON provider_data.Node_UUID = external_data.Node_UUID
            WHERE provider_data.category = 'large_context_identity'
              AND provider_data.key = 'provider'
              AND provider_data.info = ?
              AND entity_data.category = 'large_context_identity'
              AND entity_data.key = 'entity_type'
              AND external_data.category = 'large_context_identity'
              AND external_data.key = 'external_id'
            """,
            (provider_id,),
        )
        return {(row[1], row[2]): row[0] for row in rows}

    def _replace_large_context_data(
        self,
        dao: GraphDAO,
        node_uuid: str,
        *,
        snapshot: ProviderSnapshot,
        entity_type: str,
        external_id: str,
        container_id: str,
        title: str,
        summary: str,
        status: str,
        project: Optional[str],
        feature_tags: Iterable[str],
        people: Iterable[str],
        related_entities: Iterable[str],
        updated_at: Optional[str],
        source_url: Optional[str],
        snapshot_path: str,
        run_id: str,
    ) -> None:
        dao.execute_write(
            "DELETE FROM data_table WHERE Node_UUID = ? AND category LIKE 'large_context_%'",
            (node_uuid,),
        )

        for key, value in {
            "provider": snapshot.provider_id,
            "entity_type": entity_type,
            "external_id": external_id,
            "container_id": container_id,
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_identity")

        for key, value in {
            "title": title,
            "summary": summary,
            "status": status,
            "project": project or "",
            "feature_tags_json": json.dumps(list(feature_tags)),
            "updated_at": updated_at or "",
            "source_url": source_url or "",
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_summary")

        dao.add_data(node_uuid, "people_json", "json", json.dumps(list(people)), "large_context_people")
        dao.add_data(node_uuid, "related_entities_json", "json", json.dumps(list(related_entities)), "large_context_links")
        for key, value in {
            "snapshot_file": snapshot_path,
            "last_synced_at": snapshot.generated_at,
            "run_id": run_id,
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_sync")
