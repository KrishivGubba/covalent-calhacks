"""
Graph management endpoints.
"""
import json
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..dependencies import tree_dependency, get_encrypted_conn

router = APIRouter()


class GraphDataResponse(BaseModel):
    nodes: list
    edges: list
    stats: dict


@router.get("/data")
async def get_graph_data():
    """
    Return full graph data (nodes, edges, actions, data entries) for UI visualization.
    """
    try:
        conn = get_encrypted_conn()
        cursor = conn.cursor()
        
        # Get all nodes
        cursor.execute("SELECT UUID, Metadata, parent_uuid, children_uuid_arr FROM node_table")
        raw_nodes = cursor.fetchall()
        
        # Get all actions
        cursor.execute("SELECT UUID, Action_name, Node_UUID FROM action_table")
        raw_actions = cursor.fetchall()
        
        # Get all data entries
        cursor.execute("SELECT UUID, Node_UUID, key, type, category FROM data_table")
        raw_data = cursor.fetchall()
        
        conn.close()
        
        # Build actions-per-node lookup
        actions_per_node = defaultdict(list)
        for action_uuid, action_name, node_uuid in raw_actions:
            actions_per_node[node_uuid].append({"uuid": action_uuid, "name": action_name})
        
        # Build data-per-node lookup
        data_per_node = defaultdict(list)
        for data_uuid, node_uuid, key, dtype, category in raw_data:
            data_per_node[node_uuid].append({
                "uuid": data_uuid,
                "key": key,
                "type": dtype,
                "category": category,
            })
        
        # Build depth lookup
        node_parent = {}
        for uuid, metadata, parent_uuid, children_arr in raw_nodes:
            node_parent[uuid] = parent_uuid
        
        def get_depth(uuid, depth=0):
            parent = node_parent.get(uuid)
            if parent is None:
                return depth
            return get_depth(parent, depth + 1)
        
        # Build node list and edge list
        nodes = []
        edges = []
        for uuid, metadata, parent_uuid, children_arr in raw_nodes:
            depth = get_depth(uuid)
            nodes.append({
                "id": uuid,
                "label": metadata or "Untitled",
                "parent_id": parent_uuid,
                "depth": depth,
                "actions": actions_per_node.get(uuid, []),
                "data": data_per_node.get(uuid, []),
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
    tree._ensure_graph_constructed()
    
    if not tree.root:
        return {"status": "error", "message": "No graph to reset"}
    
    root_uuid = tree.root.node_uuid
    deleted_count = 0
    
    for node_uuid in list(tree.nodes.keys()):
        if node_uuid != root_uuid:
            try:
                tree.dao.delete_node(node_uuid, cascade=True)
                if node_uuid in tree.nodes:
                    del tree.nodes[node_uuid]
                deleted_count += 1
            except Exception:
                pass
    
    tree.root.children = []
    tree.root.children_uuid_arr = []
    
    return {
        "status": "success",
        "message": f"Reset graph. Deleted {deleted_count} nodes.",
        "remaining_nodes": 1,
    }


@router.post("/cleanup")
async def cleanup_graph(
    threshold: int = 10,
    tree=Depends(tree_dependency)
):
    """
    Trigger cleanup of stale actions in nodes that have high insertion counts.
    """
    from graph import Tree
    
    tree._ensure_graph_constructed()
    cleaned_nodes = Tree.cleanup_nodes_batch(tree.dao, threshold)
    
    return {
        "status": "success",
        "nodes_cleaned": len(cleaned_nodes),
        "node_uuids": cleaned_nodes,
    }
