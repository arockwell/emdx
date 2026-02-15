"""
TF-IDF-based document similarity service for EMDX.

Uses scikit-learn's TfidfVectorizer to compute document similarity
with hybrid scoring that combines content similarity and tag similarity.

For duplicate detection, uses radius-based nearest neighbor search
(ball tree) to achieve O(n*k) complexity instead of O(n²) pairwise
comparison, where k is the average number of similar documents per doc.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Set

from ..config.constants import EMDX_CONFIG_DIR

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from ..database import db


def _require_sklearn() -> None:
    """Raise ImportError with helpful message if sklearn is not installed."""
    if not HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for similarity features. "
            "Install it with: pip install 'emdx[similarity]'"
        )


@dataclass
class SimilarDocument:
    """Represents a document similar to a query document."""
    doc_id: int
    title: str
    project: str | None
    similarity_score: float
    content_similarity: float
    tag_similarity: float
    common_tags: List[str]


@dataclass
class IndexStats:
    """Statistics about the TF-IDF index."""
    document_count: int
    vocabulary_size: int
    cache_size_bytes: int
    cache_age_seconds: float
    last_built: datetime | None


class SimilarityService:
    """TF-IDF-based document similarity service."""

    # Configuration
    MAX_FEATURES = 10000      # Vocabulary size limit
    MIN_DF = 2                # Minimum document frequency
    MAX_DF = 0.95             # Maximum document frequency
    CONTENT_WEIGHT = 0.6      # Content similarity weight
    TAG_WEIGHT = 0.4          # Tag similarity weight

    def __init__(self, db_path: Path | None = None):
        """Initialize the similarity service.

        Args:
            db_path: Optional database path (unused, kept for API compatibility)
        """
        # Get cache directory
        self._cache_dir = EMDX_CONFIG_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / "similarity_cache.pkl"

        # Index state
        self._vectorizer: TfidfVectorizer | None = None
        self._tfidf_matrix = None
        self._doc_ids: List[int] = []
        self._doc_titles: List[str] = []
        self._doc_projects: List[str | None] = []
        self._doc_tags: List[Set[str]] = []
        self._last_built: datetime | None = None

    def _load_cache(self) -> bool:
        """Load the cached index if it exists.

        Returns:
            True if cache was loaded successfully, False otherwise
        """
        if not self._cache_path.exists():
            return False

        try:
            with open(self._cache_path, 'rb') as f:
                cache_data = pickle.load(f)

            self._vectorizer = cache_data['vectorizer']
            self._tfidf_matrix = cache_data['tfidf_matrix']
            self._doc_ids = cache_data['doc_ids']
            self._doc_titles = cache_data['doc_titles']
            self._doc_projects = cache_data['doc_projects']
            self._doc_tags = cache_data['doc_tags']
            self._last_built = cache_data.get('last_built')
            return True
        except (OSError, pickle.UnpicklingError, KeyError) as e:
            logger.debug("Failed to load similarity cache: %s", e)
            return False

    def _save_cache(self) -> None:
        """Save the current index to cache."""
        cache_data = {
            'vectorizer': self._vectorizer,
            'tfidf_matrix': self._tfidf_matrix,
            'doc_ids': self._doc_ids,
            'doc_titles': self._doc_titles,
            'doc_projects': self._doc_projects,
            'doc_tags': self._doc_tags,
            'last_built': self._last_built
        }

        with open(self._cache_path, 'wb') as f:
            pickle.dump(cache_data, f)

    def _ensure_index(self) -> None:
        """Ensure the index is loaded, building if necessary."""
        if self._vectorizer is None:
            if not self._load_cache():
                self.build_index()

    def build_index(self, force: bool = False) -> IndexStats:
        """Build or rebuild the TF-IDF index.

        Args:
            force: If True, rebuild even if cache exists

        Returns:
            Statistics about the built index
        """
        _require_sklearn()
        if not force and self._vectorizer is not None:
            return self.get_index_stats()

        # Fetch all documents from database
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active documents with their content
            cursor.execute("""
                SELECT
                    d.id,
                    d.title,
                    d.content,
                    d.project,
                    GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = 0
                AND LENGTH(d.content) > 50
                GROUP BY d.id
                ORDER BY d.id
            """)

            documents = cursor.fetchall()

        if not documents:
            # Empty corpus - create minimal state
            self._vectorizer = TfidfVectorizer(
                max_features=self.MAX_FEATURES,
                min_df=1,
                max_df=self.MAX_DF,
                stop_words='english',
                ngram_range=(1, 2),
                sublinear_tf=True,
            )
            self._tfidf_matrix = None
            self._doc_ids = []
            self._doc_titles = []
            self._doc_projects = []
            self._doc_tags = []
            self._last_built = datetime.now()
            self._save_cache()
            return self.get_index_stats()

        # Prepare document data
        self._doc_ids = []
        self._doc_titles = []
        self._doc_projects = []
        self._doc_tags = []
        corpus = []

        for doc in documents:
            self._doc_ids.append(doc['id'])
            self._doc_titles.append(doc['title'])
            self._doc_projects.append(doc['project'])

            # Parse tags
            tags_str = doc['tags'] or ''
            tags = set(t.strip() for t in tags_str.split(',') if t.strip())
            self._doc_tags.append(tags)

            # Combine title and content for TF-IDF
            text = f"{doc['title']} {doc['content']}"
            corpus.append(text)

        # Build TF-IDF matrix
        min_df = min(self.MIN_DF, len(corpus)) if len(corpus) > 1 else 1
        self._vectorizer = TfidfVectorizer(
            max_features=self.MAX_FEATURES,
            min_df=min_df,
            max_df=self.MAX_DF,
            stop_words='english',
            ngram_range=(1, 2),
            sublinear_tf=True,
        )

        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        self._last_built = datetime.now()

        # Save cache
        self._save_cache()

        return self.get_index_stats()

    def _calculate_tag_similarity(self, tags1: Set[str], tags2: Set[str]) -> float:
        """Calculate Jaccard similarity between two tag sets.

        Args:
            tags1: First set of tags
            tags2: Second set of tags

        Returns:
            Jaccard similarity coefficient (0.0 to 1.0)
        """
        if not tags1 and not tags2:
            return 0.0
        if not tags1 or not tags2:
            return 0.0

        intersection = len(tags1 & tags2)
        union = len(tags1 | tags2)

        return intersection / union if union > 0 else 0.0

    def find_similar(
        self,
        doc_id: int,
        limit: int = 5,
        min_similarity: float = 0.1,
        content_only: bool = False,
        tags_only: bool = False,
        same_project: bool = False
    ) -> List[SimilarDocument]:
        """Find documents similar to the given document.

        Args:
            doc_id: Document ID to find similar documents for
            limit: Maximum number of results to return
            min_similarity: Minimum similarity score threshold
            content_only: Only use content similarity (ignore tags)
            tags_only: Only use tag similarity (ignore content)
            same_project: Only find similar docs in same project

        Returns:
            List of similar documents, ordered by similarity score
        """
        _require_sklearn()
        self._ensure_index()

        if not self._doc_ids or self._tfidf_matrix is None:
            return []

        # Find the document index
        try:
            doc_index = self._doc_ids.index(doc_id)
        except ValueError:
            # Document not in index - try rebuilding
            self.build_index(force=True)
            try:
                doc_index = self._doc_ids.index(doc_id)
            except ValueError:
                return []

        query_tags = self._doc_tags[doc_index]
        query_project = self._doc_projects[doc_index]

        # Compute content similarities
        if tags_only:
            content_similarities = [0.0] * len(self._doc_ids)
        else:
            doc_vector = self._tfidf_matrix[doc_index:doc_index+1]
            content_similarities = cosine_similarity(doc_vector, self._tfidf_matrix)[0]

        # Compute hybrid scores
        results = []
        for i, other_doc_id in enumerate(self._doc_ids):
            if other_doc_id == doc_id:
                continue

            # Apply project filter
            if same_project and self._doc_projects[i] != query_project:
                continue

            content_sim = float(content_similarities[i])
            tag_sim = self._calculate_tag_similarity(query_tags, self._doc_tags[i])

            # Calculate hybrid score
            if content_only:
                score = content_sim
            elif tags_only:
                score = tag_sim
            else:
                score = (self.CONTENT_WEIGHT * content_sim +
                         self.TAG_WEIGHT * tag_sim)

            if score >= min_similarity:
                common_tags = list(query_tags & self._doc_tags[i])
                results.append(SimilarDocument(
                    doc_id=other_doc_id,
                    title=self._doc_titles[i],
                    project=self._doc_projects[i],
                    similarity_score=score,
                    content_similarity=content_sim,
                    tag_similarity=tag_sim,
                    common_tags=common_tags
                ))

        # Sort by score and limit
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:limit]

    def find_similar_by_text(
        self,
        text: str,
        limit: int = 5,
        min_similarity: float = 0.1
    ) -> List[SimilarDocument]:
        """Find documents similar to arbitrary text.

        Args:
            text: Text to find similar documents for
            limit: Maximum number of results to return
            min_similarity: Minimum similarity score threshold

        Returns:
            List of similar documents, ordered by similarity score
        """
        _require_sklearn()
        self._ensure_index()

        if not self._doc_ids or self._tfidf_matrix is None or self._vectorizer is None:
            return []

        # Transform the query text
        query_vector = self._vectorizer.transform([text])

        # Compute similarities
        similarities = cosine_similarity(query_vector, self._tfidf_matrix)[0]

        # Build results
        results = []
        for i, doc_id in enumerate(self._doc_ids):
            score = float(similarities[i])

            if score >= min_similarity:
                results.append(SimilarDocument(
                    doc_id=doc_id,
                    title=self._doc_titles[i],
                    project=self._doc_projects[i],
                    similarity_score=score,
                    content_similarity=score,
                    tag_similarity=0.0,  # No tag comparison for text queries
                    common_tags=[]
                ))

        # Sort by score and limit
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:limit]

    def get_index_stats(self) -> IndexStats:
        """Get statistics about the current index.

        Returns:
            Statistics about the index
        """
        cache_size = 0
        if self._cache_path.exists():
            cache_size = self._cache_path.stat().st_size

        cache_age = 0.0
        if self._last_built:
            cache_age = (datetime.now() - self._last_built).total_seconds()

        vocab_size = 0
        if self._vectorizer is not None:
            try:
                vocab_size = len(self._vectorizer.vocabulary_)
            except AttributeError:
                # Vectorizer may not have vocabulary_ if not fitted yet
                logger.debug("Vectorizer has no vocabulary_ attribute, may not be fitted")

        return IndexStats(
            document_count=len(self._doc_ids),
            vocabulary_size=vocab_size,
            cache_size_bytes=cache_size,
            cache_age_seconds=cache_age,
            last_built=self._last_built
        )

    def invalidate_cache(self) -> None:
        """Clear the cached index (force rebuild on next query)."""
        if self._cache_path.exists():
            self._cache_path.unlink()

        self._vectorizer = None
        self._tfidf_matrix = None
        self._doc_ids = []
        self._doc_titles = []
        self._doc_projects = []
        self._doc_tags = []
        self._last_built = None

    def find_all_duplicate_pairs(
        self,
        min_similarity: float = 0.7,
        progress_callback: Callable | None = None,
    ) -> List[tuple]:
        """Find all pairs of similar documents efficiently using radius neighbors.

        Uses sklearn NearestNeighbors with radius_neighbors for O(n*k) complexity
        where k is the average number of similar neighbors per document, instead of
        O(n²) pairwise comparison.

        The algorithm:
        1. Build a ball tree index on TF-IDF vectors (O(n log n))
        2. Query radius neighbors for each document (O(n*k) total)
        3. Convert cosine distance to similarity and filter by threshold

        Args:
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            progress_callback: Optional callback(current, total, found) for progress

        Returns:
            List of tuples: (doc1_id, doc2_id, doc1_title, doc2_title, similarity)
        """
        _require_sklearn()
        self._ensure_index()

        if not self._doc_ids or self._tfidf_matrix is None:
            return []

        import numpy as np
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import normalize

        n_docs = len(self._doc_ids)

        if progress_callback:
            progress_callback(0, 100, 0)

        # Normalize vectors for cosine similarity computation
        # For normalized vectors: cosine_similarity = 1 - (euclidean_distance² / 2)
        # So: euclidean_distance = sqrt(2 * (1 - cosine_similarity))
        normalized_matrix = normalize(self._tfidf_matrix, norm='l2')

        # Convert similarity threshold to distance threshold
        # cosine_sim = 1 - (dist² / 2), so dist = sqrt(2 * (1 - sim))
        max_distance = np.sqrt(2 * (1 - min_similarity))

        if progress_callback:
            progress_callback(10, 100, 0)

        # Use ball_tree algorithm which works well with sparse high-dimensional data
        # Convert to dense for NearestNeighbors (required for ball_tree)
        # For very large datasets, could chunk this or use brute with sparse
        dense_matrix = normalized_matrix.toarray()

        if progress_callback:
            progress_callback(20, 100, 0)

        # Build the neighbor index - O(n log n)
        nn = NearestNeighbors(
            radius=max_distance,
            algorithm='ball_tree',
            metric='euclidean',
            n_jobs=-1  # Use all CPUs
        )
        nn.fit(dense_matrix)

        if progress_callback:
            progress_callback(40, 100, 0)

        # Query all neighbors within radius - O(n*k) where k is avg neighbors
        distances, indices = nn.radius_neighbors(dense_matrix, return_distance=True)

        if progress_callback:
            progress_callback(70, 100, 0)

        # Build pairs (avoiding duplicates by only keeping i < j)
        pairs = []
        seen_pairs = set()

        for i in range(n_docs):
            neighbor_indices = indices[i]
            neighbor_distances = distances[i]

            for j_idx, j in enumerate(neighbor_indices):
                if i >= j:  # Skip self and avoid duplicates (only keep i < j)
                    continue

                pair_key = (i, j)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Convert euclidean distance back to cosine similarity
                dist = neighbor_distances[j_idx]
                similarity = 1 - (dist * dist / 2)

                if similarity >= min_similarity:
                    pairs.append((
                        self._doc_ids[i],
                        self._doc_ids[j],
                        self._doc_titles[i],
                        self._doc_titles[j],
                        float(similarity)
                    ))

        if progress_callback:
            progress_callback(90, 100, len(pairs))

        # Sort by similarity descending
        pairs.sort(key=lambda x: x[4], reverse=True)

        if progress_callback:
            progress_callback(100, 100, len(pairs))

        return pairs


def compute_content_similarity(content1: str, content2: str) -> float:
    """Compute TF-IDF cosine similarity between two pieces of content.

    This is a standalone function for quick pairwise comparison without
    building the full index.

    Args:
        content1: First document content
        content2: Second document content

    Returns:
        Cosine similarity between 0.0 and 1.0
    """
    _require_sklearn()
    if not content1 or not content2:
        return 0.0

    try:
        vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform([content1, content2])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(similarity)
    except Exception as e:
        # If vectorization fails (e.g., empty vocabulary), return 0
        logger.warning("TF-IDF vectorization failed, returning 0 similarity: %s", e)
        return 0.0
