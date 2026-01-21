"""
Search functionality for emdx documents using FTS5

Includes caching layer for improved performance on repeated searches.
"""

import hashlib
import logging
from typing import Any, Optional

from ..utils.datetime_utils import parse_datetime
from .connection import db_connection

logger = logging.getLogger(__name__)


def _make_search_cache_key(
    query: str,
    project: Optional[str],
    limit: int,
    fuzzy: bool,
    created_after: Optional[str],
    created_before: Optional[str],
    modified_after: Optional[str],
    modified_before: Optional[str],
) -> str:
    """Generate a cache key for search parameters."""
    # Create a deterministic key from all search parameters
    key_parts = [
        query,
        project or "",
        str(limit),
        str(fuzzy),
        created_after or "",
        created_before or "",
        modified_after or "",
        modified_before or "",
    ]
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def search_documents(
    query: str,
    project: Optional[str] = None,
    limit: int = 10,
    fuzzy: bool = False,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Search documents using FTS5 with optional caching.

    Args:
        query: The search query string
        project: Optional project filter
        limit: Maximum number of results to return
        fuzzy: Enable fuzzy search (currently uses regular FTS5)
        created_after: Filter for documents created after this date
        created_before: Filter for documents created before this date
        modified_after: Filter for documents modified after this date
        modified_before: Filter for documents modified before this date
        use_cache: Whether to use the search cache (default True)

    Returns:
        List of document dictionaries with search results including snippets and ranking
    """
    # Check cache first
    if use_cache:
        from emdx.services.cache import CacheManager

        cache_manager = CacheManager.instance()
        search_cache = cache_manager.get_cache("search")

        if search_cache and cache_manager.enabled:
            cache_key = _make_search_cache_key(
                query, project, limit, fuzzy,
                created_after, created_before,
                modified_after, modified_before
            )
            cached_result = search_cache.get(cache_key)
            if cached_result is not None:
                logger.debug("Search cache hit for query: %s", query[:50])
                return cached_result

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
                    doc[field] = parse_datetime(doc[field])
            docs.append(doc)

    # Store in cache if enabled
    if use_cache and docs:
        from emdx.services.cache import CacheManager

        cache_manager = CacheManager.instance()
        search_cache = cache_manager.get_cache("search")

        if search_cache and cache_manager.enabled:
            cache_key = _make_search_cache_key(
                query, project, limit, fuzzy,
                created_after, created_before,
                modified_after, modified_before
            )
            search_cache.set(cache_key, docs)
            logger.debug("Cached search results for query: %s", query[:50])

    return docs
