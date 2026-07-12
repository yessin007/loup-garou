from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.get("/")
def root():
    return jsonify(
        {
            "message": "Bienvenue sur l'API Loup Garou",
            "status": "ok",
        }
    )


@app.get("/api/health")
def health():
    return jsonify(
        {
            "service": "loup-garou-backend",
            "status": "ok",
        }
    )
