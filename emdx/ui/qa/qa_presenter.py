"""
Presenter for the QA Screen.

Handles Q&A logic: retrieves context from the knowledge base,
generates answers via Claude CLI, and manages conversation state.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QASource:
    """A source document referenced in an answer."""

    doc_id: int
    title: str


@dataclass
class QAEntry:
    """A single Q&A exchange."""

    question: str
    answer: str = ""
    sources: list[QASource] = field(default_factory=list)
    method: str = ""  # "semantic" or "keyword"
    timestamp: datetime = field(default_factory=datetime.now)
    is_loading: bool = False
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class QAStateVM:
    """Complete Q&A state for the UI."""

    entries: list[QAEntry] = field(default_factory=list)
    is_asking: bool = False
    has_claude_cli: bool = False
    has_embeddings: bool = False
    status_text: str = ""


class QAPresenter:
    """
    Handles Q&A business logic.

    - Retrieves relevant documents via hybrid/keyword search
    - Generates answers via Claude CLI (UnifiedExecutor)
    - Manages conversation history
    """

    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
    MIN_EMBEDDINGS_FOR_SEMANTIC = 50

    def __init__(
        self,
        on_state_update: Callable[[QAStateVM], Awaitable[None]] | None = None,
        on_answer_chunk: Callable[[str], Awaitable[None]] | None = None,
    ):
        self.on_state_update = on_state_update
        self.on_answer_chunk = on_answer_chunk
        self._state = QAStateVM()
        self._embedding_service: Any = None
        self._cancel_event: asyncio.Event | None = None

    @property
    def state(self) -> QAStateVM:
        return self._state

    async def initialize(self) -> None:
        """Check capabilities on startup."""
        has_claude_cli = shutil.which("claude") is not None
        self._state.has_claude_cli = has_claude_cli

        self._state.has_embeddings = self._has_embeddings()

        if has_claude_cli:
            method = "semantic" if self._state.has_embeddings else "keyword"
            self._state.status_text = f"Ready | {method} retrieval"
        else:
            self._state.status_text = (
                "Claude CLI not found — install from: https://docs.anthropic.com/claude-code"
            )

        await self._notify_update()

    def _get_embedding_service(self) -> Any:
        if self._embedding_service is None:
            try:
                from emdx.services.embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except ImportError:
                return None
        return self._embedding_service

    def _has_embeddings(self) -> bool:
        svc = self._get_embedding_service()
        if svc is None:
            return False
        try:
            stats = svc.stats()
            return bool(stats.indexed_documents >= self.MIN_EMBEDDINGS_FOR_SEMANTIC)
        except Exception:
            return False

    async def _notify_update(self) -> None:
        if self.on_state_update:
            await self.on_state_update(self._state)

    async def ask(self, question: str) -> None:
        """Ask a question — retrieves context and streams an answer."""
        if not question.strip():
            return

        if not self._state.has_claude_cli:
            entry = QAEntry(
                question=question,
                error=(
                    "Claude CLI not found. Install from: https://docs.anthropic.com/claude-code"
                ),
            )
            self._state.entries.append(entry)
            await self._notify_update()
            return

        # Create entry and mark loading
        entry = QAEntry(question=question, is_loading=True)
        self._state.entries.append(entry)
        self._state.is_asking = True
        self._state.status_text = "Retrieving context..."
        await self._notify_update()

        self._cancel_event = asyncio.Event()
        start = time.time()

        try:
            # 1. Retrieve context documents
            docs, method = await asyncio.to_thread(self._retrieve, question)
            entry.method = method

            if self._cancel_event.is_set():
                return

            # Build sources list
            entry.sources = [QASource(doc_id=d[0], title=d[1]) for d in docs]

            # 2. Stream the answer
            self._state.status_text = "Generating answer..."
            await self._notify_update()

            context = self._build_context(docs)
            answer_text = await self._stream_answer(question, context)
            entry.answer = answer_text

        except asyncio.CancelledError:
            entry.answer = "(cancelled)"
            entry.error = "Cancelled"
        except Exception as e:
            logger.error(f"Q&A failed: {e}", exc_info=True)
            entry.error = str(e)
            entry.answer = f"Error: {e}"
        finally:
            entry.is_loading = False
            entry.elapsed_ms = int((time.time() - start) * 1000)
            self._state.is_asking = False
            src_count = len(entry.sources)
            self._state.status_text = f"{src_count} sources | {entry.method} | {entry.elapsed_ms}ms"
            self._cancel_event = None
            await self._notify_update()

    def cancel(self) -> None:
        """Cancel any in-progress question."""
        if self._cancel_event:
            self._cancel_event.set()

    def _retrieve(self, question: str, limit: int = 8) -> tuple[list[tuple], str]:
        """Retrieve relevant documents (runs in thread pool)."""
        import re

        from emdx.database import db

        docs: list[tuple] = []
        seen: set[int] = set()

        # Check for explicit doc references (#42)
        doc_refs = re.findall(r"#(\d+)", question)
        if doc_refs:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for ref in doc_refs:
                    try:
                        cursor.execute(
                            "SELECT id, title, content FROM documents "
                            "WHERE id = ? AND is_deleted = 0",
                            (int(ref),),
                        )
                        row = cursor.fetchone()
                        if row and row[0] not in seen:
                            docs.append(row)
                            seen.add(row[0])
                    except ValueError:
                        pass

        # Semantic or keyword retrieval
        remaining = limit - len(docs)
        if remaining > 0:
            if self._has_embeddings():
                sem_docs = self._retrieve_semantic(question, remaining)
                for d in sem_docs:
                    if d[0] not in seen:
                        docs.append(d)
                        seen.add(d[0])
                if sem_docs:
                    return docs[:limit], "semantic"

            # Fallback to keyword
            kw_docs = self._retrieve_keyword(question, remaining)
            for d in kw_docs:
                if d[0] not in seen:
                    docs.append(d)
                    seen.add(d[0])

        method = "semantic" if self._has_embeddings() else "keyword"
        return docs[:limit], method

    def _retrieve_semantic(self, question: str, limit: int) -> list[tuple]:
        svc = self._get_embedding_service()
        if svc is None:
            return []
        try:
            from emdx.database import db

            matches = svc.search(question, limit=limit * 2)
            docs = []
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for m in matches:
                    cursor.execute(
                        "SELECT id, title, content FROM documents WHERE id = ?",
                        (m.doc_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        docs.append(row)
                    if len(docs) >= limit:
                        break
            return docs
        except Exception as e:
            logger.warning(f"Semantic retrieval failed: {e}")
            return []

    def _retrieve_keyword(self, question: str, limit: int) -> list[tuple]:
        import re

        from emdx.database import db

        terms = re.sub(r"[^\w\s]", " ", question).strip()
        if not terms:
            return []
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, content FROM documents "
                    "WHERE documents_fts MATCH ? AND is_deleted = 0 "
                    "ORDER BY rank LIMIT ?",
                    (terms, limit),
                )
                return cursor.fetchall()
        except Exception as e:
            logger.debug(f"FTS retrieval failed: {e}")
            return []

    def _build_context(self, docs: list[tuple]) -> str:
        """Build context string from retrieved documents."""
        parts = []
        for doc_id, title, content in docs:
            truncated = content[:3000] if len(content) > 3000 else content
            parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}")
        return "\n\n---\n\n".join(parts)

    async def _stream_answer(self, question: str, context: str) -> str:
        """Generate an answer via Claude CLI, delivering the result as a single chunk."""
        from emdx.services.ask_service import _execute_claude_prompt

        system_prompt = (
            "You answer questions using the provided knowledge base context.\n\n"
            "Rules:\n"
            "- Only answer based on the provided documents\n"
            "- Cite document IDs when referencing information "
            "(e.g., 'According to Document #42...')\n"
            "- If the context doesn't contain relevant information, say so clearly\n"
            "- Be concise but complete\n"
            "- If documents contain conflicting information, note the discrepancy"
        )
        user_message = (
            f"Context from my knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}"
        )

        answer = await asyncio.to_thread(
            _execute_claude_prompt,
            system_prompt,
            user_message,
            f"TUI Ask: {question[:50]}",
            self.DEFAULT_MODEL,
        )

        if self.on_answer_chunk:
            await self.on_answer_chunk(answer)

        return answer

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._state.entries.clear()
        self._state.status_text = "History cleared"

    def get_entry_count(self) -> int:
        return len(self._state.entries)
