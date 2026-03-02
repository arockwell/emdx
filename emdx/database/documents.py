"""
Document CRUD operations for emdx knowledge base
"""

from __future__ import annotations

import logging
from typing import Any, Union, cast

from ..utils.datetime_utils import parse_datetime
from .connection import db_connection
from .types import (
    ChildDocumentItem,
    DatabaseStats,
    DeletedDocumentItem,
    DocumentListItem,
    DocumentRow,
    MostViewedDoc,
    RecentDocumentItem,
    SupersedeCandidate,
)

logger = logging.getLogger(__name__)


def _parse_doc_datetimes(
    doc: dict[str, Any],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Parse datetime string fields in a document dictionary, in place.

    Returns the same dict for call-chaining convenience.  Callers should
    ``cast()`` to the concrete TypedDict *before* calling this so that
    their local variable already carries the right type.
    """
    if fields is None:
        fields = ["created_at", "updated_at", "accessed_at", "deleted_at"]
    for field in fields:
        if field in doc and isinstance(doc[field], str):
            doc[field] = parse_datetime(doc[field])
    return doc


def save_document(
    title: str,
    content: str,
    project: str | None = None,
    tags: list[str] | None = None,
    parent_id: int | None = None,
    doc_type: str | None = None,
) -> int:
    """Save a document to the knowledge base"""
    with db_connection.get_connection() as conn:
        if doc_type is not None:
            cursor = conn.execute(
                """
                INSERT INTO documents (title, content, project, parent_id, doc_type)
                VALUES (?, ?, ?, ?, ?)
            """,
                (title, content, project, parent_id, doc_type),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO documents (title, content, project, parent_id)
                VALUES (?, ?, ?, ?)
            """,
                (title, content, project, parent_id),
            )

        # Get lastrowid before commit (required by SQLite)
        doc_id = cursor.lastrowid
        assert doc_id is not None

        # Add tags if provided - pass connection for atomic transaction
        if tags:
            from emdx.models.tags import add_tags_to_document

            add_tags_to_document(doc_id, tags, conn=conn)

        # Commit after both document and tags are inserted (atomic transaction)
        conn.commit()

    # Record 'create' event (non-critical, best-effort)
    # Must be outside the connection context to avoid opening a second
    # connection while the first is still active (causes FTS5 corruption
    # in delete journal mode).
    from emdx.models.events import record_event

    record_event("create", doc_id=doc_id)

    return doc_id


def get_document(identifier: Union[str, int]) -> DocumentRow | None:
    """Get a document by ID or title"""
    with db_connection.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)

        # Update access tracking
        if identifier_str.isdigit():
            conn.execute(
                """
                UPDATE documents
                SET accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ? AND is_deleted = FALSE
            """,
                (int(identifier_str),),
            )

            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE id = ? AND is_deleted = FALSE
            """,
                (int(identifier_str),),
            )
        else:
            conn.execute(
                """
                UPDATE documents
                SET accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
            """,
                (identifier_str,),
            )

            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
            """,
                (identifier_str,),
            )

        conn.commit()
        row = cursor.fetchone()

        if row:
            raw = dict(row)
            _parse_doc_datetimes(raw)
            return cast(DocumentRow, raw)
        return None


def list_documents(
    project: str | None = None,
    limit: int = 50,
    parent_id: int | None = None,
    offset: int = 0,
    doc_type: str | None = "user",
) -> list[DocumentListItem]:
    """List documents with optional project and hierarchy filters.

    Args:
        project: Filter by project name (None = all projects)
        limit: Maximum number of documents to return (must be non-negative)
        parent_id: Filter by parent document:
            - None: Only top-level documents (parent_id IS NULL)
            - -1: All documents regardless of parent
            - int > 0: Only children of specific parent
        offset: Starting offset for pagination (must be non-negative)
        doc_type: Filter by document type. 'user' (default), 'wiki', or None for all types.

    Returns:
        List of document dictionaries

    Raises:
        ValueError: If limit or offset is negative
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    with db_connection.get_connection() as conn:
        # Build query with filters
        conditions = ["is_deleted = FALSE", "archived_at IS NULL"]
        params: list[str | int | None] = []

        # doc_type filter
        if doc_type is not None:
            conditions.append("doc_type = ?")
            params.append(doc_type)

        # Parent filter
        if parent_id is None:
            conditions.append("parent_id IS NULL")
        elif parent_id > 0:
            conditions.append("parent_id = ?")
            params.append(parent_id)
        # If parent_id == -1, no parent filter (show all)

        # Project filter
        if project:
            conditions.append("project = ?")
            params.append(project)

        where_clause = " AND ".join(conditions)
        params.extend([limit, offset])

        cursor = conn.execute(
            f"""
            SELECT id, title, project, created_at, access_count,
                   parent_id, relationship, archived_at, accessed_at
            FROM documents
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )

        # Convert rows and parse datetime strings
        docs: list[DocumentListItem] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw, ["created_at", "accessed_at", "archived_at"])
            docs.append(cast(DocumentListItem, raw))
        return docs


