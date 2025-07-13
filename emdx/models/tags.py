"""Tag management operations for emdx."""

import sqlite3
from typing import Any, Optional

from emdx.database import db


def get_or_create_tag(conn: sqlite3.Connection, tag_name: str) -> int:
    """Get existing tag ID or create new tag. Returns tag ID."""
    tag_name = tag_name.lower().strip()

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = cursor.fetchone()

    if result:
        return result[0]

    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    return cursor.lastrowid


def add_tags_to_document(doc_id: int, tag_names: list[str]) -> list[str]:
    """Add tags to a document. Returns list of newly added tags."""
    with db.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        added_tags = []
        for tag_name in tag_names:
            tag_name = tag_name.lower().strip()
            if not tag_name:
                continue

            tag_id = get_or_create_tag(conn, tag_name)

            try:
                conn.execute(
                    """
                    INSERT INTO document_tags (document_id, tag_id)
                    VALUES (?, ?)
                """,
                    (doc_id, tag_id),
                )
                added_tags.append(tag_name)

                # Update usage count
                conn.execute(
                    """
                    UPDATE tags SET usage_count = usage_count + 1
                    WHERE id = ?
                """,
                    (tag_id,),
                )
            except sqlite3.IntegrityError:
                # Tag already exists for this document
                pass

        conn.commit()
        return added_tags


def remove_tags_from_document(doc_id: int, tag_names: list[str]) -> list[str]:
    """Remove tags from a document. Returns list of removed tags."""
    with db.get_connection() as conn:
        removed_tags = []

        for tag_name in tag_names:
            tag_name = tag_name.lower().strip()

            cursor = conn.execute(
                """
                DELETE FROM document_tags
                WHERE document_id = ? AND tag_id = (
                    SELECT id FROM tags WHERE name = ?
                )
            """,
                (doc_id, tag_name),
            )

            if cursor.rowcount > 0:
                removed_tags.append(tag_name)

                # Update usage count
                conn.execute(
                    """
                    UPDATE tags SET usage_count = usage_count - 1
                    WHERE name = ?
                """,
                    (tag_name,),
                )

        conn.commit()
        return removed_tags


def get_document_tags(doc_id: int) -> list[str]:
    """Get all tags for a document."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.name
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id = ?
            ORDER BY t.name
        """,
            (doc_id,),
        )

        return [row[0] for row in cursor.fetchall()]


def list_all_tags(sort_by: str = "usage") -> list[dict[str, Any]]:
    """List all tags with statistics.

    Args:
        sort_by: 'usage', 'name', or 'created'
    """
    with db.get_connection() as conn:
        order_clause = {
            "usage": "usage_count DESC, name",
            "name": "name",
            "created": "created_at DESC",
        }.get(sort_by, "usage_count DESC, name")

        cursor = conn.execute(
            f"""
            SELECT
                t.id,
                t.name,
                t.usage_count,
                t.created_at,
                MAX(dt.created_at) as last_used
            FROM tags t
            LEFT JOIN document_tags dt ON t.id = dt.tag_id
            GROUP BY t.id, t.name, t.usage_count, t.created_at
            ORDER BY {order_clause}
        """
        )

        tags = []
        for row in cursor.fetchall():
            from datetime import datetime

            created_at = row[3]
            last_used = row[4]

            # Parse datetime strings if needed
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at) if created_at else None
            if isinstance(last_used, str):
                last_used = datetime.fromisoformat(last_used) if last_used else None

            tags.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "count": row[2],
                    "created_at": created_at,
                    "last_used": last_used,
                }
            )

        return tags


def search_by_tags(
    tag_names: list[str], mode: str = "all", project: Optional[str] = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Search documents by tags.

    Args:
        tag_names: List of tag names to search for
        mode: 'all' (must have all tags) or 'any' (has any of the tags)
        project: Optional project filter
        limit: Maximum results to return
    """
    with db.get_connection() as conn:
        tag_names = [tag.lower().strip() for tag in tag_names]

        if mode == "all":
            # Documents must have ALL specified tags
            query = """
                SELECT DISTINCT
                    d.id, d.title, d.project, d.created_at, d.access_count,
                    GROUP_CONCAT(t.name, ', ') as tags
                FROM documents d
                JOIN document_tags dt ON d.id = dt.document_id
                JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = FALSE
                AND d.id IN (
                    SELECT document_id
                    FROM document_tags dt
                    JOIN tags t ON dt.tag_id = t.id
                    WHERE t.name IN ({})
                    GROUP BY document_id
                    HAVING COUNT(DISTINCT t.name) = ?
                )
            """.format(
                ",".join("?" * len(tag_names))
            )

            params = tag_names + [len(tag_names)]
        else:
            # Documents with ANY of the specified tags
            query = """
                SELECT DISTINCT
                    d.id, d.title, d.project, d.created_at, d.access_count,
                    GROUP_CONCAT(t.name, ', ') as tags
                FROM documents d
                JOIN document_tags dt ON d.id = dt.document_id
                JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = FALSE
                AND t.name IN ({})
            """.format(
                ",".join("?" * len(tag_names))
            )

            params = tag_names

        if project:
            query += " AND d.project = ?"
            params.append(project)

        query += " GROUP BY d.id ORDER BY d.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)

        docs = []
        for row in cursor.fetchall():
            doc = dict(zip([col[0] for col in cursor.description], row))
            docs.append(doc)

        return docs


def rename_tag(old_name: str, new_name: str) -> bool:
    """Rename a tag globally."""
    with db.get_connection() as conn:
        old_name = old_name.lower().strip()
        new_name = new_name.lower().strip()

        try:
            cursor = conn.execute(
                """
                UPDATE tags SET name = ?
                WHERE name = ?
            """,
                (new_name, old_name),
            )

            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            # New tag name already exists
            return False


def merge_tags(source_tags: list[str], target_tag: str) -> int:
    """Merge multiple tags into one target tag."""
    with db.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        target_tag = target_tag.lower().strip()
        source_tags = [tag.lower().strip() for tag in source_tags]

        # Get or create target tag
        target_tag_id = get_or_create_tag(conn, target_tag)

        merged_count = 0

        for source_tag in source_tags:
            if source_tag == target_tag:
                continue

            # Get source tag ID
            cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
            result = cursor.fetchone()

            if not result:
                continue

            source_tag_id = result[0]

            # Update all document_tags entries
            cursor = conn.execute(
                """
                UPDATE OR IGNORE document_tags
                SET tag_id = ?
                WHERE tag_id = ?
            """,
                (target_tag_id, source_tag_id),
            )

            merged_count += cursor.rowcount

            # Delete the source tag
            conn.execute("DELETE FROM tags WHERE id = ?", (source_tag_id,))

        # Update usage count for target tag
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT document_id)
            FROM document_tags
            WHERE tag_id = ?
        """,
            (target_tag_id,),
        )

        new_count = cursor.fetchone()[0]
        conn.execute(
            """
            UPDATE tags SET usage_count = ?
            WHERE id = ?
        """,
            (new_count, target_tag_id),
        )

        conn.commit()
        return merged_count


def get_tag_suggestions(partial: str, limit: int = 10) -> list[str]:
    """Get tag suggestions based on partial input."""
    with db.get_connection() as conn:
        partial = partial.lower().strip()

        cursor = conn.execute(
            """
            SELECT name
            FROM tags
            WHERE name LIKE ?
            ORDER BY usage_count DESC, name
            LIMIT ?
        """,
            (f"{partial}%", limit),
        )

        return [row[0] for row in cursor.fetchall()]
