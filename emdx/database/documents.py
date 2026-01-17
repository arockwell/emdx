"""
Document CRUD operations for emdx knowledge base
"""

import logging
from typing import Any, Optional, Union

from ..utils.datetime import parse_datetime
from .connection import db_connection

logger = logging.getLogger(__name__)


def _parse_doc_datetimes(doc: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    """Parse datetime fields in a document dictionary."""
    if fields is None:
        fields = ["created_at", "updated_at", "accessed_at", "deleted_at"]
    for field in fields:
        if field in doc and isinstance(doc[field], str):
            doc[field] = parse_datetime(doc[field])
    return doc


def save_document(
    title: str,
    content: str,
    project: Optional[str] = None,
    tags: Optional[list[str]] = None,
    parent_id: Optional[int] = None,
) -> int:
    """Save a document to the knowledge base"""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content, project, parent_id)
            VALUES (?, ?, ?, ?)
        """,
            (title, content, project, parent_id),
        )

        conn.commit()
        doc_id = cursor.lastrowid
        
        # Add tags if provided
        if tags:
            from emdx.models.tags import add_tags_to_document
            add_tags_to_document(doc_id, tags)
        
        return doc_id


def get_document(identifier: Union[str, int]) -> Optional[dict[str, Any]]:
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
            # Convert Row to dict and parse datetime strings
            doc = dict(row)
            return _parse_doc_datetimes(doc)
        return None


def list_documents(
    project: Optional[str] = None,
    limit: int = 50,
    include_archived: bool = False,
    parent_id: Optional[int] = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List documents with optional project and hierarchy filters.

    Args:
        project: Filter by project name (None = all projects)
        limit: Maximum number of documents to return
        include_archived: Whether to include archived documents
        parent_id: Filter by parent document:
            - None: Only top-level documents (parent_id IS NULL)
            - -1: All documents regardless of parent
            - int > 0: Only children of specific parent
        offset: Starting offset for pagination

    Returns:
        List of document dictionaries
    """
    with db_connection.get_connection() as conn:
        # Build query with filters
        conditions = ["is_deleted = FALSE"]
        params: list[Any] = []

        # Parent filter
        if parent_id is None:
            conditions.append("parent_id IS NULL")
        elif parent_id > 0:
            conditions.append("parent_id = ?")
            params.append(parent_id)
        # If parent_id == -1, no parent filter (show all)

        # Archive filter
        if not include_archived:
            conditions.append("archived_at IS NULL")

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
        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            docs.append(
                _parse_doc_datetimes(doc, ["created_at", "accessed_at", "archived_at"])
            )
        return docs


def count_documents(
    project: Optional[str] = None,
    include_archived: bool = False,
    parent_id: Optional[int] = None,
) -> int:
    """Count documents with optional project and hierarchy filters.

    Args:
        project: Filter by project name (None = all projects)
        include_archived: Whether to include archived documents
        parent_id: Filter by parent document (see list_documents for details)

    Returns:
        Count of matching documents
    """
    with db_connection.get_connection() as conn:
        conditions = ["is_deleted = FALSE"]
        params: list[Any] = []

        if parent_id is None:
            conditions.append("parent_id IS NULL")
        elif parent_id > 0:
            conditions.append("parent_id = ?")
            params.append(parent_id)

        if not include_archived:
            conditions.append("archived_at IS NULL")

        if project:
            conditions.append("project = ?")
            params.append(project)

        where_clause = " AND ".join(conditions)

        cursor = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where_clause}",
            params,
        )
        return cursor.fetchone()[0]


def has_children(doc_id: int, include_archived: bool = False) -> bool:
    """Check if a document has children.

    Args:
        doc_id: Parent document ID
        include_archived: Whether to count archived children

    Returns:
        True if the document has at least one child
    """
    with db_connection.get_connection() as conn:
        conditions = ["is_deleted = FALSE", "parent_id = ?"]
        params: list[Any] = [doc_id]

        if not include_archived:
            conditions.append("archived_at IS NULL")

        where_clause = " AND ".join(conditions)

        cursor = conn.execute(
            f"SELECT 1 FROM documents WHERE {where_clause} LIMIT 1",
            params,
        )
        return cursor.fetchone() is not None


def get_children_count(
    doc_ids: list[int], include_archived: bool = False
) -> dict[int, int]:
    """Get child counts for multiple documents efficiently.

    Args:
        doc_ids: List of parent document IDs
        include_archived: Whether to count archived children

    Returns:
        Dictionary mapping doc_id to child count
    """
    if not doc_ids:
        return {}

    with db_connection.get_connection() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        conditions = ["is_deleted = FALSE", f"parent_id IN ({placeholders})"]
        params: list[Any] = list(doc_ids)

        if not include_archived:
            conditions.append("archived_at IS NULL")

        where_clause = " AND ".join(conditions)

        cursor = conn.execute(
            f"""
            SELECT parent_id, COUNT(*) as child_count
            FROM documents
            WHERE {where_clause}
            GROUP BY parent_id
            """,
            params,
        )

        result = {doc_id: 0 for doc_id in doc_ids}
        for row in cursor.fetchall():
            result[row["parent_id"]] = row["child_count"]
        return result


