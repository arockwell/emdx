"""Execution tracking models and database operations."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..database.connection import db_connection
from ..utils.datetime_utils import parse_timestamp
from .types import ExecutionStatsDict


@dataclass
class Execution:
    """Represents a Claude execution."""

    id: int  # Now numeric auto-incrementing ID
    doc_id: int | None  # Can be None for standalone delegate executions
    doc_title: str
    status: str  # 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: datetime | None = None
    log_file: str = ""
    exit_code: int | None = None
    working_dir: str | None = None
    pid: int | None = None
    task_id: int | None = None
    cost_usd: float | None = None
    tokens_used: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    output_text: str | None = None

    @property
    def duration(self) -> float | None:
        """Get execution duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        """Check if execution is still running."""
        return self.status == "running"

    @property
    def is_zombie(self) -> bool:
        """Check if this is a zombie process (marked running but process is dead)."""
        if not self.is_running or not self.pid:
            return False

        # Check if process exists
        try:
            # Send signal 0 to check if process exists
            os.kill(self.pid, 0)
            return False  # Process exists
        except ProcessLookupError:
            return True  # Process doesn't exist - zombie!
        except PermissionError:
            # Process exists but we can't access it
            return False

    @property
    def log_path(self) -> Path:
        """Get Path object for log file."""
        return Path(self.log_file).expanduser()


def create_execution(
    doc_id: int | None,
    doc_title: str,
    log_file: str,
    working_dir: str | None = None,
    pid: int | None = None,
) -> int:
    """Create a new execution and return its ID.

    Args:
        doc_id: Document ID (can be None for standalone delegate executions)
        doc_title: Title for the execution
        log_file: Path to log file
        working_dir: Working directory for execution
        pid: Process ID

    Returns:
        Created execution ID
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO executions
            (doc_id, doc_title, status, started_at, log_file, working_dir, pid)
            VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?, ?, ?)
        """,
            (doc_id, doc_title, log_file, working_dir, pid),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def get_execution(exec_id: int) -> Execution | None:
    """Get execution by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, doc_id, doc_title, status, started_at, completed_at,
                   log_file, exit_code, working_dir, pid, output_text
            FROM executions WHERE id = ?
        """,
            (exec_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        # Parse timestamps with centralized datetime utility
        started_at = parse_timestamp(row[4])
        completed_at = parse_timestamp(row[5]) if row[5] else None

        return Execution(
            id=row[0],
            doc_id=row[1],
            doc_title=row[2],
            status=row[3],
            started_at=started_at,
            completed_at=completed_at,
            log_file=row[6],
            exit_code=row[7],
            working_dir=row[8],
            pid=row[9] if len(row) > 9 else None,
            output_text=row[10] if len(row) > 10 else None,
        )


def get_recent_executions(limit: int = 20) -> list[Execution]:
    """Get recent executions ordered by start time."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, doc_id, doc_title, status, started_at, completed_at,
                   log_file, exit_code, working_dir, pid, output_text
            FROM executions
            ORDER BY id DESC
            LIMIT ?
        """,
            (limit,),
        )

        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None

            executions.append(
                Execution(
                    id=int(row[0]),  # Convert to int for numeric ID
                    doc_id=row[1],
                    doc_title=row[2],
                    status=row[3],
                    started_at=started_at,
                    completed_at=completed_at,
                    log_file=row[6],
                    exit_code=row[7],
                    working_dir=row[8],
                    pid=row[9] if len(row) > 9 else None,
                    output_text=row[10] if len(row) > 10 else None,
                )
            )

        return executions


def get_running_executions() -> list[Execution]:
    """Get all currently running executions."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, doc_id, doc_title, status, started_at, completed_at,
                   log_file, exit_code, working_dir, pid, output_text
            FROM executions
            WHERE status = 'running'
            ORDER BY started_at DESC
        """,
        )

        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None

            executions.append(
                Execution(
                    id=int(row[0]),  # Convert to int for numeric ID
                    doc_id=row[1],
                    doc_title=row[2],
                    status=row[3],
                    started_at=started_at,
                    completed_at=completed_at,
                    log_file=row[6],
                    exit_code=row[7],
                    working_dir=row[8],
                    pid=row[9] if len(row) > 9 else None,
                    output_text=row[10] if len(row) > 10 else None,
                )
            )

        return executions


def update_execution_status(exec_id: int, status: str, exit_code: int | None = None) -> None:
    """Update execution status and completion time."""
    with db_connection.get_connection() as conn:
        if status in ["completed", "failed"]:
            conn.execute(
                """
                UPDATE executions
                SET status = ?, completed_at = CURRENT_TIMESTAMP, exit_code = ?
                WHERE id = ?
            """,
                (status, exit_code, exec_id),
            )
        else:
            conn.execute(
                """
                UPDATE executions
                SET status = ?
                WHERE id = ?
            """,
                (status, exec_id),
            )

        conn.commit()


