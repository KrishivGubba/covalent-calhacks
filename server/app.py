from flask import Flask, request, jsonify
import sqlite3
import os
import sys

from flask_cors import CORS

# Add context-engine to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'context-engine'))
from graph import Tree

app = Flask(__name__)
CORS(app)

# Connect to SQLite Database
db_path = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')
conn = sqlite3.connect(db_path, check_same_thread=False)
db1 = conn.cursor()


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
        
        tree = Tree(db_path)
        
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
        
        tree = Tree(db_path)
        
        success = tree.trigger_action(action_uuid)

        # Use the description field as needed
        return jsonify({"message": "Action triggered", "success": success}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
