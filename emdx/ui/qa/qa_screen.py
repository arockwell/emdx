"""
QA Screen - Conversational Q&A over your knowledge base.

Runs claude CLI directly via subprocess.Popen, bypassing UnifiedExecutor
to avoid terminal corruption that breaks Textual's mouse event parsing.
"""

import asyncio
import json
import logging
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static

from ..modals import HelpMixin

logger = logging.getLogger(__name__)

_msg_counter = 0


def _next_msg_id() -> str:
    global _msg_counter
    _msg_counter += 1
    return f"qa-msg-{_msg_counter}"


# ---------------------------------------------------------------------------
# Subprocess helpers (run in thread pool, no UnifiedExecutor)
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
_ANSWER_TIMEOUT = 120.0


def _save_terminal_state() -> "list[Any] | None":
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


def _restore_terminal_state(saved: "list[Any] | None") -> None:
    """Restore terminal attributes saved by _save_terminal_state."""
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
        _DEFAULT_MODEL,
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
            line = stdout_q.get(timeout=_ANSWER_TIMEOUT)
        except queue.Empty:
            break
        if line is None:
            break
        stdout_lines.append(line)

    t.join(timeout=5.0)
    process.wait()

    # Parse result from stream-json
    for line in stdout_lines:
        try:
            data = json.loads(line)
            if data.get("type") == "result":
                result: str = data.get("result", "(no result)")
                return result
        except (json.JSONDecodeError, KeyError):
            continue

    return "(no answer parsed)"


def _retrieve_context(question: str, limit: int = 8) -> tuple[list[tuple[int, str, str]], str]:
    """Retrieve relevant documents for context."""
    import re

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
    remaining = limit - len(docs)
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
                            if len(docs) >= limit:
                                break
            except Exception as e:
                logger.debug(f"FTS retrieval failed: {e}")

    # NOTE: Semantic fallback (EmbeddingService) is intentionally excluded here.
    # Importing torch/sentence-transformers resets the terminal from raw to
    # cooked mode, which kills Textual's mouse and key handling.
    # Keyword FTS + explicit #ID references cover the common Q&A cases well.

    # Build context string
    parts = []
    for doc_id, title, content in docs:
        truncated = content[:3000] if len(content) > 3000 else content
        parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}")
    context = "\n\n---\n\n".join(parts)

    return docs, context


# ---------------------------------------------------------------------------
# QAScreen widget
# ---------------------------------------------------------------------------