def update_document(doc_id: int, title: str, content: str) -> bool:
    """Update a document"""
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
        return cursor.rowcount > 0


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


def get_recent_documents(limit: int = 10) -> list[dict[str, Any]]:
    """Get recently accessed documents"""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, project, accessed_at, access_count
            FROM documents
            WHERE is_deleted = FALSE
            ORDER BY accessed_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        # Convert rows and parse datetime strings
        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            docs.append(_parse_doc_datetimes(doc))
        return docs


def get_stats(project: Optional[str] = None) -> dict[str, Any]:
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

        stats = dict(cursor.fetchone())

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
            stats["most_viewed"] = dict(most_viewed)

        return stats


def list_deleted_documents(days: Optional[int] = None, limit: int = 50) -> list[dict[str, Any]]:
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
        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            docs.append(_parse_doc_datetimes(doc))
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


def purge_deleted_documents(older_than_days: Optional[int] = None) -> int:
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
    project: Optional[str] = None,
    title_threshold: float = 0.85,
    content: Optional[str] = None,
    content_threshold: float = 0.5,
) -> Optional[dict[str, Any]]:
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
            # Return most recent exact match
            return _parse_doc_datetimes(exact_matches[0][0])

        # For fuzzy matches, we need content similarity check
        if content and candidates:
            from ..services.similarity import compute_content_similarity

            for doc, title_sim, match_type in candidates:
                content_sim = compute_content_similarity(content, doc["content"])
                if content_sim >= content_threshold:
                    return _parse_doc_datetimes(doc)

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


