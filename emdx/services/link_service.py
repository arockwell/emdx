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
    project: str | None = None,
) -> AutoLinkResult:
    """Find semantically similar documents and create links.

    Requires the embedding index to be built (``emdx ai index``).
    Embeds the document if not already indexed, then finds similar
    documents above the threshold and creates links.

    Args:
        doc_id: The document to auto-link.
        threshold: Minimum cosine similarity (0-1) for auto-linking.
        max_links: Maximum number of links to create.
        project: If set, only match documents in this project.

    Returns:
        AutoLinkResult with created link details.
    """
    from .embedding_service import EmbeddingService

    service = EmbeddingService()

    # Check if we have an embedding index at all
    stats = service.stats()
    if stats.indexed_documents == 0:
        logger.info("No embedding index — skipping auto-link for doc %d", doc_id)
        return AutoLinkResult(doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[])

    # Embed this document if not already indexed
    service.embed_document(doc_id)

    # Find similar documents
    similar = service.find_similar(doc_id, limit=max_links, project=project)

    # Filter by threshold
    candidates = [m for m in similar if m.similarity >= threshold]

    if not candidates:
        return AutoLinkResult(doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[])

    # Get existing links so we don't duplicate
    existing = set(document_links.get_linked_doc_ids(doc_id))

    links_to_create: list[tuple[int, int, float, str]] = []
    for match in candidates:
        if match.doc_id not in existing:
            links_to_create.append((doc_id, match.doc_id, match.similarity, "auto"))

    if not links_to_create:
        return AutoLinkResult(doc_id=doc_id, links_created=0, linked_doc_ids=[], scores=[])

    created = document_links.create_links_batch(links_to_create)

    return AutoLinkResult(
        doc_id=doc_id,
        links_created=created,
        linked_doc_ids=[t[1] for t in links_to_create[:created]],
        scores=[t[2] for t in links_to_create[:created]],
    )


@dataclass
class PendingLinkSummary:
    """Result of draining the deferred auto-link queue (#1038)."""

    docs_processed: int
    links_created: int
    docs_skipped: int  # deleted/missing docs dequeued without linking
    docs_failed: int  # errors — left queued for the next run
    no_index: bool = False  # True when there is no embedding index at all


def process_pending_links(
    threshold: float = DEFAULT_THRESHOLD,
    max_links: int = DEFAULT_MAX_LINKS,
) -> PendingLinkSummary:
    """Embed and auto-link documents queued by `emdx save` (#1038).

    Saves defer embedding + semantic linking by default; this drains the
    pending_auto_links queue: each queued document is embedded (if not
    already) and auto-linked using the project scope recorded at save
    time. Deleted/missing documents are dequeued without linking. If no
    embedding index exists yet, the queue is left untouched — run
    `emdx maintain index` first.
    """
    from ..database import db, pending_links

    pending = pending_links.get_pending()
    if not pending:
        return PendingLinkSummary(0, 0, 0, 0)

    from .embedding_service import EmbeddingService

    service = EmbeddingService()
    if service.stats().indexed_documents == 0:
        # auto_link_document would no-op without an index; keep the queue
        # so the docs get linked once an index exists.
        return PendingLinkSummary(0, 0, 0, 0, no_index=True)

    processed = links = skipped = failed = 0
    for item in pending:
        doc_id = item["document_id"]
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT is_deleted FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
        if row is None or row[0]:
            pending_links.remove(doc_id)
            skipped += 1
            continue
        try:
            result = auto_link_document(
                doc_id,
                threshold=threshold,
                max_links=max_links,
                project=item["project_scope"],
            )
        except Exception:
            logger.warning(
                "Deferred auto-link failed for doc %d — leaving it queued", doc_id, exc_info=True
            )
            failed += 1
            continue
        pending_links.remove(doc_id)
        processed += 1
        links += result.links_created

    return PendingLinkSummary(processed, links, skipped, failed)


def auto_link_all(
    threshold: float = DEFAULT_THRESHOLD,
    max_links: int = DEFAULT_MAX_LINKS,
    cross_project: bool = False,
) -> int:
    """Backfill auto-links for all documents that have embeddings.

    Args:
        threshold: Minimum cosine similarity for linking.
        max_links: Maximum links per document.
        cross_project: If False, scope each document's matches to its own project.

    Returns total number of links created.
    """
    from ..database import db
    from .embedding_service import EmbeddingService

    service = EmbeddingService()
    stats = service.stats()
    if stats.indexed_documents == 0:
        return 0

    # Get all indexed document IDs and their projects
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT e.document_id, d.project
            FROM document_embeddings e
            JOIN documents d ON e.document_id = d.id
            WHERE d.is_deleted = 0
            """
        )
        docs = [(row[0], row[1]) for row in cursor.fetchall()]

    total_created = 0
    for did, doc_project in docs:
        scope_project = None if cross_project else doc_project
        result = auto_link_document(
            did, threshold=threshold, max_links=max_links, project=scope_project
        )
        total_created += result.links_created

    return total_created