def get_documents_for_export(
    project: str | None = None,
    tags: list[str] | None = None,
    doc_type: str | None = "user",
) -> list[DocumentRow]:
    """Fetch all documents for export without bumping access counts.

    Args:
        project: Filter by project name (None = all projects)
        tags: Filter by tags (AND — doc must have all tags)
        doc_type: Filter by type. 'user' (default), 'wiki', or None for all.

    Returns:
        Full document rows ordered by id.
    """
    with db_connection.get_connection() as conn:
        conditions = ["d.is_deleted = FALSE"]
        params: list[str | int | None] = []

        if doc_type is not None:
            conditions.append("d.doc_type = ?")
            params.append(doc_type)

        if project:
            conditions.append("d.project = ?")
            params.append(project)

        if tags:
            tag_placeholders = ",".join("?" * len(tags))
            conditions.append(
                f"d.id IN ("
                f"SELECT dt.document_id FROM document_tags dt "
                f"JOIN tags t ON dt.tag_id = t.id "
                f"WHERE t.name IN ({tag_placeholders}) "
                f"GROUP BY dt.document_id "
                f"HAVING COUNT(DISTINCT t.name) = ?"
                f")"
            )
            params.extend(t.lower().strip() for t in tags)
            params.append(len(tags))

        where_clause = " AND ".join(conditions)
        cursor = conn.execute(
            f"SELECT d.* FROM documents d WHERE {where_clause} ORDER BY d.id",
            params,
        )

        docs: list[DocumentRow] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw)
            docs.append(cast(DocumentRow, raw))
        return docs


def count_documents(
    project: str | None = None,
    parent_id: int | None = None,
) -> int:
    """Count documents with optional project and hierarchy filters.

    Args:
        project: Filter by project name (None = all projects)
        parent_id: Filter by parent document (see list_documents for details)

    Returns:
        Count of matching documents
    """
    with db_connection.get_connection() as conn:
        conditions = ["is_deleted = FALSE", "archived_at IS NULL"]
        params: list[str | int | None] = []

        if parent_id is None:
            conditions.append("parent_id IS NULL")
        elif parent_id > 0:
            conditions.append("parent_id = ?")
            params.append(parent_id)

        if project:
            conditions.append("project = ?")
            params.append(project)

        where_clause = " AND ".join(conditions)

        cursor = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where_clause}",
            params,
        )
        result = cursor.fetchone()
        return int(result[0]) if result else 0


def get_children_count(
    doc_ids: list[int],
) -> dict[int, int]:
    """Get child counts for multiple documents efficiently.

    Args:
        doc_ids: List of parent document IDs

    Returns:
        Dictionary mapping doc_id to child count
    """
    if not doc_ids:
        return {}

    with db_connection.get_connection() as conn:
        placeholders = ",".join("?" * len(doc_ids))

        cursor = conn.execute(
            f"""
            SELECT parent_id, COUNT(*) as child_count
            FROM documents
            WHERE is_deleted = FALSE AND parent_id IN ({placeholders}) AND archived_at IS NULL
            GROUP BY parent_id
            """,
            list(doc_ids),
        )

        result = dict.fromkeys(doc_ids, 0)
        for row in cursor.fetchall():
            result[row["parent_id"]] = row["child_count"]
        return result