class QAScreen(HelpMixin, Widget):
    """
    Conversational Q&A widget over your knowledge base.

    Layout: Input bar | Scrollable conversation | Status bar | Nav bar
    """

    HELP_TITLE = "Q&A"

    BINDINGS = [
        Binding("enter", "submit_question", "Ask", show=True),
        Binding("escape", "exit_qa", "Exit"),
        Binding("slash", "focus_input", "Focus Input"),
        Binding("s", "save_exchange", "Save"),
        Binding("c", "clear_history", "Clear"),
        Binding("question_mark", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    QAScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr 1 1;
    }

    #qa-input-bar {
        height: auto;
        max-height: 5;
        padding: 0 1;
        background: $surface;
    }

    #qa-input {
        width: 1fr;
        border: solid $primary-darken-1;
    }

    #qa-input:focus {
        border: solid $primary;
    }

    #qa-mode-label {
        width: auto;
        height: 1;
        margin: 1 0 0 1;
        padding: 0 1;
        background: $primary;
        color: $text;
    }

    #qa-conversation {
        height: 1fr;
        width: 100%;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    .qa-message {
        width: 100%;
        margin: 0;
        padding: 0;
    }

    .qa-answer {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0;
    }

    #qa-status {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #qa-nav {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._is_asking = False
        self._has_claude_cli = shutil.which("claude") is not None
        self._source_ids: list[int] = []
        self._entries: list[dict[str, Any]] = []
        self._pending_question: str | None = None  # In-flight question text
        # Background task that survives widget unmount/remount
        self._bg_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="qa-input-bar"):
            yield Input(
                placeholder="Ask a question about your knowledge base...",
                id="qa-input",
            )
            yield Static("Q&A", id="qa-mode-label")

        yield ScrollableContainer(id="qa-conversation")

        yield Static("Ready | Type a question and press Enter", id="qa-status")
        yield Static(
            "[dim]1[/dim] Activity | [dim]2[/dim] Tasks | [bold]3[/bold] Q&A | "
            "[dim]/[/dim] type | [dim]Enter[/dim] ask | "
            "[dim]s[/dim] save | [dim]c[/dim] clear",
            id="qa-nav",
        )

    async def on_mount(self) -> None:
        """Initialize or restore the Q&A screen.

        Called both on first mount and on re-mount after switching screens.
        If we have prior conversation entries, rebuild them instead of
        showing the welcome message.
        """
        has_state = bool(self._entries) or self._is_asking
        logger.info(
            "QAScreen mounted (entries=%d, asking=%s, pending=%s)",
            len(self._entries),
            self._is_asking,
            self._pending_question is not None,
        )
        if has_state:
            self._rebuild_conversation()
        else:
            self._show_welcome()
        # Focus conversation, not Input — avoids mouse sequence corruption
        self.query_one("#qa-conversation", ScrollableContainer).focus()

    def _append_message(self, markup: str) -> None:
        """Append a Rich markup message to the conversation."""
        container = self.query_one("#qa-conversation", ScrollableContainer)
        msg = Static(markup, classes="qa-message", id=_next_msg_id())
        container.mount(msg)
        msg.scroll_visible()

    def _append_markdown(self, content: str) -> None:
        """Append a rendered Markdown widget to the conversation."""
        container = self.query_one("#qa-conversation", ScrollableContainer)
        md = Markdown(content, classes="qa-answer", id=_next_msg_id())
        container.mount(md)
        md.scroll_visible()

    def _show_welcome(self) -> None:
        """Show welcome message."""
        self._append_message(
            "[bold]Welcome to Q&A[/bold]\n"
            "\n"
            "Ask questions about your knowledge base in natural language.\n"
            "Answers are generated from your documents using Claude.\n"
            "\n"
            "[dim]Examples:[/dim]\n"
            "  [italic]What's our caching strategy?[/italic]\n"
            "  [italic]How did we fix the auth bug?[/italic]\n"
            "  [italic]Summarize the architecture decisions[/italic]\n"
            "\n"
            "[dim]Tip: Reference docs directly with #42 syntax[/dim]\n"
            "[dim]─────────────────────────────────────────[/dim]"
        )

    def _rebuild_conversation(self) -> None:
        """Rebuild conversation DOM from saved entries.

        Called on re-mount after switching screens.  The child widgets
        were destroyed by remove_children() but _entries survived on
        the Python object.
        """
        for entry in self._entries:
            self._append_message(f"\n[bold cyan]Q:[/bold cyan] {entry['question']}\n")
            self._render_entry(entry)

        if self._is_asking and self._pending_question:
            self._append_message(f"\n[bold cyan]Q:[/bold cyan] {self._pending_question}\n")
            self._set_thinking("[dim]Still generating answer...[/dim]")

    def _update_status(self, text: str) -> None:
        """Update the status bar text."""
        try:
            self.query_one("#qa-status", Static).update(text)
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter press in the input."""
        if event.input.id != "qa-input":
            return
        question = event.value.strip()
        if not question:
            return
        if self._is_asking:
            self.notify("Still waiting — press Escape to cancel", timeout=2)
            return

        if not self._has_claude_cli:
            self.notify("Claude CLI not found", severity="error", timeout=3)
            return

        # Clear input and unfocus
        event.input.value = ""
        self.query_one("#qa-conversation", ScrollableContainer).focus()

        # Show the question
        self._append_message(f"\n[bold cyan]Q:[/bold cyan] {question}\n")

        # Launch as a free-standing asyncio task so it survives widget
        # unmount/remount (run_worker gets cancelled on unmount).
        self._is_asking = True
        self._pending_question = question
        self._bg_task = asyncio.get_event_loop().create_task(self._fetch_and_store(question))

    def _cancel_asking(self) -> None:
        """Cancel the current Q&A operation and reset state."""
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        self._is_asking = False
        self._pending_question = None
        self._remove_thinking()
        self._append_message("[dim italic]Cancelled[/dim italic]")
        self._append_message("[dim]─────────────────────────────────────────[/dim]")
        self._update_status("Cancelled | Ready")

    def _set_thinking(self, text: str) -> None:
        """Update or create the thinking indicator."""
        try:
            existing = self.query_one("#qa-thinking", Static)
            existing.update(text)
        except Exception:
            try:
                container = self.query_one("#qa-conversation", ScrollableContainer)
                indicator = Static(text, id="qa-thinking", classes="qa-message")
                container.mount(indicator)
                indicator.scroll_visible()
            except Exception:
                pass  # Widget not mounted

    def _remove_thinking(self) -> None:
        """Remove the thinking indicator."""
        try:
            self.query_one("#qa-thinking", Static).remove()
        except Exception:
            pass

    def _is_mounted_in_dom(self) -> bool:
        """Check if this widget is currently in the live DOM."""
        try:
            self.query_one("#qa-conversation", ScrollableContainer)
            return True
        except Exception:
            return False

    def _render_entry(self, entry: dict[str, Any]) -> None:
        """Render a single Q&A entry into the conversation DOM."""
        self._append_message("[bold green]A:[/bold green]")
        self._append_markdown(entry["answer"])
        docs = entry.get("sources", [])
        meta_parts: list[str] = []
        if docs:
            self._source_ids = [d[0] for d in docs]
            source_parts = [f"#{d[0]} {d[1]}" for d in docs]
            meta_parts.append(f"Sources: {' · '.join(source_parts)}")
        elapsed = entry.get("elapsed")
        if elapsed is not None:
            meta_parts.append(f"{elapsed:.1f}s")
        if meta_parts:
            self._append_message(f"[dim]{' | '.join(meta_parts)}[/dim]")
        self._append_message("[dim]─────────────────────────────────────────[/dim]")

    async def _fetch_and_store(self, question: str) -> None:
        """Fetch context + answer and store in _entries.

        This is a free-standing asyncio task (NOT a Textual worker) so
        it survives widget unmount/remount when switching screens.
        UI updates are best-effort — if we're unmounted, they silently
        fail and on_mount will rebuild from _entries.
        """
        t0 = time.monotonic()
        self._set_thinking("[dim]Searching knowledge base...[/dim]")
        self._update_status("Retrieving context...")

        # Save terminal state on the main thread before background work.
        term_state = _save_terminal_state()

        try:
            docs, context = await asyncio.to_thread(_retrieve_context, question)
            _restore_terminal_state(term_state)

            t_retrieve = time.monotonic() - t0
            src_count = len(docs)
            self._set_thinking(
                f"[dim]Found {src_count} sources ({t_retrieve:.1f}s) — generating answer...[/dim]"
            )
            self._update_status("Generating answer...")

            answer = await asyncio.to_thread(_run_claude, question, context)
            _restore_terminal_state(term_state)

            t_total = time.monotonic() - t0

            # Always store — this is the durable state
            entry: dict[str, Any] = {
                "question": question,
                "answer": answer,
                "sources": docs,
                "elapsed": t_total,
            }
            self._entries.append(entry)

            # Render if we're still in the DOM
            self._remove_thinking()
            if self._is_mounted_in_dom():
                self._render_entry(entry)
                self._update_status(f"Done | {src_count} sources | {t_total:.1f}s")

        except asyncio.CancelledError:
            logger.info("Q&A task cancelled")
            self._remove_thinking()
            return
        except Exception as e:
            logger.error(f"Q&A failed: {e}", exc_info=True)
            self._remove_thinking()
            if self._is_mounted_in_dom():
                self._append_message(f"[bold red]Error:[/bold red] {e}")
                self._update_status(f"Error: {e}")
        finally:
            self._is_asking = False
            self._pending_question = None

    # -- Actions --

    def action_submit_question(self) -> None:
        """Submit the current question (Enter key)."""
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            return
        inp.focus()

    def action_focus_input(self) -> None:
        """Focus the question input."""
        self.query_one("#qa-input", Input).focus()

    def action_clear_history(self) -> None:
        """Clear conversation history."""
        container = self.query_one("#qa-conversation", ScrollableContainer)
        container.remove_children()
        self._entries.clear()
        self._source_ids.clear()
        self._show_welcome()
        self.notify("History cleared", timeout=1)

    def action_save_exchange(self) -> None:
        """Save the most recent Q&A exchange as a document."""
        if not self._entries:
            self.notify("Nothing to save", timeout=2)
            return

        entry = self._entries[-1]
        question = entry["question"]
        answer = entry["answer"]
        docs = entry["sources"]

        content = f"# Q: {question}\n\n{answer}\n"
        if docs:
            content += "\n## Sources\n\n"
            for d in docs:
                content += f"- Document #{d[0]}: {d[1]}\n"

        try:
            from emdx.models.documents import save_document

            doc_id = save_document(
                title=f"Q&A: {question[:60]}",
                content=content,
                tags=["qa", "auto"],
            )
            self.notify(f"Saved as document #{doc_id}", timeout=3)
        except Exception as e:
            logger.error(f"Failed to save Q&A: {e}")
            self.notify(f"Save failed: {e}", severity="error", timeout=3)

    async def action_exit_qa(self) -> None:
        """Cancel current question if asking, otherwise exit Q&A screen."""
        if self._is_asking:
            self._cancel_asking()
            return
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    def on_key(self, event: events.Key) -> None:
        """Block action keys when input is focused (let user type freely)."""
        try:
            search_input = self.query_one("#qa-input", Input)
            if search_input.has_focus:
                pass_through_keys = {"s", "c", "1", "2", "slash"}
                if event.key in pass_through_keys:
                    return
        except Exception:
            pass

    def set_query(self, query: str) -> None:
        """Set the input query programmatically (from command palette)."""
        inp = self.query_one("#qa-input", Input)
        inp.value = query
        inp.focus()

    def save_state(self) -> dict[str, Any]:
        """Save current state for restoration.

        Conversation data lives in self._entries which survives on the
        cached widget instance. on_mount rebuilds the DOM from entries.
        """
        return {
            "entry_count": len(self._entries),
            "is_asking": self._is_asking,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Called after re-mount. DOM is already rebuilt by on_mount."""
        pass
