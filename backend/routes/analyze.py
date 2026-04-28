"""
Analyze route — POST /api/analyze
Invokes the temporal-visualizer skill to analyze a workflow.
"""

import logging
from flask import Blueprint, jsonify, request
from services.analyzer import analyze_workflow
from models.database import get_analyzed_workflows, get_workflow_by_name

logger = logging.getLogger(__name__)

analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Analyze a Temporal workflow.

    Expected JSON body:
        { "workflow_name": "StockAnalysis", "directory_path": "/path/to/project" }
    """
    body = request.get_json(force=True) or {}
    logger.info(f"[ROUTE] POST /api/analyze — body: {body}")

    workflow_name = body.get("workflow_name", "").strip()
    directory_path = body.get("directory_path", "").strip()

    if not workflow_name:
        logger.warning("[ROUTE] Missing workflow_name")
        return jsonify({"error": "workflow_name is required"}), 400
    if not directory_path:
        logger.warning("[ROUTE] Missing directory_path")
        return jsonify({"error": "directory_path is required"}), 400

    try:
        logger.info(f"[ROUTE] Starting analysis: {workflow_name} @ {directory_path}")
        result = analyze_workflow(workflow_name, directory_path)
        logger.info(f"[ROUTE] Analysis succeeded for {workflow_name}")
        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        logger.error(f"[ROUTE] Analysis FAILED: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@analyze_bp.route("/api/workflows", methods=["GET"])
def list_workflows():
    """Return all previously analyzed workflows."""
    workflows = get_analyzed_workflows()
    return jsonify({"workflows": workflows, "count": len(workflows)})


@analyze_bp.route("/api/workflows/<name>", methods=["GET"])
def get_workflow(name: str):
    """Return a specific analyzed workflow by name."""
    workflow = get_workflow_by_name(name)
    if not workflow:
        return jsonify({"error": f"Workflow '{name}' not found"}), 404
    return jsonify(workflow)
