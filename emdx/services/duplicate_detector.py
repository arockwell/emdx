"""
Duplicate detection service for EMDX.
Finds exact and near-duplicate documents based on content and metadata.

Uses MinHash/LSH for O(n) approximate near-duplicate detection instead of
O(n²) pairwise comparisons. This makes duplicate detection scalable to
thousands of documents.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from typing import cast

from ..services.types import DuplicateDocument, DuplicateStats, MostDuplicated

try:
    from datasketch import MinHash, MinHashLSH

    HAS_DATASKETCH = True
except ImportError:
    HAS_DATASKETCH = False

from ..database import db


def _require_datasketch() -> None:
    """Raise ImportError with helpful message if datasketch is not installed."""
    if not HAS_DATASKETCH:
        raise ImportError(
            "datasketch is required for near-duplicate detection. "
            "Install it with: pip install 'emdx[similarity]'"
        )


# Default parameters for MinHash/LSH
DEFAULT_NUM_PERM = 128  # Number of permutations for MinHash (higher = more accurate)
DEFAULT_LSH_THRESHOLD = 0.5  # Lower threshold for LSH candidate generation


def _tokenize(text: str) -> set[str]:
    """
    Tokenize text into word n-grams for MinHash computation.

    Uses word-level tokens combined with character 3-grams for better
    detection of near-duplicates with minor edits.

    Args:
        text: The text to tokenize

    Returns:
        Set of tokens (words and character n-grams)
    """
    if not text:
        return set()

    # Normalize: lowercase and remove excessive whitespace
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    tokens = set()

    # Add word-level tokens
    words = re.findall(r"\b\w+\b", text)
    tokens.update(words)

    # Add word bigrams for better context capture
    for i in range(len(words) - 1):
        tokens.add(f"{words[i]}_{words[i + 1]}")

    # Add character 3-grams for catching small edits
    for i in range(len(text) - 2):
        tokens.add(text[i : i + 3])

    return tokens


def _create_minhash(tokens: set[str], num_perm: int = DEFAULT_NUM_PERM) -> MinHash:
    """
    Create a MinHash signature from a set of tokens.

    Args:
        tokens: Set of string tokens
        num_perm: Number of permutations for MinHash

    Returns:
        MinHash object representing the token set
    """
    mh = MinHash(num_perm=num_perm)
    for token in tokens:
        mh.update(token.encode("utf-8"))
    return mh


class DuplicateDetector:
    """Service for detecting and managing duplicate documents."""

    def __init__(self) -> None:
        """Initialize the duplicate detector. Uses the shared db module for connections."""
        pass

    def _get_content_hash(self, content: str | None) -> str:
        """Generate hash of content for duplicate detection."""
        if not content:
            return "empty"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def find_duplicates(self) -> list[list[DuplicateDocument]]:
        """
        Find all duplicate documents based on content hash.

        Returns:
            List of duplicate groups, each group is a list of documents
            with identical content.
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active documents
            cursor.execute("""
                SELECT
                    d.id,
                    d.title,
                    d.content,
                    d.project,
                    d.access_count,
                    d.created_at,
                    d.updated_at,
                    LENGTH(d.content) as content_length,
                    GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = 0
                GROUP BY d.id
            """)

            documents = cursor.fetchall()

        # Group by content hash
        hash_groups = defaultdict(list)
        for doc in documents:
            content_hash = self._get_content_hash(doc["content"])
            doc_dict = cast(DuplicateDocument, dict(doc))
            hash_groups[content_hash].append(doc_dict)

        # Filter to only groups with duplicates
        duplicate_groups = [group for group in hash_groups.values() if len(group) > 1]

        # Sort groups by total views (most important first)
        duplicate_groups.sort(
            key=lambda group: sum(doc["access_count"] for doc in group), reverse=True
        )

        return duplicate_groups

    def find_near_duplicates(
        self,
        threshold: float = 0.85,
        num_perm: int = DEFAULT_NUM_PERM,
        max_documents: int | None = None,
    ) -> list[tuple[DuplicateDocument, DuplicateDocument, float]]:
        """
        Find near-duplicate documents based on content similarity using MinHash/LSH.

        This implementation uses Locality-Sensitive Hashing (LSH) with MinHash
        signatures for O(n) approximate near-duplicate detection, replacing the
        previous O(n²) pairwise comparison approach.

        The algorithm:
        1. Tokenize each document into word n-grams and character 3-grams
        2. Create MinHash signatures for each document
        3. Use LSH to find candidate pairs with high Jaccard similarity
        4. Verify candidates with actual MinHash similarity estimation

        Args:
            threshold: Minimum similarity ratio (0.0 to 1.0). Higher values
                      require more similar documents.
            num_perm: Number of permutations for MinHash. Higher values give
                     more accurate estimates but use more memory.
            max_documents: Maximum number of documents to process (None for all).

        Returns:
            List of tuples (doc1, doc2, similarity_score) sorted by similarity.

        Performance:
            - Time complexity: O(n) average case for LSH lookup
            - Space complexity: O(n * num_perm) for MinHash storage
            - At 1000 documents with 128 permutations: ~500KB memory, <1s runtime
        """
        _require_datasketch()
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active documents with content
            query = """
                SELECT
                    d.id,
                    d.title,
                    d.content,
                    d.project,
                    d.access_count,
                    d.created_at,
                    LENGTH(d.content) as content_length
                FROM documents d
                WHERE d.is_deleted = 0
                AND LENGTH(d.content) > 50
                ORDER BY d.access_count DESC, d.id
            """
            if max_documents:
                query += f" LIMIT {max_documents}"

            cursor.execute(query)
            documents = [cast(DuplicateDocument, dict(row)) for row in cursor.fetchall()]

        if len(documents) < 2:
            return []

        # Build MinHash signatures for all documents
        # O(n * document_size) - linear in total content
        doc_minhashes: dict[int, MinHash] = {}
        doc_tokens: dict[int, set[str]] = {}

        for doc in documents:
            tokens = _tokenize(doc.get("content") or "")
            if len(tokens) < 5:  # Skip documents with too few tokens
                continue
            doc_tokens[doc["id"]] = tokens
            doc_minhashes[doc["id"]] = _create_minhash(tokens, num_perm)

        # Create LSH index with a lower threshold to catch candidates
        # We use a lower threshold for LSH and then verify with exact MinHash similarity
        lsh_threshold = min(threshold * 0.7, DEFAULT_LSH_THRESHOLD)
        lsh = MinHashLSH(threshold=lsh_threshold, num_perm=num_perm)

        # Insert all documents into LSH index - O(n)
        for doc_id, mh in doc_minhashes.items():
            lsh.insert(str(doc_id), mh)

        # Find candidate pairs using LSH - O(n) average case
        candidate_pairs: set[tuple[int, int]] = set()

        for doc_id, mh in doc_minhashes.items():
            # Query returns similar documents in O(1) average time
            candidates = lsh.query(mh)
            for candidate_id_str in candidates:
                candidate_id = int(candidate_id_str)
                if candidate_id != doc_id:
                    # Store pairs in sorted order to avoid duplicates
                    pair = (min(doc_id, candidate_id), max(doc_id, candidate_id))
                    candidate_pairs.add(pair)

        # Verify candidates and compute exact similarity
        near_duplicates = []
        doc_by_id = {doc["id"]: doc for doc in documents}

        for id1, id2 in candidate_pairs:
            if id1 not in doc_minhashes or id2 not in doc_minhashes:
                continue

            # Use MinHash Jaccard estimation (very fast, O(num_perm))
            similarity = doc_minhashes[id1].jaccard(doc_minhashes[id2])

            if similarity >= threshold:
                doc1 = doc_by_id.get(id1)
                doc2 = doc_by_id.get(id2)
                if doc1 and doc2:
                    near_duplicates.append((doc1, doc2, similarity))

        # Sort by similarity (highest first)
        near_duplicates.sort(key=lambda x: x[2], reverse=True)
        return near_duplicates

    def find_near_duplicates_exact(
        self, threshold: float = 0.85, max_documents: int = 200
    ) -> list[tuple[DuplicateDocument, DuplicateDocument, float]]:
        """
        Find near-duplicate documents using exact pairwise comparison.

        This is the legacy O(n²) algorithm kept for verification and small datasets.
        For most use cases, prefer find_near_duplicates() which uses LSH.

        Args:
            threshold: Minimum similarity ratio (0.0 to 1.0)
            max_documents: Maximum number of documents to compare

        Returns:
            List of tuples (doc1, doc2, similarity_score)

        Warning:
            This method has O(n²) time complexity. For n=200, this means
            ~20,000 comparisons. Use find_near_duplicates() for better performance.
        """
        import difflib

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.content,
                    d.project,
                    d.access_count,
                    d.created_at,
                    LENGTH(d.content) as content_length
                FROM documents d
                WHERE d.is_deleted = 0
                AND LENGTH(d.content) > 50
                ORDER BY LENGTH(d.content) DESC
                LIMIT ?
            """,
                (max_documents,),
            )

            documents = [cast(DuplicateDocument, dict(row)) for row in cursor.fetchall()]

        near_duplicates: list[tuple[DuplicateDocument, DuplicateDocument, float]] = []

        # O(n²) pairwise comparison
        for i, doc1 in enumerate(documents):
            for doc2 in documents[i + 1 :]:
                len1 = doc1.get("content_length", 0)
                len2 = doc2.get("content_length", 0)
                if min(len1, len2) / max(len1, len2) < 0.5:
                    continue

                similarity = difflib.SequenceMatcher(None, doc1["content"], doc2["content"]).ratio()

                if similarity >= threshold:
                    near_duplicates.append((doc1, doc2, similarity))

        near_duplicates.sort(key=lambda x: x[2], reverse=True)
        return near_duplicates

    def sort_by_strategy(
        self, group: list[DuplicateDocument], strategy: str
    ) -> list[DuplicateDocument]:
        """
        Sort a duplicate group by the given strategy.
        The first document in the sorted list should be kept.

        Args:
            group: List of duplicate documents
            strategy: One of 'highest-views', 'newest', 'oldest'

        Returns:
            Sorted list with the document to keep first
        """
        if strategy == "highest-views":
            # Sort by views (descending), then by ID (ascending) for stability
            return sorted(group, key=lambda x: (-x.get("access_count", 0), x.get("id", 0)))
        elif strategy == "newest":
            # Sort by creation date (descending)
            return sorted(group, key=lambda x: x.get("created_at") or "", reverse=True)
        elif strategy == "oldest":
            # Sort by creation date (ascending)
            return sorted(group, key=lambda x: x.get("created_at") or "")
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def get_documents_to_delete(
        self, duplicate_groups: list[list[DuplicateDocument]], strategy: str = "highest-views"
    ) -> list[int]:
        """
        Get list of document IDs to delete based on strategy.

        Args:
            duplicate_groups: List of duplicate groups
            strategy: Strategy for choosing which document to keep

        Returns:
            List of document IDs to delete
        """
        docs_to_delete = []

        for group in duplicate_groups:
            sorted_group = self.sort_by_strategy(group, strategy)
            # Keep the first one, delete the rest
            docs_to_delete.extend([doc["id"] for doc in sorted_group[1:]])

        return docs_to_delete

    def delete_documents(self, doc_ids: list[int]) -> int:
        """
        Soft delete the specified documents.

        Args:
            doc_ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        if not doc_ids:
            return 0

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Perform soft delete in batches
            deleted_count = 0
            batch_size = 100
            timestamp = datetime.now().isoformat()

            for i in range(0, len(doc_ids), batch_size):
                batch = doc_ids[i : i + batch_size]
                placeholders = ",".join("?" * len(batch))

                cursor.execute(
                    f"""
                    UPDATE documents
                    SET is_deleted = 1, deleted_at = ?
                    WHERE id IN ({placeholders})
                    AND is_deleted = 0
                """,
                    [timestamp, *batch],
                )

                deleted_count += cursor.rowcount

            conn.commit()

        return deleted_count

    def get_duplicate_stats(self) -> DuplicateStats:
        """
        Get statistics about duplicates in the knowledge base.

        Returns:
            Dictionary with duplicate statistics
        """
        duplicate_groups = self.find_duplicates()

        total_duplicates = sum(len(group) - 1 for group in duplicate_groups)
        space_wasted = sum(
            sum(doc["content_length"] for doc in group[1:]) for group in duplicate_groups
        )

        # Find most duplicated content
        most_duplicated: MostDuplicated | None = None
        if duplicate_groups:
            largest_group = max(duplicate_groups, key=len)
            most_duplicated = {
                "title": largest_group[0]["title"],
                "copies": len(largest_group),
                "total_views": sum(doc.get("access_count", 0) for doc in largest_group),
            }

        return {
            "duplicate_groups": len(duplicate_groups),
            "total_duplicates": total_duplicates,
            "space_wasted": space_wasted,
            "most_duplicated": most_duplicated,
        }

    def find_similar_titles(self) -> list[list[DuplicateDocument]]:
        """
        Find documents with identical titles but different content.

        Returns:
            List of title groups with different content
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all active documents
            cursor.execute("""
                SELECT
                    d.id,
                    d.title,
                    d.content,
                    d.project,
                    d.access_count,
                    LENGTH(d.content) as content_length
                FROM documents d
                WHERE d.is_deleted = 0
                ORDER BY d.title, d.id
            """)

            documents = cursor.fetchall()

        # Group by title
        title_groups = defaultdict(list)
        for doc in documents:
            title_groups[doc["title"].strip()].append(cast(DuplicateDocument, dict(doc)))

        # Filter to groups with multiple documents and different content
        similar_title_groups = []
        for _title, group in title_groups.items():
            if len(group) > 1:
                # Check if content is different
                hashes = {self._get_content_hash(doc["content"]) for doc in group}
                if len(hashes) > 1:  # Different content
                    similar_title_groups.append(group)

        return similar_title_groups
