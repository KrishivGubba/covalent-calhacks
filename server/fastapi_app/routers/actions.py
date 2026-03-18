"""
Action planning and execution endpoints.
"""
import asyncio
import json
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from ..dependencies import tree_dependency, get_action_executor, get_display_schema_func, get_resolve_display_fields_func
from logger import get_logger

log = get_logger()
router = APIRouter()


class PlanActionRequest(BaseModel):
    action_uuid: str
    action_override: Optional[Dict[str, Any]] = None
    skip_research: bool = False


class PlanActionDirectRequest(BaseModel):
    action_text: str
    context: str = ""
    skip_research: bool = False


class ExecuteActionRequest(BaseModel):
    action_uuid: str
    tool_name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None


class EditActionRequest(BaseModel):
    action_uuid: str
    action_name: str
    action_plan: str
    persist: bool = False


def _resolve_tool_display(proposed_action: dict, loop=None) -> dict:
    """Resolve display schema for a proposed action."""
    tool_name = proposed_action.get("tool_name", "")
    parameters = proposed_action.get("parameters", {})
    
    get_display_schema = get_display_schema_func()
    schema = get_display_schema(tool_name)
    
    if schema is None:
        fallback_fields = []
        for key, value in parameters.items():
            fallback_fields.append({
                "key": key,
                "label": key.replace("_", " ").title(),
                "source": "param",
                "editable": True,
                "widget": "text_input",
                "required": False,
                "value": value,
            })
        return {
            "display_name": tool_name.replace("_", " ").title(),
            "description": "",
            "fields": fallback_fields,
            "has_schema": False,
        }
    
    resolve_display_fields = get_resolve_display_fields_func()
    _loop = loop or asyncio.new_event_loop()
    _owns_loop = loop is None
    if _owns_loop:
        asyncio.set_event_loop(_loop)
    try:
        display_info = _loop.run_until_complete(
            resolve_display_fields(schema, parameters)
        )
    finally:
        if _owns_loop:
            _loop.close()
    
    display_info["has_schema"] = True
    return display_info


