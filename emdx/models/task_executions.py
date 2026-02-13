"""Task executions model - tracks how tasks are executed."""

from typing import Any, Optional

from emdx.database import db


def create_task_execution(
    task_id: int,
    execution_type: str,
    execution_id: Optional[int] = None,
    notes: Optional[str] = None,
    **kwargs,
) -> int:
    """Create a task execution record. Returns the execution ID.

    Args:
        task_id: The task being executed
        execution_type: 'direct' or 'manual'
        execution_id: Set if execution_type is 'direct'
        notes: Optional notes about the execution
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO task_executions
            (task_id, execution_type, execution_id, notes, status)
            VALUES (?, ?, ?, ?, 'running')
        """, (task_id, execution_type, execution_id, notes))
        conn.commit()
        return cursor.lastrowid


def get_task_execution(task_execution_id: int) -> Optional[dict[str, Any]]:
    """Get a task execution by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM task_executions WHERE id = ?",
            (task_execution_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_task_executions(
    task_id: Optional[int] = None,
    execution_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    **kwargs,
) -> list[dict[str, Any]]:
    """List task executions with optional filters."""
    conditions, params = ["1=1"], []

    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)
    if execution_type:
        conditions.append("execution_type = ?")
        params.append(execution_type)
    if status:
        conditions.append("status = ?")
        params.append(status)

    params.append(limit)

    with db.get_connection() as conn:
        cursor = conn.execute(f"""
            SELECT * FROM task_executions
            WHERE {' AND '.join(conditions)}
            ORDER BY started_at DESC LIMIT ?
        """, params)
        return [dict(row) for row in cursor.fetchall()]


def update_task_execution(
    task_execution_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> bool:
    """Update a task execution record."""
    updates, params = [], []

    if status:
        updates.append("status = ?")
        params.append(status)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if completed_at:
        updates.append("completed_at = ?")
        params.append(completed_at)

    if not updates:
        return False

    params.append(task_execution_id)

    with db.get_connection() as conn:
        cursor = conn.execute(f"""
            UPDATE task_executions
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        conn.commit()
        return cursor.rowcount > 0


def complete_task_execution(task_execution_id: int, success: bool = True) -> bool:
    """Mark a task execution as completed or failed."""
    status = 'completed' if success else 'failed'
    with db.get_connection() as conn:
        cursor = conn.execute("""
            UPDATE task_executions
            SET status = ?, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, task_execution_id))
        conn.commit()
        return cursor.rowcount > 0


def cancel_task_execution(task_execution_id: int) -> bool:
    """Cancel a running task execution."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            UPDATE task_executions
            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'running'
        """, (task_execution_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_latest_task_execution(task_id: int) -> Optional[dict[str, Any]]:
    """Get the most recent execution for a task."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM task_executions
            WHERE task_id = ?
            ORDER BY started_at DESC LIMIT 1
        """, (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_execution_stats(task_id: int) -> dict[str, Any]:
    """Get execution statistics for a task."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN execution_type = 'workflow' THEN 1 ELSE 0 END) as workflow_runs,
                SUM(CASE WHEN execution_type = 'direct' THEN 1 ELSE 0 END) as direct_runs,
                SUM(CASE WHEN execution_type = 'manual' THEN 1 ELSE 0 END) as manual_runs
            FROM task_executions
            WHERE task_id = ?
        """, (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else {
            'total': 0, 'completed': 0, 'failed': 0, 'running': 0,
            'workflow_runs': 0, 'direct_runs': 0, 'manual_runs': 0
        }
