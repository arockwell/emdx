"""
Hybrid search service for EMDX.

Combines FTS5 keyword search with chunk-level semantic search
using Reciprocal Rank Fusion (RRF) for better relevance ranking.

Also provides query parsing, fuzzy title matching, tag-based search,
and convenience methods for the TUI (recent documents, popular tags, etc.).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
from typing import TYPE_CHECKING, TypedDict

from ..database import db
from ..database.search import search_documents
from ..models.tags import get_tags_for_documents, search_by_tags
from ..utils.datetime_utils import parse_datetime

if TYPE_CHECKING:
    from .embedding_service import EmbeddingService, SemanticMatch

logger = logging.getLogger(__name__)


# ── TypedDicts ───────────────────────────────────────────────────────


class FuzzyMatchDoc(TypedDict):
    """Document data used in fuzzy matching."""

    id: int
    title: str
    project: str | None
    created_at: str | None
    updated_at: str | None


class PopularTagDict(TypedDict):
    """Popular tag with count."""

    name: str
    count: int


# ── Enums & dataclasses ──────────────────────────────────────────────


class SearchMode(Enum):
    """Search mode determines which backends to use."""

    KEYWORD = "keyword"  # FTS5 only (fast, exact)
    SEMANTIC = "semantic"  # Embedding search only (conceptual)
    HYBRID = "hybrid"  # Both combined (default when index exists)


@dataclass
class SearchQuery:
    """Represents a parsed search query with all filter options."""

    text: str = ""
    tags: list[str] = field(default_factory=list)
    tag_mode: str = "all"  # "all" or "any"
    semantic: bool = False
    created_after: datetime | None = None
    created_before: datetime | None = None
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    project: str | None = None
    limit: int = 50


@dataclass
class HybridSearchResult:
    """A unified search result with combined scoring."""

    doc_id: int
    title: str
    project: str | None
    score: float  # Normalized 0-1, combined score
    keyword_score: float  # FTS5 score component (normalized)
    semantic_score: float  # Semantic score component (cosine similarity)
    source: str  # "keyword", "semantic", "hybrid", "fts", "tags", "fuzzy", "recent", "id"
    snippet: str
    tags: list[str] = field(default_factory=list)
    doc_type: str = "user"
    # Chunk-level data (populated when extract=True or from semantic search)
    chunk_heading: str | None = None
    chunk_text: str | None = None
    # Timestamps (populated by query-parsing search path and utility methods)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Constants ────────────────────────────────────────────────────────

# Reciprocal Rank Fusion constant (standard default from Cormack et al.)
# Higher k reduces the impact of high rankings from a single list.
RRF_K = 60

# Legacy weight constants kept for backward compatibility in tests
KEYWORD_WEIGHT = 0.4
SEMANTIC_WEIGHT = 0.6
HYBRID_BOOST = 0.15


# ── Free functions ───────────────────────────────────────────────────


def normalize_fts5_score(rank: float) -> float:
    """Normalize FTS5 rank to 0-1 scale.

    FTS5 rank is typically negative (closer to 0 is better).
    Typical range is -20 to 0.
    """
    if rank is None or rank == 0:
        return 0.5
    # Convert negative rank to positive score
    return max(0.0, min(1.0, 1.0 + (rank / 20.0)))


def normalize_fts5_scores_minmax(
    results: list[HybridSearchResult],
) -> None:
    """Normalize FTS5 keyword_score values in-place using min-max scaling.

    This produces better relative ranking within a result set than the
    fixed-range normalize_fts5_score() function.
    """
    if not results:
        return

    scores = [r.keyword_score for r in results]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score

    if score_range == 0:
        # All same score — assign uniform 0.5
        for r in results:
            r.keyword_score = 0.5
        return

    for r in results:
        r.keyword_score = (r.keyword_score - min_score) / score_range


def rrf_score(
    keyword_rank: int | None,
    semantic_rank: int | None,
    k: int = RRF_K,
) -> float:
    """Compute Reciprocal Rank Fusion score for a document.

    RRF(d) = sum( 1 / (k + rank_i(d)) ) for each list where d appears.
    Ranks are 1-based. If a document doesn't appear in a list, that term
    is omitted (not penalized).

    Args:
        keyword_rank: 1-based rank in keyword results, or None if absent.
        semantic_rank: 1-based rank in semantic results, or None if absent.
        k: RRF constant (default 60).

    Returns:
        Combined RRF score (higher is better).
    """
    score = 0.0
    if keyword_rank is not None:
        score += 1.0 / (k + keyword_rank)
    if semantic_rank is not None:
        score += 1.0 / (k + semantic_rank)
    return score


# ── Service ──────────────────────────────────────────────────────────


class HybridSearchService:
    """Canonical search service combining FTS5, semantic, tag, and fuzzy search.

    Supports two calling conventions:
    - ``search(query_str, ...)`` — the RRF-based hybrid path used by the CLI
    - ``search_unified(SearchQuery)`` — the query-parsing path used by the TUI
    """

    def __init__(self) -> None:
        self._embedding_service: EmbeddingService | None = None

    @property
    def embedding_service(self) -> EmbeddingService | None:
        """Lazy load the embedding service."""
        if self._embedding_service is None:
            try:
                from .embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except ImportError:
                logger.warning("EmbeddingService not available")
                self._embedding_service = None
        return self._embedding_service

    # ── Availability checks ──────────────────────────────────────────

    def has_embeddings(self) -> bool:
        """Check if semantic search is available."""
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM document_embeddings LIMIT 1")
                count: int = cursor.fetchone()[0]
                return count > 0
        except Exception:
            return False

    def has_chunk_index(self) -> bool:
        """Check if chunk-level index is available."""
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM chunk_embeddings LIMIT 1")
                count: int = cursor.fetchone()[0]
                return count > 0
        except Exception:
            return False

    def determine_mode(self, requested_mode: str | None = None) -> SearchMode:
        """Determine the search mode based on request and availability."""
        if requested_mode:
            try:
                return SearchMode(requested_mode.lower())
            except ValueError:
                logger.warning(f"Invalid mode '{requested_mode}', defaulting to hybrid")

        # Default: hybrid if index exists, keyword otherwise
        if self.has_embeddings() or self.has_chunk_index():
            return SearchMode.HYBRID
        return SearchMode.KEYWORD

    # ── RRF-based hybrid search (CLI path) ───────────────────────────

    def search(
        self,
        query: str,
        limit: int = 10,
        mode: str | None = None,
        extract: bool = False,
        project: str | None = None,
        doc_type: str | None = "user",
    ) -> list[HybridSearchResult]:
        """Execute hybrid search combining keyword and semantic search.

        Args:
            query: Search query text
            limit: Maximum results to return
            mode: "keyword", "semantic", or "hybrid" (auto-detect)
            extract: If True, include chunk-level text in results
            project: Filter by project name
            doc_type: Filter by document type. 'user' (default), 'wiki', or None for all.

        Returns:
            List of HybridSearchResult sorted by combined score
        """
        search_mode = self.determine_mode(mode)

        if search_mode == SearchMode.KEYWORD:
            return self._search_keyword(query, limit, project, doc_type=doc_type)
        elif search_mode == SearchMode.SEMANTIC:
            return self._search_semantic(query, limit, project, extract, doc_type=doc_type)
        else:  # HYBRID
            return self._search_hybrid(query, limit, project, extract, doc_type=doc_type)

    # ── Query-parsing search (TUI path) ──────────────────────────────

    def parse_query(self, raw_query: str) -> SearchQuery:
        """Parse a query string with special syntax.

        Syntax:
            tags:active,done  — Match documents with these tags (AND)
            tags:any:bug,error — Match documents with any of these tags (OR)
            semantic: — Enable semantic search
            ai: — Alias for semantic:
            after:2024-01-01 — Created after date
            before:2024-12-31 — Created before date
            modified:2024-01-01 — Modified after date
            project:myproject — Filter by project

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
            remaining_text = (
                remaining_text[: tags_match.start()] + remaining_text[tags_match.end() :]
            )

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
            remaining_text = (
                remaining_text[: after_match.start()] + remaining_text[after_match.end() :]
            )

        # Extract before: date
        before_match = re.search(r"before:(\d{4}-\d{2}-\d{2})", remaining_text, re.IGNORECASE)
        if before_match:
            query.created_before = parse_datetime(before_match.group(1))
            remaining_text = (
                remaining_text[: before_match.start()] + remaining_text[before_match.end() :]
            )

        # Extract modified: date
        modified_match = re.search(r"modified:(\d{4}-\d{2}-\d{2})", remaining_text, re.IGNORECASE)
        if modified_match:
            query.modified_after = parse_datetime(modified_match.group(1))
            remaining_text = (
                remaining_text[: modified_match.start()] + remaining_text[modified_match.end() :]
            )

        # Extract project: filter
        project_match = re.search(r"project:(\S+)", remaining_text, re.IGNORECASE)
        if project_match:
            query.project = project_match.group(1)
            remaining_text = (
                remaining_text[: project_match.start()] + remaining_text[project_match.end() :]
            )

        # Clean up remaining text
        query.text = " ".join(remaining_text.split()).strip()

        return query

    def _prepare_fts_query(self, text: str) -> str:
        """Prepare text for FTS5 query with prefix matching.

        Converts "ana" to "ana*" for prefix matching.
        Handles multiple words: "ana test" becomes "ana* test*"
        """
        if not text or not text.strip():
            return text

        words = text.strip().split()
        prepared_words = []
        for word in words:
            # Skip if already has FTS5 operators
            if word.endswith("*") or word.startswith("-") or word.startswith('"'):
                prepared_words.append(word)
            else:
                prepared_words.append(f"{word}*")

        return " ".join(prepared_words)

    async def search_unified(self, query: SearchQuery) -> list[HybridSearchResult]:
        """Execute search using a parsed SearchQuery (async, TUI path).

        Automatically determines which search backends to use based on query
        fields (text, tags, semantic flag).
        """
        import asyncio

        return await asyncio.to_thread(self._search_unified_sync, query)

    def _search_unified_sync(self, query: SearchQuery) -> list[HybridSearchResult]:
        """Synchronous implementation of the query-parsing search."""
        results: list[HybridSearchResult] = []
        seen_ids: set[int] = set()

        if query.text:
            # FTS5 full-text search with prefix expansion
            fts_results = self._search_fts_parsed(query)
            for result in fts_results:
                if result.doc_id not in seen_ids:
                    results.append(result)
                    seen_ids.add(result.doc_id)

            # Supplement with fuzzy title search when FTS returns few results
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
            semantic_results = self._search_semantic_parsed(query)
            for result in semantic_results:
                if result.doc_id not in seen_ids:
                    results.append(result)
                    seen_ids.add(result.doc_id)
                else:
                    for existing in results:
                        if existing.doc_id == result.doc_id:
                            existing.score = min(1.0, existing.score + result.score * 0.3)
                            existing.source = f"{existing.source}+semantic"
                            break

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[: query.limit]

        # Fetch tags for all results
        doc_ids = [r.doc_id for r in results]
        if doc_ids:
            tags_map = get_tags_for_documents(doc_ids)
            for result in results:
                result.tags = tags_map.get(result.doc_id, [])

        return results

    def _search_fts_parsed(self, query: SearchQuery) -> list[HybridSearchResult]:
        """Execute FTS5 search via the query-parsing path (prefix wildcards)."""
        created_after_str = query.created_after.isoformat() if query.created_after else None
        created_before_str = query.created_before.isoformat() if query.created_before else None
        modified_after_str = query.modified_after.isoformat() if query.modified_after else None

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
            raw_rank = doc.get("rank", 0)
            score = max(0.0, min(1.0, 1.0 + (raw_rank / 20.0))) if raw_rank else 0.5

            results.append(
                HybridSearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    project=doc.get("project"),
                    score=score,
                    keyword_score=score,
                    semantic_score=0.0,
                    source="fts",
                    snippet=(doc.get("snippet") or "")[:200],
                    created_at=parse_datetime(doc.get("created_at"))
                    if doc.get("created_at")
                    else None,
                    updated_at=parse_datetime(doc.get("updated_at"))
                    if doc.get("updated_at")
                    else None,
                )
            )

        return results

    def _search_tags(self, query: SearchQuery) -> list[HybridSearchResult]:
        """Execute tag-based search."""
        docs = search_by_tags(
            tag_names=query.tags,
            mode=query.tag_mode,
            project=query.project,
            limit=query.limit,
        )

        results = []
        for doc in docs:
            results.append(
                HybridSearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    project=doc.get("project"),
                    score=0.8,
                    keyword_score=0.0,
                    semantic_score=0.0,
                    source="tags",
                    snippet="",
                    created_at=parse_datetime(doc.get("created_at"))
                    if doc.get("created_at")
                    else None,
                )
            )

        return results

    def _search_semantic_parsed(self, query: SearchQuery) -> list[HybridSearchResult]:
        """Execute semantic search via the query-parsing path."""
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

    def _convert_semantic_matches(self, matches: list[SemanticMatch]) -> list[HybridSearchResult]:
        """Convert semantic matches to HybridSearchResult objects."""
        results = []
        for match in matches:
            results.append(
                HybridSearchResult(
                    doc_id=match.doc_id,
                    title=match.title,
                    project=match.project,
                    score=match.similarity,
                    keyword_score=0.0,
                    semantic_score=match.similarity,
                    source="semantic",
                    snippet=match.snippet,
                )
            )
        return results

    # ── Fuzzy title search ───────────────────────────────────────────

    def fuzzy_search_titles(
        self,
        query: str,
        limit: int = 20,
        threshold: float = 0.4,
        exclude_ids: set[int] | None = None,
    ) -> list[HybridSearchResult]:
        """Fuzzy search document titles using SequenceMatcher.

        Useful for command palette quick lookups where the user might
        not type exact words but expects partial matches.
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
        scored: list[tuple[float, FuzzyMatchDoc]] = []

        for row in rows:
            doc_id = row[0]
            if doc_id in exclude_ids:
                continue

            title = row[1]
            title_lower = title.lower()

            full_score = SequenceMatcher(None, query_lower, title_lower).ratio()
            contains_boost = 0.3 if query_lower in title_lower else 0.0

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
            score = min(1.0, max(full_score, word_score) + contains_boost)

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

        scored.sort(key=lambda x: -x[0])

        results = []
        for score, doc in scored[:limit]:
            results.append(
                HybridSearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    project=doc["project"],
                    score=score,
                    keyword_score=0.0,
                    semantic_score=0.0,
                    source="fuzzy",
                    snippet="",
                    created_at=parse_datetime(doc["created_at"]) if doc["created_at"] else None,
                    updated_at=parse_datetime(doc["updated_at"]) if doc["updated_at"] else None,
                )
            )

        return results

    # ── Convenience methods (TUI) ────────────────────────────────────

    def get_recent_documents(self, limit: int = 10) -> list[HybridSearchResult]:
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
                HybridSearchResult(
                    doc_id=row[0],
                    title=row[1],
                    project=row[2],
                    score=1.0,
                    keyword_score=0.0,
                    semantic_score=0.0,
                    source="recent",
                    snippet="",
                    created_at=parse_datetime(row[3]) if row[3] else None,
                    updated_at=parse_datetime(row[4]) if row[4] else None,
                )
            )

        if doc_ids:
            tags_map = get_tags_for_documents(doc_ids)
            for result in results:
                result.tags = tags_map.get(result.doc_id, [])

        return results

    def get_popular_tags(self, limit: int = 15) -> list[PopularTagDict]:
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

        return [{"name": row[0], "count": row[1]} for row in rows]

    def get_document_by_id(self, doc_id: int) -> HybridSearchResult | None:
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

        result = HybridSearchResult(
            doc_id=row[0],
            title=row[1],
            project=row[2],
            score=1.0,
            keyword_score=0.0,
            semantic_score=0.0,
            source="id",
            snippet="",
            created_at=parse_datetime(row[3]) if row[3] else None,
            updated_at=parse_datetime(row[4]) if row[4] else None,
        )

        tags_map = get_tags_for_documents([doc_id])
        result.tags = tags_map.get(doc_id, [])

        return result

    # ── RRF-based internal methods ───────────────────────────────────

    def _search_keyword(
        self,
        query: str,
        limit: int,
        project: str | None,
        doc_type: str | None = "user",
    ) -> list[HybridSearchResult]:
        """Execute FTS5 keyword search only."""
        docs = search_documents(query=query, project=project, limit=limit, doc_type=doc_type)

        results = []
        for doc in docs:
            score = normalize_fts5_score(doc.get("rank", 0))
            results.append(
                HybridSearchResult(
                    doc_id=doc["id"],
                    title=doc["title"],
                    project=doc.get("project"),
                    score=score,
                    keyword_score=score,
                    semantic_score=0.0,
                    source="keyword",
                    snippet=(doc.get("snippet") or "")[:200],
                    doc_type=doc.get("doc_type", "user"),
                )
            )

        # Re-normalize keyword scores within result set
        normalize_fts5_scores_minmax(results)
        # Set score = keyword_score after normalization
        for r in results:
            r.score = r.keyword_score

        # Fetch tags
        self._populate_tags(results)
        return results

    def _search_semantic(
        self,
        query: str,
        limit: int,
        project: str | None,
        extract: bool,
        doc_type: str | None = "user",
    ) -> list[HybridSearchResult]:
        """Execute semantic search using chunks or documents."""
        if not self.embedding_service:
            return []

        # Prefer chunk search if available
        if self.has_chunk_index():
            return self._search_chunks(query, limit, project, extract, doc_type=doc_type)

        # Fall back to document-level semantic search
        try:
            matches = self.embedding_service.search(query, limit=limit, threshold=0.3)
        except Exception as e:
            logger.debug(f"Semantic search unavailable: {e}")
            return []

        # Filter by project if specified
        if project:
            matches = [m for m in matches if m.project == project]

        # Filter by doc_type if specified
        if doc_type is not None:
            allowed_ids = self._get_doc_ids_by_type([m.doc_id for m in matches], doc_type)
            matches = [m for m in matches if m.doc_id in allowed_ids]

        results = []
        for match in matches:
            results.append(
                HybridSearchResult(
                    doc_id=match.doc_id,
                    title=match.title,
                    project=match.project,
                    score=match.similarity,
                    keyword_score=0.0,
                    semantic_score=match.similarity,
                    source="semantic",
                    snippet=match.snippet,
                )
            )

        self._populate_tags(results)
        self._populate_doc_types(results)
        return results

    def _search_chunks(
        self,
        query: str,
        limit: int,
        project: str | None,
        extract: bool,
        doc_type: str | None = "user",
    ) -> list[HybridSearchResult]:
        """Search at chunk level for more precise results."""
        if not self.embedding_service:
            return []

        try:
            matches = self.embedding_service.search_chunks(
                query,
                limit=limit * 2,
                threshold=0.3,  # Get more, then dedupe
            )
        except Exception as e:
            logger.debug(f"Chunk search unavailable: {e}")
            return []

        # Filter by project
        if project:
            matches = [m for m in matches if m.project == project]

        # Filter by doc_type
        if doc_type is not None:
            allowed_ids = self._get_doc_ids_by_type([m.doc_id for m in matches], doc_type)
            matches = [m for m in matches if m.doc_id in allowed_ids]

        # Deduplicate by document, keeping highest-scoring chunk
        seen_docs: set[int] = set()
        results: list[HybridSearchResult] = []

        for match in matches:
            if match.doc_id in seen_docs:
                # Boost existing result slightly for multi-chunk hits
                for r in results:
                    if r.doc_id == match.doc_id:
                        r.score = min(1.0, r.score + 0.05)
                        r.semantic_score = r.score
                        break
                continue

            seen_docs.add(match.doc_id)

            chunk_preview = (
                match.chunk_text[:200] + "..." if len(match.chunk_text) > 200 else match.chunk_text
            )

            results.append(
                HybridSearchResult(
                    doc_id=match.doc_id,
                    title=match.title,
                    project=match.project,
                    score=match.similarity,
                    keyword_score=0.0,
                    semantic_score=match.similarity,
                    source="semantic",
                    snippet=chunk_preview,
                    chunk_heading=match.heading_path,
                    chunk_text=(match.chunk_text if extract else None),
                )
            )

            if len(results) >= limit:
                break

        self._populate_tags(results)
        self._populate_doc_types(results)
        return results

    def _search_hybrid(
        self,
        query: str,
        limit: int,
        project: str | None,
        extract: bool,
        doc_type: str | None = "user",
    ) -> list[HybridSearchResult]:
        """Combine keyword and semantic results with Reciprocal Rank Fusion."""
        keyword_results = self._search_keyword(query, limit * 2, project, doc_type=doc_type)
        semantic_results = self._search_semantic(
            query, limit * 2, project, extract, doc_type=doc_type
        )

        # Build rank maps (1-based)
        keyword_ranks: dict[int, int] = {
            r.doc_id: rank for rank, r in enumerate(keyword_results, start=1)
        }
        semantic_ranks: dict[int, int] = {
            r.doc_id: rank for rank, r in enumerate(semantic_results, start=1)
        }

        all_doc_ids = set(keyword_ranks.keys()) | set(semantic_ranks.keys())

        keyword_by_id = {r.doc_id: r for r in keyword_results}
        semantic_by_id = {r.doc_id: r for r in semantic_results}

        merged: list[HybridSearchResult] = []
        for doc_id in all_doc_ids:
            kw_rank = keyword_ranks.get(doc_id)
            sem_rank = semantic_ranks.get(doc_id)

            score = rrf_score(kw_rank, sem_rank)

            kw_result = keyword_by_id.get(doc_id)
            sem_result = semantic_by_id.get(doc_id)

            if kw_result and sem_result:
                source = "hybrid"
            elif kw_result:
                source = "keyword"
            else:
                source = "semantic"

            if sem_result and kw_result:
                snippet = sem_result.snippet or kw_result.snippet
                title = kw_result.title
                proj = kw_result.project
                tags = kw_result.tags or sem_result.tags
                dtype = kw_result.doc_type
            elif sem_result:
                snippet = sem_result.snippet
                title = sem_result.title
                proj = sem_result.project
                tags = sem_result.tags
                dtype = sem_result.doc_type
            else:
                assert kw_result is not None
                snippet = kw_result.snippet
                title = kw_result.title
                proj = kw_result.project
                tags = kw_result.tags
                dtype = kw_result.doc_type

            merged.append(
                HybridSearchResult(
                    doc_id=doc_id,
                    title=title,
                    project=proj,
                    score=score,
                    keyword_score=(kw_result.keyword_score if kw_result else 0.0),
                    semantic_score=(sem_result.semantic_score if sem_result else 0.0),
                    source=source,
                    snippet=snippet,
                    tags=tags,
                    doc_type=dtype,
                    chunk_heading=(sem_result.chunk_heading if sem_result else None),
                    chunk_text=(sem_result.chunk_text if sem_result else None),
                )
            )

        merged.sort(key=lambda r: r.score, reverse=True)

        if merged:
            max_rrf = merged[0].score
            if max_rrf > 0:
                for r in merged:
                    r.score = r.score / max_rrf

        return merged[:limit]

    # ── Internal helpers ─────────────────────────────────────────────

    def _get_doc_ids_by_type(self, doc_ids: list[int], doc_type: str) -> set[int]:
        """Return the subset of doc_ids that match the given doc_type."""
        if not doc_ids:
            return set()
        with db.get_connection() as conn:
            placeholders = ",".join("?" * len(doc_ids))
            cursor = conn.execute(
                f"SELECT id FROM documents WHERE id IN ({placeholders}) AND doc_type = ?",
                [*doc_ids, doc_type],
            )
            return {row[0] for row in cursor.fetchall()}

    def _populate_tags(self, results: list[HybridSearchResult]) -> None:
        """Fetch and populate tags for all results."""
        if not results:
            return

        doc_ids = [r.doc_id for r in results]
        tags_map = get_tags_for_documents(doc_ids)

        for result in results:
            result.tags = tags_map.get(result.doc_id, [])

    def _populate_doc_types(self, results: list[HybridSearchResult]) -> None:
        """Fetch and populate doc_type for all results."""
        if not results:
            return
        doc_ids = [r.doc_id for r in results]
        with db.get_connection() as conn:
            placeholders = ",".join("?" * len(doc_ids))
            cursor = conn.execute(
                f"SELECT id, doc_type FROM documents WHERE id IN ({placeholders})",
                doc_ids,
            )
            type_map = {row[0]: row[1] for row in cursor.fetchall()}
        for result in results:
            result.doc_type = type_map.get(result.doc_id, "user")
