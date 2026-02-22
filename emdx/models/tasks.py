"""Task operations for emdx."""

import re
import sqlite3
from typing import Any, cast

from emdx.config.constants import (
    DEFAULT_BROWSE_LIMIT,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_TASK_PRIORITY,
)
from emdx.database import db
from emdx.models.types import (
    ActiveDelegateTaskDict,
    EpicTaskDict,
    EpicViewDict,
    TaskDict,
    TaskLogEntryDict,
)

# Valid status values
STATUSES = ("open", "active", "blocked", "done", "failed", "wontdo")


def create_task(
    title: str,
    description: str = "",
    priority: int = DEFAULT_TASK_PRIORITY,
    gameplan_id: int | None = None,
    project: str | None = None,
    depends_on: list[int] | None = None,
    # Delegate activity tracking fields
    prompt: str | None = None,
    task_type: str = "single",
    execution_id: int | None = None,
    output_doc_id: int | None = None,
    source_doc_id: int | None = None,
    parent_task_id: int | None = None,
    seq: int | None = None,
    retry_of: int | None = None,
    tags: str | None = None,
    status: str = "open",
    epic_key: str | None = None,
) -> int:
    """Create task and return its ID.

    When epic_key is set:
      - Auto-creates category if needed
      - Assigns next epic_seq (epics and tasks share one sequence)
      - Prepends "KEY-N: " to title for non-epic tasks only
    """
    epic_seq_val = None

    if epic_key:
        from emdx.models.categories import ensure_category

        epic_key = ensure_category(epic_key.upper())

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Auto-number tasks within a category (epics and regular tasks share one sequence)
        if epic_key:
            cursor.execute(
                "SELECT COALESCE(MAX(epic_seq), 0) + 1 FROM tasks WHERE epic_key = ?",
                (epic_key,),
            )
            seq_result = cursor.fetchone()
            epic_seq_val = seq_result[0] if seq_result else 1
            # Prepend KEY-N: prefix to non-epic tasks only (epics use their title as-is)
            if task_type != "epic":
                prefix = f"{epic_key}-{epic_seq_val}: "
                if not title.startswith(prefix):
                    title = f"{prefix}{title}"

        cursor.execute(
            """
            INSERT INTO tasks (
                title, description, priority, gameplan_id, project, status,
                prompt, type, execution_id, output_doc_id, source_doc_id,
                parent_task_id, seq, retry_of, tags,
                epic_key, epic_seq
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                title,
                description,
                priority,
                gameplan_id,
                project,
                status,
                prompt,
                task_type,
                execution_id,
                output_doc_id,
                source_doc_id,
                parent_task_id,
                seq,
                retry_of,
                tags,
                epic_key,
                epic_seq_val,
            ),
        )
        task_id = cursor.lastrowid
        assert task_id is not None

        if depends_on:
            # Use executemany for efficient batch insertion
            cursor.executemany(
                "INSERT INTO task_deps (task_id, depends_on) VALUES (?, ?)",
                [(task_id, dep_id) for dep_id in depends_on if dep_id is not None],
            )
        conn.commit()
        return task_id


def create_epic(name: str, category_key: str, description: str = "") -> int:
    """Create an epic task. Returns task ID."""
    return create_task(
        title=name,
        description=description,
        task_type="epic",
        epic_key=category_key.upper(),
    )


def delete_epic(epic_id: int, force: bool = False) -> dict[str, int]:
    """Delete an epic task and handle orphaned children.

    If force=False (default), refuses to delete if open/active child tasks exist.
    If force=True, unlinks all children (clears parent_task_id), then deletes the epic.

    Returns dict with counts: children_unlinked.
    Raises ValueError if epic not found, not an epic, or has open children (when not forced).
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND type = 'epic'",
            (epic_id,),
        )
        epic = cursor.fetchone()
        if not epic:
            raise ValueError(f"Epic #{epic_id} not found")

        # Count open/active children
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE parent_task_id = ? AND status IN ('open', 'active')",
            (epic_id,),
        )
        open_count = cursor.fetchone()[0]

        if open_count > 0 and not force:
            raise ValueError(
                f"Epic #{epic_id} has {open_count} open/active child task(s). "
                f"Use --force to delete anyway."
            )

        # Count children that will be unlinked
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE parent_task_id = ?",
            (epic_id,),
        )
        children_unlinked = cursor.fetchone()[0]

        # Unlink children (don't delete them)
        conn.execute(
            "UPDATE tasks SET parent_task_id = NULL WHERE parent_task_id = ?",
            (epic_id,),
        )

        # Delete the epic task itself
        conn.execute("DELETE FROM tasks WHERE id = ?", (epic_id,))
        conn.commit()

    return {"children_unlinked": children_unlinked}


