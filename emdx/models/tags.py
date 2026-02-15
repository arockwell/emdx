"""Tag management operations for emdx."""

import sqlite3
from typing import Any

from emdx.database import db
from emdx.utils.datetime_utils import parse_datetime
from emdx.utils.emoji_aliases import expand_aliases, normalize_tag_to_emoji


def get_or_create_tag(conn: sqlite3.Connection, tag_name: str) -> int:
    """Get existing tag ID or create new tag. Returns tag ID."""
    tag_name = tag_name.lower().strip()

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = cursor.fetchone()

    if result is not None:
        return int(result[0])

    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def add_tags_to_document(
    doc_id: int, tag_names: list[str], conn: sqlite3.Connection | None = None
) -> list[str]:
    """Add tags to a document. Returns list of newly added tags.

    Args:
        doc_id: Document ID to add tags to
        tag_names: List of tag names to add
        conn: Optional existing connection for atomic transactions.
              If provided, caller is responsible for commit.
    """
    # Expand aliases before processing
    expanded_tags = expand_aliases(tag_names)

    def _add_tags(connection: sqlite3.Connection) -> list[str]:
        added_tags = []
        for tag_name in expanded_tags:
            tag_name = tag_name.lower().strip()
            if not tag_name:
                continue

            tag_id = get_or_create_tag(connection, tag_name)

            try:
                connection.execute(
                    """
                    INSERT INTO document_tags (document_id, tag_id)
                    VALUES (?, ?)
                """,
                    (doc_id, tag_id),
                )
                added_tags.append(tag_name)

                # Update usage count
                connection.execute(
                    """
                    UPDATE tags SET usage_count = usage_count + 1
                    WHERE id = ?
                """,
                    (tag_id,),
                )
            except sqlite3.IntegrityError:
                # Tag already exists for this document
                pass
        return added_tags

    if conn is not None:
        # Use provided connection - caller handles commit
        return _add_tags(conn)
    else:
        # Create new connection and commit
        with db.get_connection() as new_conn:
            result = _add_tags(new_conn)
            new_conn.commit()
            return result


def remove_tags_from_document(doc_id: int, tag_names: list[str]) -> list[str]:
    """Remove tags from a document. Returns list of removed tags."""
    # Expand aliases before processing
    expanded_tags = expand_aliases(tag_names)

    with db.get_connection() as conn:
        removed_tags = []

        for tag_name in expanded_tags:
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
    """Get all tags for a document, automatically converting text aliases to emojis."""
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

        # Convert any text aliases to emojis for display
        raw_tags = [row[0] for row in cursor.fetchall()]
        normalized_tags = [normalize_tag_to_emoji(tag) for tag in raw_tags]

        # Remove duplicates while preserving order (in case both "gameplan" and "🎯" exist)
        seen = set()
        unique_tags = []
        for tag in normalized_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        return unique_tags


def get_tags_for_documents(doc_ids: list[int]) -> dict[int, list[str]]:
    """Get tags for multiple documents in a single query.

    This batch function eliminates N+1 query patterns by fetching all tags
    for multiple documents in one database call.

    Args:
        doc_ids: List of document IDs

    Returns:
        Dict mapping doc_id to list of tag names (normalized to emojis)
    """
    if not doc_ids:
        return {}

    with db.get_connection() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        cursor = conn.execute(
            f"""
            SELECT dt.document_id, t.name
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id IN ({placeholders})
            ORDER BY dt.document_id, t.name
        """,
            doc_ids,
        )

        # Initialize result dict with empty lists for all requested doc_ids
        result: dict[int, list[str]] = {doc_id: [] for doc_id in doc_ids}

        for row in cursor.fetchall():
            doc_id, tag_name = row
            normalized = normalize_tag_to_emoji(tag_name)
            # Dedupe (in case both text alias and emoji exist)
            if normalized not in result[doc_id]:
                result[doc_id].append(normalized)

        return result


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
            created_at = row[3]
            last_used = row[4]

            # Parse datetime strings if needed using centralized utility
            created_at = parse_datetime(created_at)
            last_used = parse_datetime(last_used)

            # Normalize tag name to emoji for display
            normalized_name = normalize_tag_to_emoji(row[1])

            tags.append(
                {
                    "id": row[0],
                    "name": normalized_name,
                    "count": row[2],
                    "created_at": created_at,
                    "last_used": last_used,
                }
            )

        return tags


def search_by_tags(
    tag_names: list[str], mode: str = "all", project: str | None = None, limit: int = 20,
    prefix_match: bool = True
) -> list[dict[str, Any]]:
    """Search documents by tags.

    Args:
        tag_names: List of tag names to search for
        mode: 'all' (must have all tags) or 'any' (has any of the tags)
        project: Optional project filter
        limit: Maximum results to return
        prefix_match: If True, 'workflow' matches 'workflow-output' etc.
    """
    # Expand aliases before processing
    expanded_tags = expand_aliases(tag_names)

    with db.get_connection() as conn:
        tag_names_lower = [tag.lower().strip() for tag in expanded_tags]

        # Build tag matching conditions - use LIKE for prefix matching
        if prefix_match:
            # Use LIKE with % for prefix matching
            tag_conditions = " OR ".join(["t.name LIKE ?" for _ in tag_names_lower])
            tag_params = [f"{tag}%" for tag in tag_names_lower]
        else:
            # Exact match
            tag_conditions = "t.name IN ({})".format(",".join("?" * len(tag_names_lower)))
            tag_params = tag_names_lower

        if mode == "all" and not prefix_match:
            # Documents must have ALL specified tags (only works with exact match)
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
                ",".join("?" * len(tag_names_lower))
            )

            params: list[Any] = list(tag_names_lower) + [len(tag_names_lower)]
        else:
            # Documents with ANY of the specified tags (or prefix matches)
            query = f"""
                SELECT DISTINCT
                    d.id, d.title, d.project, d.created_at, d.access_count,
                    GROUP_CONCAT(t.name, ', ') as tags
                FROM documents d
                JOIN document_tags dt ON d.id = dt.document_id
                JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = FALSE
                AND ({tag_conditions})
            """

            params = list(tag_params)

        if project:
            query += " AND d.project = ?"
            params.append(project)

        query += " GROUP BY d.id ORDER BY d.id DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)

        docs = []
        for row in cursor.fetchall():
            doc = dict(zip([col[0] for col in cursor.description], row, strict=False))
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

        count_result = cursor.fetchone()
        new_count = count_result[0] if count_result else 0
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
