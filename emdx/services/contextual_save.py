"""
Contextual Save service for duplicate prevention.

Provides similarity checking before save operations to help prevent
duplicate documents in the knowledge base.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..database import db
from ..models.tags import get_tags_for_documents

logger = logging.getLogger(__name__)

# Similarity thresholds
DUPLICATE_THRESHOLD = 0.80  # >80% = likely duplicate
RELATED_THRESHOLD = 0.50    # 50-80% = related
NEW_TOPIC_THRESHOLD = 0.50  # <50% = new topic


@dataclass
class SimilarDoc:
    """A similar document with its metadata."""
    doc_id: int
    title: str
    project: Optional[str]
    similarity: float
    tags: List[str]


@dataclass
class CheckResult:
    """Result of a contextual save check."""
    similar_docs: List[SimilarDoc]
    suggested_tags: List[str]
    suggested_project: Optional[str]
    recommendation: str
    classification: str  # "duplicate", "related", or "new"

    def has_duplicates(self) -> bool:
        """Check if any similar docs are above the duplicate threshold."""
        return any(d.similarity >= DUPLICATE_THRESHOLD for d in self.similar_docs)

    def has_related(self) -> bool:
        """Check if any similar docs are in the related range."""
        return any(
            RELATED_THRESHOLD <= d.similarity < DUPLICATE_THRESHOLD
            for d in self.similar_docs
        )


def check_for_similar(
    text: str,
    title: Optional[str] = None,
    limit: int = 5,
    min_similarity: float = 0.3,
) -> CheckResult:
    """
    Check for similar documents before saving.

    This is the core function for contextual save - it finds similar docs
    and suggests tags/project based on nearest neighbors.

    Args:
        text: The content to check (title + content combined, or just content)
        title: Optional title to prepend to text for better matching
        limit: Maximum number of similar docs to return
        min_similarity: Minimum similarity threshold

    Returns:
        CheckResult with similar docs, suggested tags, project, and recommendation
    """
    # Combine title and text for matching
    search_text = f"{title} {text}" if title else text

    # Try to use the similarity service
    similar_docs = _find_similar_docs(search_text, limit=limit, min_similarity=min_similarity)

    # If no similar docs found, return early
    if not similar_docs:
        return CheckResult(
            similar_docs=[],
            suggested_tags=[],
            suggested_project=None,
            recommendation="New topic - no similar documents found.",
            classification="new",
        )

    # Get tags for all similar docs
    doc_ids = [d.doc_id for d in similar_docs]
    tags_map = get_tags_for_documents(doc_ids)

    # Enrich similar docs with tags
    for doc in similar_docs:
        doc.tags = tags_map.get(doc.doc_id, [])

    # Generate tag suggestions from top 3 neighbors
    suggested_tags = _suggest_tags_from_neighbors(similar_docs[:3])

    # Suggest project from highest similarity neighbor
    suggested_project = similar_docs[0].project if similar_docs else None

    # Generate recommendation based on highest similarity
    top_similarity = similar_docs[0].similarity if similar_docs else 0
    recommendation, classification = _generate_recommendation(similar_docs, top_similarity)

    return CheckResult(
        similar_docs=similar_docs,
        suggested_tags=suggested_tags,
        suggested_project=suggested_project,
        recommendation=recommendation,
        classification=classification,
    )


def _find_similar_docs(
    text: str,
    limit: int = 5,
    min_similarity: float = 0.3,
) -> List[SimilarDoc]:
    """
    Find similar documents using TF-IDF similarity.

    Falls back to keyword matching if similarity service is unavailable.
    """
    try:
        from ..services.similarity import SimilarityService

        service = SimilarityService()
        results = service.find_similar_by_text(
            text=text,
            limit=limit,
            min_similarity=min_similarity,
        )

        return [
            SimilarDoc(
                doc_id=r.doc_id,
                title=r.title,
                project=r.project,
                similarity=r.similarity_score,
                tags=[],  # Will be filled in later
            )
            for r in results
        ]

    except ImportError:
        logger.debug("Similarity service unavailable, using keyword fallback")
        return _fallback_keyword_search(text, limit=limit)
    except Exception as e:
        logger.warning("Similarity search failed: %s, using keyword fallback", e)
        return _fallback_keyword_search(text, limit=limit)


def _fallback_keyword_search(text: str, limit: int = 5) -> List[SimilarDoc]:
    """
    Fallback keyword-based search when TF-IDF is unavailable.

    Uses SQLite FTS5 to find documents matching keywords from the text.
    """
    # Extract significant keywords from text (simple approach)
    words = text.lower().split()
    # Filter out common words and short words
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "under",
        "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
        "not", "only", "own", "same", "than", "too", "very", "just", "also",
        "this", "that", "these", "those", "it", "its", "they", "them", "their",
    }
    keywords = [w for w in words if len(w) > 3 and w not in stopwords][:10]

    if not keywords:
        return []

    # Build FTS query
    query = " OR ".join(keywords)

    try:
        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT d.id, d.title, d.project,
                       bm25(documents_fts) as score
                FROM documents_fts
                JOIN documents d ON documents_fts.rowid = d.id
                WHERE documents_fts MATCH ?
                AND d.is_deleted = 0
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
            rows = cursor.fetchall()

        # Convert BM25 scores to rough similarity (BM25 is negative, lower = better)
        results = []
        if rows:
            # Normalize scores to 0-1 range (rough approximation)
            min_score = min(r["score"] for r in rows)
            max_score = max(r["score"] for r in rows)
            score_range = max_score - min_score if max_score != min_score else 1

            for row in rows:
                # Invert and normalize (BM25 is negative, lower = better match)
                normalized = (max_score - row["score"]) / score_range if score_range else 0.5
                # Scale to reasonable similarity range
                similarity = 0.3 + (normalized * 0.5)  # Range: 0.3-0.8

                results.append(SimilarDoc(
                    doc_id=row["id"],
                    title=row["title"],
                    project=row["project"],
                    similarity=similarity,
                    tags=[],
                ))

        return results

    except Exception as e:
        logger.warning("Keyword search failed: %s", e)
        return []


def _suggest_tags_from_neighbors(similar_docs: List[SimilarDoc], max_tags: int = 3) -> List[str]:
    """
    Suggest tags based on the most common tags among similar documents.

    Args:
        similar_docs: List of similar documents (should be top 3)
        max_tags: Maximum number of tags to suggest

    Returns:
        List of suggested tags, ordered by frequency
    """
    if not similar_docs:
        return []

    # Count tag occurrences across all similar docs
    tag_counter: Counter = Counter()
    for doc in similar_docs:
        for tag in doc.tags:
            tag_counter[tag] += 1

    # Return tags that appear in at least 2 docs, or top tags if none repeat
    suggestions = []
    for tag, count in tag_counter.most_common():
        if len(suggestions) >= max_tags:
            break
        # Prefer tags that appear multiple times
        if count >= 2 or len(suggestions) < max_tags:
            suggestions.append(tag)

    return suggestions


def _generate_recommendation(similar_docs: List[SimilarDoc], top_similarity: float) -> Tuple[str, str]:
    """
    Generate a recommendation message based on similarity analysis.

    Returns:
        Tuple of (recommendation message, classification)
    """
    if top_similarity >= DUPLICATE_THRESHOLD:
        top_doc = similar_docs[0]
        return (
            f"Overlaps with #{top_doc.doc_id} ({top_similarity:.0%} similar). "
            f"Consider updating instead.",
            "duplicate",
        )

    elif top_similarity >= RELATED_THRESHOLD:
        top_doc = similar_docs[0]
        return (
            f"Related to #{top_doc.doc_id} ({top_similarity:.0%} similar).",
            "related",
        )

    else:
        return ("New topic.", "new")


def format_check_output(result: CheckResult, doc_id: Optional[int] = None) -> str:
    """
    Format check result for CLI output.

    This is designed to be concise for Claude consumption.

    Args:
        result: The check result to format
        doc_id: Optional doc ID if this is being called after save

    Returns:
        Formatted string for CLI output
    """
    lines = []

    # If we have a doc_id, this is post-save output
    if doc_id is not None and result.similar_docs:
        lines.append(f"⚠ Similar docs found:")
        for doc in result.similar_docs[:3]:
            action = f"consider `emdx edit {doc.doc_id}`" if doc.similarity >= DUPLICATE_THRESHOLD else ""
            line = f"  #{doc.doc_id} ({doc.similarity:.0%} similar)"
            if action:
                line += f" — {action}"
            lines.append(line)

    elif not doc_id:
        # Pre-save check output
        if result.similar_docs:
            lines.append("Similar existing docs:")
            for doc in result.similar_docs[:5]:
                similarity_str = f"{doc.similarity:.0%}"
                lines.append(f"  #{doc.doc_id} \"{doc.title}\" ({similarity_str} similar)")

        if result.suggested_tags:
            lines.append(f"Suggested tags: {', '.join(result.suggested_tags)}")

        if result.suggested_project:
            lines.append(f"Suggested project: {result.suggested_project}")

        lines.append(f"Recommendation: {result.recommendation}")

    return "\n".join(lines)