def update_document(doc_id: int, title: str, content: str) -> bool:
    """Update a document, snapshotting the previous version first."""
    # Snapshot on a separate connection to avoid FTS5 content-sync
    # trigger corruption (the SELECT + INSERT on `documents` in the
    # same transaction as the UPDATE can confuse FTS5 on some builds).
    _snapshot_version(doc_id, new_content=content)

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (title, content, doc_id),
        )

        conn.commit()
        updated = cursor.rowcount > 0

    # Record 'update' event (non-critical, best-effort)
    if updated:
        from emdx.models.events import record_event

        record_event("update", doc_id=doc_id)

    # Mark any wiki articles sourced from this document as stale ($0 cost)
    if updated:
        try:
            from emdx.services.wiki_synthesis_service import mark_stale

            mark_stale(doc_id, reason="source_updated")
        except Exception:
            pass  # Wiki tables may not exist yet; non-critical

    return updated


def _snapshot_version(
    doc_id: int,
    new_content: str,
    change_source: str = "manual",
) -> None:
    """Snapshot the current document content into document_versions.

    Uses its own connection to avoid FTS5 content-sync trigger
    corruption when the caller subsequently UPDATEs the same row.
    Failures are logged but never propagated -- versioning is non-critical.
    """
    import hashlib

    try:
        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT title, content FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                return

            old_title: str = row[0]
            old_content: str = row[1]
            content_hash = hashlib.sha256(old_content.encode()).hexdigest()
            char_delta = len(new_content) - len(old_content)

            # Determine next version number
            ver_row = conn.execute(
                "SELECT MAX(version_number) FROM document_versions WHERE document_id = ?",
                (doc_id,),
            ).fetchone()
            next_version = (ver_row[0] or 0) + 1

            conn.execute(
                "INSERT INTO document_versions "
                "(document_id, version_number, title, content, "
                "content_hash, char_delta, change_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    next_version,
                    old_title,
                    old_content,
                    content_hash,
                    char_delta,
                    change_source,
                ),
            )
            conn.commit()
    except Exception:
        logger.debug(
            "Failed to snapshot version for doc %d (document_versions table may not exist yet)",
            doc_id,
            exc_info=True,
        )


def delete_document(identifier: Union[str, int], hard_delete: bool = False) -> bool:
    """Delete a document by ID or title (soft delete by default)"""
    with db_connection.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)

        if hard_delete:
            # Permanent deletion
            if identifier_str.isdigit():
                cursor = conn.execute(
                    """
                    DELETE FROM documents WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier_str),),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier_str,),
                )
        else:
            # Soft delete
            if identifier_str.isdigit():
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier_str),),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                    WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier_str,),
                )

        conn.commit()
        return cursor.rowcount > 0


def get_recent_documents(
    limit: int = 10,
    doc_type: str | None = "user",
) -> list[RecentDocumentItem]:
    """Get recently accessed documents.

    Args:
        limit: Maximum number of documents to return.
        doc_type: Filter by document type. 'user' (default), 'wiki', or None for all types.
    """
    with db_connection.get_connection() as conn:
        conditions = ["is_deleted = FALSE"]
        params: list[str | int] = []

        if doc_type is not None:
            conditions.append("doc_type = ?")
            params.append(doc_type)

        where_clause = " AND ".join(conditions)
        params.append(limit)

        cursor = conn.execute(
            f"""
            SELECT id, title, project, accessed_at, access_count
            FROM documents
            WHERE {where_clause}
            ORDER BY accessed_at DESC
            LIMIT ?
        """,
            params,
        )

        # Convert rows and parse datetime strings
        docs: list[RecentDocumentItem] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw)
            docs.append(cast(RecentDocumentItem, raw))
        return docs


def get_stats(project: str | None = None) -> DatabaseStats:
    """Get database statistics"""
    with db_connection.get_connection() as conn:
        if project:
            # Project-specific stats
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_documents,
                    SUM(access_count) as total_views,
                    AVG(access_count) as avg_views,
                    MAX(created_at) as newest_doc,
                    MAX(accessed_at) as last_accessed
                FROM documents
                WHERE project = ? AND is_deleted = FALSE
            """,
                (project,),
            )
        else:
            # Overall stats
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_documents,
                    COUNT(DISTINCT project) as total_projects,
                    SUM(access_count) as total_views,
                    AVG(access_count) as avg_views,
                    MAX(created_at) as newest_doc,
                    MAX(accessed_at) as last_accessed
                FROM documents
                WHERE is_deleted = FALSE
            """
            )

        row = cursor.fetchone()
        stats: DatabaseStats = cast(DatabaseStats, dict(row)) if row else cast(DatabaseStats, {})

        # Get database file size
        stats["table_size"] = f"{db_connection.db_path.stat().st_size / 1024 / 1024:.2f} MB"

        # Get most viewed document
        if project:
            cursor = conn.execute(
                """
                SELECT id, title, access_count
                FROM documents
                WHERE project = ? AND is_deleted = FALSE
                ORDER BY access_count DESC
                LIMIT 1
            """,
                (project,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, access_count
                FROM documents
                WHERE is_deleted = FALSE
                ORDER BY access_count DESC
                LIMIT 1
            """
            )

        most_viewed = cursor.fetchone()
        if most_viewed:
            stats["most_viewed"] = cast(MostViewedDoc, dict(most_viewed))

        return stats


