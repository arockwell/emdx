"""
Hybrid search service for EMDX.

Combines FTS5 keyword search with chunk-level semantic search
using Reciprocal Rank Fusion (RRF) for better relevance ranking.
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
    keyword_score: float  # FTS5 score component (normalized)
    semantic_score: float  # Semantic score component (cosine similarity)
    source: str  # "keyword", "semantic", or "hybrid"
    snippet: str
    tags: list[str] = field(default_factory=list)
    # Chunk-level data (populated when extract=True or from semantic search)
    chunk_heading: str | None = None
    chunk_text: str | None = None


# Reciprocal Rank Fusion constant (standard default from Cormack et al.)
# Higher k reduces the impact of high rankings from a single list.
RRF_K = 60

# Legacy weight constants kept for backward compatibility in tests
KEYWORD_WEIGHT = 0.4
SEMANTIC_WEIGHT = 0.6
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

    def search(
        self,
        query: str,
        limit: int = 10,
        mode: str | None = None,
        extract: bool = False,
        project: str | None = None,
    ) -> list[HybridSearchResult]:
        """Execute hybrid search combining keyword and semantic search.

        Args:
            query: Search query text
            limit: Maximum results to return
            mode: "keyword", "semantic", or "hybrid" (auto-detect)
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
        self,
        query: str,
        limit: int,
        project: str | None,
        extract: bool,
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
        return results

    def _search_hybrid(
        self,
        query: str,
        limit: int,
        project: str | None,
        extract: bool,
    ) -> list[HybridSearchResult]:
        """Combine keyword and semantic results with Reciprocal Rank Fusion.

        Strategy:
        1. Run FTS5 keyword search (returns ranked list)
        2. Run semantic search — chunks preferred (returns ranked list)
        3. Assign 1-based ranks to each list
        4. Merge using RRF: score(d) = sum(1/(k + rank_i(d)))
        5. Preserve component scores for observability
        6. Return top results sorted by RRF score
        """
        # Run both searches — fetch extra candidates for better fusion
        keyword_results = self._search_keyword(query, limit * 2, project)
        semantic_results = self._search_semantic(query, limit * 2, project, extract)

        # Build rank maps (1-based)
        keyword_ranks: dict[int, int] = {
            r.doc_id: rank for rank, r in enumerate(keyword_results, start=1)
        }
        semantic_ranks: dict[int, int] = {
            r.doc_id: rank for rank, r in enumerate(semantic_results, start=1)
        }

        # Collect all doc IDs
        all_doc_ids = set(keyword_ranks.keys()) | set(semantic_ranks.keys())

        # Build lookup maps for metadata
        keyword_by_id = {r.doc_id: r for r in keyword_results}
        semantic_by_id = {r.doc_id: r for r in semantic_results}

        # Compute RRF score for each document and build results
        merged: list[HybridSearchResult] = []
        for doc_id in all_doc_ids:
            kw_rank = keyword_ranks.get(doc_id)
            sem_rank = semantic_ranks.get(doc_id)

            score = rrf_score(kw_rank, sem_rank)

            kw_result = keyword_by_id.get(doc_id)
            sem_result = semantic_by_id.get(doc_id)

            # Determine source label
            if kw_result and sem_result:
                source = "hybrid"
            elif kw_result:
                source = "keyword"
            else:
                source = "semantic"

            # Pick best metadata from available results
            # Prefer semantic snippet (chunk-based, more precise)
            if sem_result and kw_result:
                snippet = sem_result.snippet or kw_result.snippet
                title = kw_result.title
                proj = kw_result.project
                tags = kw_result.tags or sem_result.tags
            elif sem_result:
                snippet = sem_result.snippet
                title = sem_result.title
                proj = sem_result.project
                tags = sem_result.tags
            else:
                assert kw_result is not None
                snippet = kw_result.snippet
                title = kw_result.title
                proj = kw_result.project
                tags = kw_result.tags

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
                    chunk_heading=(sem_result.chunk_heading if sem_result else None),
                    chunk_text=(sem_result.chunk_text if sem_result else None),
                )
            )

        # Sort by RRF score descending
        merged.sort(key=lambda r: r.score, reverse=True)

        # Normalize RRF scores to 0-1 for display consistency
        if merged:
            max_rrf = merged[0].score
            if max_rrf > 0:
                for r in merged:
                    r.score = r.score / max_rrf

        return merged[:limit]

    def _populate_tags(self, results: list[HybridSearchResult]) -> None:
        """Fetch and populate tags for all results."""
        if not results:
            return

        doc_ids = [r.doc_id for r in results]
        tags_map = get_tags_for_documents(doc_ids)

        for result in results:
            result.tags = tags_map.get(result.doc_id, [])
