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
        
        result = tree.trigger_action(action_uuid)
        
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
                "graph_output": serializable_output
            }), 200
        else:
            return jsonify({"message": "Action triggered but no result returned"}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
