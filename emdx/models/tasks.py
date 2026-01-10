"""Task operations for emdx."""

from typing import Any, Optional

from emdx.database import db

# Valid status values
STATUSES = ('open', 'active', 'blocked', 'done', 'failed')


def create_task(
    title: str,
    description: str = "",
    priority: int = 3,
    gameplan_id: Optional[int] = None,
    project: Optional[str] = None,
    depends_on: Optional[list[int]] = None,
) -> int:
    """Create task and return its ID."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (title, description, priority, gameplan_id, project)
            VALUES (?, ?, ?, ?, ?)
        """, (title, description, priority, gameplan_id, project))
        task_id = cursor.lastrowid

        if depends_on:
            # Use executemany for efficient batch insertion
            cursor.executemany(
                "INSERT INTO task_deps (task_id, depends_on) VALUES (?, ?)",
                [(task_id, dep_id) for dep_id in depends_on]
            )
        conn.commit()
        return task_id


def get_task(task_id: int) -> Optional[dict[str, Any]]:
    """Get task by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_tasks(
    status: Optional[list[str]] = None,
    gameplan_id: Optional[int] = None,
    project: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List tasks with filters."""
    conditions, params = ["1=1"], []

    if status:
        conditions.append(f"status IN ({','.join('?' * len(status))})")
        params.extend(status)
    if gameplan_id:
        conditions.append("gameplan_id = ?")
        params.append(gameplan_id)
    if project:
        conditions.append("project = ?")
        params.append(project)

    params.append(limit)

    with db.get_connection() as conn:
        cursor = conn.execute(f"""
            SELECT * FROM tasks WHERE {' AND '.join(conditions)}
            ORDER BY priority, created_at DESC LIMIT ?
        """, params)
        return [dict(row) for row in cursor.fetchall()]


def update_task(task_id: int, **kwargs) -> bool:
    """Update task fields."""
    if not kwargs:
        return False

    sets = []
    params = []

    for key, value in kwargs.items():
        sets.append(f"{key} = ?")
        params.append(value)
        # Set completed_at when status becomes done
        if key == 'status' and value == 'done':
            sets.append("completed_at = CURRENT_TIMESTAMP")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)

    with db.get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_task(task_id: int) -> bool:
    """Delete task."""
    with db.get_connection() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_dependencies(task_id: int) -> list[dict[str, Any]]:
    """Get tasks this task depends on."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.* FROM tasks t
            JOIN task_deps d ON t.id = d.depends_on
            WHERE d.task_id = ?
        """, (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_dependents(task_id: int) -> list[dict[str, Any]]:
    """Get tasks that depend on this task (tasks this one blocks)."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.* FROM tasks t
            JOIN task_deps d ON t.id = d.task_id
            WHERE d.depends_on = ?
        """, (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_ready_tasks(gameplan_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Get tasks ready to work (open + all deps done)."""
    conditions = ["t.status = 'open'"]
    params = []

    if gameplan_id:
        conditions.append("t.gameplan_id = ?")
        params.append(gameplan_id)

    with db.get_connection() as conn:
        cursor = conn.execute(f"""
            SELECT t.* FROM tasks t
            WHERE {' AND '.join(conditions)}
            AND NOT EXISTS (
                SELECT 1 FROM task_deps d
                JOIN tasks dep ON d.depends_on = dep.id
                WHERE d.task_id = t.id AND dep.status != 'done'
            )
            ORDER BY t.priority, t.created_at
        """, params)
        return [dict(row) for row in cursor.fetchall()]


def add_dependency(task_id: int, depends_on: int) -> bool:
    """Add dependency. Returns False if would create cycle."""
    if task_id == depends_on:
        return False
    if _would_cycle(task_id, depends_on):
        return False

    with db.get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO task_deps (task_id, depends_on) VALUES (?, ?)",
                (task_id, depends_on)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Dependency already exists or would create invalid state
            return False
        except sqlite3.Error as e:
            # Other database error
            import logging
            logging.error(f"Database error adding task dependency: {e}")
            return False


def _would_cycle(task_id: int, new_dep: int) -> bool:
    """Check if adding dep would create cycle (DFS)."""
    visited, stack = set(), [new_dep]
    with db.get_connection() as conn:
        while stack:
            current = stack.pop()
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            cursor = conn.execute(
                "SELECT depends_on FROM task_deps WHERE task_id = ?", (current,)
            )
            stack.extend(row[0] for row in cursor.fetchall())
    return False


def log_progress(task_id: int, message: str) -> int:
    """Add entry to task log."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO task_log (task_id, message) VALUES (?, ?)",
            (task_id, message)
        )
        conn.execute(
            "UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,)
        )
        conn.commit()
        return cursor.lastrowid


def get_task_log(task_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Get task log entries."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM task_log WHERE task_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (task_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_gameplan_stats(gameplan_id: int) -> dict[str, Any]:
    """Get task stats for a gameplan."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT status, COUNT(*) as count FROM tasks
            WHERE gameplan_id = ? GROUP BY status
        """, (gameplan_id,))
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}
        total = sum(by_status.values())
        done = by_status.get('done', 0)
        return {'total': total, 'done': done, 'by_status': by_status}
