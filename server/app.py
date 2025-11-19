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
        
        # Call learn function - it's a regular function, not async
        print(f"\n📍 DEBUG: Calling tree.learn()...")
        action, actionID = tree.learn(enhanced_description, data_str)
        print(f"📍 DEBUG: tree.learn() returned - action={action}, actionID={actionID}")

        # Return in format expected by Rust code
        return jsonify({
            "message": f"Context processed successfully. Suggested action: {action if action else 'None'}", 
            "written": str(actionID) if actionID else "no-action-generated"
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
        
        success = tree.trigger_action(action_uuid)

        # Use the description field as needed
        return jsonify({"message": "Action triggered", "success": success}), 200
    except Exception as e:
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
        action, action_id = tree.learn(summary, context_data, key=f"tab_context_{activity_id}")
        
        return jsonify({
            "message": "Context updated successfully",
            "node_id": action_id if action_id else None
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
