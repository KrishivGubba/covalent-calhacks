"""
Graph management endpoints.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..dependencies import tree_dependency

router = APIRouter()


class GraphDataResponse(BaseModel):
    nodes: list
    edges: list


@router.get("/data")
async def get_graph_data(tree=Depends(tree_dependency)):
    """
    Get the full graph data for visualization.
    
    Returns nodes and edges for the frontend graph view.
    """
    tree._ensure_graph_constructed()
    
    nodes = []
    edges = []
    
    for node_uuid, node in tree.nodes.items():
        nodes.append({
            "id": node_uuid,
            "label": node.metadata or "Unknown",
            "metadata": node.metadata,
            "created": node.created,
            "last_modified": node.last_modified,
            "has_children": len(node.children) > 0,
            "action_count": len(node.actions),
        })
        
        if node.parent_uuid:
            edges.append({
                "from": node.parent_uuid,
                "to": node_uuid,
            })
    
    return {"nodes": nodes, "edges": edges}


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
