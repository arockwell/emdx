"""CRUD operations for the document_links table.

Provides functions to create, query, and delete bidirectional
links between documents in the knowledge graph.
"""

from __future__ import annotations

import sqlite3
from typing import cast

from .connection import db_connection
from .types import DocumentLinkDetail


def create_link(
    source_doc_id: int,
    target_doc_id: int,
    similarity_score: float = 0.0,
    method: str = "auto",
    conn: sqlite3.Connection | None = None,
) -> int | None:
    """Create a link between two documents.

    Returns the link ID, or None if the link already exists.
    The link is directional (source -> target) but queries can
    treat it as bidirectional.
    """
    if source_doc_id == target_doc_id:
        return None

    def _insert(c: sqlite3.Connection) -> int | None:
        try:
            cursor = c.execute(
                "INSERT INTO document_links "
                "(source_doc_id, target_doc_id, similarity_score, method) "
                "VALUES (?, ?, ?, ?)",
                (source_doc_id, target_doc_id, similarity_score, method),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    if conn is not None:
        return _insert(conn)

    with db_connection.get_connection() as c:
        result = _insert(c)
        c.commit()
        return result


def delete_link(
    source_doc_id: int,
    target_doc_id: int,
) -> bool:
    """Delete a link between two documents (either direction).

    Returns True if a link was deleted.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM document_links "
            "WHERE (source_doc_id = ? AND target_doc_id = ?) "
            "OR (source_doc_id = ? AND target_doc_id = ?)",
            (source_doc_id, target_doc_id, target_doc_id, source_doc_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_links_for_document(doc_id: int) -> int:
    """Delete all links involving a document. Returns count deleted."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM document_links WHERE source_doc_id = ? OR target_doc_id = ?",
            (doc_id, doc_id),
        )
        conn.commit()
        return cursor.rowcount


def get_links_for_document(doc_id: int) -> list[DocumentLinkDetail]:
    """Get all links for a document (both directions) with titles.

    Returns links where the document is either source or target,
    with joined document titles for display.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT l.id, l.source_doc_id, s.title AS source_title, "
            "l.target_doc_id, t.title AS target_title, "
            "l.similarity_score, l.created_at, l.method "
            "FROM document_links l "
            "JOIN documents s ON l.source_doc_id = s.id "
            "JOIN documents t ON l.target_doc_id = t.id "
            "WHERE (l.source_doc_id = ? OR l.target_doc_id = ?) "
            "AND s.is_deleted = 0 AND t.is_deleted = 0 "
            "ORDER BY l.similarity_score DESC",
            (doc_id, doc_id),
        )
        return [cast(DocumentLinkDetail, dict(row)) for row in cursor.fetchall()]


def get_linked_doc_ids(doc_id: int) -> list[int]:
    """Get IDs of all documents linked to the given document."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT CASE "
            "  WHEN source_doc_id = ? THEN target_doc_id "
            "  ELSE source_doc_id "
            "END AS linked_id "
            "FROM document_links "
            "WHERE source_doc_id = ? OR target_doc_id = ?",
            (doc_id, doc_id, doc_id),
        )
        return [row[0] for row in cursor.fetchall()]


def link_exists(source_doc_id: int, target_doc_id: int) -> bool:
    """Check if a link exists between two documents (either direction)."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM document_links "
            "WHERE (source_doc_id = ? AND target_doc_id = ?) "
            "OR (source_doc_id = ? AND target_doc_id = ?) "
            "LIMIT 1",
            (
                source_doc_id,
                target_doc_id,
                target_doc_id,
                source_doc_id,
            ),
        )
        return cursor.fetchone() is not None


def get_link_count(doc_id: int) -> int:
    """Get the number of links for a document."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM document_links WHERE source_doc_id = ? OR target_doc_id = ?",
            (doc_id, doc_id),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def batch_get_link_counts(doc_ids: list[int]) -> dict[int, int]:
    """Get link counts for multiple documents efficiently."""
    if not doc_ids:
        return {}

    with db_connection.get_connection() as conn:
        placeholders = ",".join("?" for _ in doc_ids)
        cursor = conn.execute(
            f"SELECT doc_id, COUNT(*) AS cnt FROM ("
            f"  SELECT source_doc_id AS doc_id FROM document_links "
            f"  WHERE source_doc_id IN ({placeholders}) "
            f"  UNION ALL "
            f"  SELECT target_doc_id AS doc_id FROM document_links "
            f"  WHERE target_doc_id IN ({placeholders})"
            f") GROUP BY doc_id",
            doc_ids + doc_ids,
        )
        counts = {row[0]: row[1] for row in cursor.fetchall()}
        return {doc_id: counts.get(doc_id, 0) for doc_id in doc_ids}


def create_links_batch(
    links: list[tuple[int, int, float, str]],
    conn: sqlite3.Connection | None = None,
) -> int:
    """Create multiple links in a batch.

    Each tuple is (source_doc_id, target_doc_id, similarity_score, method).
    Returns the number of links created.
    """

    def _insert_batch(c: sqlite3.Connection) -> int:
        count = 0
        for source_id, target_id, score, method in links:
            if source_id == target_id:
                continue
            try:
                c.execute(
                    "INSERT INTO document_links "
                    "(source_doc_id, target_doc_id, "
                    "similarity_score, method) "
                    "VALUES (?, ?, ?, ?)",
                    (source_id, target_id, score, method),
                )
                count += 1
            except sqlite3.IntegrityError:
                continue
        return count

    if conn is not None:
        return _insert_batch(conn)

    with db_connection.get_connection() as c:
        count = _insert_batch(c)
        c.commit()
        return count
