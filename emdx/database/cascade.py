"""Cascade-specific database operations for emdx.

This module manages cascade metadata stored in document_cascade_metadata table.
It provides the primary interface for cascade stage management.

The cascade system transforms documents through stages:
idea -> prompt -> analyzed -> planned -> done

Each document in the cascade has metadata tracked here, separate from the
main documents table for efficiency (only ~1% of docs use cascade).
"""

import logging
from typing import Any

from ..utils.datetime_utils import parse_datetime
from .connection import db_connection

logger = logging.getLogger(__name__)

# Valid cascade stages
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]


def _parse_cascade_datetimes(record: dict[str, Any]) -> dict[str, Any]:
    """Parse datetime fields in a cascade metadata record."""
    for field in ["created_at", "updated_at"]:
        if field in record and isinstance(record[field], str):
            record[field] = parse_datetime(record[field])
    return record


def get_cascade_metadata(doc_id: int) -> dict[str, Any] | None:
    """Get cascade metadata for a document.

    Args:
        doc_id: Document ID

    Returns:
        Dict with stage, pr_url, timestamps, or None if not in cascade
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, document_id, stage, pr_url, created_at, updated_at
            FROM document_cascade_metadata
            WHERE document_id = ?
            """,
            (doc_id,),
        )
        row = cursor.fetchone()
        if row:
            return _parse_cascade_datetimes(dict(row))
        return None


def update_cascade_stage(doc_id: int, stage: str | None) -> bool:
    """Update a document's cascade stage (upsert).

    Args:
        doc_id: Document ID
        stage: New stage (or None to remove from cascade)

    Returns:
        True if update was successful
    """
    with db_connection.get_connection() as conn:
        if stage is None:
            # Remove from cascade
            cursor = conn.execute(
                "DELETE FROM document_cascade_metadata WHERE document_id = ?",
                (doc_id,),
            )
        else:
            # Upsert: insert or update
            cursor = conn.execute(
                """
                INSERT INTO document_cascade_metadata (document_id, stage, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(document_id) DO UPDATE SET
                    stage = excluded.stage,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (doc_id, stage),
            )
        conn.commit()
        return cursor.rowcount > 0 or stage is not None


def update_cascade_pr_url(doc_id: int, pr_url: str) -> bool:
    """Update a document's PR URL (upsert).

    Args:
        doc_id: Document ID
        pr_url: The PR URL (e.g., https://github.com/user/repo/pull/123)

    Returns:
        True if update was successful
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO document_cascade_metadata (document_id, pr_url, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(document_id) DO UPDATE SET
                pr_url = excluded.pr_url,
                updated_at = CURRENT_TIMESTAMP
            """,
            (doc_id, pr_url),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_cascade_pr_url(doc_id: int) -> str | None:
    """Get a document's PR URL.

    Args:
        doc_id: Document ID

    Returns:
        PR URL or None if not set
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT pr_url FROM document_cascade_metadata WHERE document_id = ?",
            (doc_id,),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None


def get_oldest_at_stage(stage: str) -> dict[str, Any] | None:
    """Get the oldest document at a given cascade stage.

    This is the core primitive for the patrol system - each patrol watches
    a stage and picks up the oldest unprocessed document.

    Args:
        stage: The stage to query (e.g., 'idea', 'prompt', 'analyzed', 'planned')

    Returns:
        The oldest document at that stage (with cascade metadata), or None
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT d.*, cm.stage as cascade_stage, cm.pr_url as cascade_pr_url
            FROM documents d
            JOIN document_cascade_metadata cm ON d.id = cm.document_id
            WHERE cm.stage = ? AND d.is_deleted = FALSE
            ORDER BY d.created_at ASC
            LIMIT 1
            """,
            (stage,),
        )
        row = cursor.fetchone()
        if row:
            doc = dict(row)
            # Map cascade metadata to expected fields
            doc["stage"] = doc.pop("cascade_stage", None)
            doc["pr_url"] = doc.pop("cascade_pr_url", None)
            return doc
        return None


def list_documents_at_stage(stage: str, limit: int = 50) -> list[dict[str, Any]]:
    """List all documents at a given cascade stage.

    Args:
        stage: The stage to query
        limit: Maximum documents to return

    Returns:
        List of documents at that stage, oldest first
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT d.id, d.title, d.project, d.created_at, d.updated_at,
                   d.parent_id, cm.stage, cm.pr_url
            FROM documents d
            JOIN document_cascade_metadata cm ON d.id = cm.document_id
            WHERE cm.stage = ? AND d.is_deleted = FALSE
            ORDER BY d.created_at ASC
            LIMIT ?
            """,
            (stage, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def count_documents_at_stage(stage: str) -> int:
    """Count documents at a given cascade stage.

    Args:
        stage: The stage to query

    Returns:
        Number of documents at that stage
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM documents d
            JOIN document_cascade_metadata cm ON d.id = cm.document_id
            WHERE cm.stage = ? AND d.is_deleted = FALSE
            """,
            (stage,),
        )
        return cursor.fetchone()[0]


def get_cascade_stats() -> dict[str, int]:
    """Get counts of documents at each cascade stage.

    Returns:
        Dictionary mapping stage name to document count
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT cm.stage, COUNT(*) as count
            FROM documents d
            JOIN document_cascade_metadata cm ON d.id = cm.document_id
            WHERE cm.stage IS NOT NULL AND d.is_deleted = FALSE
            GROUP BY cm.stage
            """
        )
        results = dict.fromkeys(STAGES, 0)
        for row in cursor.fetchall():
            results[row["stage"]] = row["count"]
        return results


def remove_from_cascade(doc_id: int) -> bool:
    """Remove cascade metadata for a document.

    This removes the document from cascade processing but does not
    delete the document itself.

    Args:
        doc_id: Document ID

    Returns:
        True if metadata was removed
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM document_cascade_metadata WHERE document_id = ?",
            (doc_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def save_document_to_cascade(
    title: str,
    content: str,
    stage: str = "idea",
    project: str | None = None,
    tags: list[str] | None = None,
    parent_id: int | None = None,
) -> int:
    """Save a document directly into the cascade at a given stage.

    Args:
        title: Document title
        content: Document content
        stage: Initial cascade stage (default: 'idea')
        project: Optional project name
        tags: Optional list of tags
        parent_id: Optional parent document ID

    Returns:
        The new document's ID
    """
    from .documents import save_document

    # Create the document first
    doc_id = save_document(
        title=title,
        content=content,
        project=project,
        tags=tags,
        parent_id=parent_id,
    )

    # Add to cascade
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO document_cascade_metadata (document_id, stage)
            VALUES (?, ?)
            """,
            (doc_id, stage),
        )
        conn.commit()

    # Also update documents table for backward compatibility
    with db_connection.get_connection() as conn:
        conn.execute(
            "UPDATE documents SET stage = ? WHERE id = ?",
            (stage, doc_id),
        )
        conn.commit()

    return doc_id


def list_cascade_runs(limit: int = 20) -> list[dict[str, Any]]:
    """List recent cascade runs.

    Args:
        limit: Maximum runs to return

    Returns:
        List of cascade run records
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT cr.*, d.title as start_doc_title
            FROM cascade_runs cr
            LEFT JOIN documents d ON cr.start_doc_id = d.id
            ORDER BY cr.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_cascade_run_executions(run_id: int) -> list[dict[str, Any]]:
    """Get all executions for a cascade run.

    Args:
        run_id: Cascade run ID

    Returns:
        List of execution records linked to this run
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.*, d.stage as doc_stage
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.cascade_run_id = ?
            ORDER BY e.started_at ASC
            """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
