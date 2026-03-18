"""
MCP (Model Context Protocol) endpoints.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from ..dependencies import tree_dependency, get_action_executor
from logger import get_logger

log = get_logger()
router = APIRouter()


@router.get("/mcp_health")
async def mcp_health():
    """
    Check MCP server health and available tools.
    """
    try:
        ae = get_action_executor()
        health_result = await ae.health_check()
        return health_result
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/action_history")
async def get_action_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    tree=Depends(tree_dependency),
):
    """
    Get action execution history.
    """
    try:
        records = tree.dao.get_action_history(
            limit=limit,
            offset=offset,
            status=status,
            action_type=action_type
        )
        
        history_list = []
        for record in records:
            (id_, action_uuid, action_type_, action_data, creation_timestamp,
             node_uuid, status_, result, error_message, duration_ms) = record
            
            action_data_parsed = None
            if action_data:
                try:
                    action_data_parsed = json.loads(action_data)
                except json.JSONDecodeError:
                    action_data_parsed = action_data
            
            history_list.append({
                "id": id_,
                "action_uuid": action_uuid,
                "action_type": action_type_,
                "action_data": action_data_parsed,
                "creation_timestamp": creation_timestamp,
                "node_uuid": node_uuid,
                "status": status_,
                "result": result,
                "error_message": error_message,
                "duration_ms": duration_ms
            })
        
        return {
            "status": "success",
            "history": history_list,
            "count": len(history_list),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        log.error(f"Error in /action_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