def get_task(task_id: int) -> TaskDict | None:
    """Get task by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return cast(TaskDict, dict(row)) if row else None


_PREFIXED_ID_RE = re.compile(r"^([A-Za-z]+)-(\d+)$")


def resolve_task_id(identifier: str) -> int | None:
    """Resolve a task identifier to a database ID.

    Accepts:
      - Category-prefixed IDs like "TOOL-12" (looks up by epic_key + epic_seq)
      - Raw integer IDs like "42" or "#42"

    Returns the database ID, or None if the format is invalid or task not found.
    """
    identifier = identifier.strip().lstrip("#")

    # Try plain integer first
    if identifier.isdigit():
        return int(identifier)

    # Try category-prefixed format (e.g. TOOL-12)
    match = _PREFIXED_ID_RE.match(identifier)
    if match:
        epic_key = match.group(1).upper()
        epic_seq = int(match.group(2))
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM tasks WHERE epic_key = ? AND epic_seq = ?",
                (epic_key, epic_seq),
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

    return None


def list_tasks(
    status: list[str] | None = None,
    gameplan_id: int | None = None,
    project: str | None = None,
    limit: int = DEFAULT_BROWSE_LIMIT,
    exclude_delegate: bool = False,
    epic_key: str | None = None,
    parent_task_id: int | None = None,
) -> list[TaskDict]:
    """List tasks with filters.

    Args:
        exclude_delegate: If True, exclude delegate-created tasks (prompt IS NULL).
        epic_key: Filter by category key.
        parent_task_id: Filter by parent task (epic) ID.
    """
    conditions: list[str] = ["1=1"]
    params: list[str | int | None] = []

    if status:
        conditions.append(f"status IN ({','.join('?' * len(status))})")
        params.extend(status)
    if gameplan_id:
        conditions.append("gameplan_id = ?")
        params.append(gameplan_id)
    if project:
        conditions.append("project = ?")
        params.append(project)
    if exclude_delegate:
        conditions.append("prompt IS NULL")
    if epic_key:
        conditions.append("epic_key = ?")
        params.append(epic_key.upper())
    if parent_task_id is not None:
        conditions.append("parent_task_id = ?")
        params.append(parent_task_id)

    params.append(limit)

    with db.get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT * FROM tasks WHERE {" AND ".join(conditions)}
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'blocked' THEN 1
                    WHEN 'open' THEN 2
                    WHEN 'failed' THEN 3
                    WHEN 'done' THEN 4
                    WHEN 'wontdo' THEN 5
                END,
                priority,
                created_at DESC
            LIMIT ?
        """,
            params,
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


# Allowed columns for task updates (prevents SQL injection via column names)
ALLOWED_UPDATE_COLUMNS = frozenset(
    {
        "title",
        "description",
        "priority",
        "status",
        "error",
        "gameplan_id",
        "project",
        "prompt",
        "type",
        "execution_id",
        "output_doc_id",
        "source_doc_id",
        "parent_task_id",
        "seq",
        "retry_of",
        "tags",
        "epic_key",
        "epic_seq",
    }
)


