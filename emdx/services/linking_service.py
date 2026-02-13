"""
Auto-linking service for EMDX.

Manages bidirectional document links based on semantic similarity.
When a new document is saved, this service finds similar documents
and creates links to them, making the KB a self-organizing knowledge graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from ..database import db

logger = logging.getLogger(__name__)


@dataclass
class DocumentLink:
    """Represents a link between two documents."""

    doc_id: int
    title: str
    similarity_score: float
    project: Optional[str] = None


@dataclass
class LinkStats:
    """Statistics about document links."""

    total_links: int
    documents_with_links: int
    avg_links_per_doc: float
    avg_similarity: float


class LinkingService:
    """Manages document links based on semantic similarity."""

    # Configuration
    MIN_SIMILARITY = 0.50  # Minimum similarity to create a link (50%)
    MAX_LINKS = 5  # Maximum links per document

    def __init__(self):
        """Initialize the linking service."""
        pass

    def _get_embedding_service(self):
        """Lazy load embedding service to avoid import overhead."""
        try:
            from .embedding_service import EmbeddingService

            return EmbeddingService()
        except ImportError:
            logger.warning("Embedding service not available for auto-linking")
            return None

    def find_similar_documents(
        self,
        doc_id: int,
        limit: int = MAX_LINKS,
        min_similarity: float = MIN_SIMILARITY,
    ) -> List[DocumentLink]:
        """Find documents similar to a given document using embeddings.

        Args:
            doc_id: Document ID to find similar documents for
            limit: Maximum number of similar documents to return
            min_similarity: Minimum similarity threshold

        Returns:
            List of DocumentLink objects, sorted by similarity descending
        """
        embedding_service = self._get_embedding_service()
        if not embedding_service:
            return []

        try:
            # Get similar documents using the embedding service
            similar = embedding_service.find_similar(doc_id, limit=limit)

            # Filter by minimum similarity and convert to DocumentLink
            links = []
            for match in similar:
                if match.similarity >= min_similarity:
                    links.append(
                        DocumentLink(
                            doc_id=match.doc_id,
                            title=match.title,
                            similarity_score=match.similarity,
                            project=match.project,
                        )
                    )

            return links[:limit]
        except Exception as e:
            logger.warning(f"Error finding similar documents for {doc_id}: {e}")
            return []

    def create_links(
        self,
        doc_id: int,
        links: List[DocumentLink],
    ) -> int:
        """Store links for a document in the database.

        Creates bidirectional links: if A links to B, B also links to A.

        Args:
            doc_id: Source document ID
            links: List of DocumentLink objects to create

        Returns:
            Number of links created
        """
        if not links:
            return 0

        count = 0
        with db.get_connection() as conn:
            cursor = conn.cursor()

            for link in links:
                try:
                    # Create forward link (source -> target)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO document_links
                        (source_doc_id, target_doc_id, similarity_score)
                        VALUES (?, ?, ?)
                        """,
                        (doc_id, link.doc_id, link.similarity_score),
                    )

                    # Create reverse link (target -> source) with same score
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO document_links
                        (source_doc_id, target_doc_id, similarity_score)
                        VALUES (?, ?, ?)
                        """,
                        (link.doc_id, doc_id, link.similarity_score),
                    )

                    count += 1
                except Exception as e:
                    logger.warning(f"Error creating link {doc_id} -> {link.doc_id}: {e}")

            conn.commit()

        return count

    def link_document(
        self,
        doc_id: int,
        force: bool = False,
    ) -> List[DocumentLink]:
        """Auto-link a document to similar documents.

        This is the main entry point for auto-linking. It:
        1. Embeds the document (if not already)
        2. Finds similar documents
        3. Creates bidirectional links

        Args:
            doc_id: Document ID to link
            force: If True, recompute links even if they exist

        Returns:
            List of created links
        """
        # Check if document already has links (unless force=True)
        if not force:
            existing = self.get_links(doc_id)
            if existing:
                return existing

        # Ensure the document is embedded first
        embedding_service = self._get_embedding_service()
        if not embedding_service:
            return []

        try:
            # Embed the document (will use cache if already embedded)
            embedding_service.embed_document(doc_id, force=force)
        except Exception as e:
            logger.warning(f"Error embedding document {doc_id}: {e}")
            return []

        # Find similar documents
        links = self.find_similar_documents(doc_id)

        # Store links
        if links:
            self.create_links(doc_id, links)

        return links

    def get_links(self, doc_id: int, limit: int = MAX_LINKS) -> List[DocumentLink]:
        """Get existing links for a document.

        Args:
            doc_id: Document ID to get links for
            limit: Maximum number of links to return

        Returns:
            List of DocumentLink objects, sorted by similarity descending
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT dl.target_doc_id, d.title, dl.similarity_score, d.project
                FROM document_links dl
                JOIN documents d ON dl.target_doc_id = d.id
                WHERE dl.source_doc_id = ? AND d.is_deleted = 0
                ORDER BY dl.similarity_score DESC
                LIMIT ?
                """,
                (doc_id, limit),
            )

            links = []
            for row in cursor.fetchall():
                links.append(
                    DocumentLink(
                        doc_id=row[0],
                        title=row[1],
                        similarity_score=row[2],
                        project=row[3],
                    )
                )

            return links

    def delete_links(self, doc_id: int) -> int:
        """Delete all links for a document.

        Args:
            doc_id: Document ID to delete links for

        Returns:
            Number of links deleted
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Delete links where this doc is the source
            cursor.execute(
                "DELETE FROM document_links WHERE source_doc_id = ?",
                (doc_id,),
            )
            count = cursor.rowcount

            # Delete links where this doc is the target
            cursor.execute(
                "DELETE FROM document_links WHERE target_doc_id = ?",
                (doc_id,),
            )
            count += cursor.rowcount

            conn.commit()

        return count

    def link_all(
        self,
        force: bool = False,
        batch_size: int = 50,
        progress_callback=None,
    ) -> int:
        """Link all documents in the knowledge base.

        This is the backfill operation that computes links for all existing documents.

        Args:
            force: If True, recompute links even for documents that already have them
            batch_size: Number of documents to process in each batch
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            Number of documents linked
        """
        embedding_service = self._get_embedding_service()
        if not embedding_service:
            logger.error("Embedding service not available. Run 'emdx ai index' first.")
            return 0

        # Get all documents that need linking
        with db.get_connection() as conn:
            cursor = conn.cursor()

            if force:
                # Get all documents
                cursor.execute(
                    """
                    SELECT id FROM documents
                    WHERE is_deleted = 0
                    ORDER BY id
                    """
                )
            else:
                # Get documents without links
                cursor.execute(
                    """
                    SELECT d.id FROM documents d
                    LEFT JOIN document_links dl ON d.id = dl.source_doc_id
                    WHERE d.is_deleted = 0 AND dl.id IS NULL
                    ORDER BY d.id
                    """
                )

            doc_ids = [row[0] for row in cursor.fetchall()]

        if not doc_ids:
            return 0

        total = len(doc_ids)
        linked = 0

        # Process in batches
        for i in range(0, total, batch_size):
            batch = doc_ids[i : i + batch_size]

            for doc_id in batch:
                try:
                    links = self.link_document(doc_id, force=force)
                    if links:
                        linked += 1
                except Exception as e:
                    logger.warning(f"Error linking document {doc_id}: {e}")

            if progress_callback:
                progress_callback(min(i + batch_size, total), total)

        return linked

    def get_link_graph(
        self,
        doc_id: int,
        depth: int = 2,
        visited: set = None,
    ) -> dict:
        """Get the link graph for a document, traversing N levels deep.

        Args:
            doc_id: Root document ID
            depth: How many levels to traverse
            visited: Set of already-visited doc IDs (to prevent cycles)

        Returns:
            Nested dict representing the link graph
        """
        if visited is None:
            visited = set()

        if doc_id in visited or depth <= 0:
            return {}

        visited.add(doc_id)

        # Get document info
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, project FROM documents WHERE id = ? AND is_deleted = 0",
                (doc_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {}

            title, project = row

        # Get links for this document
        links = self.get_links(doc_id)

        # Build graph node
        node = {
            "id": doc_id,
            "title": title,
            "project": project,
            "links": [],
        }

        # Recursively get linked documents
        for link in links:
            if link.doc_id not in visited:
                child_graph = self.get_link_graph(link.doc_id, depth - 1, visited.copy())
                node["links"].append(
                    {
                        "id": link.doc_id,
                        "title": link.title,
                        "similarity": link.similarity_score,
                        "project": link.project,
                        "links": child_graph.get("links", []) if child_graph else [],
                    }
                )

        return node

    def get_stats(self) -> LinkStats:
        """Get statistics about document links.

        Returns:
            LinkStats object with link statistics
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Total links
            cursor.execute("SELECT COUNT(*) FROM document_links")
            total_links = cursor.fetchone()[0]

            # Documents with links (counting unique source_doc_ids)
            cursor.execute(
                "SELECT COUNT(DISTINCT source_doc_id) FROM document_links"
            )
            docs_with_links = cursor.fetchone()[0]

            # Average similarity
            cursor.execute("SELECT AVG(similarity_score) FROM document_links")
            avg_similarity = cursor.fetchone()[0] or 0.0

            # Average links per document
            avg_links = total_links / docs_with_links if docs_with_links > 0 else 0.0

        return LinkStats(
            total_links=total_links,
            documents_with_links=docs_with_links,
            avg_links_per_doc=avg_links,
            avg_similarity=avg_similarity,
        )
