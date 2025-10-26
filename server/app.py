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
        
        tree = Tree(db_path)
        
        action, actionID = tree.learn(description, data)

        # Use the description field as needed
        return jsonify({"action": action, "actionID": actionID}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "covalent-context-engine"}), 200

@app.route("trigger_action", methods=["POST"])
def trigger_action():
    try:
        body = request.get_json()
        action_uuid = body.get("action_uuid", "")
        
        tree = Tree(db_path)
        
        node_uuid, data = tree.trigger_action(action_uuid)

        # Use the description field as needed
        return jsonify({"message": "Action triggered", "written": node_uuid}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
