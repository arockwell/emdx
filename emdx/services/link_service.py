"""Service for auto-linking documents via semantic similarity.

Uses the EmbeddingService to find similar documents and create
bidirectional links in the document_links table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..database import document_links

logger = logging.getLogger(__name__)

# Minimum similarity to auto-link
DEFAULT_THRESHOLD = 0.5
# Maximum auto-links per document
DEFAULT_MAX_LINKS = 5


@dataclass
class AutoLinkResult:
    """Result of auto-linking a document."""

    doc_id: int
    links_created: int
    linked_doc_ids: list[int]
    scores: list[float]


def auto_link_document(
    doc_id: int,
    threshold: float = DEFAULT_THRESHOLD,
    max_links: int = DEFAULT_MAX_LINKS,
) -> AutoLinkResult:
    """Find semantically similar documents and create links.

    Requires the embedding index to be built (``emdx ai index``).
    Embeds the document if not already indexed, then finds similar
    documents above the threshold and creates links.

    Args:
        doc_id: The document to auto-link.
        threshold: Minimum cosine similarity (0-1) for auto-linking.
        max_links: Maximum number of links to create.

    Returns:
        AutoLinkResult with created link details.
    """
    from .embedding_service import EmbeddingService

    service = EmbeddingService()

    # Check if we have an embedding index at all
    stats = service.stats()
    if stats.indexed_documents == 0:
        logger.info("No embedding index — skipping auto-link for doc %d", doc_id)
        return AutoLinkResult(
            doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[]
        )

    # Embed this document if not already indexed
    service.embed_document(doc_id)

    # Find similar documents
    similar = service.find_similar(doc_id, limit=max_links)

    # Filter by threshold
    candidates = [m for m in similar if m.similarity >= threshold]

    if not candidates:
        return AutoLinkResult(
            doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[]
        )

    # Get existing links so we don't duplicate
    existing = set(document_links.get_linked_doc_ids(doc_id))

    links_to_create: list[tuple[int, int, float, str]] = []
    for match in candidates:
        if match.doc_id not in existing:
            links_to_create.append(
                (doc_id, match.doc_id, match.similarity, "auto")
            )

    if not links_to_create:
        return AutoLinkResult(
            doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[]
        )

    created = document_links.create_links_batch(links_to_create)

    return AutoLinkResult(
        doc_id=doc_id,
        links_created=created,
        linked_doc_ids=[t[1] for t in links_to_create[:created]],
        scores=[t[2] for t in links_to_create[:created]],
    )


def auto_link_all(
    threshold: float = DEFAULT_THRESHOLD,
    max_links: int = DEFAULT_MAX_LINKS,
) -> int:
    """Backfill auto-links for all documents that have embeddings.

    Returns total number of links created.
    """
    from ..database import db
    from .embedding_service import EmbeddingService

    service = EmbeddingService()
    stats = service.stats()
    if stats.indexed_documents == 0:
        return 0

    # Get all indexed document IDs
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT DISTINCT document_id FROM document_embeddings"
        )
        doc_ids = [row[0] for row in cursor.fetchall()]

    total_created = 0
    for did in doc_ids:
        result = auto_link_document(
            did, threshold=threshold, max_links=max_links
        )
        total_created += result.links_created

    return total_created
