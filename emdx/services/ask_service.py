"""
Q&A service for EMDX - RAG over your knowledge base.

Uses semantic search when available (embeddings indexed),
falls back to keyword search (FTS) otherwise.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Tuple

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False

from ..database import db

logger = logging.getLogger(__name__)


@dataclass
class Answer:
    """An answer from the knowledge base."""

    text: str
    sources: List[int]  # Document IDs used
    method: str  # "semantic" or "keyword"
    context_size: int  # Characters of context used


class AskService:
    """Answer questions using your knowledge base."""

    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
    MIN_EMBEDDINGS_FOR_SEMANTIC = 50  # Use semantic only if we have enough coverage

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self._client = None
        self._embedding_service = None

    def _get_client(self):
        """Lazy load Anthropic client."""
        if not HAS_ANTHROPIC:
            raise ImportError(
                "anthropic is required for AI Q&A features. "
                "Install it with: pip install 'emdx[ai]'"
            )
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def _get_embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            try:
                from .embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except ImportError:
                logger.warning("sentence-transformers not installed, semantic search unavailable")
                return None
        return self._embedding_service

    def _has_embeddings(self) -> bool:
        """Check if we have enough embeddings for semantic search."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return False

        try:
            stats = embedding_service.stats()
            return stats.indexed_documents >= self.MIN_EMBEDDINGS_FOR_SEMANTIC
        except Exception as e:
            logger.debug(f"Could not check embedding stats: {e}")
            return False

    def ask(
        self,
        question: str,
        limit: int = 10,
        project: str | None = None,
        force_keyword: bool = False,
    ) -> Answer:
        """
        Ask a question about your knowledge base.

        Automatically chooses semantic or keyword search based on
        whether embeddings are available.
        """
        # Choose retrieval method
        if force_keyword or not self._has_embeddings():
            docs, method = self._retrieve_keyword(question, limit, project)
        else:
            docs, method = self._retrieve_semantic(question, limit, project)

        # Generate answer
        answer_text, context_size = self._generate_answer(question, docs)

        return Answer(
            text=answer_text,
            sources=[d[0] for d in docs],
            method=method,
            context_size=context_size,
        )

    def _retrieve_keyword(
        self, question: str, limit: int, project: str | None = None
    ) -> Tuple[List[tuple], str]:
        """Retrieve documents using FTS keyword search."""
        docs = []
        seen = set()

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Extract and search for explicit references (AUTH-123, #42)
            ticket_refs = re.findall(r"[A-Z]{2,10}-\d+", question)
            doc_refs = re.findall(r"#(\d+)", question)

            # Fetch explicitly referenced docs
            for doc_id in doc_refs:
                try:
                    doc_id_int = int(doc_id)
                    cursor.execute(
                        "SELECT id, title, content FROM documents WHERE id = ? AND is_deleted = 0",
                        (doc_id_int,),
                    )
                    row = cursor.fetchone()
                    if row and row[0] not in seen:
                        docs.append(row)
                        seen.add(row[0])
                except ValueError:
                    # Invalid doc ID format, skip this reference
                    pass

            # Search for ticket references in content
            for ticket in ticket_refs:
                query = """
                    SELECT id, title, content FROM documents
                    WHERE content LIKE ? AND is_deleted = 0
                """
                params = [f"%{ticket}%"]

                if project:
                    query += " AND project = ?"
                    params.append(project)

                query += " LIMIT 3"
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    if row[0] not in seen:
                        docs.append(row)
                        seen.add(row[0])

            # 2. FTS search for question terms
            # Clean question for FTS (remove special chars, keep words)
            terms = re.sub(r"[^\w\s]", " ", question).strip()
            if terms and len(docs) < limit:
                query = """
                    SELECT id, title, content FROM documents
                    WHERE documents_fts MATCH ? AND is_deleted = 0
                """
                params = [terms]

                if project:
                    query += " AND project = ?"
                    params.append(project)

                query += " ORDER BY rank LIMIT ?"
                params.append(limit - len(docs))

                try:
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        if row[0] not in seen:
                            docs.append(row)
                            seen.add(row[0])
                except Exception as e:
                    # FTS query might fail on complex queries
                    logger.debug(f"FTS search failed: {e}")

            # 3. Fallback to recent docs if nothing found
            if not docs:
                query = """
                    SELECT id, title, content FROM documents
                    WHERE is_deleted = 0
                """
                params = []

                if project:
                    query += " AND project = ?"
                    params.append(project)

                query += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                docs = cursor.fetchall()

        return docs[:limit], "keyword"

    def _retrieve_semantic(
        self, question: str, limit: int, project: str | None = None
    ) -> Tuple[List[tuple], str]:
        """Retrieve documents using semantic (embedding) search."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return self._retrieve_keyword(question, limit, project)

        try:
            matches = embedding_service.search(question, limit=limit * 2)

            # Fetch full content for matches
            docs = []
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for match in matches:
                    query = "SELECT id, title, content FROM documents WHERE id = ?"
                    params = [match.doc_id]

                    if project:
                        query += " AND project = ?"
                        params.append(project)

                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    if row:
                        docs.append(row)

                    if len(docs) >= limit:
                        break

            if docs:
                return docs, "semantic"

            # Fall back to keyword if semantic returns nothing
            return self._retrieve_keyword(question, limit, project)

        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            return self._retrieve_keyword(question, limit, project)

    def _generate_answer(
        self, question: str, docs: List[tuple]
    ) -> Tuple[str, int]:
        """Generate answer from retrieved documents using Claude."""
        if not docs:
            return (
                "I couldn't find any relevant documents to answer this question. "
                "Try rephrasing or check if you have documents on this topic.",
                0,
            )

        # Build context from documents
        context_parts = []
        for doc_id, title, content in docs:
            # Truncate very long documents
            truncated = content[:3000] if len(content) > 3000 else content
            context_parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}")

        context = "\n\n---\n\n".join(context_parts)
        context_size = len(context)

        # Generate answer with Claude
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=1000,
                system="""You answer questions using the provided knowledge base context.

Rules:
- Only answer based on the provided documents
- Cite document IDs when referencing information (e.g., "According to Document #42...")
- If the context doesn't contain relevant information, say so clearly
- Be concise but complete
- If documents contain conflicting information, note the discrepancy""",
                messages=[
                    {
                        "role": "user",
                        "content": f"Context from my knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}",
                    }
                ],
            )

            return response.content[0].text, context_size

        except Exception as e:
            if HAS_ANTHROPIC and isinstance(e, anthropic.APIError):
                logger.error(f"Claude API error: {e}")
                return f"Error generating answer: {e}", context_size
            raise

    def ask_with_context(
        self,
        question: str,
        additional_context: str,
        limit: int = 5,
        project: str | None = None,
    ) -> Answer:
        """
        Ask a question with additional context (e.g., from external resources).

        The additional_context is prepended to the retrieved documents.
        """
        # Retrieve relevant docs
        if self._has_embeddings():
            docs, method = self._retrieve_semantic(question, limit, project)
        else:
            docs, method = self._retrieve_keyword(question, limit, project)

        # Build combined context
        context_parts = [additional_context] if additional_context else []

        for doc_id, title, content in docs:
            truncated = content[:2000] if len(content) > 2000 else content
            context_parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}")

        context = "\n\n---\n\n".join(context_parts)

        # Generate answer
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=1000,
                system="""You answer questions using the provided context which may include:
1. External resource data (Jira tickets, GitHub issues, etc.)
2. Documents from the user's knowledge base

Rules:
- Cite sources clearly (Jira tickets by ID, documents by #ID)
- If sources conflict, note the discrepancy
- Be concise but complete""",
                messages=[
                    {
                        "role": "user",
                        "content": f"Context:\n\n{context}\n\n---\n\nQuestion: {question}",
                    }
                ],
            )

            return Answer(
                text=response.content[0].text,
                sources=[d[0] for d in docs],
                method=method,
                context_size=len(context),
            )

        except Exception as e:
            if HAS_ANTHROPIC and isinstance(e, anthropic.APIError):
                logger.error(f"Claude API error: {e}")
                return Answer(
                    text=f"Error generating answer: {e}",
                    sources=[d[0] for d in docs],
                    method=method,
                    context_size=len(context),
                )
            raise
