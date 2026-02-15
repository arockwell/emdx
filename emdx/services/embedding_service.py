"""
Semantic embedding service for EMDX.

Uses sentence-transformers for local embedding generation,
enabling semantic search without API costs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

from ..database import db

logger = logging.getLogger(__name__)

# Lazy load - model is ~90MB, loads in ~2 seconds
_model = None

def _get_model():
    """Lazy load the embedding model."""
    global _model
    if _model is None:
        if not HAS_NUMPY:
            raise ImportError(
                "numpy is required for embedding features. "
                "Install it with: pip install 'emdx[ai]'"
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
class EmbeddingStats:
    """Statistics about the embedding index."""

    total_documents: int
    indexed_documents: int
    coverage_percent: float
    model_name: str
    index_size_bytes: int

class EmbeddingService:
    """Manages document embeddings for semantic search."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def embed_text(self, text: str):
        """Embed arbitrary text."""
        model = _get_model()
        return model.encode(text, convert_to_numpy=True, normalize_embeddings=True)

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
                "SELECT embedding FROM document_embeddings WHERE document_id = ? AND model_name = ?",
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
                cursor.execute(
                    "SELECT id, title, content FROM documents WHERE is_deleted = 0"
                )
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

    def search(
        self, query: str, limit: int = 10, threshold: float = 0.3
    ) -> list[SemanticMatch]:
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
                        snippet=snippet.replace("\n", " ")[:150] + "..."
                        if snippet
                        else "",
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
        return await loop.run_in_executor(
            None, lambda: self._search_sync(query, limit, threshold)
        )

    def find_similar(self, doc_id: int, limit: int = 5) -> list[SemanticMatch]:
        """Find documents similar to a given document."""
        doc_embedding = self.embed_document(doc_id)

        with db.get_connection() as conn:
            cursor = conn.cursor()
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
        for other_id, emb_bytes, title, project, snippet in rows:
            other_embedding = np.frombuffer(emb_bytes, dtype=np.float32)
            similarity = float(np.dot(doc_embedding, other_embedding))

            results.append(
                SemanticMatch(
                    doc_id=other_id,
                    title=title,
                    project=project,
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

        coverage = (indexed / total * 100) if total > 0 else 0

        return EmbeddingStats(
            total_documents=total,
            indexed_documents=indexed,
            coverage_percent=round(coverage, 1),
            model_name=self.MODEL_NAME,
            index_size_bytes=size,
        )

    def delete_embedding(self, doc_id: int) -> bool:
        """Delete embedding for a document."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM document_embeddings WHERE document_id = ?", (doc_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_index(self) -> int:
        """Clear all embeddings. Returns count deleted."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM document_embeddings")
            count = cursor.rowcount
            conn.commit()
            return count
