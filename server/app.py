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
        description = body.get("description", "")
        data = body.get("data", "")
        
        # Parse the analysis data to enhance the description with app context
        enhanced_description = description  # Default to original
        try:
            import json
            analysis_data = json.loads(data) if data else {}
            app_name = analysis_data.get("app_name", "Unknown")
            context_type = analysis_data.get("context_type", "Unknown")
            activity_level = analysis_data.get("activity_level", "Unknown")
            workflow_stage = analysis_data.get("workflow_stage", "Unknown")
            
            # Enhance description with app context for better action generation
            enhanced_description = f"Current App: {app_name} | Context: {context_type} | Activity: {activity_level} | Stage: {workflow_stage} | {description}"
            
            print(f"Enhanced description: {enhanced_description}")
            
        except Exception as parse_error:
            print(f"Warning: Could not parse analysis data: {parse_error}")
        
        tree = Tree(db_path)
        
        action, actionID = tree.learn(enhanced_description, data)

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
