"""
Search functionality for emdx documents using FTS5
"""

from datetime import datetime
from typing import Any, Optional

from .connection import db_connection


def search_documents(
    query: str, project: Optional[str] = None, limit: int = 10, fuzzy: bool = False
) -> list[dict[str, Any]]:
    """Search documents using FTS5
    
    Args:
        query: The search query string
        project: Optional project filter
        limit: Maximum number of results to return
        fuzzy: Enable fuzzy search (currently uses regular FTS5)
        
    Returns:
        List of document dictionaries with search results including snippets and ranking
    """
    with db_connection.get_connection() as conn:
        # For now, fuzzy search just uses regular FTS5
        # Could add rapidfuzz later for title matching

        if project:
            cursor = conn.execute(
                """
                SELECT
                    d.id, d.title, d.project, d.created_at,
                    snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                    rank as rank
                FROM documents d
                JOIN documents_fts ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ? AND d.project = ? AND d.deleted_at IS NULL
                ORDER BY rank
                LIMIT ?
            """,
                (query, project, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT
                    d.id, d.title, d.project, d.created_at,
                    snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                    rank as rank
                FROM documents d
                JOIN documents_fts ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ? AND d.deleted_at IS NULL
                ORDER BY rank
                LIMIT ?
            """,
                (query, limit),
            )

        # Convert rows and parse datetime strings
        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            for field in ["created_at", "updated_at", "last_accessed"]:
                if field in doc and isinstance(doc[field], str):
                    doc[field] = datetime.fromisoformat(doc[field])
            docs.append(doc)
        return docs