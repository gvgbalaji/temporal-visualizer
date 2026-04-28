"""
Flask application — Temporal Workflow Visualizer & Editor API.

Routes:
  POST /api/analyze              → Analyze a Temporal workflow via Claude skill
  GET  /api/workflows            → List all analyzed workflows
  GET  /api/workflows/<name>     → Get specific workflow analysis
  POST /api/chat                 → Conversational editor agent
  POST /api/apply                → Apply code changes to disk
  GET  /api/chat/history/<id>    → Get chat history
  POST /api/trigger              → Trigger a Temporal workflow execution
  GET  /api/trigger/<id>/status  → Get workflow execution status
  GET  /api/components           → List reusable components
  GET  /api/components/<name>    → Get specific component
"""

import os
import logging
from dotenv import load_dotenv
from flask import Flask, send_from_directory

from models.database import init_db
from routes.analyze import analyze_bp
from routes.edit import edit_bp
from routes.workflow import workflow_bp
from routes.components import components_bp

load_dotenv()

# Configure logging — show all logs in terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR)


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# Register blueprints
app.register_blueprint(analyze_bp)
app.register_blueprint(edit_bp)
app.register_blueprint(workflow_bp)
app.register_blueprint(components_bp)


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "temporal-visualizer-api"}


@app.route("/")
def serve_index():
    """Serve the frontend index.html."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Serve static frontend files."""
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    init_db()
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(host=host, port=port, debug=debug)