@router.post("/plan_action")
async def plan_action_endpoint(
    body: PlanActionRequest,
    tree=Depends(tree_dependency),
):
    """
    Research and plan an action using MCP tools.
    
    Returns proposed action(s) for user approval/editing.
    """
    start_time = time.perf_counter()
    
    try:
        action_text, collected_data = tree.get_action_context(
            body.action_uuid, 
            action_override=body.action_override
        )
        
        if not action_text:
            raise HTTPException(status_code=400, detail="Failed to retrieve action details")
        
        log.info(f"📋 Planning action: {action_text[:100]}...")
        
        ae = get_action_executor()
        
        if body.skip_research:
            plan_result = await ae.plan_action(action_text, collected_data)
            research_info = {"resources_read": [], "context_gathered": collected_data}
        else:
            result = await ae.research_and_plan(action_text, collected_data)
            plan_result = {
                "status": result["status"],
                "proposed_actions": result.get("proposed_actions"),
                "is_multi_action": result.get("is_multi_action", False),
                "overall_reasoning": result.get("overall_reasoning", ""),
                "error": result.get("error")
            }
            research_info = result.get("research", {"resources_read": [], "context_gathered": collected_data})
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if plan_result["status"] == "error":
            return {
                "status": "error",
                "error": plan_result["error"],
                "research": research_info,
                "duration_ms": duration_ms
            }
        
        # Resolve display schemas
        displays = []
        proposed_actions = plan_result.get("proposed_actions") or []
        for action in proposed_actions:
            try:
                display_info = _resolve_tool_display(action)
                displays.append({
                    "step_id": action.get("step_id", len(displays) + 1),
                    **display_info
                })
            except Exception as display_err:
                log.warning(f"Display schema resolution failed: {display_err}")
                displays.append({
                    "step_id": action.get("step_id", len(displays) + 1),
                    "display_name": action.get("tool_name", "Unknown").replace("_", " ").title(),
                    "description": "",
                    "fields": [],
                    "has_schema": False
                })
        
        return {
            "status": "success",
            "research": research_info,
            "proposed_actions": proposed_actions,
            "is_multi_action": plan_result.get("is_multi_action", False),
            "overall_reasoning": plan_result.get("overall_reasoning", ""),
            "displays": displays,
            "action_text": action_text,
            "context_data": research_info.get("context_gathered", collected_data),
            "duration_ms": duration_ms
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error in /plan_action: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan_action_direct")
async def plan_action_direct_endpoint(body: PlanActionDirectRequest):
    """
    Plan an action directly without going through the action_uuid lookup.
    """
    start_time = time.perf_counter()
    
    try:
        if not body.action_text:
            raise HTTPException(status_code=400, detail="action_text is required")
        
        log.info(f"📋 Planning action (direct): {body.action_text[:100]}...")
        
        ae = get_action_executor()
        
        if body.skip_research:
            plan_result = await ae.plan_action(body.action_text, body.context)
            research_info = {"resources_read": [], "context_gathered": body.context}
        else:
            result = await ae.research_and_plan(body.action_text, body.context)
            plan_result = {
                "status": result["status"],
                "proposed_actions": result.get("proposed_actions"),
                "is_multi_action": result.get("is_multi_action", False),
                "overall_reasoning": result.get("overall_reasoning", ""),
                "error": result.get("error")
            }
            research_info = result.get("research", {"resources_read": [], "context_gathered": body.context})
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        if plan_result["status"] == "error":
            return {
                "status": "error",
                "error": plan_result["error"],
                "research": research_info,
                "duration_ms": duration_ms
            }
        
        # Resolve display schemas
        displays = []
        proposed_actions = plan_result.get("proposed_actions") or []
        for action in proposed_actions:
            try:
                display_info = _resolve_tool_display(action)
                displays.append({
                    "step_id": action.get("step_id", len(displays) + 1),
                    **display_info
                })
            except Exception:
                displays.append({
                    "step_id": action.get("step_id", len(displays) + 1),
                    "display_name": action.get("tool_name", "Unknown").replace("_", " ").title(),
                    "description": "",
                    "fields": [],
                    "has_schema": False
                })
        
        return {
            "status": "success",
            "research": research_info,
            "proposed_actions": proposed_actions,
            "is_multi_action": plan_result.get("is_multi_action", False),
            "overall_reasoning": plan_result.get("overall_reasoning", ""),
            "displays": displays,
            "action_text": body.action_text,
            "context_data": research_info.get("context_gathered", body.context),
            "duration_ms": duration_ms
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error in /plan_action_direct: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute_action")
async def execute_action_endpoint(
    body: ExecuteActionRequest,
    tree=Depends(tree_dependency),
):
    """
    Execute an approved action.
    
    Supports both single-action and multi-action (chain) execution.
    """
    start_time = time.perf_counter()
    
    try:
        ae = get_action_executor()
        action_data = tree.dao.get_action_by_id(body.action_uuid)
        node_uuid = action_data[4] if action_data else None
        
        if body.actions and isinstance(body.actions, list):
            # Multi-action execution
            log.info(f"🚀 Executing action chain with {len(body.actions)} actions")
            
            chain_result = await ae.execute_action_chain(body.actions)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log each action result to history
            for step_result in chain_result.get("results", []):
                try:
                    _step_tool = step_result.get("tool_name", "unknown")
                    _step_params = next(
                        (a.get("parameters", {}) for a in body.actions if a.get("step_id") == step_result.get("step_id")),
                        {}
                    )
                    _step_status = step_result.get("status")
                    tree.dao.insert_action_history(
                        action_uuid=body.action_uuid,
                        action_type=_step_tool,
                        action_data=json.dumps(_step_params),
                        node_uuid=node_uuid,
                        status="completed" if _step_status == "success" else "failed",
                        result=str(step_result.get("result")) if _step_status == "success" else None,
                        error_message=step_result.get("error") if _step_status == "error" else None,
                        duration_ms=None
                    )
                except Exception as log_err:
                    log.warning(f"⚠️ Failed to log action history: {log_err}")
            
            # Update last_selected timestamp
            tree.dao.update_action_last_selected(body.action_uuid)
            
            return {
                "status": chain_result.get("status", "success"),
                "results": chain_result.get("results", []),
                "duration_ms": duration_ms
            }
        
        elif body.tool_name and body.parameters is not None:
            # Single-action execution
            log.info(f"🚀 Executing {body.tool_name} with parameters: {body.parameters}")
            
            exec_result = await ae.execute_action(body.tool_name, body.parameters)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            if exec_result["status"] == "error":
                tree.dao.insert_action_history(
                    action_uuid=body.action_uuid,
                    action_type=body.tool_name,
                    action_data=json.dumps(body.parameters),
                    node_uuid=node_uuid,
                    status="failed",
                    result=None,
                    error_message=exec_result["error"],
                    duration_ms=duration_ms
                )
                return {
                    "status": "error",
                    "error": exec_result["error"],
                    "duration_ms": duration_ms
                }
            
            # Log successful execution
            tree.dao.insert_action_history(
                action_uuid=body.action_uuid,
                action_type=body.tool_name,
                action_data=json.dumps(body.parameters),
                node_uuid=node_uuid,
                status="completed",
                result=str(exec_result.get("result")),
                error_message=None,
                duration_ms=duration_ms
            )
            
            tree.dao.update_action_last_selected(body.action_uuid)
            
            return {
                "status": "success",
                "result": exec_result.get("result"),
                "duration_ms": duration_ms
            }
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Missing tool_name or parameters (for single action) or actions array (for multi-action)"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error in /execute_action: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edit_action")
async def edit_action_endpoint(
    body: EditActionRequest,
    tree=Depends(tree_dependency),
):
    """
    Edit an action's name and plan, optionally persisting to database.
    """
    try:
        log.info(f"✏️ Editing action {body.action_uuid} (persist={body.persist})")
        
        if body.persist:
            tree.dao.update_action(body.action_uuid, body.action_name, body.action_plan)
        
        return {
            "status": "success",
            "action_uuid": body.action_uuid,
            "action_name": body.action_name,
            "action_plan": body.action_plan,
            "persisted": body.persist
        }
        
    except Exception as e:
        log.error(f"Error in /edit_action: {e}")
        raise HTTPException(status_code=500, detail=str(e))
