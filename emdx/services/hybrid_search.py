"""
Hybrid search service for EMDX.

Combines FTS5 keyword search with chunk-level semantic search,
providing unified search that finds both exact matches and
conceptually related content.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..database import db
from ..database.search import search_documents
from ..models.tags import get_tags_for_documents

if TYPE_CHECKING:
    from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search mode determines which backends to use."""

    KEYWORD = "keyword"  # FTS5 only (fast, exact)
    SEMANTIC = "semantic"  # Embedding search only (conceptual)
    HYBRID = "hybrid"  # Both combined (default when index exists)


@dataclass
class HybridSearchResult:
    """A unified search result with combined scoring."""

    doc_id: int
    title: str
    project: str | None
    score: float  # Normalized 0-1, combined score
    keyword_score: float  # FTS5 score component
    semantic_score: float  # Semantic score component
    source: str  # "keyword", "semantic", or "hybrid"
    snippet: str
    tags: list[str] = field(default_factory=list)
    # Chunk-level data (populated when extract=True or from semantic search)
    chunk_heading: str | None = None
    chunk_text: str | None = None


# Weights for combining keyword and semantic scores
KEYWORD_WEIGHT = 0.4
SEMANTIC_WEIGHT = 0.6
# Boost for documents found by both methods
HYBRID_BOOST = 0.15


def normalize_fts5_score(rank: float) -> float:
    """Normalize FTS5 rank to 0-1 scale.

    FTS5 rank is typically negative (closer to 0 is better).
    Typical range is -20 to 0.
    """
    if rank is None or rank == 0:
        return 0.5
    # Convert negative rank to positive score
    return max(0.0, min(1.0, 1.0 + (rank / 20.0)))


class HybridSearchService:
    """Combines FTS5 and semantic search into a unified search experience."""

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
        """Determine the search mode based on request and index availability."""
        if requested_mode:
            try:
                return SearchMode(requested_mode.lower())
            except ValueError:
                logger.warning(f"Invalid mode '{requested_mode}', defaulting to hybrid")

        # Default: hybrid if index exists, keyword otherwise
        if self.has_embeddings() or self.has_chunk_index():
            return SearchMode.HYBRID
        return SearchMode.KEYWORD

    def search(
        self,
        query: str,
        limit: int = 10,
        mode: str | None = None,
        extract: bool = False,
        project: str | None = None,
    ) -> list[HybridSearchResult]:
        """
        Execute hybrid search combining keyword and semantic search.

        Args:
            query: Search query text
            limit: Maximum results to return
            mode: "keyword", "semantic", or "hybrid" (default: auto-detect)
            extract: If True, include chunk-level text in results
            project: Filter by project name

        Returns:
            List of HybridSearchResult sorted by combined score
        """
        search_mode = self.determine_mode(mode)

        if search_mode == SearchMode.KEYWORD:
            return self._search_keyword(query, limit, project)
        elif search_mode == SearchMode.SEMANTIC:
            return self._search_semantic(query, limit, project, extract)
        else:  # HYBRID
            return self._search_hybrid(query, limit, project, extract)

    def _search_keyword(
        self, query: str, limit: int, project: str | None
    ) -> list[HybridSearchResult]:
        """Execute FTS5 keyword search only."""
        docs = search_documents(query=query, project=project, limit=limit)

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
                )
            )

        # Fetch tags
        self._populate_tags(results)
        return results

    def _search_semantic(
        self, query: str, limit: int, project: str | None, extract: bool
    ) -> list[HybridSearchResult]:
        """Execute semantic search using chunks or documents."""
        if not self.embedding_service:
            return []

        # Prefer chunk search if available
        if self.has_chunk_index():
            return self._search_chunks(query, limit, project, extract)

        # Fall back to document-level semantic search
        try:
            matches = self.embedding_service.search(query, limit=limit, threshold=0.3)
        except Exception as e:
            logger.debug(f"Semantic search unavailable: {e}")
            return []

        # Filter by project if specified
        if project:
            matches = [m for m in matches if m.project == project]

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
        return results

    def _search_chunks(
        self, query: str, limit: int, project: str | None, extract: bool
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

        # Deduplicate by document, keeping highest-scoring chunk per doc
        seen_docs: set[int] = set()
        results: list[HybridSearchResult] = []

        for match in matches:
            if match.doc_id in seen_docs:
                # Boost existing result if this chunk also matches well
                for r in results:
                    if r.doc_id == match.doc_id:
                        r.score = min(1.0, r.score + 0.05)  # Small boost
                        break
                continue

            seen_docs.add(match.doc_id)

            # Build snippet from chunk
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
                    chunk_text=match.chunk_text if extract else None,
                )
            )

            if len(results) >= limit:
                break

        self._populate_tags(results)
        return results

    def _search_hybrid(
        self, query: str, limit: int, project: str | None, extract: bool
    ) -> list[HybridSearchResult]:
        """
        Combine keyword and semantic search results.

        Strategy:
        1. Run FTS5 keyword search
        2. Run semantic search (chunks preferred)
        3. Merge results with weighted scoring
        4. Boost documents found by both methods
        5. Deduplicate and return top results
        """
        # Run both searches
        keyword_results = self._search_keyword(query, limit * 2, project)
        semantic_results = self._search_semantic(query, limit * 2, project, extract)

        # Build lookup map
        semantic_by_id = {r.doc_id: r for r in semantic_results}

        # Merge results
        merged: dict[int, HybridSearchResult] = {}

        # Process keyword results
        for result in keyword_results:
            if result.doc_id in semantic_by_id:
                # Found in both - combine scores with boost
                sem_result = semantic_by_id[result.doc_id]
                combined_score = (
                    KEYWORD_WEIGHT * result.keyword_score
                    + SEMANTIC_WEIGHT * sem_result.semantic_score
                    + HYBRID_BOOST  # Boost for appearing in both
                )
                combined_score = min(1.0, combined_score)

                merged[result.doc_id] = HybridSearchResult(
                    doc_id=result.doc_id,
                    title=result.title,
                    project=result.project,
                    score=combined_score,
                    keyword_score=result.keyword_score,
                    semantic_score=sem_result.semantic_score,
                    source="hybrid",
                    # Prefer semantic snippet (chunk-based)
                    snippet=sem_result.snippet or result.snippet,
                    tags=result.tags or sem_result.tags,
                    chunk_heading=sem_result.chunk_heading,
                    chunk_text=sem_result.chunk_text,
                )
            else:
                # Keyword only
                result.score = KEYWORD_WEIGHT * result.keyword_score
                merged[result.doc_id] = result

        # Add semantic-only results
        for result in semantic_results:
            if result.doc_id not in merged:
                result.score = SEMANTIC_WEIGHT * result.semantic_score
                merged[result.doc_id] = result

        # Sort by combined score and limit
        final_results = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        return final_results[:limit]

    def _populate_tags(self, results: list[HybridSearchResult]) -> None:
        """Fetch and populate tags for all results."""
        if not results:
            return

        doc_ids = [r.doc_id for r in results]
        tags_map = get_tags_for_documents(doc_ids)

        for result in results:
            result.tags = tags_map.get(result.doc_id, [])
