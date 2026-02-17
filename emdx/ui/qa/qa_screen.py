"""
QA Screen - Conversational Q&A over your knowledge base.

Bypasses UnifiedExecutor to avoid terminal corruption caused by
the executor's subprocess environment. Runs claude CLI directly.
"""

import asyncio
import json
import logging
import queue
import subprocess
import threading
from typing import Any

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Input, Static

logger = logging.getLogger(__name__)

_msg_counter = 0


def _next_msg_id() -> str:
    global _msg_counter
    _msg_counter += 1
    return f"qa-msg-{_msg_counter}"


def _run_claude(question: str, context: str) -> str:
    """Run claude CLI directly — bypasses UnifiedExecutor."""
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
    user_message = f"Context from my knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}"
    prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_message}"

    cmd = [
        "claude",
        "--print",
        prompt,
        "--model",
        "claude-sonnet-4-5-20250929",
        "--output-format",
        "stream-json",
        "--verbose",
    ]

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    stdout_q: queue.Queue[str | None] = queue.Queue()

    def reader(pipe: Any, q: queue.Queue[str | None]) -> None:
        try:
            for line in pipe:
                q.put(line)
        finally:
            q.put(None)

    t = threading.Thread(target=reader, args=(process.stdout, stdout_q), daemon=True)
    t.start()

    stdout_lines: list[str] = []
    while True:
        try:
            line = stdout_q.get(timeout=120.0)
        except queue.Empty:
            break
        if line is None:
            break
        stdout_lines.append(line)

    t.join(timeout=5.0)
    process.wait()

    # Parse result
    for line in stdout_lines:
        try:
            data = json.loads(line)
            if data.get("type") == "result":
                result: str = data.get("result", "(no result)")
                return result
        except (json.JSONDecodeError, KeyError):
            continue

    return "(no answer parsed)"


def _retrieve_context(question: str) -> tuple[list[tuple[int, str, str]], str]:
    """Retrieve relevant documents for context."""
    import re
    import shutil

    from emdx.database import db

    docs: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    # Check for explicit doc references (#42)
    doc_refs = re.findall(r"#(\d+)", question)
    if doc_refs:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for ref in doc_refs:
                try:
                    cursor.execute(
                        "SELECT id, title, content FROM documents WHERE id = ? AND is_deleted = 0",
                        (int(ref),),
                    )
                    row = cursor.fetchone()
                    if row and row[0] not in seen:
                        docs.append(row)
                        seen.add(row[0])
                except ValueError:
                    pass

    # Keyword retrieval
    remaining = 8 - len(docs)
    if remaining > 0:
        terms = re.sub(r"[^\w\s]", " ", question).strip()
        if terms:
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT d.id, d.title, d.content FROM documents d "
                        "JOIN documents_fts fts ON d.id = fts.rowid "
                        "WHERE fts.documents_fts MATCH ? AND d.is_deleted = 0 "
                        "ORDER BY rank LIMIT ?",
                        (terms, remaining),
                    )
                    for row in cursor.fetchall():
                        if row[0] not in seen:
                            docs.append(row)
                            seen.add(row[0])
                            if len(docs) >= 8:
                                break
            except Exception as e:
                logger.debug(f"FTS retrieval failed: {e}")

    # Try semantic if available
    if not docs:
        try:
            has_semantic = shutil.which("claude") is not None
            if has_semantic:
                from emdx.services.embedding_service import EmbeddingService

                svc = EmbeddingService()
                stats = svc.stats()
                if stats.indexed_documents >= 50:
                    matches = svc.search(question, limit=8)
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
                            if len(docs) >= 8:
                                break
        except Exception:
            pass

    # Build context string
    parts = []
    for doc_id, title, content in docs:
        truncated = content[:3000] if len(content) > 3000 else content
        parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}")
    context = "\n\n---\n\n".join(parts)

    return docs, context


class QAScreen(Widget):
    """Q&A screen — runs claude directly, bypassing UnifiedExecutor."""

    DEFAULT_CSS = """
    QAScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr 1;
    }

    #qa-input {
        width: 100%;
    }

    #qa-conversation {
        height: 1fr;
        width: 100%;
        padding: 0 1;
    }

    .qa-message {
        width: 100%;
        margin: 0;
        padding: 0;
    }

    #qa-status {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._is_asking = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Ask a question...", id="qa-input")
        yield ScrollableContainer(id="qa-conversation")
        yield Static("Ready", id="qa-status")

    async def on_mount(self) -> None:
        logger.info("QAScreen mounted")
        self.query_one("#qa-conversation", ScrollableContainer).focus()

    def _append_message(self, markup: str) -> None:
        container = self.query_one("#qa-conversation", ScrollableContainer)
        msg = Static(markup, classes="qa-message", id=_next_msg_id())
        container.mount(msg)
        msg.scroll_visible()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "qa-input":
            return
        question = event.value.strip()
        if not question:
            return
        if self._is_asking:
            return

        event.input.value = ""
        self.query_one("#qa-conversation", ScrollableContainer).focus()
        self._append_message(f"\n[bold cyan]Q:[/bold cyan] {question}\n")

        self.run_worker(
            self._ask_and_render(question),
            name="qa_ask",
            group="qa_ask",
            exclusive=True,
            exit_on_error=False,
        )

    async def _ask_and_render(self, question: str) -> None:
        self._is_asking = True
        self._append_message("[dim]Thinking...[/dim]")

        try:
            # Retrieve context docs
            docs, context = await asyncio.to_thread(_retrieve_context, question)

            # Run claude
            answer = await asyncio.to_thread(_run_claude, question, context)

            self._append_message(f"[bold green]A:[/bold green] {answer}")

            # Show sources
            if docs:
                source_parts = [f"#{d[0]} {d[1]}" for d in docs]
                self._append_message(f"[dim]Sources: {' · '.join(source_parts)}[/dim]")
        except Exception as e:
            logger.error(f"Q&A failed: {e}", exc_info=True)
            self._append_message(f"[bold red]Error:[/bold red] {e}")

        self._append_message("[dim]─────────────────────────────────────────[/dim]")
        self._is_asking = False

    def save_state(self) -> dict:
        return {}

    def restore_state(self, state: dict) -> None:
        pass