def list_deleted_documents(days: int | None = None, limit: int = 50) -> list[DeletedDocumentItem]:
    """List soft-deleted documents"""
    with db_connection.get_connection() as conn:
        if days:
            cursor = conn.execute(
                """
                SELECT id, title, project, deleted_at, access_count
                FROM documents
                WHERE is_deleted = TRUE
                AND deleted_at >= datetime('now', '-' || ? || ' days')
                ORDER BY deleted_at DESC
                LIMIT ?
            """,
                (days, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, project, deleted_at, access_count
                FROM documents
                WHERE is_deleted = TRUE
                ORDER BY deleted_at DESC
                LIMIT ?
            """,
                (limit,),
            )

        # Convert rows and parse datetime strings
        docs: list[DeletedDocumentItem] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw)
            docs.append(cast(DeletedDocumentItem, raw))
        return docs


def restore_document(identifier: Union[str, int]) -> bool:
    """Restore a soft-deleted document"""
    with db_connection.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)
        if identifier_str.isdigit():
            cursor = conn.execute(
                """
                UPDATE documents
                SET is_deleted = FALSE, deleted_at = NULL
                WHERE id = ? AND is_deleted = TRUE
            """,
                (int(identifier),),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE documents
                SET is_deleted = FALSE, deleted_at = NULL
                WHERE LOWER(title) = LOWER(?) AND is_deleted = TRUE
            """,
                (identifier,),
            )

        conn.commit()
        return cursor.rowcount > 0


def purge_deleted_documents(older_than_days: int | None = None) -> int:
    """Permanently delete soft-deleted documents"""
    with db_connection.get_connection() as conn:
        if older_than_days:
            cursor = conn.execute(
                """
                DELETE FROM documents
                WHERE is_deleted = TRUE
                AND deleted_at <= datetime('now', '-' || ? || ' days')
            """,
                (older_than_days,),
            )
        else:
            cursor = conn.execute(
                """
                DELETE FROM documents
                WHERE is_deleted = TRUE
            """
            )

        conn.commit()
        return cursor.rowcount


def find_supersede_candidate(
    title: str,
    project: str | None = None,
    title_threshold: float = 0.85,
    content: str | None = None,
    content_threshold: float = 0.5,
) -> SupersedeCandidate | None:
    """Find a document that should be superseded by a new document with the given title.

    Uses title normalization and optional content similarity to find the best candidate.

    Args:
        title: Title of the new document
        project: Project to search within (if None, searches all)
        title_threshold: Minimum title similarity (0.0-1.0) for fuzzy matching
        content: Content of new document (for content similarity check)
        content_threshold: Minimum content similarity required when title_threshold < 1.0

    Returns:
        The most recent document that should be superseded, or None
    """
    from ..utils.title_normalization import normalize_title, title_similarity

    normalized_new = normalize_title(title)
    if not normalized_new:
        return None

    with db_connection.get_connection() as conn:
        # Find docs that could be superseded
        # Only consider docs without a parent (docs with parent_id are already
        # linked via workflow or previous supersede, and that takes precedence)
        if project:
            cursor = conn.execute(
                """
                SELECT id, title, content, project, created_at, parent_id
                FROM documents
                WHERE project = ? AND is_deleted = FALSE AND archived_at IS NULL
                AND parent_id IS NULL
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (project,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, content, project, created_at, parent_id
                FROM documents
                WHERE is_deleted = FALSE AND archived_at IS NULL
                AND parent_id IS NULL
                ORDER BY created_at DESC
                LIMIT 100
                """,
            )

        candidates = []
        for row in cursor.fetchall():
            doc = dict(row)
            normalized_existing = normalize_title(doc["title"])

            # Exact normalized match - always a candidate
            if normalized_existing == normalized_new:
                candidates.append((doc, 1.0, "exact"))
                continue

            # Fuzzy title match - needs content check
            sim = title_similarity(title, doc["title"])
            if sim >= title_threshold:
                candidates.append((doc, sim, "fuzzy"))

        if not candidates:
            return None

        # For exact matches, return the most recent one
        exact_matches = [c for c in candidates if c[2] == "exact"]
        if exact_matches:
            raw = exact_matches[0][0]
            _parse_doc_datetimes(raw)
            return cast(SupersedeCandidate, raw)

        # For fuzzy matches, we need content similarity check
        if content and candidates:
            from ..services.similarity import compute_content_similarity

            for doc, _title_sim, _match_type in candidates:
                content_sim = compute_content_similarity(content, doc["content"])
                if content_sim >= content_threshold:
                    _parse_doc_datetimes(doc)
                    return cast(SupersedeCandidate, doc)

        return None


def set_parent(doc_id: int, parent_id: int, relationship: str = "supersedes") -> bool:
    """Set the parent of a document.

    Args:
        doc_id: ID of the child document
        parent_id: ID of the parent document
        relationship: Type of relationship ('supersedes', 'exploration', 'variant')

    Returns:
        True if update was successful
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET parent_id = ?, relationship = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE
            """,
            (parent_id, relationship, doc_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_children(doc_id: int) -> list[ChildDocumentItem]:
    """Get all child documents of a parent.

    Args:
        doc_id: ID of parent document

    Returns:
        List of child documents
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, project, created_at, parent_id, relationship, archived_at
            FROM documents
            WHERE parent_id = ? AND is_deleted = FALSE AND archived_at IS NULL
            ORDER BY created_at DESC
            """,
            (doc_id,),
        )

        docs: list[ChildDocumentItem] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw)
            docs.append(cast(ChildDocumentItem, raw))
        return docs


