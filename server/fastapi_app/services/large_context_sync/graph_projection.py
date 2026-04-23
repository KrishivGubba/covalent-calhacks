"""Graph projection for durable and active large-context entities."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.append(str(_PROJECT_ROOT / "context-engine"))

from graph_dao import GraphDAO  # type: ignore  # noqa: E402

from .entity_state import parse_deleted_entity_key
from .models import ProviderSnapshot, SnapshotContainer, SnapshotEntity


class LargeContextGraphProjector:
    """Projects provider entities into durable and active graph layers."""

    LONG_TERM_ROOT_LABEL = "Long Term Context"
    ACTIVE_ROOT_LABEL = "Active Context"

    def __init__(self, db_path: str, refresh_tree_callback=None):
        self.db_path = db_path
        self._refresh_tree_callback = refresh_tree_callback

    def project_snapshot(self, snapshot: ProviderSnapshot, *, snapshot_path: str, run_id: str) -> None:
        """Compatibility path for full snapshot projection."""
        dao = GraphDAO(self.db_path)
        try:
            for entity in snapshot.entities:
                self._upsert_durable_entity_with_dao(
                    dao,
                    snapshot=snapshot,
                    entity=entity,
                    run_id=run_id,
                    snapshot_path=snapshot_path,
                )

            if snapshot.is_incremental:
                for raw_deleted in snapshot.deleted_entities:
                    entity_type, external_id = parse_deleted_entity_key(raw_deleted)
                    self._delete_entity_with_dao(
                        dao,
                        provider_id=snapshot.provider_id,
                        entity_type=entity_type,
                        external_id=external_id,
                    )
            else:
                existing = self._get_existing_entity_nodes(dao, "large_context_identity", snapshot.provider_id)
                seen = {(entity.entity_type, entity.external_id) for entity in snapshot.entities}
                for entity_key, node_uuid in existing.items():
                    if entity_key not in seen:
                        dao.delete_node(node_uuid, cascade=True)

            self._refresh_tree_if_needed()
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def upsert_durable_entity(
        self,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        *,
        run_id: str,
        snapshot_path: str = "",
    ) -> str:
        dao = GraphDAO(self.db_path)
        try:
            node_uuid = self._upsert_durable_entity_with_dao(
                dao,
                snapshot=snapshot,
                entity=entity,
                run_id=run_id,
                snapshot_path=snapshot_path,
            )
            self._refresh_tree_if_needed()
            return node_uuid
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def upsert_active_entity(
        self,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        *,
        active_score: float,
        active_reasons: list[str],
        promoted_at: str,
        expires_at: Optional[str],
    ) -> str:
        dao = GraphDAO(self.db_path)
        try:
            node_uuid = self._upsert_active_entity_with_dao(
                dao,
                snapshot=snapshot,
                entity=entity,
                active_score=active_score,
                active_reasons=active_reasons,
                promoted_at=promoted_at,
                expires_at=expires_at,
            )
            self._refresh_tree_if_needed()
            return node_uuid
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def remove_active_entity(self, provider_id: str, entity_type: str, external_id: str, *, node_uuid: Optional[str] = None) -> None:
        dao = GraphDAO(self.db_path)
        try:
            target_uuid = node_uuid or self._get_existing_entity_node(
                dao,
                "active_context_identity",
                provider_id,
                entity_type,
                external_id,
            )
            if target_uuid:
                dao.delete_node(target_uuid, cascade=True)
            self._refresh_tree_if_needed()
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def delete_entity(
        self,
        *,
        provider_id: str,
        entity_type: str,
        external_id: str,
        durable_node_uuid: Optional[str] = None,
        active_node_uuid: Optional[str] = None,
    ) -> None:
        dao = GraphDAO(self.db_path)
        try:
            self._delete_entity_with_dao(
                dao,
                provider_id=provider_id,
                entity_type=entity_type,
                external_id=external_id,
                durable_node_uuid=durable_node_uuid,
                active_node_uuid=active_node_uuid,
            )
            self._refresh_tree_if_needed()
        finally:
            try:
                dao.conn.close()
            except Exception:
                pass

    def _delete_entity_with_dao(
        self,
        dao: GraphDAO,
        *,
        provider_id: str,
        entity_type: str,
        external_id: str,
        durable_node_uuid: Optional[str] = None,
        active_node_uuid: Optional[str] = None,
    ) -> None:
        target_durable = durable_node_uuid or self._get_existing_entity_node(
            dao,
            "large_context_identity",
            provider_id,
            entity_type,
            external_id,
        )
        target_active = active_node_uuid or self._get_existing_entity_node(
            dao,
            "active_context_identity",
            provider_id,
            entity_type,
            external_id,
        )
        if target_active:
            dao.delete_node(target_active, cascade=True)
        if target_durable:
            dao.delete_node(target_durable, cascade=True)

    def _upsert_durable_entity_with_dao(
        self,
        dao: GraphDAO,
        *,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        run_id: str,
        snapshot_path: str,
    ) -> str:
        graph_root_uuid = self._ensure_graph_root(dao)
        long_term_root_uuid = self._ensure_child_node(dao, graph_root_uuid, self.LONG_TERM_ROOT_LABEL)
        provider_uuid = self._ensure_child_node(dao, long_term_root_uuid, snapshot.provider_display_name)
        container_uuid = self._ensure_container_node(
            dao,
            snapshot=snapshot,
            provider_uuid=provider_uuid,
            container_id=entity.container_id,
        )

        existing_uuid = self._get_existing_entity_node(
            dao,
            "large_context_identity",
            snapshot.provider_id,
            entity.entity_type,
            entity.external_id,
        )
        metadata = self._durable_metadata(entity)
        if existing_uuid is None:
            existing_uuid = dao.create_node(metadata, parent_uuid=container_uuid)
            dao.add_child_to_node(container_uuid, existing_uuid)
        else:
            current_node = dao.get_node_by_id(existing_uuid)
            if current_node and current_node[4] != container_uuid:
                dao.update_node_parent(existing_uuid, container_uuid)
            dao.update_node_metadata(existing_uuid, metadata)

        self._replace_category_prefix(dao, existing_uuid, "large_context_")
        self._write_durable_entity_data(
            dao,
            node_uuid=existing_uuid,
            snapshot=snapshot,
            entity=entity,
            run_id=run_id,
            snapshot_path=snapshot_path,
        )
        return existing_uuid

    def _upsert_active_entity_with_dao(
        self,
        dao: GraphDAO,
        *,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        active_score: float,
        active_reasons: list[str],
        promoted_at: str,
        expires_at: Optional[str],
    ) -> str:
        graph_root_uuid = self._ensure_graph_root(dao)
        active_root_uuid = self._ensure_child_node(dao, graph_root_uuid, self.ACTIVE_ROOT_LABEL)
        provider_uuid = self._ensure_child_node(dao, active_root_uuid, snapshot.provider_display_name)
        existing_uuid = self._get_existing_entity_node(
            dao,
            "active_context_identity",
            snapshot.provider_id,
            entity.entity_type,
            entity.external_id,
        )
        metadata = self._active_metadata(entity)
        if existing_uuid is None:
            existing_uuid = dao.create_node(metadata, parent_uuid=provider_uuid)
            dao.add_child_to_node(provider_uuid, existing_uuid)
        else:
            current_node = dao.get_node_by_id(existing_uuid)
            if current_node and current_node[4] != provider_uuid:
                dao.update_node_parent(existing_uuid, provider_uuid)
            dao.update_node_metadata(existing_uuid, metadata)

        self._replace_category_prefix(dao, existing_uuid, "active_context_")
        self._write_active_entity_data(
            dao,
            node_uuid=existing_uuid,
            snapshot=snapshot,
            entity=entity,
            active_score=active_score,
            active_reasons=active_reasons,
            promoted_at=promoted_at,
            expires_at=expires_at,
        )
        return existing_uuid

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

    def _ensure_container_node(
        self,
        dao: GraphDAO,
        *,
        snapshot: ProviderSnapshot,
        provider_uuid: str,
        container_id: str,
    ) -> str:
        containers = {container.container_id: container for container in snapshot.containers}
        container = containers.get(container_id)
        if container is None:
            return provider_uuid

        parent_uuid = provider_uuid
        if container.parent_id:
            parent_uuid = self._ensure_container_node(
                dao,
                snapshot=snapshot,
                provider_uuid=provider_uuid,
                container_id=container.parent_id,
            )
        return self._ensure_child_node(dao, parent_uuid, container.title)

    def _get_existing_entity_nodes(
        self,
        dao: GraphDAO,
        identity_category: str,
        provider_id: str,
    ) -> Dict[Tuple[str, str], str]:
        rows = dao.execute_query(
            f"""
            SELECT provider_data.Node_UUID, entity_data.info, external_data.info
            FROM data_table AS provider_data
            JOIN data_table AS entity_data ON provider_data.Node_UUID = entity_data.Node_UUID
            JOIN data_table AS external_data ON provider_data.Node_UUID = external_data.Node_UUID
            WHERE provider_data.category = ?
              AND provider_data.key = 'provider'
              AND provider_data.info = ?
              AND entity_data.category = ?
              AND entity_data.key = 'entity_type'
              AND external_data.category = ?
              AND external_data.key = 'external_id'
            """,
            (identity_category, provider_id, identity_category, identity_category),
        )
        return {(row[1], row[2]): row[0] for row in rows}

    def _get_existing_entity_node(
        self,
        dao: GraphDAO,
        identity_category: str,
        provider_id: str,
        entity_type: str,
        external_id: str,
    ) -> Optional[str]:
        rows = dao.execute_query(
            f"""
            SELECT provider_data.Node_UUID
            FROM data_table AS provider_data
            JOIN data_table AS entity_data ON provider_data.Node_UUID = entity_data.Node_UUID
            JOIN data_table AS external_data ON provider_data.Node_UUID = external_data.Node_UUID
            WHERE provider_data.category = ?
              AND provider_data.key = 'provider'
              AND provider_data.info = ?
              AND entity_data.category = ?
              AND entity_data.key = 'entity_type'
              AND entity_data.info = ?
              AND external_data.category = ?
              AND external_data.key = 'external_id'
              AND external_data.info = ?
            LIMIT 1
            """,
            (
                identity_category,
                provider_id,
                identity_category,
                entity_type,
                identity_category,
                external_id,
            ),
        )
        if not rows:
            return None
        return rows[0][0]

    def _replace_category_prefix(self, dao: GraphDAO, node_uuid: str, prefix: str) -> None:
        dao.execute_write(
            "DELETE FROM data_table WHERE Node_UUID = ? AND category LIKE ?",
            (node_uuid, f"{prefix}%"),
        )

    def _write_durable_entity_data(
        self,
        dao: GraphDAO,
        *,
        node_uuid: str,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        run_id: str,
        snapshot_path: str,
    ) -> None:
        for key, value in {
            "provider": snapshot.provider_id,
            "entity_type": entity.entity_type,
            "external_id": entity.external_id,
            "container_id": entity.container_id,
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_identity")

        for key, value in {
            "title": entity.title,
            "summary": entity.summary,
            "status": entity.status,
            "project": entity.project or "",
            "feature_tags_json": json.dumps(list(entity.feature_tags)),
            "updated_at": entity.updated_at or "",
            "source_url": entity.source_url or "",
            "extra_fields_json": json.dumps(entity.extra_fields),
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_summary")

        dao.add_data(node_uuid, "people_json", "json", json.dumps(list(entity.people)), "large_context_people")
        dao.add_data(
            node_uuid,
            "related_entities_json",
            "json",
            json.dumps(list(entity.related_entities)),
            "large_context_links",
        )
        for key, value in {
            "snapshot_file": snapshot_path,
            "last_synced_at": snapshot.generated_at,
            "run_id": run_id,
        }.items():
            dao.add_data(node_uuid, key, "text", value, "large_context_sync")

    def _write_active_entity_data(
        self,
        dao: GraphDAO,
        *,
        node_uuid: str,
        snapshot: ProviderSnapshot,
        entity: SnapshotEntity,
        active_score: float,
        active_reasons: list[str],
        promoted_at: str,
        expires_at: Optional[str],
    ) -> None:
        for key, value in {
            "provider": snapshot.provider_id,
            "entity_type": entity.entity_type,
            "external_id": entity.external_id,
            "container_id": entity.container_id,
        }.items():
            dao.add_data(node_uuid, key, "text", value, "active_context_identity")

        for key, value in {
            "title": entity.title,
            "summary": entity.summary,
            "project": entity.project or "",
            "updated_at": entity.updated_at or "",
            "source_url": entity.source_url or "",
        }.items():
            dao.add_data(node_uuid, key, "text", value, "active_context_summary")

        for key, value in {
            "active_score": str(active_score),
            "active_reasons_json": json.dumps(active_reasons),
            "promoted_at": promoted_at,
            "expires_at": expires_at or "",
        }.items():
            dao.add_data(node_uuid, key, "text", value, "active_context_reasoning")

    def _durable_metadata(self, entity: SnapshotEntity) -> str:
        project = f" [{entity.project}]" if entity.project else ""
        return f"{entity.title or entity.external_id}{project} ({entity.entity_type})"

    def _active_metadata(self, entity: SnapshotEntity) -> str:
        project = f" [{entity.project}]" if entity.project else ""
        return f"ACTIVE: {entity.title or entity.external_id}{project}"

    def _refresh_tree_if_needed(self) -> None:
        if self._refresh_tree_callback:
            self._refresh_tree_callback()
