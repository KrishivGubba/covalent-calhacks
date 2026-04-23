"""
Tab completion endpoints.
"""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from ..dependencies import tree_dependency
from logger import get_logger

log = get_logger()
router = APIRouter()


class TabPredictRequest(BaseModel):
    app_name: Optional[str] = "Unknown"
    text_buffer: Optional[str] = None
    # Legacy compatibility: older callers may send "buffer".
    buffer: Optional[str] = None
    context_type: Optional[str] = ""
    activity_id: Optional[str] = ""


class TabContextRequest(BaseModel):
    app_name: Optional[str] = "Unknown"
    activity_id: Optional[str] = ""
    context_data: Optional[str] = ""
    activity_type: Optional[str] = "Unknown"
    window_title: Optional[str] = None


class TabFeedbackRequest(BaseModel):
    app_name: Optional[str] = "Unknown"
    activity_id: Optional[str] = ""
    declined_prediction: Optional[str] = ""
    typed_text: Optional[str] = ""
    chars_after: Optional[str] = ""
    time_to_decline_ms: Optional[int] = 0
    signal: Optional[str] = "negative"


def generate_tab_prediction(text_buffer: str, context_data: list) -> str:
    """
    Generate tab completion prediction based on text buffer and graph context.
    Mirrors Flask behavior for parity.
    """
    last_line = text_buffer.split('\n')[-1] if '\n' in text_buffer else text_buffer
    words = last_line.split()

    if not words:
        return ""

    last_word = words[-1]

    for context in context_data:
        if isinstance(context, str):
            context_words = context.split()
            for i, word in enumerate(context_words):
                if word.startswith(last_word) and i + 1 < len(context_words):
                    return context_words[i + 1]

    common_completions = {
        "import": "numpy as np",
        "from": "typing import",
        "def": "function_name():",
        "class": "ClassName:",
        "if": "__name__ == '__main__':",
        "for": "i in range():",
        "return": "None",
        "const": "variable = ",
        "let": "variable = ",
        "function": "name() {",
    }

    for keyword, completion in common_completions.items():
        if last_word.startswith(keyword) or keyword.startswith(last_word):
            return completion

    return ""


@router.post("/tab_predict")
async def tab_predict(
    request: Request,
    body: TabPredictRequest,
    tree=Depends(tree_dependency),
):
    """
    Get tab completion prediction for the given buffer.
    """
    try:
        text_buffer = body.text_buffer if body.text_buffer is not None else (body.buffer or "")
        if not text_buffer:
            return JSONResponse(
                status_code=400,
                content={"error": "text_buffer is required"},
            )

        app_name = body.app_name or "Unknown"
        log.debug(f"Tab predict request: app={app_name}, buffer={text_buffer[:50]}...")
        large_context_service = getattr(request.app.state, "large_context_sync_service", None)

        relevant_node = tree.traverse(f"App: {app_name} | Context: Typing '{text_buffer}'")

        context_data = []
        suggested_actions = []
        if large_context_service is not None:
            active_context = large_context_service.get_active_context(
                f"{app_name} {text_buffer}",
                limit=5,
            )
            for item in active_context:
                context_data.append(
                    f"{item['title']} | {item.get('project') or ''} | "
                    f"{item.get('summary') or ''} | "
                    f"why active: {', '.join(item.get('why_active') or [])}"
                )
        if relevant_node:
            metadata_chain = tree.get_parent_metadata(relevant_node)
            context_data.append(metadata_chain)

            if relevant_node.actions:
                for action in relevant_node.actions[:3]:
                    context_data.append(action.get("action_name", ""))
                suggested_actions = [a.get("action_name", "") for a in relevant_node.actions[:3]]

        prediction = generate_tab_prediction(text_buffer, context_data)

        return {
            "prediction": prediction,
            "confidence": 0.85,
            "suggested_actions": suggested_actions,
        }

    except Exception as e:
        log.error(f"Error in /tab_predict: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/tab_context")
async def tab_context(
    body: TabContextRequest,
    tree=Depends(tree_dependency),
):
    """
    Get context for tab completion based on app and window.
    """
    try:
        app_name = body.app_name or "Unknown"
        activity_id = body.activity_id or ""
        context_data = body.context_data or ""
        activity_type = body.activity_type or "Unknown"

        summary = f"Tab completion context update for {app_name} | Activity: {activity_type}"
        recent_actions = tree.learn(summary, context_data, key=f"tab_context_{activity_id}")

        node_id = None
        if recent_actions:
            node_id = str(recent_actions[0][4]) if recent_actions[0][4] else None

        return {
            "message": "Context updated successfully",
            "node_id": node_id,
        }

    except Exception as e:
        log.error(f"Error in /tab_context: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/tab_feedback")
async def tab_feedback(
    body: TabFeedbackRequest,
    tree=Depends(tree_dependency),
):
    """
    Record decline feedback for tab-completion learning.
    This endpoint is intentionally best-effort for frontend stability.
    """
    try:
        app_name = body.app_name or "Unknown"
        activity_id = body.activity_id or ""
        signal = body.signal or "negative"

        feedback_payload = {
            "declined_prediction": body.declined_prediction or "",
            "typed_text": body.typed_text or "",
            "chars_after": body.chars_after or "",
            "time_to_decline_ms": body.time_to_decline_ms or 0,
            "signal": signal,
        }
        summary = f"Tab completion feedback for {app_name} | Signal: {signal}"

        try:
            tree.learn(summary, json.dumps(feedback_payload), key=f"tab_feedback_{activity_id}")
        except Exception as learn_err:
            log.warning(f"Failed to persist tab feedback: {learn_err}")

        return {"message": "Feedback acknowledged", "acknowledged": True}
    except Exception as e:
        log.error(f"Error in /tab_feedback: {e}")
        return {
            "message": "Feedback received with warnings",
            "acknowledged": False,
        }
