"""
Components route — GET /api/components
Manages the reusable components registry.
"""

from flask import Blueprint, jsonify
from models.database import get_all_components, get_component_by_name

components_bp = Blueprint("components", __name__)


@components_bp.route("/api/components", methods=["GET"])
def list_components():
    """Return all reusable components."""
    components = get_all_components()
    return jsonify({"components": components, "count": len(components)})


@components_bp.route("/api/components/<name>", methods=["GET"])
def get_component(name: str):
    """Return a specific component by name."""
    component = get_component_by_name(name)
    if not component:
        return jsonify({"error": f"Component '{name}' not found"}), 404
    return jsonify(component)
