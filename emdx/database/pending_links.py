"""Queue of documents awaiting deferred embedding + auto-linking (#1038).

`emdx save` enqueues documents here instead of loading the embedding
model synchronously; the queue is drained by `emdx maintain index` (or
`emdx maintain link --pending`), which embeds queued documents and
creates their semantic links out of band.
"""

from __future__ import annotations

from .connection import db_connection
from .types import PendingAutoLink


def enqueue(doc_id: int, project_scope: str | None = None) -> None:
    """Queue a document for deferred embedding + auto-linking.

    project_scope is the project the eventual auto-link pass should be
    scoped to (None = match across all projects). Re-enqueueing an
    already-queued document updates its scope.
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pending_auto_links (document_id, project_scope) VALUES (?, ?)",
            (doc_id, project_scope),
        )
        conn.commit()


def get_pending() -> list[PendingAutoLink]:
    """Return all queued documents, oldest first."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT document_id, project_scope FROM pending_auto_links "
            "ORDER BY created_at, document_id"
        )
        return [
            PendingAutoLink(document_id=row[0], project_scope=row[1]) for row in cursor.fetchall()
        ]


def remove(doc_id: int) -> None:
    """Remove a document from the queue (processed or no longer relevant)."""
    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM pending_auto_links WHERE document_id = ?", (doc_id,))
        conn.commit()


def count() -> int:
    """Number of documents currently queued."""
    with db_connection.get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM pending_auto_links").fetchone()
        return int(row[0])
