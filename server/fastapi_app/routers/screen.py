"""
Screen context endpoint.
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..dependencies import tree_dependency, integration_dao_dependency, get_tree, get_integration_dao
from logger import get_logger

log = get_logger()
router = APIRouter()


class ScreenContextRequest(BaseModel):
    description: Optional[str] = ""
    app_name: Optional[str] = "Unknown"
    context_type: Optional[Dict[str, Any]] = {}
    activity_level: Optional[str] = "Unknown"
    workflow_stage: Optional[str] = "Unknown"
    data: Optional[Any] = None
    raw_ocr_text: Optional[str] = ""


@router.post("/screen")
async def screen(
    body: ScreenContextRequest,
    tree=Depends(tree_dependency),
    integration_dao=Depends(integration_dao_dependency),
):
    """
    Process screen context and return suggested actions.
    
    This endpoint:
    1. Receives screen context (OCR text, app name, context type, etc.)
    2. Learns from the context using the knowledge graph
    3. Returns suggested actions based on the context
    """
    try:
        log.debug(f"🔍 Screen endpoint called with body: {body}")
        
        # Parse the comprehensive data from the 'data' field
        full_context_data = {}
        if body.data:
            if isinstance(body.data, str):
                try:
                    full_context_data = json.loads(body.data)
                except json.JSONDecodeError:
                    full_context_data = body.model_dump()
            else:
                full_context_data = body.data if isinstance(body.data, dict) else body.model_dump()
        else:
            full_context_data = body.model_dump()
        
        # Extract key fields
        description = full_context_data.get("description", body.description)
        app_name = full_context_data.get("app_name", body.app_name)
        context_type = full_context_data.get("context_type", body.context_type)
        activity_level = full_context_data.get("activity_level", body.activity_level)
        workflow_stage = full_context_data.get("workflow_stage", body.workflow_stage)
        raw_ocr_text = full_context_data.get("raw_ocr_text", body.raw_ocr_text)
        
        # Format context_type
        context_type_str = "Unknown"
        if isinstance(context_type, dict) and context_type:
            for key, value in context_type.items():
                context_type_str = f"{key}({value})" if value else key
                break
        
        # Build OCR section
        ocr_section = ""
        if raw_ocr_text:
            ocr_section = f"""
RAW OCR TEXT FROM SCREEN (ALL TEXT VISIBLE TO USER):
{raw_ocr_text}
"""
        
        # Create comprehensive context string
        comprehensive_context_str = f"""=== COMPREHENSIVE CONTEXT DATA ===

APPLICATION INFO:
- App Name: {app_name}
- Context Type: {context_type_str}
- Activity Level: {activity_level}
- Workflow Stage: {workflow_stage}

USER ACTIVITY DESCRIPTION:
{description}
{ocr_section}
FULL CONTEXT DATA (JSON):
{json.dumps(full_context_data, indent=2, ensure_ascii=False)}

=== END CONTEXT DATA ==="""
        
        log.info(f"📊 Comprehensive context length: {len(comprehensive_context_str)} chars")
        
        # Get MCP integration statuses
        statuses = integration_dao.get_all_statuses()
        
        available_mcps = [
            {"id": "filesystem", "name": "Filesystem", "description": "Access local files and directories", "connected": statuses.get("filesystem", False)},
            {"id": "github", "name": "GitHub", "description": "Access repositories, issues, and pull requests", "connected": statuses.get("github", False)},
            {"id": "perplexity", "name": "Perplexity Search", "description": "AI-powered web search", "connected": True},
            {"id": "notion", "name": "Notion", "description": "Access Notion workspaces and pages", "connected": statuses.get("notion", False)},
            {"id": "google", "name": "Google Workspace", "description": "Docs, Drive, Mail, Calendar", "connected": statuses.get("google", False)},
        ]
        
        connected_mcps = [mcp for mcp in available_mcps if mcp["connected"]]
        log.info(f"Available MCPs: {[mcp['name'] for mcp in connected_mcps]}")
        
        # Convert body to JSON string for storage
        data_str = json.dumps(body.model_dump(), ensure_ascii=False)
        
        # Call learn_with_structure in a thread pool so the event loop stays free
        # for dashboard/graph/action requests during this blocking LLM+DB work.
        log.debug("📍 Calling tree.learn_with_structure()...")
        result = await asyncio.to_thread(
            tree.learn_with_structure, comprehensive_context_str, data_str, connected_mcps
        )
        log.debug(f"📍 Operation: {result['operation']}, Confidence: {result['confidence']}")
        
        recent_actions = result.get("actions", [])
        log.debug(f"📍 Got {len(recent_actions)} recent actions")
        
        # Format actions for frontend
        actions_list = []
        for action in recent_actions:
            uuid, name, plan, node_uuid, last_selected = action
            actions_list.append({
                "action_uuid": str(uuid),
                "action_name": name,
                "action_plan": plan,
                "last_selected": last_selected
            })
        
        primary_action = actions_list[0] if actions_list else None
        
        return {
            "message": f"Context processed successfully. {len(actions_list)} recent actions available.",
            "primary_action": primary_action,
            "recent_actions": actions_list,
            "action_name": primary_action["action_name"] if primary_action else None,
            "action_plan": primary_action["action_plan"] if primary_action else None,
            "action_uuid": primary_action["action_uuid"] if primary_action else None
        }
        
    except Exception as e:
        log.error(f"Error in /screen endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
