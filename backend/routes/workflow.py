"""
Workflow trigger route — POST /api/trigger, GET /api/trigger/<id>/status
Triggers Temporal workflow executions and checks their status.
"""

from flask import Blueprint, jsonify, request
from services.temporal_client import trigger_workflow, get_workflow_status

workflow_bp = Blueprint("workflow", __name__)


@workflow_bp.route("/api/trigger", methods=["POST"])
def trigger():
    """
    Trigger a Temporal workflow execution.

    Expected JSON body:
        {
            "workflow_name": "StockAnalysis",
            "task_queue": "stock-analysis-queue",
            "input": { "names": ["Reliance"], "symbols": null }
        }
    """
    body = request.get_json(force=True) or {}

    workflow_name = body.get("workflow_name", "").strip()
    task_queue = body.get("task_queue", "").strip()
    input_data = body.get("input", {})

    if not workflow_name:
        return jsonify({"error": "workflow_name is required"}), 400
    if not task_queue:
        return jsonify({"error": "task_queue is required"}), 400

    try:
        result = trigger_workflow(workflow_name, task_queue, input_data)
        return jsonify(result), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@workflow_bp.route("/api/trigger/<workflow_id>/status", methods=["GET"])
def status(workflow_id: str):
    """Get the status of a running workflow."""
    try:
        result = get_workflow_status(workflow_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
