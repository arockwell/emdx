"""
Presenter for the QA Screen.

Handles Q&A logic: retrieves context from the knowledge base,
generates answers via Claude CLI, and manages conversation state.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _save_terminal_state() -> list[Any] | None:
    """Save current terminal attributes so they can be restored later.

    Something in the retrieval/subprocess pipeline resets the terminal
    from raw mode to cooked mode, which kills Textual's mouse and key
    handling.  We save before and restore after.
    """
    import sys
    import termios

    try:
        fd = sys.stdin.fileno()
        return termios.tcgetattr(fd)  # type: ignore[no-any-return]
    except Exception:
        return None


def _restore_terminal_state(saved: list[Any] | None) -> None:
    """Restore terminal attributes saved by _save_terminal_state.

    Only restores termios attributes (raw/cooked mode).  We do NOT
    re-send mouse tracking escape sequences because writing raw bytes
    to stderr bypasses Textual's driver output buffer and can corrupt
    the escape sequence stream, breaking mouse handling.

    Subprocess.Popen with stdin/stdout/stderr=PIPE should not affect
    the parent's DEC private-mode escape state since the child has no
    access to the terminal.  If termios attributes changed (e.g., a
    library reset raw mode), restoring them is sufficient.
    """
    import sys
    import termios

    if saved is None:
        return
    try:
        fd = sys.stdin.fileno()
        current = termios.tcgetattr(fd)
        if current != saved:
            logger.info(
                "Terminal state changed — restoring (lflag %#x -> %#x)",
                current[3],
                saved[3],
            )
            termios.tcsetattr(fd, termios.TCSANOW, saved)
    except Exception as e:
        logger.warning("Failed to restore terminal state: %s", e)


@dataclass
class QASource:
    """A source document referenced in an answer."""

    doc_id: int
    title: str
    snippet: str = ""


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
    saved_doc_id: int | None = None  # DB doc ID if loaded from/saved to KB


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

    def initialize_sync(self) -> None:
        """Fast synchronous init — CLI check + load history. No heavy imports."""
        self._state.has_claude_cli = shutil.which("claude") is not None
        self.load_history()

    async def preload_embeddings(self) -> None:
        """Pre-import sentence-transformers/torch in a background thread.

        This library corrupts terminal state (raw → cooked) on import.
        We save terminal state before dispatching to the thread, and
        restore on the main thread after. Writing mouse-tracking escape
        sequences from a background thread can race with Textual's
        rendering and corrupt terminal state further.
        """

        def _preload_and_check() -> bool:
            has = self._has_embeddings()
            if has:
                try:
                    from sentence_transformers import SentenceTransformer  # noqa: F401

                    logger.info("Pre-loaded sentence-transformers")
                except ImportError:
                    pass
            return has

        term_state = _save_terminal_state()
        self._state.has_embeddings = await asyncio.to_thread(_preload_and_check)
        _restore_terminal_state(term_state)

        if self._state.has_claude_cli:
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
            term_state = _save_terminal_state()
            docs, method = await asyncio.to_thread(self._retrieve, question)
            _restore_terminal_state(term_state)
            entry.method = method

            if self._cancel_event.is_set():
                return

            # Build sources list with content snippets
            entry.sources = [
                QASource(
                    doc_id=d[0],
                    title=d[1],
                    snippet=d[2][:200] if len(d) > 2 else "",
                )
                for d in docs
            ]

            # 2. Stream the answer
            self._state.status_text = "Generating answer..."
            await self._notify_update()

            context = self._build_context(docs)
            term_state = _save_terminal_state()
            answer_text = await self._stream_answer(question, context)
            _restore_terminal_state(term_state)
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

            # Auto-save completed answers to the knowledge base
            logger.info(
                "ask() finally: answer=%d chars, error=%r, saving=%s",
                len(entry.answer),
                entry.error,
                bool(entry.answer and not entry.error),
            )
            if entry.answer and not entry.error:
                self._auto_save_entry(entry)

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
                    "SELECT d.id, d.title, d.content FROM documents d "
                    "JOIN documents_fts fts ON d.id = fts.rowid "
                    "WHERE fts.documents_fts MATCH ? AND d.is_deleted = 0 "
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

    # ~2000 tokens ≈ 8000 chars for prior conversation context
    MAX_HISTORY_CHARS = 8000

    def _build_conversation_history(self) -> str:
        """Build prior Q&A context from recent entries (excluding the current one).

        Returns a formatted string of recent exchanges, capped at MAX_HISTORY_CHARS.
        Only includes completed entries (not loading, not errored).
        """
        # Current question is already appended to entries, so exclude the last one
        completed = [e for e in self._state.entries[:-1] if e.answer and not e.error]
        if not completed:
            return ""

        # Build from most recent backward, stop when we hit the char budget
        parts: list[str] = []
        chars = 0
        for entry in reversed(completed):
            # Truncate long answers to keep context focused
            answer = entry.answer[:2000] if len(entry.answer) > 2000 else entry.answer
            exchange = f"Q: {entry.question}\nA: {answer}"
            if chars + len(exchange) > self.MAX_HISTORY_CHARS:
                break
            parts.append(exchange)
            chars += len(exchange)

        if not parts:
            return ""

        parts.reverse()  # chronological order
        return "\n\n".join(parts)

    async def _stream_answer(self, question: str, context: str) -> str:
        """Generate an answer via Claude CLI, streaming chunks as they arrive."""
        from emdx.services.cli_executor.claude import ClaudeCliExecutor
        from emdx.utils.environment import get_subprocess_env
        from emdx.utils.stream_json_parser import parse_stream_json_line

        history = self._build_conversation_history()
        history_section = ""
        if history:
            history_section = (
                "\n\nPrior conversation for context:\n\n"
                f"{history}\n\n"
                "Use the above conversation history to understand follow-up questions."
            )

        system_prompt = (
            "You answer questions using the provided knowledge base context.\n\n"
            "Rules:\n"
            "- Only answer based on the provided documents\n"
            "- Cite document IDs when referencing information "
            "(e.g., 'According to Document #42...')\n"
            "- If the context doesn't contain relevant information, say so clearly\n"
            "- Be concise but complete\n"
            "- If documents contain conflicting information, note the discrepancy"
            f"{history_section}"
        )
        user_message = (
            f"Context from my knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}"
        )
        prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_message}"

        # Build CLI command
        executor = ClaudeCliExecutor()
        cmd = executor.build_command(
            prompt=prompt,
            model=self.DEFAULT_MODEL,
            allowed_tools=[],
            output_format="stream-json",
        )

        # Spawn subprocess
        process = subprocess.Popen(
            cmd.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cmd.cwd,
            env=get_subprocess_env(),
        )

        # Feed prompt via stdin then close
        if cmd.stdin_data and process.stdin:
            process.stdin.write(cmd.stdin_data)
            process.stdin.close()

        # Read stdout via background thread (macOS-safe, see unified_executor.py)
        stdout_q: queue.Queue[str | None] = queue.Queue()

        def reader_thread() -> None:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    stdout_q.put(line)
            finally:
                stdout_q.put(None)

        reader = threading.Thread(target=reader_thread, daemon=True)
        reader.start()

        # Consume queue from async event loop, streaming chunks
        accumulated: list[str] = []
        timeout = 120  # seconds
        deadline = time.time() + timeout

        try:
            while True:
                if self._cancel_event and self._cancel_event.is_set():
                    process.kill()
                    break

                if time.time() > deadline:
                    process.kill()
                    raise TimeoutError("Answer generation timed out")

                try:
                    line = await asyncio.to_thread(stdout_q.get, timeout=0.5)
                except Exception:
                    # Queue.get timeout — check cancel/deadline and retry
                    continue

                if line is None:
                    break  # Reader finished

                content_type, text = parse_stream_json_line(line)
                if content_type == "text" and text:
                    accumulated.append(text)
                    if self.on_answer_chunk:
                        await self.on_answer_chunk(text)

            process.wait(timeout=5)
        except Exception:
            process.kill()
            raise
        finally:
            reader.join(timeout=2)

        if process.returncode and process.returncode != 0:
            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
            raise RuntimeError(f"Claude CLI failed (exit {process.returncode}): {stderr_output}")

        return "".join(accumulated)

    def _auto_save_entry(self, entry: QAEntry) -> None:
        """Persist a completed Q&A entry to the knowledge base."""
        try:
            from emdx.models.documents import save_document

            content = f"# Q: {entry.question}\n\n{entry.answer}\n"
            if entry.sources:
                content += "\n## Sources\n\n"
                for s in entry.sources:
                    content += f"- Document #{s.doc_id}: {s.title}\n"

            doc_id = save_document(
                title=f"Q&A: {entry.question[:60]}",
                content=content,
                tags=["qa", "auto"],
                doc_type="qa",
            )
            entry.saved_doc_id = doc_id
            logger.info("Auto-saved Q&A entry as document #%d", doc_id)
        except Exception as e:
            logger.warning("Failed to auto-save Q&A entry: %s", e)

    def load_history(self, limit: int = 50) -> None:
        """Load saved Q&A exchanges from the knowledge base.

        Queries documents with doc_type='qa' and parses question/answer from
        their content format (``# Q: question\\n\\nanswer``).
        """
        import re

        from emdx.database import db

        try:
            with db.get_connection() as conn:
                # Migrate any old Q&A docs that were saved with doc_type='user'
                conn.execute(
                    "UPDATE documents SET doc_type = 'qa' "
                    "WHERE doc_type = 'user' AND is_deleted = 0 "
                    "AND title LIKE 'Q&A: %'"
                )
                conn.commit()

                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, content, created_at "
                    "FROM documents "
                    "WHERE doc_type = 'qa' AND is_deleted = 0 "
                    "ORDER BY created_at ASC "
                    "LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
        except Exception as e:
            logger.warning("Failed to load Q&A history: %s", e)
            return

        for row in rows:
            doc_id, title, content, created_at = row[0], row[1], row[2], row[3]

            # Parse question from title (format: "Q&A: question text")
            question = title
            if title.startswith("Q&A: "):
                question = title[5:]

            # Parse answer from content (format: "# Q: ...\n\n<answer>\n\n## Sources")
            answer = content
            # Strip the heading line
            lines = content.split("\n", 2)
            if len(lines) > 2 and lines[0].startswith("# Q:"):
                answer = lines[2]
            # Strip the sources section at the end
            sources_idx = answer.rfind("\n## Sources\n")
            if sources_idx >= 0:
                answer = answer[:sources_idx]
            answer = answer.strip()

            # Parse sources from content
            sources: list[QASource] = []
            source_match = re.findall(r"- Document #(\d+): (.+)", content)
            for sid, stitle in source_match:
                sources.append(QASource(doc_id=int(sid), title=stitle))

            # Parse timestamp
            try:
                ts = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                ts = datetime.now()

            entry = QAEntry(
                question=question,
                answer=answer,
                sources=sources,
                timestamp=ts,
                saved_doc_id=doc_id,
            )
            self._state.entries.append(entry)

        logger.info("Loaded %d Q&A entries from database", len(rows))

    def clear_history(self) -> None:
        """Clear conversation history (session only, does not delete from DB)."""
        self._state.entries.clear()
        self._state.status_text = "History cleared"

    def get_entry_count(self) -> int:
        return len(self._state.entries)
