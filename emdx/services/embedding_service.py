"""
Semantic embedding service for EMDX.

Uses sentence-transformers for local embedding generation,
enabling semantic search without API costs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

from ..database import db

logger = logging.getLogger(__name__)

# Lazy load - model is ~90MB, loads in ~2 seconds
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy load the embedding model."""
    global _model
    if _model is None:
        if not HAS_NUMPY:
            raise ImportError(
                "numpy is required for embedding features. Install it with: pip install 'emdx[ai]'"
            ) from None
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embedding features. "
                "Install it with: pip install 'emdx[ai]'"
            ) from None

        # all-MiniLM-L6-v2: Good balance of speed/quality
        # ~90MB download, ~80ms per doc, 384 dimensions
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded embedding model: all-MiniLM-L6-v2")
    return _model


@dataclass
class SemanticMatch:
    """A semantically similar document."""

    doc_id: int
    title: str
    project: str | None
    similarity: float
    snippet: str


@dataclass
class ChunkMatch:
    """A semantically similar chunk within a document."""

    doc_id: int
    title: str
    project: str | None
    chunk_index: int
    heading_path: str
    similarity: float
    chunk_text: str

    @property
    def display_heading(self) -> str:
        """Format heading path for display."""
        if self.heading_path:
            return f'§"{self.heading_path}"'
        return ""


@dataclass
class EmbeddingStats:
    """Statistics about the embedding index."""

    total_documents: int
    indexed_documents: int
    coverage_percent: float
    model_name: str
    index_size_bytes: int
    indexed_chunks: int = 0
    chunk_index_size_bytes: int = 0


