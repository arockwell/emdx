"""
Unified search service for EMDX.

Orchestrates FTS5, tag-based, and semantic search into a single interface.
Supports query parsing with special syntax for different search modes.
"""

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from ..database import db
from ..database.search import search_documents
from ..models.tags import get_tags_for_documents, search_by_tags
from ..utils.datetime_utils import parse_datetime

logger = logging.getLogger(__name__)


@dataclass
class SearchQuery:
    """Represents a parsed search query with all filter options."""

    text: str = ""
    tags: List[str] = field(default_factory=list)
    tag_mode: str = "all"  # "all" or "any"
    semantic: bool = False
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None
    project: Optional[str] = None
    limit: int = 50


@dataclass
class SearchResult:
    """A single search result with unified scoring."""

    doc_id: int
    title: str
    snippet: str
    score: float  # Normalized 0-1
    source: str  # "fts", "tags", "semantic", "fuzzy"
    tags: List[str] = field(default_factory=list)
    project: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UnifiedSearchService:
    """
    Orchestrates FTS5, tag, and semantic search.

    Supports query syntax:
    - Plain text: FTS5 full-text search
    - tags:active,done: Tag filter (comma-separated)
    - tags:any:bug,error: Tag filter with ANY mode
    - semantic: or ai:: Enable semantic search
    - after:2024-01-01: Created after date
    - before:2024-12-31: Created before date
    - project:myproject: Filter by project
    - #123: Document ID lookup
    """

    def __init__(self):
        self._embedding_service = None  # Lazy load

    @property
    def embedding_service(self):
        """Lazy load the embedding service."""
        if self._embedding_service is None:
            try:
                from .embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except ImportError:
                logger.warning("EmbeddingService not available")
                self._embedding_service = None
        return self._embedding_service

    def parse_query(self, raw_query: str) -> SearchQuery:
        """
        Parse a query string with special syntax.

        Syntax:
            tags:active,done  - Match documents with these tags (AND)
            tags:any:bug,error - Match documents with any of these tags (OR)
            semantic: - Enable semantic search
            ai: - Alias for semantic:
            after:2024-01-01 - Created after date
            before:2024-12-31 - Created before date
            modified:2024-01-01 - Modified after date
            project:myproject - Filter by project

        Returns:
            SearchQuery with parsed components
        """
        query = SearchQuery()
        remaining_text = raw_query.strip()

        # Extract tags:... patterns
        tags_match = re.search(r"tags:(any:)?([^\s]+)", remaining_text, re.IGNORECASE)
        if tags_match:
            if tags_match.group(1):
                query.tag_mode = "any"
            tag_str = tags_match.group(2)
            query.tags = [t.strip() for t in tag_str.split(",") if t.strip()]
            remaining_text = remaining_text[: tags_match.start()] + remaining_text[tags_match.end() :]

        # Extract @tag patterns (alternative syntax)
        at_tags = re.findall(r"@(\w+)", remaining_text)
        if at_tags:
            query.tags.extend(at_tags)
            remaining_text = re.sub(r"@\w+", "", remaining_text)

        # Extract semantic: or ai: flag
        if re.search(r"\b(semantic:|ai:)\b", remaining_text, re.IGNORECASE):
            query.semantic = True
            remaining_text = re.sub(r"\b(semantic:|ai:)\b", "", remaining_text, flags=re.IGNORECASE)

        # Extract after: date
        after_match = re.search(r"after:(\d{4}-\d{2}-\d{2})", remaining_text, re.IGNORECASE)
        if after_match:
            query.created_after = parse_datetime(after_match.group(1))
            remaining_text = remaining_text[: after_match.start()] + remaining_text[after_match.end() :]

        # Extract before: date
        before_match = re.search(r"before:(\d{4}-\d{2}-\d{2})", remaining_text, re.IGNORECASE)
        if before_match:
            query.created_before = parse_datetime(before_match.group(1))
            remaining_text = remaining_text[: before_match.start()] + remaining_text[before_match.end() :]

        # Extract modified: date
        modified_match = re.search(r"modified:(\d{4}-\d{2}-\d{2})", remaining_text, re.IGNORECASE)
        if modified_match:
            query.modified_after = parse_datetime(modified_match.group(1))
            remaining_text = remaining_text[: modified_match.start()] + remaining_text[modified_match.end() :]

        # Extract project: filter
        project_match = re.search(r"project:(\S+)", remaining_text, re.IGNORECASE)
        if project_match:
            query.project = project_match.group(1)
            remaining_text = remaining_text[: project_match.start()] + remaining_text[project_match.end() :]

        # Clean up remaining text
        query.text = " ".join(remaining_text.split()).strip()

        return query

    def _prepare_fts_query(self, text: str) -> str:
        """
        Prepare text for FTS5 query with prefix matching.

        Converts "ana" to "ana*" for prefix matching.
        Handles multiple words: "ana test" becomes "ana* test*"
        """
        if not text or not text.strip():
            return text

        words = text.strip().split()
        # Add prefix wildcard to each word for partial matching
        # This makes "ana" match "analysis"
        prepared_words = []
        for word in words:
            # Skip if already has FTS5 operators
            if word.endswith("*") or word.startswith("-") or word.startswith('"'):
                prepared_words.append(word)
            else:
                # Add prefix wildcard
                prepared_words.append(f"{word}*")

        return " ".join(prepared_words)

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        """
        Execute search across all specified modes.

        Automatically determines which search backends to use based on query.
        """
        import asyncio

        # Run blocking search in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._search_sync, query)

    def _search_sync(self, query: SearchQuery) -> List[SearchResult]:
        """Synchronous search implementation (runs in thread pool)."""
        results: List[SearchResult] = []
        seen_ids: Set[int] = set()

        # Collect results from different sources
        if query.text:
            # FTS5 full-text search
            fts_results = self._search_fts(query)
            for result in fts_results:
                if result.doc_id not in seen_ids:
                    results.append(result)
                    seen_ids.add(result.doc_id)

            # If FTS returned few results, supplement with fuzzy title search
            # This helps when porter stemmer doesn't match partial words
            if len(fts_results) < 5 and len(query.text) >= 3:
                fuzzy_results = self.fuzzy_search_titles(
                    query.text,
                    limit=10,
                    threshold=0.3,
                    exclude_ids=seen_ids,
                )
                for result in fuzzy_results:
                    if result.doc_id not in seen_ids:
                        results.append(result)
                        seen_ids.add(result.doc_id)

        if query.tags:
            # Tag-based search
            tag_results = self._search_tags(query)
            for result in tag_results:
                if result.doc_id not in seen_ids:
                    results.append(result)
                    seen_ids.add(result.doc_id)
                else:
                    # Boost score for documents matching both text and tags
                    for existing in results:
                        if existing.doc_id == result.doc_id:
                            existing.score = min(1.0, existing.score + 0.2)
                            existing.source = f"{existing.source}+tags"
                            break

        if query.semantic and query.text and self.embedding_service:
            # Semantic search - runs in same thread pool as rest of search
            # (entire _search_sync runs via asyncio.to_thread, so this won't block UI)
            semantic_results = self._search_semantic(query)
            for result in semantic_results:
                if result.doc_id not in seen_ids:
                    results.append(result)
                    seen_ids.add(result.doc_id)
                else:
                    # Boost score for documents matching both FTS and semantic
                    for existing in results:
                        if existing.doc_id == result.doc_id:
                            existing.score = min(1.0, existing.score + result.score * 0.3)
                            existing.source = f"{existing.source}+semantic"
                            break

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        # Apply limit
        results = results[: query.limit]

        # Fetch tags for all results
        doc_ids = [r.doc_id for r in results]
        if doc_ids:
            tags_map = get_tags_for_documents(doc_ids)
            for result in results:
                result.tags = tags_map.get(result.doc_id, [])

        return results

    def _search_fts(self, query: SearchQuery) -> List[SearchResult]:
        """Execute FTS5 full-text search."""
        # Build date filter strings
        created_after_str = query.created_after.isoformat() if query.created_after else None
        created_before_str = query.created_before.isoformat() if query.created_before else None
        modified_after_str = query.modified_after.isoformat() if query.modified_after else None

        # Prepare FTS5 query - add prefix matching for better partial matches
        # "ana" becomes "ana*" to match "analysis"
        fts_query = self._prepare_fts_query(query.text)

        docs = search_documents(
            query=fts_query,
            project=query.project,
            limit=query.limit,
            created_after=created_after_str,
            created_before=created_before_str,
            modified_after=modified_after_str,
        )

        results = []
        for doc in docs:
            # Normalize FTS5 rank to 0-1 score
            # FTS5 rank is typically negative (closer to 0 is better)
            raw_rank = doc.get("rank", 0)
            # Convert negative rank to positive score (0-1 range)
            # Typical rank range is -20 to 0
            score = max(0.0, min(1.0, 1.0 + (raw_rank / 20.0))) if raw_rank else 0.5

            results.append(
                SearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    snippet=doc.get("snippet", "")[:200] if doc.get("snippet") else "",
                    score=score,
                    source="fts",
                    project=doc.get("project"),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )

        return results

    def _search_tags(self, query: SearchQuery) -> List[SearchResult]:
        """Execute tag-based search."""
        docs = search_by_tags(
            tag_names=query.tags,
            mode=query.tag_mode,
            project=query.project,
            limit=query.limit,
        )

        results = []
        for doc in docs:
            # Tag matches get a high base score
            results.append(
                SearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    snippet="",  # Tag search doesn't provide snippets
                    score=0.8,  # High base score for tag matches
                    source="tags",
                    project=doc.get("project"),
                    created_at=doc.get("created_at"),
                )
            )

        return results

    def _search_semantic(self, query: SearchQuery) -> List[SearchResult]:
        """Execute semantic similarity search (sync version)."""
        if not self.embedding_service:
            return []

        try:
            matches = self.embedding_service.search(
                query=query.text,
                limit=query.limit,
                threshold=0.3,
            )

            return self._convert_semantic_matches(matches)
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    async def _search_semantic_async(self, query: SearchQuery) -> List[SearchResult]:
        """Execute semantic similarity search (async version - runs in thread pool)."""
        if not self.embedding_service:
            return []

        try:
            matches = await self.embedding_service.search_async(
                query=query.text,
                limit=query.limit,
                threshold=0.3,
            )

            return self._convert_semantic_matches(matches)
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    def _convert_semantic_matches(self, matches) -> List[SearchResult]:
        """Convert semantic matches to SearchResult objects."""
        results = []
        for match in matches:
            results.append(
                SearchResult(
                    doc_id=match.doc_id,
                    title=match.title,
                    snippet=match.snippet,
                    score=match.similarity,  # Already 0-1
                    source="semantic",
                    project=match.project,
                )
            )
        return results

    def fuzzy_search_titles(
        self,
        query: str,
        limit: int = 20,
        threshold: float = 0.4,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[SearchResult]:
        """
        Fuzzy search document titles using SequenceMatcher.

        This is useful for command palette quick lookups where the user
        might not type exact words but expects partial matches.
        """
        exclude_ids = exclude_ids or set()

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, project, created_at, updated_at
                FROM documents
                WHERE deleted_at IS NULL AND is_deleted = 0
                ORDER BY access_count DESC, updated_at DESC
                LIMIT 1000
            """
            )
            rows = cursor.fetchall()

        query_lower = query.lower()
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for row in rows:
            doc_id = row[0]
            if doc_id in exclude_ids:
                continue

            title = row[1]
            title_lower = title.lower()

            # Calculate fuzzy match score
            # Check both full title and individual words
            full_score = SequenceMatcher(None, query_lower, title_lower).ratio()

            # Also check if query appears as substring (boost for contains)
            contains_boost = 0.3 if query_lower in title_lower else 0.0

            # Check word-level matching
            query_words = query_lower.split()
            title_words = title_lower.split()
            word_scores = []
            for qw in query_words:
                best_word_score = max(
                    (SequenceMatcher(None, qw, tw).ratio() for tw in title_words),
                    default=0.0,
                )
                word_scores.append(best_word_score)

            word_score = sum(word_scores) / len(word_scores) if word_scores else 0.0

            # Combine scores
            score = max(full_score, word_score) + contains_boost
            score = min(1.0, score)

            if score >= threshold:
                scored.append(
                    (
                        score,
                        {
                            "id": doc_id,
                            "title": title,
                            "project": row[2],
                            "created_at": row[3],
                            "updated_at": row[4],
                        },
                    )
                )

        # Sort by score descending
        scored.sort(key=lambda x: -x[0])

        results = []
        for score, doc in scored[:limit]:
            results.append(
                SearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    snippet="",
                    score=score,
                    source="fuzzy",
                    project=doc["project"],
                    created_at=parse_datetime(doc["created_at"]) if doc["created_at"] else None,
                    updated_at=parse_datetime(doc["updated_at"]) if doc["updated_at"] else None,
                )
            )

        return results

    def get_recent_documents(self, limit: int = 10) -> List[SearchResult]:
        """Get recently accessed documents for empty state suggestions."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, project, created_at, updated_at, accessed_at
                FROM documents
                WHERE deleted_at IS NULL AND is_deleted = 0
                ORDER BY accessed_at DESC NULLS LAST, updated_at DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

        results = []
        doc_ids = []
        for row in rows:
            doc_ids.append(row[0])
            results.append(
                SearchResult(
                    doc_id=row[0],
                    title=row[1],
                    snippet="",
                    score=1.0,
                    source="recent",
                    project=row[2],
                    created_at=parse_datetime(row[3]) if row[3] else None,
                    updated_at=parse_datetime(row[4]) if row[4] else None,
                )
            )

        # Fetch tags
        if doc_ids:
            tags_map = get_tags_for_documents(doc_ids)
            for result in results:
                result.tags = tags_map.get(result.doc_id, [])

        return results

    def get_popular_tags(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Get popular tags for empty state suggestions."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, usage_count
                FROM tags
                WHERE usage_count > 0
                ORDER BY usage_count DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

        from ..utils.emoji_aliases import normalize_tag_to_emoji

        return [{"name": normalize_tag_to_emoji(row[0]), "count": row[1]} for row in rows]

    def get_document_by_id(self, doc_id: int) -> Optional[SearchResult]:
        """Get a single document by ID."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, project, created_at, updated_at
                FROM documents
                WHERE id = ? AND deleted_at IS NULL AND is_deleted = 0
            """,
                (doc_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        result = SearchResult(
            doc_id=row[0],
            title=row[1],
            snippet="",
            score=1.0,
            source="id",
            project=row[2],
            created_at=parse_datetime(row[3]) if row[3] else None,
            updated_at=parse_datetime(row[4]) if row[4] else None,
        )

        # Fetch tags
        tags_map = get_tags_for_documents([doc_id])
        result.tags = tags_map.get(doc_id, [])

        return result

    def has_embeddings(self) -> bool:
        """Check if semantic search is available (without loading the model)."""
        # Quick check: just query the database for embeddings count
        # This avoids loading the embedding model just to check availability
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM document_embeddings LIMIT 1")
                count = cursor.fetchone()[0]
                return count > 0
        except sqlite3.OperationalError:
            # Table may not exist or database may be locked
            return False
