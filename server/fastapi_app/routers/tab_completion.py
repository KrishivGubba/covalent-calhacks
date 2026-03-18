"""
Tab completion endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..dependencies import tree_dependency
from logger import get_logger

log = get_logger()
router = APIRouter()


class TabPredictRequest(BaseModel):
    buffer: str
    cursor_position: Optional[int] = None
    app_name: Optional[str] = None
    context: Optional[str] = None


class TabContextRequest(BaseModel):
    app_name: Optional[str] = None
    window_title: Optional[str] = None


@router.post("/tab_predict")
async def tab_predict(
    body: TabPredictRequest,
    tree=Depends(tree_dependency),
):
    """
    Get tab completion prediction for the given buffer.
    """
    try:
        log.debug(f"Tab predict request: buffer={body.buffer[:50]}...")
        
        # For now, return empty prediction
        # The actual prediction logic is handled by the tab_completion module in Rust
        return {
            "prediction": None,
            "confidence": 0.0,
        }
        
    except Exception as e:
        log.error(f"Error in /tab_predict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tab_context")
async def tab_context(
    body: TabContextRequest,
    tree=Depends(tree_dependency),
):
    """
    Get context for tab completion based on app and window.
    """
    try:
        log.debug(f"Tab context request: app={body.app_name}, window={body.window_title}")
        
        return {
            "context": "",
            "suggestions": [],
        }
        
    except Exception as e:
        log.error(f"Error in /tab_context: {e}")
        raise HTTPException(status_code=500, detail=str(e))
