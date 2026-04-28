"""
Database module for the reusable components registry.
Stores analyzed workflow components (activities, helpers, workflows)
so they can be reused by the editor skill.
"""

import sqlite3
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "components.db")


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialise the database schema."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reusable_components (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL UNIQUE,
                type            TEXT NOT NULL,
                description     TEXT,
                file_path       TEXT NOT NULL,
                line_start      INTEGER,
                line_end        INTEGER,
                input_schema    TEXT,
                output_schema   TEXT,
                dependencies    TEXT,
                source_code     TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyzed_workflows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                directory_path  TEXT NOT NULL,
                workflow_json   TEXT NOT NULL,
                analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, directory_path)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                workflow_name   TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    conn.close()
    print(f"[DB] Initialised database at: {DB_PATH}")


def upsert_component(component: dict) -> None:
    """Insert or update a reusable component."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO reusable_components
                (name, type, description, file_path, line_start, line_end,
                 input_schema, output_schema, dependencies, source_code, updated_at)
            VALUES
                (:name, :type, :description, :file_path, :line_start, :line_end,
                 :input_schema, :output_schema, :dependencies, :source_code, :updated_at)
            ON CONFLICT(name) DO UPDATE SET
                type = excluded.type,
                description = excluded.description,
                file_path = excluded.file_path,
                line_start = excluded.line_start,
                line_end = excluded.line_end,
                input_schema = excluded.input_schema,
                output_schema = excluded.output_schema,
                dependencies = excluded.dependencies,
                source_code = excluded.source_code,
                updated_at = excluded.updated_at
            """,
            {
                **component,
                "input_schema": json.dumps(component.get("input_schema", {})),
                "output_schema": json.dumps(component.get("output_schema", {})),
                "dependencies": json.dumps(component.get("dependencies", [])),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    conn.close()


def get_all_components() -> list[dict]:
    """Return all reusable components."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reusable_components ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["input_schema"] = json.loads(d["input_schema"]) if d["input_schema"] else {}
        d["output_schema"] = json.loads(d["output_schema"]) if d["output_schema"] else {}
        d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else []
        result.append(d)
    return result


def get_component_by_name(name: str) -> dict | None:
    """Return a single component by name."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reusable_components WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["input_schema"] = json.loads(d["input_schema"]) if d["input_schema"] else {}
        d["output_schema"] = json.loads(d["output_schema"]) if d["output_schema"] else {}
        d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else []
        return d
    return None


def save_workflow_analysis(name: str, directory_path: str, workflow_json: dict) -> None:
    """Save or update an analyzed workflow."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO analyzed_workflows (name, directory_path, workflow_json, analyzed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name, directory_path) DO UPDATE SET
                workflow_json = excluded.workflow_json,
                analyzed_at = excluded.analyzed_at
            """,
            (name, directory_path, json.dumps(workflow_json), datetime.utcnow().isoformat()),
        )
    conn.close()


def get_analyzed_workflows() -> list[dict]:
    """Return all analyzed workflows."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analyzed_workflows ORDER BY analyzed_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["workflow_json"] = json.loads(d["workflow_json"])
        result.append(d)
    return result


def get_workflow_by_name(name: str) -> dict | None:
    """Return an analyzed workflow by name."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM analyzed_workflows WHERE name = ? ORDER BY analyzed_at DESC LIMIT 1",
        (name,),
    ).fetchone()
    
    # Fallback: try to find it by checking if it matches the JSON name
    if not row:
        rows = conn.execute("SELECT * FROM analyzed_workflows ORDER BY analyzed_at DESC").fetchall()
        for r in rows:
            d = dict(r)
            try:
                wf_json = json.loads(d["workflow_json"])
                if wf_json.get("workflow", {}).get("name") == name:
                    d["workflow_json"] = wf_json
                    conn.close()
                    return d
            except json.JSONDecodeError:
                continue

    conn.close()
    if row:
        d = dict(row)
        d["workflow_json"] = json.loads(d["workflow_json"])
        return d
    return None


def save_chat_message(session_id: str, role: str, content: str, workflow_name: str = None) -> None:
    """Save a chat message."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO chat_history (session_id, role, content, workflow_name)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, workflow_name),
        )
    conn.close()


def get_chat_history(session_id: str, limit: int = 50) -> list[dict]:
    """Return chat history for a session."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM chat_history
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
