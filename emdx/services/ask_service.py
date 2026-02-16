"""
Q&A service for EMDX - RAG over your knowledge base.

Uses semantic search when available (embeddings indexed),
falls back to keyword search (FTS) otherwise.

Uses the Claude CLI (via UnifiedExecutor) for answer generation.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from typing import Any

from ..database import db
from ..utils.emoji_aliases import normalize_tag_to_emoji

logger = logging.getLogger(__name__)

# Context budget: ~12000 chars (~3000 tokens) max for LLM context
CONTEXT_BUDGET_CHARS = 12000

ANSWER_TIMEOUT = 120  # seconds


def _has_claude_cli() -> bool:
    """Check if the Claude CLI is available."""
    return shutil.which("claude") is not None


def _execute_claude_prompt(
    system_prompt: str,
    user_message: str,
    title: str,
    model: str | None = None,
) -> str:
    """Execute a Q&A prompt via the Claude CLI.

    Combines system and user messages into a single prompt for --print mode.

    Returns:
        The answer text from Claude.

    Raises:
        RuntimeError: If the CLI execution fails.
    """
    from .unified_executor import ExecutionConfig, UnifiedExecutor

    prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_message}"

    config = ExecutionConfig(
        prompt=prompt,
        title=title,
        allowed_tools=[],
        timeout_seconds=ANSWER_TIMEOUT,
        model=model,
    )

    executor = UnifiedExecutor()
    result = executor.execute(config)

    if not result.success:
        raise RuntimeError(f"Answer generation failed: {result.error_message or 'unknown error'}")

    return result.output_content or ""


@dataclass
class Answer:
    """An answer from the knowledge base."""

    text: str
    sources: list[int]  # Document IDs used
    source_titles: list[tuple[int, str]]  # (doc_id, title) pairs for display
    method: str  # "semantic" or "keyword"
    context_size: int  # Characters of context used
    confidence: str  # "high", "medium", or "low" based on source count


class AskService:
    """Answer questions using your knowledge base."""

    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
    MIN_EMBEDDINGS_FOR_SEMANTIC = 50  # Use semantic only if we have enough coverage

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self._embedding_service: Any = None

    def _get_embedding_service(self) -> Any:
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
            return bool(stats.indexed_documents >= self.MIN_EMBEDDINGS_FOR_SEMANTIC)
        except Exception as e:
            logger.debug(f"Could not check embedding stats: {e}")
            return False

    def ask(
        self,
        question: str,
        limit: int = 10,
        project: str | None = None,
        force_keyword: bool = False,
        tags: str | None = None,
        recent_days: int | None = None,
    ) -> Answer:
        """
        Ask a question about your knowledge base.

        Automatically chooses semantic or keyword search based on
        whether embeddings are available.

        Args:
            question: The question to answer
            limit: Max documents to retrieve
            project: Limit to specific project
            force_keyword: Force keyword search even if embeddings available
            tags: Comma-separated tags to filter by (text aliases auto-expand)
            recent_days: Limit to documents created in last N days
        """
        # Choose retrieval method
        if force_keyword or not self._has_embeddings():
            docs, method = self._retrieve_keyword(
                question, limit, project, tags=tags, recent_days=recent_days
            )
        else:
            docs, method = self._retrieve_semantic(
                question, limit, project, tags=tags, recent_days=recent_days
            )

        # Generate answer with context budget
        answer_text, context_size = self._generate_answer(question, docs)

        # Calculate confidence based on source count
        confidence = self._calculate_confidence(len(docs))

        # Build source titles list
        source_titles = [(d[0], d[1]) for d in docs]

        return Answer(
            text=answer_text,
            sources=[d[0] for d in docs],
            source_titles=source_titles,
            method=method,
            context_size=context_size,
            confidence=confidence,
        )

    def _calculate_confidence(self, source_count: int) -> str:
        """Calculate confidence level based on number of sources."""
        if source_count >= 3:
            return "high"
        elif source_count >= 1:
            return "medium"
        else:
            return "low"

    def _get_filtered_doc_ids(
        self,
        tags: str | None = None,
        recent_days: int | None = None,
        project: str | None = None,
    ) -> set[int] | None:
        """
        Get document IDs matching tag and recency filters.

        Returns None if no filters applied (meaning all docs match).
        Returns empty set if filters applied but no docs match.
        """
        if not tags and not recent_days:
            return None  # No filtering needed

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Start with all non-deleted docs
            base_conditions = ["d.is_deleted = 0"]
            params: list[Any] = []

            if project:
                base_conditions.append("d.project = ?")
                params.append(project)

            # Recent days filter
            if recent_days:
                base_conditions.append("d.created_at > datetime('now', ?)")
                params.append(f"-{recent_days} days")

            # Tag filter
            if tags:
                # Parse and normalize tags (expand text aliases to emojis)
                tag_list = [normalize_tag_to_emoji(t.strip()) for t in tags.split(",") if t.strip()]

                if tag_list:
                    # Get docs that have ALL specified tags
                    placeholders = ", ".join("?" * len(tag_list))
                    query = f"""
                        SELECT d.id FROM documents d
                        JOIN document_tags dt ON d.id = dt.document_id
                        JOIN tags t ON dt.tag_id = t.id
                        WHERE {" AND ".join(base_conditions)}
                        AND t.name IN ({placeholders})
                        GROUP BY d.id
                        HAVING COUNT(DISTINCT t.name) = ?
                    """
                    params.extend(tag_list)
                    params.append(len(tag_list))

                    cursor.execute(query, params)
                    return {row[0] for row in cursor.fetchall()}

            # No tags, just recent filter
            query = f"""
                SELECT d.id FROM documents d
                WHERE {" AND ".join(base_conditions)}
            """
            cursor.execute(query, params)
            return {row[0] for row in cursor.fetchall()}

    def _retrieve_keyword(
        self,
        question: str,
        limit: int,
        project: str | None = None,
        tags: str | None = None,
        recent_days: int | None = None,
    ) -> tuple[list[tuple[int, str, str]], str]:
        """Retrieve documents using FTS keyword search."""
        docs: list[tuple[int, str, str]] = []
        seen: set[int] = set()

        # Get filtered doc IDs if filters are applied
        filtered_ids = self._get_filtered_doc_ids(tags, recent_days, project)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Helper to check if doc passes filters
            def passes_filter(doc_id: int) -> bool:
                if filtered_ids is None:
                    return True
                return doc_id in filtered_ids

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
                    if row and row[0] not in seen and passes_filter(row[0]):
                        docs.append(row)
                        seen.add(row[0])
                except ValueError:
                    pass

            # Search for ticket references in content
            for ticket in ticket_refs:
                query = """
                    SELECT id, title, content FROM documents
                    WHERE content LIKE ? AND is_deleted = 0
                """
                params: list[Any] = [f"%{ticket}%"]

                if project:
                    query += " AND project = ?"
                    params.append(project)

                query += " LIMIT 3"
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    if row[0] not in seen and passes_filter(row[0]):
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
                # Fetch more than needed since we'll filter
                params.append((limit - len(docs)) * 3)

                try:
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        if row[0] not in seen and passes_filter(row[0]):
                            docs.append(row)
                            seen.add(row[0])
                            if len(docs) >= limit:
                                break
                except Exception as e:
                    # FTS query might fail on complex queries
                    logger.debug(f"FTS search failed: {e}")

            # 3. Fallback to recent docs if nothing found
            if not docs:
                query = """
                    SELECT id, title, content FROM documents
                    WHERE is_deleted = 0
                """
                fallback_params: list[Any] = []

                if project:
                    query += " AND project = ?"
                    fallback_params.append(project)

                query += " ORDER BY updated_at DESC LIMIT ?"
                fallback_params.append(limit * 3)

                cursor.execute(query, fallback_params)
                for row in cursor.fetchall():
                    if passes_filter(row[0]):
                        docs.append(row)
                        if len(docs) >= limit:
                            break

        return docs[:limit], "keyword"

    def _retrieve_semantic(
        self,
        question: str,
        limit: int,
        project: str | None = None,
        tags: str | None = None,
        recent_days: int | None = None,
    ) -> tuple[list[tuple[int, str, str]], str]:
        """Retrieve documents using semantic (embedding) search."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return self._retrieve_keyword(question, limit, project, tags, recent_days)

        # Get filtered doc IDs if filters are applied
        filtered_ids = self._get_filtered_doc_ids(tags, recent_days, project)

        try:
            # Fetch more matches since we may filter some out
            matches = embedding_service.search(question, limit=limit * 3)

            # Fetch full content for matches
            docs: list[tuple[int, str, str]] = []
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for match in matches:
                    # Check filter first
                    if filtered_ids is not None and match.doc_id not in filtered_ids:
                        continue

                    query = "SELECT id, title, content FROM documents WHERE id = ?"
                    params: list[Any] = [match.doc_id]

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
            return self._retrieve_keyword(question, limit, project, tags, recent_days)

        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            return self._retrieve_keyword(question, limit, project, tags, recent_days)

    def _generate_answer(self, question: str, docs: list[tuple[int, str, str]]) -> tuple[str, int]:
        """Generate answer from retrieved documents using Claude CLI."""
        if not docs:
            return (
                "I couldn't find any relevant documents to answer this question. "
                "Try rephrasing or check if you have documents on this topic.",
                0,
            )

        if not _has_claude_cli():
            raise ImportError(
                "Claude CLI is required for AI Q&A features. "
                "Install it from: https://docs.anthropic.com/claude-code"
            )

        # Build context from documents with budget enforcement
        context_parts: list[str] = []
        total_chars = 0

        for doc_id, title, content in docs:
            # Calculate how much budget remains
            remaining_budget = CONTEXT_BUDGET_CHARS - total_chars

            if remaining_budget <= 0:
                logger.debug(f"Context budget exhausted, skipping doc #{doc_id}")
                break

            # Truncate document to fit in remaining budget, with per-doc cap
            max_doc_chars = min(3000, remaining_budget - 100)  # Leave room for header
            if max_doc_chars <= 100:
                break

            truncated = content[:max_doc_chars] if len(content) > max_doc_chars else content
            doc_context = f"# Document #{doc_id}: {title}\n\n{truncated}"
            context_parts.append(doc_context)
            total_chars += len(doc_context) + 10  # Account for separator

        context = "\n\n---\n\n".join(context_parts)
        context_size = len(context)

        # Generate answer via Claude CLI
        system_prompt = (
            "You answer questions using the provided knowledge base context.\n\n"
            "Rules:\n"
            "- Only answer based on the provided documents\n"
            "- Cite document IDs when referencing information "
            '(e.g., "According to Document #42...")\n'
            "- If the context doesn't contain relevant information, say so clearly\n"
            "- Be concise but complete\n"
            "- If documents contain conflicting information, note the discrepancy"
        )
        user_message = (
            f"Context from my knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}"
        )

        try:
            result = _execute_claude_prompt(
                system_prompt=system_prompt,
                user_message=user_message,
                title=f"Ask: {question[:50]}",
                model=self.model,
            )
            return result, context_size
        except RuntimeError as e:
            logger.error(f"Claude CLI error: {e}")
            return f"Error generating answer: {e}", context_size

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
        if not _has_claude_cli():
            raise ImportError(
                "Claude CLI is required for AI Q&A features. "
                "Install it from: https://docs.anthropic.com/claude-code"
            )

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

        # Generate answer via Claude CLI
        system_prompt = (
            "You answer questions using the provided context which may include:\n"
            "1. External resource data (Jira tickets, GitHub issues, etc.)\n"
            "2. Documents from the user's knowledge base\n\n"
            "Rules:\n"
            "- Cite sources clearly (Jira tickets by ID, documents by #ID)\n"
            "- If sources conflict, note the discrepancy\n"
            "- Be concise but complete"
        )
        user_message = f"Context:\n\n{context}\n\n---\n\nQuestion: {question}"

        try:
            answer_text = _execute_claude_prompt(
                system_prompt=system_prompt,
                user_message=user_message,
                title=f"Ask (with context): {question[:40]}",
                model=self.model,
            )
            return Answer(
                text=answer_text,
                sources=[d[0] for d in docs],
                source_titles=[(d[0], d[1]) for d in docs],
                method=method,
                context_size=len(context),
                confidence=self._calculate_confidence(len(docs)),
            )
        except RuntimeError as e:
            logger.error(f"Claude CLI error: {e}")
            return Answer(
                text=f"Error generating answer: {e}",
                sources=[d[0] for d in docs],
                source_titles=[(d[0], d[1]) for d in docs],
                method=method,
                context_size=len(context),
                confidence=self._calculate_confidence(len(docs)),
            )
