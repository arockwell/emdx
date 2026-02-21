"""Category operations for task epic numbering."""

import re
from typing import cast

from emdx.database import db
from emdx.models.types import CategoryDict, CategoryWithStatsDict


def create_category(key: str, name: str, description: str = "") -> str:
    """Create a category. Returns the key.

    Validates: uppercase alpha only, 2-8 chars.
    """
    key = key.upper()
    if not re.match(r"^[A-Z]{2,8}$", key):
        raise ValueError(f"Category key must be 2-8 uppercase letters, got: {key!r}")

    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO categories (key, name, description) VALUES (?, ?, ?)",
            (key, name, description),
        )
        conn.commit()
    return key


def get_category(key: str) -> CategoryDict | None:
    """Get category by key."""
    key = key.upper()
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM categories WHERE key = ?", (key,))
        row = cursor.fetchone()
        return cast(CategoryDict, dict(row)) if row else None


def list_categories() -> list[CategoryWithStatsDict]:
    """List categories with task count breakdowns."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                c.key, c.name, c.description, c.created_at,
                COUNT(CASE WHEN t.epic_seq IS NOT NULL
                    AND t.status IN ('open', 'active', 'blocked')
                    THEN 1 END) as open_count,
                COUNT(CASE WHEN t.epic_seq IS NOT NULL
                    AND t.status = 'done' THEN 1 END) as done_count,
                COUNT(CASE WHEN t.type = 'epic' THEN 1 END) as epic_count,
                COUNT(CASE WHEN t.epic_seq IS NOT NULL THEN 1 END) as total_count
            FROM categories c
            LEFT JOIN tasks t ON t.epic_key = c.key
            GROUP BY c.key
            ORDER BY c.key
        """)
        return [cast(CategoryWithStatsDict, dict(row)) for row in cursor.fetchall()]


def ensure_category(key: str) -> str:
    """Auto-create category with key as name if doesn't exist. Returns key."""
    key = key.upper()
    if not re.match(r"^[A-Z]{2,8}$", key):
        raise ValueError(f"Category key must be 2-8 uppercase letters, got: {key!r}")

    with db.get_connection() as conn:
        cursor = conn.execute("SELECT key FROM categories WHERE key = ?", (key,))
        if cursor.fetchone():
            return key
        conn.execute(
            "INSERT INTO categories (key, name) VALUES (?, ?)",
            (key, key),
        )
        conn.commit()
    return key


def delete_category(key: str, force: bool = False) -> dict[str, int]:
    """Delete a category and handle orphaned tasks.

    If force=False (default), refuses to delete if open/active tasks exist.
    If force=True, clears epic_key/epic_seq on all associated tasks, then deletes.

    Returns dict with counts: tasks_cleared, epics_cleared.
    Raises ValueError if category not found or has open tasks (when not forced).
    """
    key = key.upper()
    cat = get_category(key)
    if not cat:
        raise ValueError(f"Category {key!r} not found")

    with db.get_connection() as conn:
        # Count open/active tasks in this category
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE epic_key = ? AND status IN ('open', 'active')",
            (key,),
        )
        open_count = cursor.fetchone()[0]

        if open_count > 0 and not force:
            raise ValueError(
                f"Category {key!r} has {open_count} open/active task(s). "
                f"Use --force to delete anyway."
            )

        # Count tasks and epics that will be affected
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE epic_key = ? AND type != 'epic'",
            (key,),
        )
        tasks_cleared = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE epic_key = ? AND type = 'epic'",
            (key,),
        )
        epics_cleared = cursor.fetchone()[0]

        # Clear epic_key/epic_seq on all associated tasks (don't delete the tasks)
        conn.execute(
            "UPDATE tasks SET epic_key = NULL, epic_seq = NULL WHERE epic_key = ?",
            (key,),
        )

        # Delete the category
        conn.execute("DELETE FROM categories WHERE key = ?", (key,))
        conn.commit()

    return {"tasks_cleared": tasks_cleared, "epics_cleared": epics_cleared}


def adopt_category(key: str, name: str | None = None) -> dict[str, int]:
    """Backfill existing tasks with KEY-N: titles into the category system.

    Scans tasks where title matches '{KEY}-N:' pattern and sets epic_key/epic_seq.
    Also detects parent epic tasks titled 'EPIC: ...' and sets their type/epic_key.

    Returns dict with counts: adopted, skipped, epics_found.
    """
    key = key.upper()
    pattern = re.compile(rf"^{re.escape(key)}-(\d+):\s*")

    # Ensure category exists
    if name:
        existing = get_category(key)
        if existing:
            with db.get_connection() as conn:
                conn.execute("UPDATE categories SET name = ? WHERE key = ?", (name, key))
                conn.commit()
        else:
            create_category(key, name)
    else:
        ensure_category(key)

    adopted = 0
    skipped = 0
    epics_found = 0

    with db.get_connection() as conn:
        # Find tasks matching KEY-N: pattern that aren't already adopted
        cursor = conn.execute("SELECT id, title, parent_task_id FROM tasks WHERE epic_key IS NULL")
        rows = cursor.fetchall()

        for row in rows:
            m = pattern.match(row["title"])
            if m:
                seq = int(m.group(1))
                # Check for conflicts
                conflict = conn.execute(
                    "SELECT id FROM tasks WHERE epic_key = ? AND epic_seq = ?",
                    (key, seq),
                ).fetchone()
                if conflict:
                    skipped += 1
                    continue
                conn.execute(
                    "UPDATE tasks SET epic_key = ?, epic_seq = ? WHERE id = ?",
                    (key, seq, row["id"]),
                )
                adopted += 1

        # Find parent epic tasks (title starts with "EPIC:")
        epic_cursor = conn.execute(
            "SELECT DISTINCT parent_task_id FROM tasks "
            "WHERE epic_key = ? AND parent_task_id IS NOT NULL",
            (key,),
        )
        parent_ids = [r["parent_task_id"] for r in epic_cursor.fetchall()]

        for pid in parent_ids:
            parent = conn.execute(
                "SELECT id, type, epic_key FROM tasks WHERE id = ?", (pid,)
            ).fetchone()
            if parent and parent["epic_key"] is None:
                conn.execute(
                    "UPDATE tasks SET type = 'epic', epic_key = ? WHERE id = ?",
                    (key, pid),
                )
                epics_found += 1

        conn.commit()

    return {"adopted": adopted, "skipped": skipped, "epics_found": epics_found}
