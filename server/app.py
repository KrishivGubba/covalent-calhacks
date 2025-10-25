from flask import Flask, request, jsonify
import sqlite3

from flask_cors import CORS
from graph_dao import GraphDAO

app = Flask(__name__)
CORS(app)

# Connect to SQLite Database
conn = sqlite3.connect('graph.db', check_same_thread=False)
db1 = conn.cursor()


@app.route("/screen", methods=["POST"])
def screen():
    body = request.get_json()
    description = body.get("description", "")
    


    # Use the description field as needed
    return jsonify({"message": "Screen data received", "description": description}), 200