class EmbeddingService:
    """Manages document embeddings for semantic search."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def embed_text(self, text: str) -> np.ndarray:
        """Embed arbitrary text."""
        model = _get_model()
        result: np.ndarray = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return result

    def embed_document(self, doc_id: int, force: bool = False) -> np.ndarray:
        """Embed a document (cached in database)."""
        # Check cache first
        if not force:
            cached = self._get_cached_embedding(doc_id)
            if cached is not None:
                return cached

        # Fetch document content
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, content FROM documents WHERE id = ? AND is_deleted = 0",
                (doc_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Document {doc_id} not found") from None

            title, content = row

        # Combine title and content for richer embedding
        text = f"{title}\n\n{content}"
        embedding = self.embed_text(text)

        # Cache it
        self._save_embedding(doc_id, embedding)

        return embedding

    def _get_cached_embedding(self, doc_id: int) -> np.ndarray | None:
        """Get cached embedding from database."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT embedding FROM document_embeddings WHERE document_id = ? AND model_name = ?",  # noqa: E501
                (doc_id, self.MODEL_NAME),
            )
            row = cursor.fetchone()
            if row:
                return np.frombuffer(row[0], dtype=np.float32)
        return None

    def _save_embedding(self, doc_id: int, embedding: np.ndarray) -> None:
        """Cache embedding to database."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO document_embeddings
                (document_id, model_name, embedding, dimension, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    doc_id,
                    self.MODEL_NAME,
                    embedding.tobytes(),
                    self.EMBEDDING_DIM,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def index_all(self, force: bool = False, batch_size: int = 50) -> int:
        """Index all unembedded documents. Returns count of newly indexed docs."""
        with db.get_connection() as conn:
            cursor = conn.cursor()

            if force:
                # Get all documents
                cursor.execute("SELECT id, title, content FROM documents WHERE is_deleted = 0")
            else:
                # Only get documents without embeddings
                cursor.execute(
                    """
                    SELECT d.id, d.title, d.content
                    FROM documents d
                    LEFT JOIN document_embeddings e
                        ON d.id = e.document_id AND e.model_name = ?
                    WHERE d.is_deleted = 0 AND e.id IS NULL
                """,
                    (self.MODEL_NAME,),
                )

            docs = cursor.fetchall()

        if not docs:
            return 0

        model = _get_model()
        count = 0

        # Process in batches for efficiency
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            texts = [f"{title}\n\n{content}" for _, title, content in batch]

            # Batch encode
            embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # Save all embeddings in batch
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for (doc_id, _, _), embedding in zip(batch, embeddings, strict=False):
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO document_embeddings
                        (document_id, model_name, embedding, dimension, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            doc_id,
                            self.MODEL_NAME,
                            embedding.tobytes(),
                            self.EMBEDDING_DIM,
                            datetime.utcnow().isoformat(),
                        ),
                    )
                conn.commit()

            count += len(batch)
            logger.info(f"Indexed {count}/{len(docs)} documents")

        return count

    def search(self, query: str, limit: int = 10, threshold: float = 0.3) -> list[SemanticMatch]:
        """Semantic search across all documents."""
        return self._search_sync(query, limit, threshold)

    def _search_sync(
        self, query: str, limit: int = 10, threshold: float = 0.3
    ) -> list[SemanticMatch]:
        """Internal synchronous search implementation."""
        query_embedding = self.embed_text(query)

        # Load all embeddings from database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.document_id, e.embedding, d.title, d.project,
                       SUBSTR(d.content, 1, 200) as snippet
                FROM document_embeddings e
                JOIN documents d ON e.document_id = d.id
                WHERE e.model_name = ? AND d.is_deleted = 0
            """,
                (self.MODEL_NAME,),
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        # Compute similarities
        results = []
        for doc_id, emb_bytes, title, project, snippet in rows:
            doc_embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            # Dot product of normalized vectors = cosine similarity
            similarity = float(np.dot(query_embedding, doc_embedding))

            if similarity >= threshold:
                results.append(
                    SemanticMatch(
                        doc_id=doc_id,
                        title=title,
                        project=project,
                        similarity=similarity,
                        snippet=snippet.replace("\n", " ")[:150] + "..." if snippet else "",
                    )
                )

        # Sort by similarity descending
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    async def search_async(
        self, query: str, limit: int = 10, threshold: float = 0.3
    ) -> list[SemanticMatch]:
        """Async semantic search - runs embedding in thread pool to avoid blocking."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._search_sync(query, limit, threshold))

    def find_similar(
        self, doc_id: int, limit: int = 5, project: str | None = None
    ) -> list[SemanticMatch]:
        """Find documents similar to a given document.

        Args:
            doc_id: The document to find similar documents for.
            limit: Maximum number of results to return.
            project: If set, only match documents in this project.
        """
        doc_embedding = self.embed_document(doc_id)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            if project is not None:
                cursor.execute(
                    """
                    SELECT e.document_id, e.embedding, d.title, d.project,
                           SUBSTR(d.content, 1, 200) as snippet
                    FROM document_embeddings e
                    JOIN documents d ON e.document_id = d.id
                    WHERE e.model_name = ? AND d.is_deleted = 0
                          AND e.document_id != ? AND d.project = ?
                    """,
                    (self.MODEL_NAME, doc_id, project),
                )
            else:
                cursor.execute(
                    """
                    SELECT e.document_id, e.embedding, d.title, d.project,
                           SUBSTR(d.content, 1, 200) as snippet
                    FROM document_embeddings e
                    JOIN documents d ON e.document_id = d.id
                    WHERE e.model_name = ? AND d.is_deleted = 0 AND e.document_id != ?
                    """,
                    (self.MODEL_NAME, doc_id),
                )
            rows = cursor.fetchall()

        results = []
        for other_id, emb_bytes, title, doc_project, snippet in rows:
            other_embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            similarity = float(np.dot(doc_embedding, other_embedding))

            results.append(
                SemanticMatch(
                    doc_id=other_id,
                    title=title,
                    project=doc_project,
                    similarity=similarity,
                    snippet=snippet.replace("\n", " ")[:150] + "..." if snippet else "",
                )
            )

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    def stats(self) -> EmbeddingStats:
        """Get embedding index statistics."""
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Total documents
            cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
            total = cursor.fetchone()[0]

            # Indexed documents
            cursor.execute(
                "SELECT COUNT(*) FROM document_embeddings WHERE model_name = ?",
                (self.MODEL_NAME,),
            )
            indexed = cursor.fetchone()[0]

            # Index size
            cursor.execute(
                "SELECT SUM(LENGTH(embedding)) FROM document_embeddings WHERE model_name = ?",
                (self.MODEL_NAME,),
            )
            size = cursor.fetchone()[0] or 0

            # Chunk statistics
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM chunk_embeddings WHERE model_name = ?",
                    (self.MODEL_NAME,),
                )
                chunk_count = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT SUM(LENGTH(embedding)) FROM chunk_embeddings WHERE model_name = ?",
                    (self.MODEL_NAME,),
                )
                chunk_size = cursor.fetchone()[0] or 0
            except Exception:
                # Table might not exist yet
                chunk_count = 0
                chunk_size = 0

        coverage = (indexed / total * 100) if total > 0 else 0

        return EmbeddingStats(
            total_documents=total,
            indexed_documents=indexed,
            coverage_percent=round(coverage, 1),
            model_name=self.MODEL_NAME,
            index_size_bytes=size,
            indexed_chunks=chunk_count,
            chunk_index_size_bytes=chunk_size,
        )

    def clear_index(self) -> int:
        """Clear all embeddings. Returns count deleted."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM document_embeddings")
            doc_count = cursor.rowcount
            cursor.execute("DELETE FROM chunk_embeddings")
            chunk_count = cursor.rowcount
            conn.commit()
            return doc_count + chunk_count

    # ========== Chunk-level indexing and search ==========

    def index_chunks(self, force: bool = False, batch_size: int = 100) -> int:
        """Index all document chunks. Returns count of newly indexed chunks."""
        from ..utils.chunk_splitter import split_into_chunks

        with db.get_connection() as conn:
            cursor = conn.cursor()

            if force:
                # Get all documents
                cursor.execute("SELECT id, title, content FROM documents WHERE is_deleted = 0")
            else:
                # Only get documents without chunk embeddings
                cursor.execute(
                    """
                    SELECT d.id, d.title, d.content
                    FROM documents d
                    WHERE d.is_deleted = 0
                      AND NOT EXISTS (
                          SELECT 1 FROM chunk_embeddings c
                          WHERE c.document_id = d.id AND c.model_name = ?
                      )
                    """,
                    (self.MODEL_NAME,),
                )

            docs = cursor.fetchall()

        if not docs:
            return 0

        model = _get_model()
        total_chunks = 0

        for doc_id, title, content in docs:
            # Split document into chunks
            chunks = split_into_chunks(content, title)

            if not chunks:
                continue

            # Embed all chunks for this document
            texts = [chunk.text for chunk in chunks]
            embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # Save chunk embeddings
            with db.get_connection() as conn:
                cursor = conn.cursor()

                # Clear existing chunks for this document if force
                if force:
                    cursor.execute(
                        "DELETE FROM chunk_embeddings WHERE document_id = ? AND model_name = ?",
                        (doc_id, self.MODEL_NAME),
                    )

                for chunk, embedding in zip(chunks, embeddings, strict=False):
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO chunk_embeddings
                        (document_id, chunk_index, heading_path, text,
                         model_name, embedding, dimension, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doc_id,
                            chunk.index,
                            chunk.heading_path,
                            chunk.text,
                            self.MODEL_NAME,
                            embedding.tobytes(),
                            self.EMBEDDING_DIM,
                            datetime.utcnow().isoformat(),
                        ),
                    )
                conn.commit()

            total_chunks += len(chunks)
            logger.info(f"Indexed {len(chunks)} chunks for document {doc_id}")

        return total_chunks

    def search_chunks(
        self, query: str, limit: int = 10, threshold: float = 0.3
    ) -> list[ChunkMatch]:
        """Semantic search at chunk level - returns relevant paragraphs."""
        query_embedding = self.embed_text(query)

        # Load all chunk embeddings from database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.document_id, c.chunk_index, c.heading_path, c.text, c.embedding,
                       d.title, d.project
                FROM chunk_embeddings c
                JOIN documents d ON c.document_id = d.id
                WHERE c.model_name = ? AND d.is_deleted = 0
                """,
                (self.MODEL_NAME,),
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        # Compute similarities
        results = []
        for doc_id, chunk_index, heading_path, text, emb_bytes, title, project in rows:
            chunk_embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            similarity = float(np.dot(query_embedding, chunk_embedding))

            if similarity >= threshold:
                results.append(
                    ChunkMatch(
                        doc_id=doc_id,
                        title=title,
                        project=project,
                        chunk_index=chunk_index,
                        heading_path=heading_path,
                        similarity=similarity,
                        chunk_text=text,
                    )
                )

        # Sort by similarity descending
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]
