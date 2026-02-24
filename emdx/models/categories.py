"""Category operations for task epic numbering."""

import re
from typing import cast

from emdx.database import db
from emdx.models.types import CategoryDict, CategoryRenameResultDict, CategoryWithStatsDict


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


def rename_category(
    old_key: str, new_key: str, name: str | None = None
) -> CategoryRenameResultDict:
    """Move all tasks from old_key into new_key, renumbering to avoid conflicts.

    If new_key doesn't exist, creates it (inheriting old_key's name unless overridden).
    Retitles tasks from OLD-N: to NEW-N: with new sequence numbers.
    Deletes the old category when done.

    Raises ValueError if old_key not found, or old_key == new_key.
    """
    old_key = old_key.upper()
    new_key = new_key.upper()

    if old_key == new_key:
        raise ValueError(f"Source and target are the same: {old_key!r}")

    if not re.match(r"^[A-Z]{2,8}$", new_key):
        raise ValueError(f"Category key must be 2-8 uppercase letters, got: {new_key!r}")

    old_cat = get_category(old_key)
    if not old_cat:
        raise ValueError(f"Category {old_key!r} not found")

    # Create target category if it doesn't exist
    new_cat = get_category(new_key)
    if not new_cat:
        cat_name = name or old_cat["name"]
        create_category(new_key, cat_name, old_cat["description"])
    elif name:
        # Update name if explicitly provided
        with db.get_connection() as conn:
            conn.execute("UPDATE categories SET name = ? WHERE key = ?", (name, new_key))
            conn.commit()

    title_pattern = re.compile(rf"^{re.escape(old_key)}-(\d+):\s*")

    with db.get_connection() as conn:
        # Find the max existing epic_seq in the target category
        cursor = conn.execute(
            "SELECT COALESCE(MAX(epic_seq), 0) FROM tasks WHERE epic_key = ?",
            (new_key,),
        )
        next_seq = cursor.fetchone()[0] + 1

        # Get all tasks in the old category (epics and regular tasks)
        cursor = conn.execute(
            "SELECT id, title, type FROM tasks WHERE epic_key = ? ORDER BY epic_seq",
            (old_key,),
        )
        rows = cursor.fetchall()

        tasks_moved = 0
        epics_moved = 0

        for row in rows:
            seq = next_seq
            next_seq += 1

            # Retitle: replace OLD-N: prefix with NEW-seq:
            new_title = row["title"]
            m = title_pattern.match(new_title)
            if m:
                new_title = f"{new_key}-{seq}: {new_title[m.end() :]}"

            conn.execute(
                "UPDATE tasks SET epic_key = ?, epic_seq = ?, title = ? WHERE id = ?",
                (new_key, seq, new_title, row["id"]),
            )

            if row["type"] == "epic":
                epics_moved += 1
            else:
                tasks_moved += 1

        # Delete the old category (now empty)
        conn.execute("DELETE FROM categories WHERE key = ?", (old_key,))
        conn.commit()

    return {
        "tasks_moved": tasks_moved,
        "epics_moved": epics_moved,
        "old_category_deleted": True,
    }