# Allowed columns for execution updates (prevents SQL injection via column names)
ALLOWED_EXECUTION_COLUMNS = frozenset(
    {
        "doc_id",
        "doc_title",
        "status",
        "completed_at",
        "log_file",
        "exit_code",
        "working_dir",
        "pid",
        "task_id",
        "cost_usd",
        "tokens_used",
        "input_tokens",
        "output_tokens",
        "output_text",
    }
)


def update_execution(exec_id: int, **kwargs: Any) -> None:
    """Update arbitrary execution fields (doc_id, cost_usd, tokens, task_id, etc.).

    Only columns in ALLOWED_EXECUTION_COLUMNS can be updated.
    Unknown columns are silently ignored.
    """
    if not kwargs:
        return

    # Filter to only allowed columns
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_EXECUTION_COLUMNS}
    if not filtered_kwargs:
        return

    sets = [f"{k} = ?" for k in filtered_kwargs]
    params = list(filtered_kwargs.values()) + [exec_id]
    with db_connection.get_connection() as conn:
        conn.execute(
            f"UPDATE executions SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()


def update_execution_pid(exec_id: int, pid: int) -> None:
    """Update execution PID."""
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE executions
            SET pid = ?
            WHERE id = ?
        """,
            (pid, exec_id),
        )
        conn.commit()


def update_execution_working_dir(exec_id: int, working_dir: str) -> None:
    """Update execution working directory."""
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE executions
            SET working_dir = ?
            WHERE id = ?
        """,
            (working_dir, exec_id),
        )
        conn.commit()


def update_execution_heartbeat(exec_id: int) -> None:
    """Update execution heartbeat timestamp.

    Note: last_heartbeat column was dropped in migration 013.
    This now updates the started_at as a proxy for liveness.
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            UPDATE executions
            SET started_at = started_at
            WHERE id = ? AND status = 'running'
        """,
            (exec_id,),
        )
        conn.commit()


def get_stale_executions(timeout_seconds: int = 1800) -> list[Execution]:
    """Get executions that haven't sent a heartbeat recently.

    Args:
        timeout_seconds: Seconds after which an execution is considered stale (default 30 min)

    Returns:
        List of stale executions
    """
    # Validate timeout_seconds is a positive integer to prevent SQL injection
    if not isinstance(timeout_seconds, int) or timeout_seconds < 0:
        raise ValueError("timeout_seconds must be a non-negative integer")

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        # Build interval string safely - timeout_seconds is validated as int by function signature
        interval = f"+{int(timeout_seconds)} seconds"
        cursor.execute(
            """
            SELECT id, doc_id, doc_title, status, started_at, completed_at,
                   log_file, exit_code, working_dir, pid, output_text
            FROM executions
            WHERE status = 'running'
            AND datetime('now') > datetime(started_at, ?)
            ORDER BY started_at DESC
        """,
            (interval,),
        )

        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None

            executions.append(
                Execution(
                    id=int(row[0]),
                    doc_id=row[1],
                    doc_title=row[2],
                    status=row[3],
                    started_at=started_at,
                    completed_at=completed_at,
                    log_file=row[6],
                    exit_code=row[7],
                    working_dir=row[8],
                    pid=row[9] if len(row) > 9 else None,
                    output_text=row[10] if len(row) > 10 else None,
                )
            )

        return executions


def cleanup_old_executions(days: int = 7) -> int:
    """Clean up executions older than specified days.

    Args:
        days: Number of days to keep executions (must be positive)

    Returns:
        Number of executions deleted

    Raises:
        ValueError: If days is not positive
    """
    if days <= 0:
        raise ValueError("days must be positive")

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        # Build interval string safely - days is validated as int by function signature
        interval = f"-{int(days)} days"
        cursor.execute(
            """
            DELETE FROM executions
            WHERE started_at < datetime('now', ?)
        """,
            (interval,),
        )
        conn.commit()
        return int(cursor.rowcount)


def get_execution_stats() -> ExecutionStatsDict:
    """Get execution statistics."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*)
            FROM executions
            GROUP BY status
        """)
        status_counts = dict(cursor.fetchall())

        # Total executions
        cursor.execute("SELECT COUNT(*) FROM executions")
        total_result = cursor.fetchone()
        total = total_result[0] if total_result else 0

        # Recent activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) FROM executions
            WHERE started_at > datetime('now', '-1 day')
        """)
        recent_result = cursor.fetchone()
        recent = recent_result[0] if recent_result else 0

        return {
            "total": total,
            "recent_24h": recent,
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
        }