def archive_document(doc_id: int) -> bool:
    """Archive a document (set archived_at timestamp).

    Args:
        doc_id: ID of document to archive

    Returns:
        True if archive was successful
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE AND archived_at IS NULL
            """,
            (doc_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def unarchive_document(doc_id: int) -> bool:
    """Unarchive a document (clear archived_at timestamp).

    Args:
        doc_id: ID of document to unarchive

    Returns:
        True if unarchive was successful
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET archived_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE AND archived_at IS NOT NULL
            """,
            (doc_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_children(doc_id: int, include_archived: bool = False) -> list[dict[str, Any]]:
    """Get all child documents of a parent.

    Args:
        doc_id: ID of parent document
        include_archived: Whether to include archived children

    Returns:
        List of child documents
    """
    with db_connection.get_connection() as conn:
        if include_archived:
            cursor = conn.execute(
                """
                SELECT id, title, project, created_at, parent_id, relationship, archived_at
                FROM documents
                WHERE parent_id = ? AND is_deleted = FALSE
                ORDER BY created_at DESC
                """,
                (doc_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, project, created_at, parent_id, relationship, archived_at
                FROM documents
                WHERE parent_id = ? AND is_deleted = FALSE AND archived_at IS NULL
                ORDER BY created_at DESC
                """,
                (doc_id,),
            )

        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            docs.append(_parse_doc_datetimes(doc))
        return docs


def get_descendants(doc_id: int) -> list[dict[str, Any]]:
    """Get all descendants of a document (children, grandchildren, etc).

    Args:
        doc_id: ID of root document

    Returns:
        List of all descendant documents
    """
    descendants = []
    to_visit = [doc_id]
    visited = set()

    while to_visit:
        current_id = to_visit.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        children = get_children(current_id, include_archived=True)
        for child in children:
            descendants.append(child)
            to_visit.append(child["id"])

    return descendants


def archive_descendants(doc_id: int) -> int:
    """Archive all descendants of a document.

    Args:
        doc_id: ID of root document (not archived, only descendants)

    Returns:
        Number of documents archived
    """
    descendants = get_descendants(doc_id)
    count = 0
    for desc in descendants:
        if desc.get("archived_at") is None:
            if archive_document(desc["id"]):
                count += 1
    return count


# =============================================================================
# Document Sources (Bridge Table for Workflow Provenance)
# =============================================================================


def record_document_source(
    document_id: int,
    workflow_run_id: int | None = None,
    workflow_stage_run_id: int | None = None,
    workflow_individual_run_id: int | None = None,
    source_type: str = "individual_output",
) -> bool:
    """Record the source of a document (which workflow created it).

    Args:
        document_id: The document ID
        workflow_run_id: The workflow run that created this document
        workflow_stage_run_id: The stage run (optional)
        workflow_individual_run_id: The individual run (optional)
        source_type: One of 'individual_output', 'synthesis', 'stage_output'

    Returns:
        True if recorded successfully
    """
    with db_connection.get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO document_sources
                (document_id, workflow_run_id, workflow_stage_run_id, workflow_individual_run_id, source_type)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    document_id,
                    workflow_run_id,
                    workflow_stage_run_id,
                    workflow_individual_run_id,
                    source_type,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error recording document source: {e}")
            return False


def get_document_source(document_id: int) -> dict[str, Any] | None:
    """Get the source information for a document.

    Returns:
        Dict with workflow_run_id, stage_run_id, individual_run_id, source_type
        or None if document has no workflow source
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM document_sources WHERE document_id = ?",
            (document_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_workflow_document_ids(workflow_run_id: int | None = None) -> set[int]:
    """Get all document IDs created by workflows.

    Args:
        workflow_run_id: If provided, only return docs from this workflow run

    Returns:
        Set of document IDs
    """
    with db_connection.get_connection() as conn:
        if workflow_run_id:
            cursor = conn.execute(
                "SELECT document_id FROM document_sources WHERE workflow_run_id = ?",
                (workflow_run_id,),
            )
        else:
            cursor = conn.execute("SELECT document_id FROM document_sources")
        return {row[0] for row in cursor.fetchall()}


def list_non_workflow_documents(
    limit: int = 100,
    days: int = 7,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Get documents that were NOT created by workflows (direct saves).

    This is an efficient single-query alternative to loading all documents
    and filtering out workflow-generated ones.

    Args:
        limit: Maximum documents to return
        days: Only include documents from the last N days
        include_archived: Whether to include archived documents

    Returns:
        List of document dicts
    """
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=days)

    with db_connection.get_connection() as conn:
        query = """
            SELECT d.* FROM documents d
            LEFT JOIN document_sources ds ON d.id = ds.document_id
            WHERE ds.id IS NULL
              AND d.parent_id IS NULL
              AND d.is_deleted = FALSE
              AND d.created_at > ?
        """
        if not include_archived:
            query += " AND d.archived_at IS NULL"
        query += " ORDER BY d.created_at DESC LIMIT ?"

        cursor = conn.execute(query, (cutoff.isoformat(), limit))
        return [_parse_doc_datetimes(dict(row)) for row in cursor.fetchall()]


# =============================================================================
# Pipeline Stage Operations (for streaming document processing)
# =============================================================================


def get_oldest_at_stage(stage: str) -> dict[str, Any] | None:
    """Get the oldest document at a given pipeline stage.

    This is the core primitive for the patrol system - each patrol watches
    a stage and picks up the oldest unprocessed document.

    Args:
        stage: The stage to query (e.g., 'idea', 'prompt', 'analyzed', 'planned')

    Returns:
        The oldest document at that stage, or None if no documents are waiting
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM documents
            WHERE stage = ? AND is_deleted = FALSE
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (stage,),
        )
        row = cursor.fetchone()
        return _parse_doc_datetimes(dict(row)) if row else None


def update_document_stage(doc_id: int, stage: str | None) -> bool:
    """Update a document's pipeline stage.

    Args:
        doc_id: Document ID
        stage: New stage (or None to remove from pipeline)

    Returns:
        True if update was successful
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE
            """,
            (stage, doc_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_documents_at_stage(stage: str, limit: int = 50) -> list[dict[str, Any]]:
    """List all documents at a given pipeline stage.

    Args:
        stage: The stage to query
        limit: Maximum documents to return

    Returns:
        List of documents at that stage, oldest first
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, project, stage, created_at, updated_at
            FROM documents
            WHERE stage = ? AND is_deleted = FALSE
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (stage, limit),
        )
        return [_parse_doc_datetimes(dict(row)) for row in cursor.fetchall()]


def count_documents_at_stage(stage: str) -> int:
    """Count documents at a given pipeline stage.

    Args:
        stage: The stage to query

    Returns:
        Number of documents at that stage
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM documents
            WHERE stage = ? AND is_deleted = FALSE
            """,
            (stage,),
        )
        return cursor.fetchone()[0]


def get_pipeline_stats() -> dict[str, int]:
    """Get counts of documents at each pipeline stage.

    Returns:
        Dictionary mapping stage name to document count
    """
    stages = ["idea", "prompt", "analyzed", "planned", "done"]
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT stage, COUNT(*) as count
            FROM documents
            WHERE stage IS NOT NULL AND is_deleted = FALSE
            GROUP BY stage
            """
        )
        results = {stage: 0 for stage in stages}
        for row in cursor.fetchall():
            results[row["stage"]] = row["count"]
        return results


def save_document_to_pipeline(
    title: str,
    content: str,
    stage: str = "idea",
    project: str | None = None,
    tags: list[str] | None = None,
    parent_id: int | None = None,
) -> int:
    """Save a document directly into the pipeline at a given stage.

    Args:
        title: Document title
        content: Document content
        stage: Initial pipeline stage (default: 'idea')
        project: Optional project name
        tags: Optional list of tags
        parent_id: Optional parent document ID

    Returns:
        The new document's ID
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content, project, parent_id, stage)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, content, project, parent_id, stage),
        )
        conn.commit()
        doc_id = cursor.lastrowid

        if tags:
            from emdx.models.tags import add_tags_to_document
            add_tags_to_document(doc_id, tags)

        return doc_id