def update_task(task_id: int, **kwargs: Any) -> bool:
    """Update task fields.

    Only columns in ALLOWED_UPDATE_COLUMNS can be updated.
    Unknown columns are silently ignored.
    """
    if not kwargs:
        return False

    # Filter to only allowed columns
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_UPDATE_COLUMNS}
    if not filtered_kwargs:
        return False

    sets = []
    params = []

    for key, value in filtered_kwargs.items():
        sets.append(f"{key} = ?")
        params.append(value)
        # Set completed_at when status becomes done
        if key == "status" and value in ("done", "wontdo"):
            sets.append("completed_at = CURRENT_TIMESTAMP")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)

    with db.get_connection() as conn:
        cursor = conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0


def delete_task(task_id: int) -> bool:
    """Delete task."""
    with db.get_connection() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_dependencies(task_id: int) -> list[TaskDict]:
    """Get tasks this task depends on."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.* FROM tasks t
            JOIN task_deps d ON t.id = d.depends_on
            WHERE d.task_id = ?
        """,
            (task_id,),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def get_dependents(task_id: int) -> list[TaskDict]:
    """Get tasks that depend on this task (tasks this one blocks)."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.* FROM tasks t
            JOIN task_deps d ON t.id = d.task_id
            WHERE d.depends_on = ?
        """,
            (task_id,),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def get_ready_tasks(
    gameplan_id: int | None = None,
    exclude_delegate: bool = True,
    epic_key: str | None = None,
) -> list[TaskDict]:
    """Get tasks ready to work (open + all deps done).

    Args:
        exclude_delegate: If True (default), exclude delegate-created tasks.
        epic_key: Filter by category key.
    """
    conditions = ["t.status = 'open'"]
    params: list[str | int | None] = []

    if gameplan_id:
        conditions.append("t.gameplan_id = ?")
        params.append(gameplan_id)
    if exclude_delegate:
        conditions.append("t.prompt IS NULL")
    if epic_key:
        conditions.append("t.epic_key = ?")
        params.append(epic_key.upper())

    with db.get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT t.* FROM tasks t
            WHERE {" AND ".join(conditions)}
            AND NOT EXISTS (
                SELECT 1 FROM task_deps d
                JOIN tasks dep ON d.depends_on = dep.id
                WHERE d.task_id = t.id AND dep.status NOT IN ('done', 'wontdo')
            )
            ORDER BY t.priority, t.created_at
        """,
            params,
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def add_dependency(task_id: int, depends_on: int) -> bool:
    """Add dependency. Returns False if would create cycle."""
    if task_id == depends_on:
        return False
    if _would_cycle(task_id, depends_on):
        return False

    with db.get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO task_deps (task_id, depends_on) VALUES (?, ?)", (task_id, depends_on)
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


def remove_dependency(task_id: int, depends_on: int) -> bool:
    """Remove a dependency. Returns True if it existed."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM task_deps WHERE task_id = ? AND depends_on = ?",
            (task_id, depends_on),
        )
        conn.commit()
        return cursor.rowcount > 0


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
            cursor = conn.execute("SELECT depends_on FROM task_deps WHERE task_id = ?", (current,))
            stack.extend(row[0] for row in cursor.fetchall())
    return False


