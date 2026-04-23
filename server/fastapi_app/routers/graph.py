"""
Graph management endpoints.
"""
import asyncio
import json
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from ..dependencies import tree_dependency, get_encrypted_conn, get_db_path

router = APIRouter()


class GraphDataResponse(BaseModel):
    nodes: list
    edges: list
    stats: dict


def _fetch_graph_data_sync():
    """Run all SQLite reads for /graph/data in one blocking call (called via to_thread)."""
    conn = get_encrypted_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT UUID, Metadata, parent_uuid, children_uuid_arr FROM node_table")
    raw_nodes = cursor.fetchall()
    cursor.execute("SELECT UUID, Action_name, Node_UUID FROM action_table")
    raw_actions = cursor.fetchall()
    cursor.execute("SELECT UUID, Node_UUID, key, type, category FROM data_table")
    raw_data = cursor.fetchall()
    conn.close()
    return raw_nodes, raw_actions, raw_data


def _build_graph_payload(raw_nodes, raw_actions, raw_data):
    """Convert raw graph tables into a summarized UI-friendly payload."""
    actions_per_node = defaultdict(list)
    for _action_uuid, action_name, node_uuid in raw_actions:
        if action_name:
            actions_per_node[node_uuid].append(action_name)

    data_per_node = defaultdict(list)
    for _data_uuid, node_uuid, key, dtype, category in raw_data:
        label = (key or "").strip() or (dtype or "").strip() or "Untitled data"
        data_per_node[node_uuid].append({
            "label": label,
            "category": category,
        })

    node_parent = {}
    node_label = {}
    children_map = defaultdict(list)

    for uuid, metadata, parent_uuid, _children_arr in raw_nodes:
        node_parent[uuid] = parent_uuid
        node_label[uuid] = metadata or "Untitled"
        if parent_uuid:
            children_map[parent_uuid].append(uuid)

    def get_depth(uuid):
        depth = 0
        current_uuid = uuid
        seen = set()
        while current_uuid in node_parent and node_parent[current_uuid] is not None:
            parent_uuid = node_parent[current_uuid]
            if parent_uuid in seen:
                break
            seen.add(parent_uuid)
            depth += 1
            current_uuid = parent_uuid
        return depth

    def get_path_labels(uuid):
        path = []
        current_uuid = uuid
        seen = set()
        while current_uuid in node_label and current_uuid not in seen:
            seen.add(current_uuid)
            path.append(node_label[current_uuid])
            parent_uuid = node_parent.get(current_uuid)
            if parent_uuid is None:
                break
            current_uuid = parent_uuid
        path.reverse()
        return path

    nodes = []
    edges = []
    for uuid, metadata, parent_uuid, _children_arr in raw_nodes:
        action_names = actions_per_node.get(uuid, [])
        data_entries = data_per_node.get(uuid, [])
        nodes.append({
            "id": uuid,
            "label": metadata or "Untitled",
            "parent_id": parent_uuid,
            "depth": get_depth(uuid),
            "child_count": len(children_map.get(uuid, [])),
            "action_count": len(action_names),
            "data_count": len(data_entries),
            "action_previews": action_names[:2],
            "data_previews": data_entries[:2],
            "path_labels": get_path_labels(uuid),
        })
        if parent_uuid and parent_uuid in node_parent:
            edges.append({"from": parent_uuid, "to": uuid})

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(raw_nodes),
            "total_actions": len(raw_actions),
            "total_data": len(raw_data),
        },
    }


@router.get("/data")
async def get_graph_data():
    """
    Return summarized graph data for UI visualization.
    """
    try:
        raw_nodes, raw_actions, raw_data = await asyncio.to_thread(_fetch_graph_data_sync)
        return _build_graph_payload(raw_nodes, raw_actions, raw_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_graph(tree=Depends(tree_dependency)):
    """
    Reset the graph by clearing all nodes except root.
    
    WARNING: This is destructive and cannot be undone.
    """
    from graph import Tree

    try:
        try:
            tree.dao.close()
        except Exception:
            pass

        conn = get_encrypted_conn()
        cursor = conn.cursor()
        for table in ["data_table", "action_table", "node_counters", "node_table"]:
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

        # Reinitialize the cached singleton object in place.
        tree.__init__(get_db_path())
        return {"message": "Graph reset successfully"}
    except Exception as e:
        try:
            tree.__init__(get_db_path())
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/cleanup")
async def cleanup_graph(
    threshold: int = 10,
    tree=Depends(tree_dependency)
):
    """
    Trigger cleanup of stale actions in nodes that have high insertion counts.
    """
    from graph import Tree
    import time

    try:
        start_time = time.time()
        tree._ensure_graph_constructed()
        cleaned_nodes = Tree.cleanup_nodes_batch(tree.dao, threshold)
        elapsed = time.time() - start_time
        return {
            "nodes_cleaned": len(cleaned_nodes),
            "node_uuids": cleaned_nodes,
            "elapsed_seconds": round(elapsed, 2),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
