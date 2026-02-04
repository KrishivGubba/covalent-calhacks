from flask import Flask, request, jsonify, g
import sqlite3
import os
import sys
import time

from flask_cors import CORS

# Add context-engine to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'context-engine'))
from graph import Tree



app = Flask(__name__)
CORS(app)

@app.before_request
def start_timer():
    g.start_time = time.perf_counter()

@app.after_request
def log_request(response):
    if hasattr(g, "start_time"):
        duration = time.perf_counter() - g.start_time
        app.logger.info("Request %s %s completed in %.3f ms", request.method, request.path, duration * 1000)
        response.headers["X-Process-Time"] = f"{duration:.3f}s"
    return response

# Connect to SQLite Database
db_path = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')

tree = Tree(db_path)


@app.route("/screen", methods=["POST"])
def screen():
    try:
        body = request.get_json()
        
        # The body is already parsed JSON from the Rust code
        # Extract fields directly from the JSON object
        description = body.get("description", "")
        app_name = body.get("app_name", "Unknown")
        context_type = body.get("context_type", {})
        activity_level = body.get("activity_level", "Unknown")
        workflow_stage = body.get("workflow_stage", "Unknown")
        
        # Format context_type properly (it's a nested object like {"Development": "DevOps"})
        context_type_str = "Unknown"
        if isinstance(context_type, dict) and context_type:
            # Get the first key-value pair from the context_type dict
            for key, value in context_type.items():
                context_type_str = f"{key}({value})" if value else key
                break
        
        # Enhance description with app context for better action generation
        enhanced_description = f"Current App: {app_name} | Context: {context_type_str} | Activity: {activity_level} | Stage: {workflow_stage} | {description}"
        
        print(f"Enhanced description: {enhanced_description}")
        
        
        
        # Convert the entire body to JSON string for storage
        import json
        data_str = json.dumps(body)
        
        # Call learn function - returns dict with structure info and actions
        print(f"\n📍 DEBUG: Calling tree.learn_with_structure()...")
        result = tree.learn_with_structure(enhanced_description, data_str)
        print(f"📍 DEBUG: Operation: {result['operation']}, Confidence: {result['confidence']}")
        
        # Extract recent actions from the result
        recent_actions = result.get("actions", [])
        print(f"📍 DEBUG: Got {len(recent_actions)} recent actions")

        # Format actions for frontend
        actions_list = []
        for action in recent_actions:
            uuid, name, plan, prompt, node_uuid, last_selected = action
            actions_list.append({
                "action_uuid": str(uuid),
                "action_name": name,
                "action_plan": plan,
                "action_prompt": prompt,
                "last_selected": last_selected
            })

        # Get the most recent action (first in list) for legacy compatibility
        primary_action = actions_list[0] if actions_list else None

        # Return all recent actions to the frontend
        return jsonify({
            "message": f"Context processed successfully. {len(actions_list)} recent actions available.",
            "primary_action": primary_action,
            "recent_actions": actions_list,
            # Legacy fields for backward compatibility
            "action_name": primary_action["action_name"] if primary_action else None,
            "action_plan": primary_action["action_plan"] if primary_action else None,
            "action_prompt": primary_action["action_prompt"] if primary_action else None,
            "action_uuid": primary_action["action_uuid"] if primary_action else None
        }), 200
    except Exception as e:
        print(f"Error in /screen endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "covalent-context-engine"}), 200



@app.route("/trigger_action", methods=["POST"])
def trigger_action():
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        action = body.get("action", "")
        action_override = body.get("action_override")
        
        effective_action = None
        if action_override:
            action_data = tree.dao.get_action_by_id(action_uuid)
            if action_data:
                _, action_name, action_plan, action_prompt, _ = action_data
                effective_action = {
                    "action_name": action_override.get("action_name") or action_name,
                    "action_plan": action_override.get("action_plan") or action_plan,
                    "action_prompt": action_override.get("action_prompt") or action_prompt
                }
            else:
                effective_action = action_override

        result = tree.trigger_action(action_uuid, action_override=action_override)
        
        # result is a tuple: (action_text, collected_data_string, graph_output)
        if result and len(result) >= 3:
            action_text, collected_data, graph_output = result
            
            # Convert graph_output to JSON-serializable format
            serializable_output = {}
            if graph_output:
                for key, value in graph_output.items():
                    # Handle Pydantic models and other non-serializable objects
                    if hasattr(value, 'dict'):
                        serializable_output[key] = value.dict()
                    elif hasattr(value, '__dict__'):
                        serializable_output[key] = value.__dict__
                    elif isinstance(value, list):
                        serializable_output[key] = [
                            item.dict() if hasattr(item, 'dict') else 
                            item.__dict__ if hasattr(item, '__dict__') else 
                            str(item) for item in value
                        ]
                    else:
                        serializable_output[key] = str(value)
            
            return jsonify({
                "message": "Action triggered successfully",
                "action_text": action_text,
                "graph_output": serializable_output,
                "effective_action": effective_action
            }), 200
        else:
            return jsonify({"message": "Action triggered but no result returned"}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/edit_action", methods=["POST"])
def edit_action():
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        action_override = body.get("action_override") or {}
        persist = bool(body.get("persist", False))

        if not action_uuid:
            return jsonify({"error": "action_uuid is required"}), 400

        if "action_prompt" in action_override and not action_override.get("action_prompt"):
            return jsonify({"error": "action_prompt cannot be empty"}), 400

        action_data = tree.dao.get_action_by_id(action_uuid)
        if not action_data:
            return jsonify({"error": "action not found"}), 404

        _, action_name, action_plan, action_prompt, _ = action_data

        effective_action = {
            "action_name": action_override.get("action_name") or action_name,
            "action_plan": action_override.get("action_plan") or action_plan,
            "action_prompt": action_override.get("action_prompt") or action_prompt
        }

        if persist:
            tree.dao.update_action(
                action_uuid,
                effective_action["action_name"],
                effective_action["action_plan"],
                effective_action["action_prompt"]
            )

        return jsonify({
            "message": "Action edit processed",
            "persisted": persist,
            "effective_action": effective_action
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/tab_predict", methods=["POST"])
def tab_predict():
    """
    Get tab completion prediction using graph.db context
    Request body:
    {
        "app_name": "VSCode",
        "text_buffer": "import numpy as n",
        "context_type": "full_query",
        "activity_id": "abc123"
    }
    """
    try:
        body = request.get_json()
        app_name = body.get("app_name", "Unknown")
        text_buffer = body.get("text_buffer", "")
        context_type = body.get("context_type", "")
        activity_id = body.get("activity_id", "")
        
        if not text_buffer:
            return jsonify({"error": "text_buffer is required"}), 400
        
        # Use graph traversal to find relevant context
        # The graph.py traverse() method returns the most relevant node
        relevant_node = tree.traverse(f"App: {app_name} | Context: Typing '{text_buffer}'")
        
        # Get data from the relevant node and its ancestors
        # This gives us context about what the user is working on
        context_data = []
        if relevant_node:
            # Collect metadata chain for context
            metadata_chain = tree.get_parent_metadata(relevant_node)
            context_data.append(metadata_chain)
            
            # Get actions from this node (these are learned patterns)
            if relevant_node.actions:
                for action in relevant_node.actions[:3]:  # Top 3 actions
                    context_data.append(action.get('action_name', ''))
        
        # Generate prediction based on context
        # This is a simple completion - you could enhance with a local LLM call here
        prediction = generate_tab_prediction(text_buffer, context_data)
        
        return jsonify({
            "prediction": prediction,
            "confidence": 0.85,  # TODO: Calculate actual confidence
            "suggested_actions": [a.get('action_name', '') for a in (relevant_node.actions[:3] if relevant_node else [])]
        }), 200
        
    except Exception as e:
        print(f"Error in /tab_predict endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/tab_context", methods=["POST"])
def tab_context():
    """
    Update context in graph.db for tab completion learning
    Request body:
    {
        "app_name": "VSCode",
        "activity_id": "abc123",
        "context_data": "{json_serialized_context}",
        "activity_type": "Development::Backend"
    }
    """
    try:
        body = request.get_json()
        app_name = body.get("app_name", "Unknown")
        activity_id = body.get("activity_id", "")
        context_data = body.get("context_data", "")
        activity_type = body.get("activity_type", "Unknown")
        
        # Create a summary for graph traversal
        summary = f"Tab completion context update for {app_name} | Activity: {activity_type}"
        
        # Use tree.learn() to insert this context into the graph
        # This will find the right node and store the context there
        recent_actions = tree.learn(summary, context_data, key=f"tab_context_{activity_id}")

        # Get the node_id from the first action if available
        node_id = None
        if recent_actions:
            # Each action tuple is: (uuid, name, plan, prompt, node_uuid, last_selected)
            node_id = str(recent_actions[0][4]) if recent_actions[0][4] else None

        return jsonify({
            "message": "Context updated successfully",
            "node_id": node_id
        }), 200
        
    except Exception as e:
        print(f"Error in /tab_context endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def generate_tab_prediction(text_buffer, context_data):
    """
    Generate tab completion prediction based on text buffer and graph context.
    This is a simple heuristic - enhance with LLM for better results.
    """
    # Extract the last incomplete word or phrase
    last_line = text_buffer.split('\n')[-1] if '\n' in text_buffer else text_buffer
    words = last_line.split()
    
    if not words:
        return ""
    
    last_word = words[-1]
    
    # Simple pattern matching from context
    for context in context_data:
        if isinstance(context, str):
            # Look for common patterns in the context
            if last_word in context:
                # Find what typically follows this word in context
                context_words = context.split()
                for i, word in enumerate(context_words):
                    if word.startswith(last_word) and i + 1 < len(context_words):
                        return context_words[i + 1]
    
    # Fallback: basic Python/JS completions
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
