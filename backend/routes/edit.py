"""
Edit route — POST /api/edit, POST /api/apply
Invokes the temporal-editor skill to modify a workflow via conversational agent.
"""

from flask import Blueprint, jsonify, request
from services.editor import edit_workflow, apply_changes
from models.database import save_chat_message, get_chat_history

edit_bp = Blueprint("edit", __name__)


@edit_bp.route("/api/chat", methods=["POST"])
def chat():
    """
    Send a message to the conversational editor agent.

    Expected JSON body:
        {
            "message": "Add a step to calculate average price",
            "workflow_name": "StockAnalysis",
            "session_id": "uuid"
        }
    """
    body = request.get_json(force=True) or {}

    message = body.get("message", "").strip()
    workflow_name = body.get("workflow_name", "").strip()
    session_id = body.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400
    if not workflow_name:
        return jsonify({"error": "workflow_name is required"}), 400

    # Save user message
    save_chat_message(session_id, "user", message, workflow_name)

    try:
        result = edit_workflow(message, workflow_name)

        # Save assistant response
        save_chat_message(
            session_id,
            "assistant",
            result.get("explanation", "Changes generated."),
            workflow_name,
        )

        return jsonify({"status": "success", "data": result}), 200
    except Exception as e:
        error_msg = str(e)
        save_chat_message(session_id, "assistant", f"Error: {error_msg}", workflow_name)
        return jsonify({"error": error_msg}), 500


@edit_bp.route("/api/apply", methods=["POST"])
def apply():
    """
    Apply pending code changes to disk.

    Expected JSON body:
        { "changes": [{ "filePath": "...", "action": "modify", "fullContent": "..." }] }
    """
    body = request.get_json(force=True) or {}
    changes = body.get("changes", [])

    if not changes:
        return jsonify({"error": "No changes to apply"}), 400

    try:
        results = apply_changes(changes)
        return jsonify({"status": "applied", "results": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@edit_bp.route("/api/chat/history/<session_id>", methods=["GET"])
def chat_history(session_id: str):
    """Return chat history for a session."""
    history = get_chat_history(session_id)
    return jsonify({"history": history, "count": len(history)})