def list_recent_documents(
    limit: int = 100,
    days: int = 7,
) -> list[DocumentRow]:
    """Get recent direct-save documents.

    Args:
        limit: Maximum documents to return
        days: Only include documents from the last N days

    Returns:
        List of document dicts
    """
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=days)

    with db_connection.get_connection() as conn:
        query = """
            SELECT d.* FROM documents d
            WHERE d.parent_id IS NULL
              AND d.is_deleted = FALSE
              AND d.created_at > ?
              AND d.archived_at IS NULL
            ORDER BY d.created_at DESC LIMIT ?
        """

        cursor = conn.execute(query, (cutoff.isoformat(), limit))
        docs: list[DocumentRow] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw)
            docs.append(cast(DocumentRow, raw))
        return docs


def get_docs_in_window(hours: int, limit: int = 100) -> list[DocumentListItem]:
    """Get documents created within a time window.

    Args:
        hours: Number of hours to look back
        limit: Maximum number of documents to return

    Returns:
        List of documents created within the window
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, project, created_at, access_count,
                   parent_id, relationship, archived_at, accessed_at
            FROM documents
            WHERE is_deleted = 0
            AND created_at > datetime('now', ? || ' hours')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"-{hours}", limit),
        )
        docs: list[DocumentListItem] = []
        for row in cursor.fetchall():
            raw = dict(row)
            _parse_doc_datetimes(raw, ["created_at", "accessed_at", "archived_at"])
            docs.append(cast(DocumentListItem, raw))
        return docs
