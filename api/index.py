# api/index.py or index.py
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"message": "Hello from Vercel!"})

@app.route("/api/hello")
def hello():
    return jsonify({"message": "This is another route"})