"""Database operations for tags - core SQL only.

This module provides low-level tag operations that work with any database
connection. It has minimal dependencies to avoid circular imports.

Higher-level operations with alias expansion are in emdx/models/tags.py.
"""

import sqlite3


def get_or_create_tag_with_conn(conn: sqlite3.Connection, tag_name: str) -> int:
    """Get existing tag ID or create new tag using provided connection.

    Args:
        conn: SQLite database connection
        tag_name: Name of the tag (will be lowercased and stripped)

    Returns:
        The tag's ID
    """
    tag_name = tag_name.lower().strip()

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = cursor.fetchone()

    if result:
        return result[0]

    cursor.execute("INSERT INTO tags (name, usage_count) VALUES (?, 0)", (tag_name,))
    return cursor.lastrowid


def add_tags_with_conn(
    conn: sqlite3.Connection, doc_id: int, tag_names: list[str]
) -> list[str]:
    """Add tags to a document using provided connection.

    This does NOT perform alias expansion - pass already-expanded tag names.

    Args:
        conn: SQLite database connection
        doc_id: Document ID to tag
        tag_names: List of tag names (should already be alias-expanded)

    Returns:
        List of tags that were successfully added (excludes duplicates)
    """
    added_tags = []
    for tag_name in tag_names:
        tag_name = tag_name.lower().strip()
        if not tag_name:
            continue

        tag_id = get_or_create_tag_with_conn(conn, tag_name)

        try:
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )
            added_tags.append(tag_name)
            conn.execute(
                "UPDATE tags SET usage_count = usage_count + 1 WHERE id = ?",
                (tag_id,),
            )
        except sqlite3.IntegrityError:
            pass  # Already tagged

    return added_tags


def remove_tags_with_conn(
    conn: sqlite3.Connection, doc_id: int, tag_names: list[str]
) -> list[str]:
    """Remove tags from a document using provided connection.

    Args:
        conn: SQLite database connection
        doc_id: Document ID to untag
        tag_names: List of tag names to remove

    Returns:
        List of tags that were successfully removed
    """
    removed_tags = []
    for tag_name in tag_names:
        tag_name = tag_name.lower().strip()
        if not tag_name:
            continue

        cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        result = cursor.fetchone()
        if not result:
            continue

        tag_id = result[0]
        cursor = conn.execute(
            "DELETE FROM document_tags WHERE document_id = ? AND tag_id = ?",
            (doc_id, tag_id),
        )
        if cursor.rowcount > 0:
            removed_tags.append(tag_name)
            conn.execute(
                "UPDATE tags SET usage_count = MAX(0, usage_count - 1) WHERE id = ?",
                (tag_id,),
            )

    return removed_tags


def get_document_tags_with_conn(
    conn: sqlite3.Connection, doc_id: int
) -> list[str]:
    """Get all tags for a document using provided connection.

    Args:
        conn: SQLite database connection
        doc_id: Document ID

    Returns:
        List of tag names
    """
    cursor = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN document_tags dt ON t.id = dt.tag_id
        WHERE dt.document_id = ?
        ORDER BY t.name
        """,
        (doc_id,),
    )
    return [row[0] for row in cursor.fetchall()]


def get_all_tags_with_conn(conn: sqlite3.Connection) -> list[dict]:
    """Get all tags with their usage counts using provided connection.

    Args:
        conn: SQLite database connection

    Returns:
        List of dicts with 'id', 'name', 'usage_count' keys
    """
    cursor = conn.execute(
        """
        SELECT id, name, usage_count FROM tags
        ORDER BY usage_count DESC, name ASC
        """
    )
    return [
        {"id": row[0], "name": row[1], "usage_count": row[2]}
        for row in cursor.fetchall()
    ]
