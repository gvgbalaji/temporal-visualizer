"""
Analyzer service — orchestrates the temporal-visualizer skill.
Takes a workflow name and directory path, invokes the Claude skill
to analyze the code, and stores reusable components in the registry.
"""

import os
import glob
import json
import logging
from services.claude_runner import run_skill, extract_json_from_response
from models.database import upsert_component, save_workflow_analysis

logger = logging.getLogger(__name__)


def discover_python_files(directory: str) -> list[str]:
    """Find all Python files in a directory."""
    patterns = ["*.py"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(directory, pattern)))
    # Also check common subdirectories
    for subdir in ["activities", "workflows", "services", "helpers", "src"]:
        subpath = os.path.join(directory, subdir)
        if os.path.isdir(subpath):
            for pattern in patterns:
                files.extend(glob.glob(os.path.join(subpath, pattern)))
    result = sorted(set(files))
    logger.info(f"[ANALYZER] Discovered {len(result)} Python files in {directory}")
    for f in result:
        logger.info(f"[ANALYZER]   - {f}")
    return result


def read_files_content(file_paths: list[str]) -> str:
    """Read and concatenate file contents with headers."""
    parts = []
    for fp in file_paths:
        if os.path.exists(fp) and os.path.isfile(fp):
            try:
                with open(fp, "r") as f:
                    content = f.read()
                parts.append(f"--- FILE: {fp} ---\n{content}\n--- END FILE ---")
                logger.info(f"[ANALYZER] Read file: {fp} ({len(content)} chars)")
            except Exception as e:
                logger.error(f"[ANALYZER] Failed to read {fp}: {e}")
                continue
    combined = "\n\n".join(parts)
    logger.info(f"[ANALYZER] Total file content: {len(combined)} chars")
    return combined


def analyze_workflow(workflow_name: str, directory_path: str) -> dict:
    """
    Analyze a Temporal workflow using the temporal-visualizer Claude skill.
    """
    logger.info(f"[ANALYZER] ========================================")
    logger.info(f"[ANALYZER] Starting analysis: workflow='{workflow_name}', dir='{directory_path}'")
    logger.info(f"[ANALYZER] ========================================")

    # Validate directory exists
    if not os.path.isdir(directory_path):
        logger.error(f"[ANALYZER] Directory not found: {directory_path}")
        raise ValueError(f"Directory not found: {directory_path}")

    # Discover Python files
    py_files = discover_python_files(directory_path)
    if not py_files:
        logger.error(f"[ANALYZER] No Python files found in: {directory_path}")
        raise ValueError(f"No Python files found in: {directory_path}")

    # Read all file contents
    file_contents = read_files_content(py_files)
    if not file_contents:
        logger.error(f"[ANALYZER] Could not read any files from: {directory_path}")
        raise ValueError(f"Could not read any files from: {directory_path}")

    # Build arguments for the skill
    arguments = (
        f"Workflow Name: {workflow_name}\n"
        f"Directory Path: {directory_path}\n\n"
        f"## Source Files\n\n{file_contents}"
    )
    logger.info(f"[ANALYZER] Skill arguments built: {len(arguments)} chars")

    # Invoke the temporal-visualizer skill
    logger.info(f"[ANALYZER] Invoking temporal-visualizer skill...")
    try:
        raw_response = run_skill(
            skill_name="temporal-visualizer",
            arguments=arguments,
            cwd=directory_path,
            timeout=180,
        )
        logger.info(f"[ANALYZER] Skill returned response: {len(raw_response)} chars")
    except Exception as e:
        logger.error(f"[ANALYZER] Skill invocation FAILED: {type(e).__name__}: {e}")
        raise

    # Parse JSON from response
    logger.info(f"[ANALYZER] Parsing JSON from response...")
    try:
        result = extract_json_from_response(raw_response)
        logger.info(f"[ANALYZER] JSON parsed successfully. Keys: {list(result.keys())}")
    except Exception as e:
        logger.error(f"[ANALYZER] JSON parsing FAILED: {type(e).__name__}: {e}")
        raise

    # Store reusable components in the registry
    components = result.get("reusableComponents", [])
    logger.info(f"[ANALYZER] Storing {len(components)} reusable components...")
    for comp in components:
        try:
            upsert_component({
                "name": comp.get("name", "unknown"),
                "type": comp.get("type", "activity"),
                "description": comp.get("description", ""),
                "file_path": comp.get("filePath", ""),
                "line_start": comp.get("lineStart"),
                "line_end": comp.get("lineEnd"),
                "input_schema": comp.get("input", ""),
                "output_schema": comp.get("output", ""),
                "dependencies": comp.get("dependencies", []),
                "source_code": comp.get("sourceCode", ""),
            })
            logger.info(f"[ANALYZER]   Stored component: {comp.get('name')}")
        except Exception as e:
            logger.error(f"[ANALYZER]   Failed to store component {comp.get('name')}: {e}")

    # Save the workflow analysis
    logger.info(f"[ANALYZER] Saving workflow analysis to database...")
    try:
        canonical_name = result.get("workflow", {}).get("name", workflow_name)
        save_workflow_analysis(canonical_name, directory_path, result)
        logger.info(f"[ANALYZER] Workflow analysis saved successfully as '{canonical_name}'")
    except Exception as e:
        logger.error(f"[ANALYZER] Failed to save analysis: {e}")
        raise

    logger.info(f"[ANALYZER] ========================================")
    logger.info(f"[ANALYZER] Analysis complete for '{canonical_name}'")
    logger.info(f"[ANALYZER] ========================================")
    return result
