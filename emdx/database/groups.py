"""Database operations for document groups.

Document groups provide hierarchical organization of related documents
into batches, rounds, and initiatives - independent of how they were
created (workflow, sub-agent, manual save).
"""

import os
import sqlite3
from datetime import datetime
from typing import Any

from .connection import db_connection
from .types import DocumentGroup, DocumentGroupWithCounts, DocumentWithGroups, GroupMember


def create_group(
    name: str,
    group_type: str = "batch",
    parent_group_id: int | None = None,
    project: str | None = None,
    description: str | None = None,
    created_by: str | None = None,
) -> int:
    """Create a new document group.

    Args:
        name: Display name for the group
        group_type: One of 'batch', 'initiative', 'round', 'session', 'custom'
        parent_group_id: Parent group for nesting (optional)
        project: Associated project name (optional)
        description: Description of the group's purpose (optional)
        created_by: Who created the group (optional, defaults to USER env)

    Returns:
        The ID of the created group

    Raises:
        ValueError: If parent would create a cycle
    """
    if parent_group_id is not None and _would_create_cycle(parent_group_id, None):
        raise ValueError("Cannot set parent: would create a cycle")

    if created_by is None:
        created_by = os.environ.get("USER", "system")

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO document_groups
            (name, description, parent_group_id, group_type, project, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, parent_group_id, group_type, project, created_by),
        )
        conn.commit()
        row_id = cursor.lastrowid
        assert row_id is not None
        return row_id


def get_group(group_id: int) -> DocumentGroup | None:
    """Get a group by ID.

    Returns:
        Group dict or None if not found
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM document_groups WHERE id = ?",
            (group_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None  # type: ignore[return-value]


def list_groups(
    parent_group_id: int | None = None,
    project: str | None = None,
    group_type: str | None = None,
    include_inactive: bool = False,
    top_level_only: bool = False,
) -> list[DocumentGroup]:
    """List groups with optional filters.

    Args:
        parent_group_id: Filter by parent group (use -1 for top-level only)
        project: Filter by project name
        group_type: Filter by type ('batch', 'initiative', etc.)
        include_inactive: Include soft-deleted groups
        top_level_only: Only return groups with no parent

    Returns:
        List of group dicts
    """
    conditions: list[str] = []
    params: list[str | int | None] = []

    if not include_inactive:
        conditions.append("is_active = TRUE")

    if top_level_only or parent_group_id == -1:
        conditions.append("parent_group_id IS NULL")
    elif parent_group_id is not None:
        conditions.append("parent_group_id = ?")
        params.append(parent_group_id)

    if project is not None:
        conditions.append("project = ?")
        params.append(project)

    if group_type is not None:
        conditions.append("group_type = ?")
        params.append(group_type)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            f"""
            SELECT * FROM document_groups
            WHERE {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


def update_group(group_id: int, **kwargs: Any) -> bool:
    """Update group properties.

    Supported kwargs: name, description, parent_group_id, group_type,
                     project, is_active

    Returns:
        True if update succeeded
    """
    allowed_fields = {
        "name",
        "description",
        "parent_group_id",
        "group_type",
        "project",
        "is_active",
    }

    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return False

    # Check for cycles if updating parent
    if "parent_group_id" in updates:
        new_parent = updates["parent_group_id"]
        if new_parent is not None and _would_create_cycle(new_parent, group_id):
            raise ValueError("Cannot set parent: would create a cycle")

    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [group_id]

    with db_connection.get_connection() as conn:
        conn.execute(
            f"UPDATE document_groups SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
        return True


def delete_group(group_id: int, hard: bool = False) -> bool:
    """Delete a group.

    Args:
        group_id: Group to delete
        hard: If True, permanently delete. If False, soft-delete (set is_active=False)

    Returns:
        True if deletion succeeded
    """
    with db_connection.get_connection() as conn:
        if hard:
            conn.execute("DELETE FROM document_groups WHERE id = ?", (group_id,))
        else:
            conn.execute(
                "UPDATE document_groups SET is_active = FALSE, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), group_id),
            )
        conn.commit()
        return True


def add_document_to_group(
    group_id: int,
    document_id: int,
    role: str = "member",
    added_by: str | None = None,
) -> bool:
    """Add a document to a group.

    Args:
        group_id: Target group
        document_id: Document to add
        role: Role in group ('primary', 'exploration', 'synthesis', 'variant', 'member')
        added_by: Who added the document (optional)

    Returns:
        True if added successfully
    """
    if added_by is None:
        added_by = os.environ.get("USER", "system")

    with db_connection.get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO document_group_members (group_id, document_id, role, added_by)
                VALUES (?, ?, ?, ?)
                """,
                (group_id, document_id, role, added_by),
            )
            conn.commit()

            # Update group metrics
            _update_group_metrics(conn, group_id)

            return True
        except sqlite3.IntegrityError:
            # Already in group (unique constraint)
            return False


def remove_document_from_group(group_id: int, document_id: int) -> bool:
    """Remove a document from a group.

    Returns:
        True if removed successfully
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM document_group_members WHERE group_id = ? AND document_id = ?",
            (group_id, document_id),
        )
        conn.commit()

        if cursor.rowcount > 0:
            _update_group_metrics(conn, group_id)
            return True
        return False


def get_group_members(
    group_id: int,
) -> list[GroupMember]:
    """Get all documents in a group.

    Args:
        group_id: Group to query

    Returns:
        List of dicts with document info and membership role
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                d.*,
                dgm.role,
                dgm.added_at as group_added_at,
                dgm.added_by as group_added_by
            FROM documents d
            JOIN document_group_members dgm ON d.id = dgm.document_id
            WHERE dgm.group_id = ?
              AND d.is_deleted = FALSE
              AND d.archived_at IS NULL
            ORDER BY dgm.added_at DESC
            """,
            (group_id,),
        )
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


