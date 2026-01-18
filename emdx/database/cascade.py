"""Database operations for cascade runs.

This module provides CRUD operations for cascade_runs table,
which tracks end-to-end cascade executions for activity grouping.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .connection import db_connection


# ============================================================================
# Cascade Run Operations
# ============================================================================


def create_cascade_run(
    initial_doc_id: int,
    current_stage: str = "idea",
) -> int:
    """Create a new cascade run.

    Args:
        initial_doc_id: ID of the starting document
        current_stage: Current stage (defaults to "idea")

    Returns:
        ID of the created run
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO cascade_runs (initial_doc_id, status, current_stage, started_at)
            VALUES (?, 'running', ?, CURRENT_TIMESTAMP)
            """,
            (initial_doc_id, current_stage),
        )
        conn.commit()
        return cursor.lastrowid


def update_cascade_run_stage(run_id: int, stage: str) -> None:
    """Update the current stage of a cascade run.

    Args:
        run_id: Cascade run ID
        stage: New current stage
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE cascade_runs
            SET current_stage = ?
            WHERE id = ?
            """,
            (stage, run_id),
        )
        conn.commit()


def complete_cascade_run(
    run_id: int,
    success: bool = True,
    error_msg: Optional[str] = None,
) -> None:
    """Mark a cascade run as completed or failed.

    Args:
        run_id: Cascade run ID
        success: Whether the run completed successfully
        error_msg: Error message if failed
    """
    status = "completed" if success else "failed"
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE cascade_runs
            SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
            WHERE id = ?
            """,
            (status, error_msg, run_id),
        )
        conn.commit()


def cancel_cascade_run(run_id: int) -> None:
    """Cancel a cascade run.

    Args:
        run_id: Cascade run ID
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE cascade_runs
            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (run_id,),
        )
        conn.commit()


def get_cascade_run(run_id: int) -> Optional[Dict[str, Any]]:
    """Get a cascade run by ID.

    Args:
        run_id: Cascade run ID

    Returns:
        Run dict or None if not found
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT cr.id, cr.initial_doc_id, cr.status,
                   cr.current_stage, cr.started_at, cr.completed_at, cr.error_message,
                   d.title as initial_doc_title
            FROM cascade_runs cr
            LEFT JOIN documents d ON cr.initial_doc_id = d.id
            WHERE cr.id = ?
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if row:
            return _row_to_run(row)
    return None


def list_cascade_runs(
    limit: int = 50,
    status: Optional[str] = None,
    include_executions: bool = False,
) -> List[Dict[str, Any]]:
    """List cascade runs.

    Args:
        limit: Maximum number of runs to return
        status: Filter by status ('running', 'completed', 'failed', 'cancelled')
        include_executions: Include linked executions

    Returns:
        List of run dicts
    """
    with db_connection.get_connection() as conn:
        if status:
            cursor = conn.execute(
                """
                SELECT cr.id, cr.initial_doc_id, cr.status,
                       cr.current_stage, cr.started_at, cr.completed_at, cr.error_message,
                       d.title as initial_doc_title
                FROM cascade_runs cr
                LEFT JOIN documents d ON cr.initial_doc_id = d.id
                WHERE cr.status = ?
                ORDER BY cr.started_at DESC
                LIMIT ?
                """,
                (status, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT cr.id, cr.initial_doc_id, cr.status,
                       cr.current_stage, cr.started_at, cr.completed_at, cr.error_message,
                       d.title as initial_doc_title
                FROM cascade_runs cr
                LEFT JOIN documents d ON cr.initial_doc_id = d.id
                ORDER BY cr.started_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        runs = [_row_to_run(row) for row in cursor.fetchall()]

        if include_executions:
            for run in runs:
                run["executions"] = get_cascade_run_executions(run["id"])

        return runs


def get_cascade_run_executions(run_id: int) -> List[Dict[str, Any]]:
    """Get executions linked to a cascade run.

    Args:
        run_id: Cascade run ID

    Returns:
        List of execution dicts
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at, e.completed_at,
                   d.stage as doc_stage
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.cascade_run_id = ?
            ORDER BY e.started_at
            """,
            (run_id,),
        )
        return [
            {
                "id": row["id"],
                "doc_id": row["doc_id"],
                "doc_title": row["doc_title"],
                "status": row["status"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "doc_stage": row["doc_stage"],
            }
            for row in cursor.fetchall()
        ]


def link_execution_to_run(execution_id: int, run_id: int) -> None:
    """Link an execution to a cascade run.

    Args:
        execution_id: Execution ID
        run_id: Cascade run ID
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE executions
            SET cascade_run_id = ?
            WHERE id = ?
            """,
            (run_id, execution_id),
        )
        conn.commit()


def _row_to_run(row) -> Dict[str, Any]:
    """Convert a database row to a run dict."""
    return {
        "id": row["id"],
        "initial_doc_id": row["initial_doc_id"],
        "status": row["status"],
        "current_stage": row["current_stage"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "error_message": row["error_message"],
        "initial_doc_title": row["initial_doc_title"],
    }
