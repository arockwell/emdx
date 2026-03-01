"""
Contradiction detection service for EMDX.

Detects conflicting information across documents using a 3-stage funnel:
1. Candidate pairs via embedding similarity
2. NLI screening (optional) or heuristic fallback
3. Report generation
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    pass

from ..database import db

logger = logging.getLogger(__name__)

# Negation words used in heuristic contradiction detection
_NEGATION_WORDS = frozenset(
    {
        "not",
        "no",
        "never",
        "don't",
        "doesn't",
        "didn't",
        "won't",
        "wouldn't",
        "shouldn't",
        "can't",
        "cannot",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "hasn't",
        "haven't",
        "hadn't",
        "none",
        "nothing",
        "nowhere",
        "neither",
        "nor",
        "without",
    }
)

# Words indicating definitive claims
_CLAIM_INDICATORS = frozenset(
    {
        "always",
        "never",
        "must",
        "should",
        "is",
        "are",
        "was",
        "were",
        "will",
        "shall",
        "requires",
        "needs",
        "every",
        "all",
        "none",
        "only",
        "cannot",
        "impossible",
        "necessary",
        "essential",
        "critical",
        "mandatory",
        "forbidden",
        "prohibited",
    }
)

# Minimum sentence length to consider (in words)
_MIN_SENTENCE_WORDS = 5


class ContradictionMatchDict(TypedDict):
    """A single contradiction match between two document excerpts."""

    excerpt1: str
    excerpt2: str
    confidence: float
    method: str  # "nli" or "heuristic"


class ContradictionResultDict(TypedDict):
    """A contradiction result between a pair of documents."""

    doc1_id: int
    doc1_title: str
    doc2_id: int
    doc2_title: str
    similarity: float
    matches: list[ContradictionMatchDict]


@dataclass
class ContradictionMatch:
    """A single contradiction match between two document excerpts."""

    excerpt1: str
    excerpt2: str
    confidence: float
    method: str  # "nli" or "heuristic"

    def to_dict(self) -> ContradictionMatchDict:
        """Convert to dict for JSON serialization."""
        return ContradictionMatchDict(
            excerpt1=self.excerpt1,
            excerpt2=self.excerpt2,
            confidence=self.confidence,
            method=self.method,
        )


@dataclass
class ContradictionResult:
    """A contradiction result between a pair of documents."""

    doc1_id: int
    doc1_title: str
    doc2_id: int
    doc2_title: str
    similarity: float
    matches: list[ContradictionMatch] = field(default_factory=list)

    def to_dict(self) -> ContradictionResultDict:
        """Convert to dict for JSON serialization."""
        return ContradictionResultDict(
            doc1_id=self.doc1_id,
            doc1_title=self.doc1_title,
            doc2_id=self.doc2_id,
            doc2_title=self.doc2_title,
            similarity=self.similarity,
            matches=[m.to_dict() for m in self.matches],
        )


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering short ones."""
    # Split on sentence-ending punctuation
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for s in raw:
        s = s.strip()
        words = s.split()
        if len(words) >= _MIN_SENTENCE_WORDS:
            sentences.append(s)
    return sentences


def _is_claim_sentence(sentence: str) -> bool:
    """Check if a sentence contains definitive language (a claim)."""
    words = set(sentence.lower().split())
    return bool(words & _CLAIM_INDICATORS)


def _extract_claims(content: str) -> list[str]:
    """Extract sentences that look like claims from document content."""
    sentences = _split_sentences(content)
    return [s for s in sentences if _is_claim_sentence(s)]


def _has_negation(sentence: str) -> bool:
    """Check if a sentence contains negation words."""
    words = set(sentence.lower().split())
    return bool(words & _NEGATION_WORDS)


def _word_set(sentence: str) -> set[str]:
    """Get lowercase word set from a sentence, excluding stop words."""
    stop = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or"}
    words = set(sentence.lower().split())
    return words - stop - _NEGATION_WORDS


