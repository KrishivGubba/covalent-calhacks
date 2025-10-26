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
        
        node_uuid, data = tree.learn(description, data)

        # Use the description field as needed
        return jsonify({"message": "Screen data received", "written": node_uuid}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "covalent-context-engine"}), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
