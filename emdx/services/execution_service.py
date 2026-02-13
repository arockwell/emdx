"""Execution service facade for the UI layer.

Provides a clean import boundary between UI code and the model layer
for execution tracking operations. Re-exports the Execution dataclass
so UI code doesn't need to reach into models directly.
"""

from emdx.database.connection import db_connection
from emdx.models.executions import (
    Execution,
    create_execution,
    get_execution,
    get_recent_executions,
    update_execution_pid,
    update_execution_status,
)

__all__ = [
    "Execution",
    "create_execution",
    "get_agent_executions",
    "get_execution",
    "get_execution_log_file",
    "get_recent_executions",
    "update_execution_pid",
    "update_execution_status",
]


def get_agent_executions(cutoff_iso: str, limit: int = 30) -> list[dict]:
    """Get standalone agent/delegate executions not part of a cascade."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at,
                   e.completed_at, e.log_file, e.exit_code, e.working_dir
            FROM executions e
            WHERE e.started_at > ?
              AND (e.doc_title LIKE 'Agent:%' OR e.doc_title LIKE 'Delegate:%')
              AND e.cascade_run_id IS NULL
            ORDER BY e.started_at DESC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "doc_id": row[1],
            "doc_title": row[2],
            "status": row[3],
            "started_at": row[4],
            "completed_at": row[5],
            "log_file": row[6],
            "exit_code": row[7],
            "working_dir": row[8],
        }
        for row in rows
    ]


def get_execution_log_file(doc_title_pattern: str) -> str | None:
    """Find the log file for a running execution matching a title pattern.

"""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT log_file FROM executions
            WHERE doc_title LIKE ?
            AND status = 'running'
            ORDER BY id DESC LIMIT 1
            """,
            (doc_title_pattern,),
        )
        row = cursor.fetchone()
        return row[0] if row else None