def _word_overlap(sent1: str, sent2: str) -> float:
    """Compute Jaccard word overlap between two sentences."""
    w1 = _word_set(sent1)
    w2 = _word_set(sent2)
    if not w1 or not w2:
        return 0.0
    intersection = len(w1 & w2)
    union = len(w1 | w2)
    return intersection / union if union > 0 else 0.0


class ContradictionService:
    """Detects contradicting information across knowledge base documents."""

    def __init__(self) -> None:
        self._nli_model_available: bool | None = None

    def _check_nli_available(self) -> bool:
        """Check if the NLI cross-encoder model is available."""
        if self._nli_model_available is not None:
            return self._nli_model_available
        try:
            from sentence_transformers import CrossEncoder  # noqa: F401

            self._nli_model_available = True
        except (ImportError, OSError):
            self._nli_model_available = False
        return self._nli_model_available

    def _check_embeddings_exist(self) -> bool:
        """Check if the embedding index has been built."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM document_embeddings")
                count = cursor.fetchone()[0]
                return count > 0  # type: ignore[no-any-return]
            except Exception:
                return False

    def find_contradictions(
        self,
        limit: int = 100,
        project: str | None = None,
        threshold: float = 0.7,
    ) -> list[ContradictionResult]:
        """Find contradictions across documents.

        Args:
            limit: Maximum number of candidate pairs to check.
            project: If set, only check documents in this project.
            threshold: Similarity threshold for candidate pairs.

        Returns:
            List of ContradictionResult with detected contradictions.
        """
        # Stage 1: Get candidate pairs
        pairs = self._get_candidate_pairs(threshold=threshold, project=project, limit=limit)

        if not pairs:
            return []

        # Stage 2: Check each pair for contradictions
        use_nli = self._check_nli_available()
        results: list[ContradictionResult] = []

        for doc1_id, doc2_id, similarity, doc1_title, doc2_title in pairs:
            # Fetch document content
            doc1_content = self._get_doc_content(doc1_id)
            doc2_content = self._get_doc_content(doc2_id)

            if not doc1_content or not doc2_content:
                continue

            # Check for contradictions
            if use_nli:
                matches = self._check_nli(doc1_content, doc2_content)
            else:
                matches = self._check_heuristic(doc1_content, doc2_content)

            if matches:
                results.append(
                    ContradictionResult(
                        doc1_id=doc1_id,
                        doc1_title=doc1_title,
                        doc2_id=doc2_id,
                        doc2_title=doc2_title,
                        similarity=similarity,
                        matches=matches,
                    )
                )

        return results

    def _get_candidate_pairs(
        self,
        threshold: float,
        project: str | None,
        limit: int,
    ) -> list[tuple[int, int, float, str, str]]:
        """Get candidate document pairs via embedding similarity.

        Returns:
            List of (doc1_id, doc2_id, similarity, doc1_title, doc2_title)
        """
        from ..services.embedding_service import EmbeddingService

        svc = EmbeddingService()

        # Get all indexed document IDs
        with db.get_connection() as conn:
            cursor = conn.cursor()
            if project:
                cursor.execute(
                    "SELECT d.id, d.title FROM documents d "
                    "JOIN document_embeddings e "
                    "ON d.id = e.document_id "
                    "WHERE d.is_deleted = 0 AND d.project = ? "
                    "ORDER BY d.id",
                    (project,),
                )
            else:
                cursor.execute(
                    "SELECT d.id, d.title FROM documents d "
                    "JOIN document_embeddings e "
                    "ON d.id = e.document_id "
                    "WHERE d.is_deleted = 0 "
                    "ORDER BY d.id",
                )
            docs = cursor.fetchall()

        if len(docs) < 2:
            return []

        # Build a map of doc_id -> title
        doc_titles = {row[0]: row[1] for row in docs}
        doc_ids = list(doc_titles.keys())

        # Use find_similar for each doc to get high-similarity pairs
        seen_pairs: set[tuple[int, int]] = set()
        pairs: list[tuple[int, int, float, str, str]] = []

        for doc_id in doc_ids:
            if len(pairs) >= limit:
                break

            similar = svc.find_similar(doc_id, limit=10, project=project)
            for match in similar:
                if match.similarity < threshold:
                    continue

                pair_key = (
                    min(doc_id, match.doc_id),
                    max(doc_id, match.doc_id),
                )
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                pairs.append(
                    (
                        doc_id,
                        match.doc_id,
                        match.similarity,
                        doc_titles.get(doc_id, ""),
                        match.title,
                    )
                )

                if len(pairs) >= limit:
                    break

        # Sort by similarity descending
        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs[:limit]

    def _get_doc_content(self, doc_id: int) -> str | None:
        """Fetch document content by ID."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content FROM documents WHERE id = ? AND is_deleted = 0",
                (doc_id,),
            )
            row = cursor.fetchone()
            if row:
                return row[0]  # type: ignore[no-any-return]
        return None

    def _check_nli(self, doc1_content: str, doc2_content: str) -> list[ContradictionMatch]:
        """Check for contradictions using NLI cross-encoder.

        Uses cross-encoder/nli-deberta-v3-small to classify
        sentence pairs as entailment/neutral/contradiction.
        """
        try:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder("cross-encoder/nli-deberta-v3-small")
        except (ImportError, OSError) as err:
            logger.warning("NLI model unavailable, falling back to heuristic: %s", err)
            self._nli_model_available = False
            return self._check_heuristic(doc1_content, doc2_content)

        claims1 = _extract_claims(doc1_content)
        claims2 = _extract_claims(doc2_content)

        if not claims1 or not claims2:
            return []

        # Build sentence pairs
        sentence_pairs: list[list[str]] = []
        pair_indices: list[tuple[int, int]] = []

        for i, s1 in enumerate(claims1):
            for j, s2 in enumerate(claims2):
                # Only compare if there's some word overlap
                if _word_overlap(s1, s2) > 0.15:
                    sentence_pairs.append([s1, s2])
                    pair_indices.append((i, j))

        if not sentence_pairs:
            return []

        # NLI labels: 0=contradiction, 1=entailment, 2=neutral
        scores = model.predict(sentence_pairs)

        matches: list[ContradictionMatch] = []
        for idx, score_arr in enumerate(scores):
            # score_arr is [contradiction, entailment, neutral]
            contradiction_score = float(score_arr[0])
            if contradiction_score > 0.7:
                i, j = pair_indices[idx]
                matches.append(
                    ContradictionMatch(
                        excerpt1=claims1[i],
                        excerpt2=claims2[j],
                        confidence=contradiction_score,
                        method="nli",
                    )
                )

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def _check_heuristic(self, doc1_content: str, doc2_content: str) -> list[ContradictionMatch]:
        """Check for contradictions using keyword/negation heuristic.

        Finds sentence pairs where:
        - Both are claim sentences
        - They have significant word overlap (same topic)
        - One has negation and the other doesn't
        """
        claims1 = _extract_claims(doc1_content)
        claims2 = _extract_claims(doc2_content)

        if not claims1 or not claims2:
            return []

        matches: list[ContradictionMatch] = []

        for s1 in claims1:
            for s2 in claims2:
                overlap = _word_overlap(s1, s2)
                if overlap < 0.25:
                    continue

                neg1 = _has_negation(s1)
                neg2 = _has_negation(s2)

                # Contradiction if one negates and the other doesn't
                if neg1 != neg2:
                    # Confidence based on word overlap
                    confidence = min(0.5 + overlap, 0.85)
                    matches.append(
                        ContradictionMatch(
                            excerpt1=s1,
                            excerpt2=s2,
                            confidence=confidence,
                            method="heuristic",
                        )
                    )

        # Sort by confidence descending, deduplicate
        matches.sort(key=lambda m: m.confidence, reverse=True)
        # Keep top 5 per pair to avoid noise
        return matches[:5]