def get_document_groups(document_id: int) -> list[DocumentWithGroups]:
    """Get all groups a document belongs to.

    Returns:
        List of group dicts with membership info
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                dg.*,
                dgm.role,
                dgm.added_at as member_added_at
            FROM document_groups dg
            JOIN document_group_members dgm ON dg.id = dgm.group_id
            WHERE dgm.document_id = ?
              AND dg.is_active = TRUE
            ORDER BY dgm.added_at DESC
            """,
            (document_id,),
        )
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


def get_child_groups(parent_group_id: int) -> list[DocumentGroup]:
    """Get all direct child groups of a parent.

    Returns:
        List of child group dicts
    """
    return list_groups(parent_group_id=parent_group_id)


def get_all_grouped_document_ids() -> set[int]:
    """Get IDs of all documents that belong to at least one group.

    Returns:
        Set of document IDs
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute("SELECT DISTINCT document_id FROM document_group_members")
        return {row[0] for row in cursor.fetchall()}


def get_recursive_doc_count(group_id: int) -> int:
    """Get total document count including all nested child groups.

    Args:
        group_id: Group to calculate count for

    Returns:
        Total count of documents in this group and all descendants
    """
    with db_connection.get_connection() as conn:
        # Use recursive CTE to get all descendant groups
        # Only count documents that actually exist and aren't deleted
        cursor = conn.execute(
            """
            WITH RECURSIVE descendants AS (
                -- Base case: the group itself
                SELECT id FROM document_groups WHERE id = ?
                UNION ALL
                -- Recursive case: children of current groups
                SELECT dg.id FROM document_groups dg
                JOIN descendants d ON dg.parent_group_id = d.id
            )
            SELECT COUNT(DISTINCT dgm.document_id)
            FROM document_group_members dgm
            JOIN documents d ON dgm.document_id = d.id
            WHERE dgm.group_id IN (SELECT id FROM descendants)
              AND d.is_deleted = FALSE
            """,
            (group_id,),
        )
        result = cursor.fetchone()
        return int(result[0]) if result else 0


def list_top_groups_with_counts() -> list[DocumentGroupWithCounts]:
    """List top-level groups with child_group_count and doc_count in one query.

    Avoids the N+1 pattern of calling get_child_groups + get_recursive_doc_count
    per group. Used by the Activity view refresh loop.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                g.*,
                COALESCE(cc.child_count, 0) AS child_group_count,
                COALESCE(dc.doc_count, 0) AS doc_count
            FROM document_groups g
            LEFT JOIN (
                SELECT parent_group_id, COUNT(*) AS child_count
                FROM document_groups
                WHERE is_active = TRUE AND parent_group_id IS NOT NULL
                GROUP BY parent_group_id
            ) cc ON cc.parent_group_id = g.id
            LEFT JOIN (
                SELECT dgm.group_id, COUNT(DISTINCT dgm.document_id) AS doc_count
                FROM document_group_members dgm
                JOIN documents d ON dgm.document_id = d.id AND d.is_deleted = FALSE
                GROUP BY dgm.group_id
            ) dc ON dc.group_id = g.id
            WHERE g.parent_group_id IS NULL AND g.is_active = TRUE
            ORDER BY g.created_at DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


def update_group_metrics(group_id: int) -> bool:
    """Recalculate and update group metrics (doc_count, tokens, cost).

    Returns:
        True if updated successfully
    """
    with db_connection.get_connection() as conn:
        return _update_group_metrics(conn, group_id)


def _update_group_metrics(conn: sqlite3.Connection, group_id: int) -> bool:
    """Internal: Update group metrics using existing connection."""
    # Count documents
    cursor = conn.execute(
        """
        SELECT COUNT(*) FROM document_group_members
        WHERE group_id = ?
        """,
        (group_id,),
    )
    result = cursor.fetchone()
    doc_count = result[0] if result else 0

    conn.execute(
        """
        UPDATE document_groups
        SET doc_count = ?, updated_at = ?
        WHERE id = ?
        """,
        (doc_count, datetime.now().isoformat(), group_id),
    )
    conn.commit()
    return True


def _would_create_cycle(parent_id: int, child_id: int | None) -> bool:
    """Check if setting parent_id would create a cycle.

    Args:
        parent_id: Proposed parent group
        child_id: The group being modified (None for new groups)

    Returns:
        True if this would create a cycle
    """
    if child_id is None:
        return False

    # Walk up the parent chain from parent_id
    # If we find child_id, it would be a cycle
    with db_connection.get_connection() as conn:
        current: int | None = parent_id
        visited: set[int] = set()

        while current is not None:
            if current == child_id:
                return True
            if current in visited:
                # Already a cycle in the data (shouldn't happen)
                return True
            visited.add(current)

            cursor = conn.execute(
                "SELECT parent_group_id FROM document_groups WHERE id = ?",
                (current,),
            )
            row = cursor.fetchone()
            current = row[0] if row else None

    return False