def log_progress(task_id: int, message: str) -> int:
    """Add entry to task log."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO task_log (task_id, message) VALUES (?, ?)", (task_id, message))
        conn.execute("UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def get_task_log(task_id: int, limit: int = DEFAULT_RECENT_LIMIT) -> list[TaskLogEntryDict]:
    """Get task log entries."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM task_log WHERE task_id = ?
            ORDER BY created_at DESC LIMIT ?
        """,
            (task_id, limit),
        )
        return [cast(TaskLogEntryDict, dict(row)) for row in cursor.fetchall()]


def get_active_delegate_tasks() -> list[ActiveDelegateTaskDict]:
    """Get active top-level delegate tasks with child progress counts."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.*,
                (SELECT COUNT(*) FROM tasks c
                 WHERE c.parent_task_id = t.id) as child_count,
                (SELECT COUNT(*) FROM tasks c
                 WHERE c.parent_task_id = t.id
                 AND c.status = 'done') as children_done,
                (SELECT COUNT(*) FROM tasks c
                 WHERE c.parent_task_id = t.id
                 AND c.status = 'active') as children_active
            FROM tasks t
            WHERE t.status = 'active' AND t.parent_task_id IS NULL
            ORDER BY t.updated_at DESC
        """)
        return [cast(ActiveDelegateTaskDict, dict(row)) for row in cursor.fetchall()]


def get_children(parent_task_id: int) -> list[TaskDict]:
    """Get child tasks ordered by seq."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE parent_task_id = ?
            ORDER BY seq, id
        """,
            (parent_task_id,),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def get_recent_completed_tasks(limit: int = 10) -> list[TaskDict]:
    """Get recent completed top-level tasks."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status = 'done' AND parent_task_id IS NULL
            ORDER BY completed_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def get_failed_tasks(limit: int = 5) -> list[TaskDict]:
    """Get recent failed top-level tasks."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status = 'failed' AND parent_task_id IS NULL
            ORDER BY updated_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def list_epics(
    category_key: str | None = None,
    status: list[str] | None = None,
) -> list[EpicTaskDict]:
    """List epic tasks with child counts."""
    conditions = ["t.type = 'epic'"]
    params = []

    if category_key:
        conditions.append("t.epic_key = ?")
        params.append(category_key.upper())
    if status:
        conditions.append(f"t.status IN ({','.join('?' * len(status))})")
        params.extend(status)

    with db.get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT t.*,
                COUNT(c.id) as child_count,
                COUNT(CASE WHEN c.status IN ('open', 'active', 'blocked')
                    THEN 1 END) as children_open,
                COUNT(CASE WHEN c.status = 'done' THEN 1 END) as children_done
            FROM tasks t
            LEFT JOIN tasks c ON c.parent_task_id = t.id AND c.type != 'epic'
            WHERE {" AND ".join(conditions)}
            GROUP BY t.id
            ORDER BY t.created_at DESC
        """,
            params,
        )
        return [cast(EpicTaskDict, dict(row)) for row in cursor.fetchall()]


def get_epic_view(epic_id: int) -> EpicViewDict | None:
    """Get epic task + its children."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND type = 'epic'",
            (epic_id,),
        )
        epic_row = cursor.fetchone()
        if not epic_row:
            return None

        raw: dict[str, Any] = dict(epic_row)

        child_cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE parent_task_id = ?
            ORDER BY epic_seq, seq, id
        """,
            (epic_id,),
        )
        raw["children"] = [cast(TaskDict, dict(row)) for row in child_cursor.fetchall()]

        return cast(EpicViewDict, raw)


def get_tasks_in_window(hours: int) -> list[TaskDict]:
    """Get non-delegate tasks updated within a time window.

    Args:
        hours: Number of hours to look back

    Returns:
        List of tasks updated within the window, excluding delegate-created tasks
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE prompt IS NULL
            AND updated_at > datetime('now', ? || ' hours')
            ORDER BY updated_at DESC
            """,
            (f"-{hours}",),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]


def get_delegate_tasks_in_window(hours: int, limit: int = 20) -> list[TaskDict]:
    """Get completed delegate tasks within a time window.

    Args:
        hours: Number of hours to look back
        limit: Maximum number of tasks to return

    Returns:
        List of top-level delegate tasks (with prompt IS NOT NULL)
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.*, d.title as doc_title
            FROM tasks t
            LEFT JOIN documents d ON t.output_doc_id = d.id
            WHERE t.prompt IS NOT NULL
            AND t.parent_task_id IS NULL
            AND t.updated_at > datetime('now', ? || ' hours')
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (f"-{hours}", limit),
        )
        return [cast(TaskDict, dict(row)) for row in cursor.fetchall()]
