from flask import Flask, render_template, request, jsonify, flash, redirect
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import numpy as np
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotifylogic import SpotifyActions

from LLM import ImageMoodClassifier
from flask_cors import CORS
from PIL import Image

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
