"""
MCP (Model Context Protocol) endpoints.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
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
        return JSONResponse(status_code=500, content={
            "status": "unhealthy",
            "error": str(e)
        })


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
        limit = min(limit, 200)

        # Keep Flask behavior: ensure table exists before reading.
        try:
            tree.dao.execute_query("""
                CREATE TABLE IF NOT EXISTS action_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_uuid TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_data TEXT,
                    creation_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    node_uuid TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    error_message TEXT,
                    duration_ms INTEGER
                )
            """)
        except Exception:
            pass

        records = tree.dao.get_action_history(
            limit=limit,
            offset=offset,
            status=status,
            action_type=action_type
        )

        if records is None:
            records = []

        history = []
        for record in records:
            history.append({
                "id": record[0],
                "action_uuid": record[1],
                "action_type": record[2],
                "action_data": record[3],
                "creation_timestamp": record[4],
                "node_uuid": record[5],
                "status": record[6],
                "result": record[7],
                "error_message": record[8],
                "duration_ms": record[9],
            })

        return {"history": history, "count": len(history)}

    except Exception as e:
        log.error(f"Error in /action_history: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
