"""
Document merging service for EMDX.
Intelligently merges related documents while preserving important information.

Uses TF-IDF pre-filtering for O(n) merge candidate search instead of O(n²)
pairwise comparison. The SimilarityService handles vectorization and cosine
similarity via efficient matrix operations.
"""

import difflib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from ..config.settings import get_db_path
from ..database.connection import DatabaseConnection
from ..services.types import DocumentMetadata
from .similarity import SimilarityService

logger = logging.getLogger(__name__)


@dataclass
class MergeCandidate:
    """Represents a pair of documents that could be merged."""

    doc1_id: int
    doc2_id: int
    doc1_title: str
    doc2_title: str
    similarity_score: float
    merge_reason: str
    recommended_action: str


class DocumentMerger:
    """Service for intelligently merging related documents.

    Uses TF-IDF pre-filtering via SimilarityService to achieve O(n) complexity
    for merge candidate search instead of O(n²) pairwise comparison.
    """

    SIMILARITY_THRESHOLD = 0.7  # Minimum similarity for merge candidates
    PREFILTER_THRESHOLD = 0.3  # Lower threshold for TF-IDF pre-filtering

    def __init__(self, db_path: Union[str, Path] | None = None):
        self.db_path = Path(db_path) if db_path else get_db_path()
        self._db = DatabaseConnection(self.db_path)
        self._similarity_service = SimilarityService(self.db_path)

    def find_merge_candidates(
        self,
        project: str | None = None,
        similarity_threshold: float | None = None,
        progress_callback: Callable | None = None,
    ) -> list[MergeCandidate]:
        """
        Find documents that are candidates for merging.

        Uses TF-IDF pre-filtering via SimilarityService for O(n) complexity
        instead of O(n²) pairwise comparison. The algorithm:
        1. Build TF-IDF index of all documents (O(n))
        2. Compute similarity matrix via sparse matrix operations (O(n*k))
        3. Filter pairs above threshold
        4. Refine with title similarity for final scoring

        Args:
            project: Filter by specific project
            similarity_threshold: Minimum similarity score (0-1)
            progress_callback: Optional callback(current, total, found) for progress updates

        Returns:
            List of merge candidates sorted by similarity
        """
        threshold = similarity_threshold or self.SIMILARITY_THRESHOLD

        # Rebuild index to ensure fresh data
        if progress_callback:
            progress_callback(0, 100, 0)

        self._similarity_service.build_index(force=True)

        if progress_callback:
            progress_callback(20, 100, 0)

        # Use TF-IDF pre-filtering with lower threshold to catch potential candidates
        # The find_all_duplicate_pairs method uses efficient matrix operations
        prefilter_threshold = min(self.PREFILTER_THRESHOLD, threshold * 0.5)
        similar_pairs = self._similarity_service.find_all_duplicate_pairs(
            min_similarity=prefilter_threshold,
            progress_callback=lambda c, t, f: (
                progress_callback(20 + int(c * 0.5), 100, f) if progress_callback else None
            ),  # noqa: E501
        )

        if progress_callback:
            progress_callback(70, 100, len(similar_pairs))

        # Get document metadata for filtering and scoring
        doc_metadata = self._get_document_metadata(project)

        if progress_callback:
            progress_callback(75, 100, len(similar_pairs))

        candidates: list[MergeCandidate] = []
        total_pairs = len(similar_pairs)

        for i, (doc1_id, doc2_id, doc1_title, doc2_title, tfidf_sim) in enumerate(similar_pairs):
            # Report progress
            if progress_callback and i % 100 == 0:
                progress_callback(75 + int((i / max(total_pairs, 1)) * 20), 100, len(candidates))

            # Skip if project filter doesn't match
            if project:
                doc1_meta = doc_metadata.get(doc1_id)
                doc2_meta = doc_metadata.get(doc2_id)
                if not doc1_meta or not doc2_meta:
                    continue
                if doc1_meta["project"] != project and doc2_meta["project"] != project:
                    continue

            # Get metadata for both docs
            doc1_meta = doc_metadata.get(doc1_id)
            doc2_meta = doc_metadata.get(doc2_id)

            if not doc1_meta or not doc2_meta:
                continue

            # Skip if both have high access counts (likely both important)
            if doc1_meta["access_count"] > 50 and doc2_meta["access_count"] > 50:
                continue

            # Calculate title similarity for refined scoring
            title_sim = self._calculate_similarity(doc1_title, doc2_title)

            # Combine TF-IDF content similarity with title similarity
            # TF-IDF already captures content similarity well
            overall_sim = (title_sim * 0.4) + (tfidf_sim * 0.6)

            if overall_sim >= threshold:
                # Determine merge reason
                if title_sim > 0.8:
                    reason = "Nearly identical titles"
                elif tfidf_sim > 0.9:
                    reason = "Nearly identical content"
                elif title_sim > 0.6 and tfidf_sim > 0.7:
                    reason = "Similar title and content"
                else:
                    reason = "Related content"

                # Recommend which to keep
                doc1_content_len = len(doc1_meta.get("content") or "")
                doc2_content_len = len(doc2_meta.get("content") or "")

                if doc1_meta["access_count"] > doc2_meta["access_count"]:
                    action = f"Merge into #{doc1_id} (more views)"
                elif doc1_content_len > doc2_content_len:
                    action = f"Merge into #{doc1_id} (more content)"
                else:
                    action = f"Merge into #{doc2_id}"

                candidates.append(
                    MergeCandidate(
                        doc1_id=doc1_id,
                        doc2_id=doc2_id,
                        doc1_title=doc1_title,
                        doc2_title=doc2_title,
                        similarity_score=overall_sim,
                        merge_reason=reason,
                        recommended_action=action,
                    )
                )

        if progress_callback:
            progress_callback(100, 100, len(candidates))

        # Sort by similarity score
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)
        return candidates

    def _get_document_metadata(self, project: str | None = None) -> dict[int, DocumentMetadata]:
        """
        Get metadata for all active documents.

        Args:
            project: Optional project filter

        Returns:
            Dict mapping doc_id to metadata dict
        """
        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT id, title, content, project, access_count
                FROM documents
                WHERE is_deleted = 0
            """
            params = []

            if project:
                query += " AND project = ?"
                params.append(project)

            cursor.execute(query, params)
            documents = cursor.fetchall()

        return {
            doc["id"]: {
                "title": doc["title"],
                "content": doc["content"],
                "project": doc["project"],
                "access_count": doc["access_count"],
            }
            for doc in documents
        }

    def _merge_content(self, content1: str, content2: str, title1: str, title2: str) -> str:
        """Intelligently merge two document contents."""
        if not content1:
            return content2
        if not content2:
            return content1
        if content1 == content2:
            return content1
        if content1 in content2:
            return content2
        if content2 in content1:
            return content1

        merged = [content1, "\n\n---\n"]
        if title1 != title2:
            merged.append(f"\n_Merged from: {title2}_\n")
        else:
            merged.append("\n_Additional content from duplicate:_\n")
        merged.append("\n" + content2)
        return "".join(merged)

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using SequenceMatcher."""
        if not text1 or not text2:
            return 0.0

        # Quick check for exact match
        if text1 == text2:
            return 1.0

        # Use SequenceMatcher for similarity
        return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
