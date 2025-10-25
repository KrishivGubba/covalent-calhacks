from flask import Flask, render_template, request, jsonify, flash, redirect
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import cv2
import base64
import numpy as np
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotifylogic import SpotifyActions
import pyautogui 
import random
from LLM import ImageMoodClassifier
from flask_cors import CORS
from PIL import Image
import io
from emotionanalysis2 import predict_emotion
app = Flask(__name__)
CORS(app)

@app.route("/register", methods=["POST"])
def register():
    body = request.get_json()
    if not body.get("username"):
        return jsonify({"message": "Username is required"}), 400
    elif not body.get("password"):
        return jsonify({"message": "Password is required"}), 400

    try:
        # Check if username exists
        db1.execute(f"SELECT * FROM users")
        rows = db1.fetchall()
        if any(row[0] == body.get("username") for row in rows):
            return jsonify({"message": "Username already exists"}), 409
        # Hash the password
        hashed_password = generate_password_hash(body.get("password"))
        # Insert the new user
        db1.execute(f"INSERT INTO users values (%s,%s)", (body.get("password"), hashed_password))
        conn.commit()

    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

    return jsonify({"message": "Successfully registered"}), 200


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json()
    print(body.get("username"))
    # Ensure username was sumbitted
    if not body.get("username"):
        response = {
            "message": "Username is required"
        }
        return response, 400

    # Ensure password was submitted
    elif not body.get("password"):
        response = {
            "message": "password is required"
        }
        return response, 400

    # Query database for username
    db1.execute("SELECT * FROM users WHERE username = %s", [body.get("username")])
    # Ensure username exists and password is correct
    rows = db1.fetchall()
    for row in rows:
        if not row[0] or not check_password_hash(row[1], body.get("password")):
            response = {
                "message": "Invalid username or password"
            }
            return response, 403
    # Remember which user has logged in
    response ={
        "message" : "Successfully Logged In",
        "username" : body.get("username")
    }
    return response, 200