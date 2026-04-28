"""
Editor service — orchestrates the temporal-editor skill.
Takes user instructions + workflow context, invokes the Claude skill
to generate code changes, and optionally applies them.
"""

import os
import json
from services.claude_runner import run_skill, extract_json_from_response
from models.database import get_all_components, get_workflow_by_name, upsert_component


def read_workflow_files(directory_path: str) -> str:
    """Read all Python files from the workflow directory."""
    parts = []
    if os.path.isdir(directory_path):
        for fname in sorted(os.listdir(directory_path)):
            if fname.endswith(".py"):
                fp = os.path.join(directory_path, fname)
                try:
                    with open(fp, "r") as f:
                        content = f.read()
                    parts.append(f"--- FILE: {fp} ---\n{content}\n--- END FILE ---")
                except Exception:
                    continue
    return "\n\n".join(parts)


def edit_workflow(user_request: str, workflow_name: str) -> dict:
    """
    Process a user edit request using the temporal-editor Claude skill.

    Args:
        user_request: Natural language instruction from the user
        workflow_name: Name of the workflow to edit

    Returns:
        Dict with changes to apply
    """
    # Get the current workflow analysis
    workflow_record = get_workflow_by_name(workflow_name)
    if not workflow_record:
        raise ValueError(f"Workflow '{workflow_name}' not found. Please analyze it first.")

    workflow_json = json.dumps(workflow_record["workflow_json"], indent=2)
    directory_path = workflow_record["directory_path"]

    # Get available reusable components
    components = get_all_components()
    components_json = json.dumps(components, indent=2, default=str)

    # Read current source files
    file_contents = read_workflow_files(directory_path)

    # Build arguments for the skill
    arguments = (
        f"## User Request\n{user_request}\n\n"
        f"## Current Workflow Analysis\n{workflow_json}\n\n"
        f"## Available Reusable Components\n{components_json}\n\n"
        f"## Current Source Files\n{file_contents}"
    )

    # Invoke the temporal-editor skill
    raw_response = run_skill(
        skill_name="temporal-editor",
        arguments=arguments,
        cwd=directory_path,
        timeout=180,
    )

    # Parse response
    result = extract_json_from_response(raw_response)

    # Register any new components discovered
    for comp in result.get("newComponents", []):
        upsert_component({
            "name": comp["name"],
            "type": comp.get("type", "activity"),
            "description": comp.get("description", ""),
            "file_path": directory_path,
            "line_start": None,
            "line_end": None,
            "input_schema": comp.get("input", ""),
            "output_schema": comp.get("output", ""),
            "dependencies": comp.get("dependencies", []),
            "source_code": comp.get("sourceCode", ""),
        })

    return result


def apply_changes(changes: list[dict]) -> list[dict]:
    """
    Apply code changes to disk.

    Args:
        changes: List of change dicts from the editor

    Returns:
        List of results for each change
    """
    results = []
    for change in changes:
        file_path = change.get("filePath", "")
        action = change.get("action", "modify")

        try:
            if action == "create":
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(change.get("fullContent", ""))
                results.append({"file": file_path, "status": "created"})

            elif action == "modify":
                with open(file_path, "w") as f:
                    f.write(change.get("fullContent", ""))
                results.append({"file": file_path, "status": "modified"})

            elif action == "append":
                with open(file_path, "a") as f:
                    f.write("\n\n" + change.get("appendContent", ""))
                results.append({"file": file_path, "status": "appended"})

            else:
                results.append({"file": file_path, "status": "error", "error": f"Unknown action: {action}"})

        except Exception as e:
            results.append({"file": file_path, "status": "error", "error": str(e)})

    return results
