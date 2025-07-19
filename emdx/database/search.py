"""
Search functionality for emdx documents using FTS5
"""

from datetime import datetime
from typing import Any, Optional

from .connection import db_connection


def search_documents(
    query: str, 
    project: Optional[str] = None, 
    limit: int = 10, 
    fuzzy: bool = False,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None
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
        # Build dynamic query with date filters
        # Handle special case where we only have date filters (no text search)
        if query == "*":
            base_query = """
                SELECT
                    d.id, d.title, d.project, d.created_at, d.updated_at,
                    NULL as snippet,
                    0 as rank
                FROM documents d
                WHERE d.deleted_at IS NULL
            """
            params = []
        else:
            base_query = """
                SELECT
                    d.id, d.title, d.project, d.created_at, d.updated_at,
                    snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                    rank as rank
                FROM documents d
                JOIN documents_fts ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ? AND d.deleted_at IS NULL
            """
            params = [query]
        
        conditions = []
        
        # Add project filter
        if project:
            conditions.append("d.project = ?")
            params.append(project)
        
        # Add date filters
        if created_after:
            conditions.append("d.created_at >= ?")
            params.append(created_after)
        
        if created_before:
            conditions.append("d.created_at <= ?")
            params.append(created_before)
        
        if modified_after:
            conditions.append("d.updated_at >= ?")
            params.append(modified_after)
        
        if modified_before:
            conditions.append("d.updated_at <= ?")
            params.append(modified_before)
        
        # Combine conditions
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # Order by rank for text searches, by id for date-only searches
        if query == "*":
            base_query += " ORDER BY d.id DESC LIMIT ?"
        else:
            base_query += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(base_query, params)

        # Convert rows and parse datetime strings
        docs = []
        for row in cursor.fetchall():
            doc = dict(row)
            for field in ["created_at", "updated_at", "last_accessed"]:
                if field in doc and isinstance(doc[field], str):
                    doc[field] = datetime.fromisoformat(doc[field])
            docs.append(doc)
        return docs
