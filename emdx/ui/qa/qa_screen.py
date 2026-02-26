"""
QA Screen - Conversational Q&A over your knowledge base.

Layout: Input bar | History panel (top) + Answer panel (bottom) | Status | Nav

Uses VerticalScroll(can_focus=False) + Markdown for the answer pane — the same
pattern as Textual's MarkdownViewer and Trogon.  Streaming uses a RichLog inside
the same scroll container; completed answers swap to a Markdown widget.
"""

import asyncio
import logging
import re
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import DataTable, Input, Markdown, RichLog, Static

from ..link_helpers import linkify_text
from ..modals import HelpMixin
from .qa_presenter import QAEntry, QAPresenter, QAStateVM

logger = logging.getLogger(__name__)

_DOC_REF_RE = re.compile(r"(?<!\[)#(\d+)\b")


def _linkify_doc_refs(text: str) -> str:
    """Turn ``#N`` doc references into clickable markdown links."""
    return _DOC_REF_RE.sub(r"[#\1](emdx://doc/\1)", text)


class _ScrollFence(Vertical):
    """Vertical container that stops mouse scroll events from leaking out.

    Without this, when a child scroll container reaches its boundary the
    unhandled event bubbles up and can reach sibling panels.
    """

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()


class _AnswerScroll(VerticalScroll, can_focus=False):
    """Non-focusable scrollable container for the answer pane.

    Follows the MarkdownViewer pattern: VerticalScroll with can_focus=False.
    Mouse wheel scrolling works because VerticalScroll has overflow-y: auto
    and is_scrollable=True (it has child nodes).
    """


def _truncate(text: str, max_len: int = 35) -> str:
    """Truncate text for history panel display."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _format_timestamp(entry: QAEntry) -> str:
    """Format entry timestamp as compact time string."""
    return entry.timestamp.strftime("%H:%M")


def _format_elapsed(entry: QAEntry) -> str:
    """Format elapsed time as a compact string."""
    if entry.is_loading:
        return "\u2026"
    if not entry.elapsed_ms:
        return "\u2014"
    secs = entry.elapsed_ms / 1000
    if secs < 60:
        return f"{secs:.1f}s"
    return f"{secs / 60:.1f}m"


def _format_method(entry: QAEntry) -> str:
    """Format retrieval method as a short label."""
    if entry.is_loading:
        return "\u2026"
    m = entry.method.lower()
    if m == "semantic":
        return "sem"
    if m == "keyword":
        return "kw"
    if m == "hybrid":
        return "hyb"
    return m or "\u2014"


class QAScreen(HelpMixin, Widget):
    """
    Conversational Q&A widget over your knowledge base.

    Layout: Input bar | History (top) + Answer (bottom) | Status bar | Nav bar
    """

    HELP_TITLE = "Q&A"

    BINDINGS = [
        Binding("enter", "submit_question", "Ask", show=True),
        Binding("escape", "exit_qa", "Exit"),
        Binding("tab", "toggle_input_focus", "Input", show=False),
        Binding("shift+tab", "toggle_input_focus", "Input", show=False),
        Binding("slash", "focus_input", "Focus Input"),
        Binding("j", "history_down", "Next", show=False),
        Binding("k", "history_up", "Prev", show=False),
        Binding("s", "save_exchange", "Save"),
        Binding("c", "clear_history", "Clear"),
        Binding("question_mark", "show_help", "Help"),
        Binding("z", "toggle_zoom", "Zoom", show=False),
    ]

    DEFAULT_CSS = """
    QAScreen {
        layout: vertical;
        height: 100%;
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

    #qa-main {
        height: 1fr;
    }

    #qa-history-panel {
        height: 30%;
        width: 100%;
    }

    #qa-history-panel.zoom-hidden {
        display: none;
    }

    #qa-history-header {
        height: 1;
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }

    #qa-history-table {
        height: 1fr;
    }

    #qa-answer-panel {
        height: 70%;
        width: 100%;
        border-top: solid $primary;
    }

    #qa-answer-panel.zoom-full {
        height: 100%;
        border-top: none;
    }

    #qa-answer-header {
        height: 1;
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }

    #qa-answer-scroll {
        height: 1fr;
        padding: 0 1;
    }

    #qa-answer-md {
        height: auto;
        margin: 0 0;
    }

    #qa-answer-md MarkdownH3 {
        margin: 1 0 0 0;
        padding: 0 1;
        color: $text;
    }

    #qa-answer-md MarkdownHorizontalRule {
        margin: 0;
        color: $primary-darken-2;
    }

    #qa-answer-stream {
        height: auto;
        display: none;
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
        self._presenter = QAPresenter(
            on_state_update=self._on_state_update,
            on_answer_chunk=self._on_chunk,
        )
        self._bg_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._stream_buffer: str = ""
        self._row_key_to_entry_index: dict[str, int] = {}
        self._selected_index: int | None = None
        self._streaming_index: int | None = None
        self._rebuilding_table = False
        self._zoomed: bool = False
        self._is_streaming_visible = False

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal

        with Horizontal(id="qa-input-bar"):
            yield Input(
                placeholder="Ask a question about your knowledge base...",
                id="qa-input",
            )
            yield Static("Q&A", id="qa-mode-label")

        with Vertical(id="qa-main"):
            with _ScrollFence(id="qa-history-panel"):
                yield Static("HISTORY", id="qa-history-header")
                yield DataTable(
                    id="qa-history-table",
                    cursor_type="row",
                    show_header=True,
                    zebra_stripes=True,
                )
            with _ScrollFence(id="qa-answer-panel"):
                yield Static("ANSWER", id="qa-answer-header")
                with _AnswerScroll(id="qa-answer-scroll"):
                    yield Markdown("", id="qa-answer-md", open_links=False)
                    yield RichLog(
                        id="qa-answer-stream",
                        highlight=True,
                        markup=True,
                        wrap=True,
                        auto_scroll=True,
                    )

        yield Static("Ready | Type a question and press Enter", id="qa-status")
        yield Static(
            "[dim]1[/dim] Docs | [dim]2[/dim] Tasks | [bold]3[/bold] Q&A | "
            "[dim]/[/dim] type | [dim]j/k[/dim] history | "
            "[dim]Enter[/dim] ask | [dim]s[/dim] save | [dim]c[/dim] clear | "
            "[dim]z[/dim] zoom",
            id="qa-nav",
        )

    # -- Lifecycle --

    async def on_mount(self) -> None:
        if not self._presenter.state.entries and not self._presenter.state.is_asking:
            self._presenter.initialize_sync()

        entries = self._presenter.state.entries
        logger.info("QAScreen mounted (entries=%d, asking=%s)", len(entries), entries != [])

        table = self.query_one("#qa-history-table", DataTable)
        if not table.columns:
            table.add_column("", key="status", width=2)
            table.add_column("Question", key="question")
            table.add_column("Time", key="time", width=5)
            table.add_column("Elapsed", key="elapsed", width=6)
            table.add_column("Src", key="sources", width=3)
            table.add_column("Mode", key="method", width=4)

        if entries:
            self._rebuild_history_table()
            self._selected_index = None
            self._show_welcome()
        else:
            self._show_welcome()

        if not self._initialized:
            self._update_status("Loading embeddings...")
            asyncio.get_event_loop().create_task(self._preload_embeddings())

        table.focus()

    async def _preload_embeddings(self) -> None:
        await self._presenter.preload_embeddings()
        self._initialized = True
        self._update_status(self._presenter.state.status_text)

    # -- History panel --

    def _rebuild_history_table(self) -> None:
        self._rebuilding_table = True
        try:
            table = self.query_one("#qa-history-table", DataTable)
            table.clear()
            self._row_key_to_entry_index.clear()

            entries = self._presenter.state.entries
            for i, entry in enumerate(entries):
                icon = "\u2026" if entry.is_loading else "\u2714"
                question = _truncate(entry.question)
                row_key = table.add_row(
                    icon,
                    question,
                    _format_timestamp(entry),
                    _format_elapsed(entry),
                    str(len(entry.sources)) if entry.sources else "\u2014",
                    _format_method(entry),
                    key=f"entry-{i}",
                )
                self._row_key_to_entry_index[str(row_key)] = i

            header = self.query_one("#qa-history-header", Static)
            count = len(entries)
            header.update(f"HISTORY ({count})" if count else "HISTORY")

            if entries and self._selected_index is not None:
                target = min(self._selected_index, len(entries) - 1)
                try:
                    table.move_cursor(row=target)
                except Exception:
                    logger.warning("Could not move cursor to row %d", target)
        finally:
            self._rebuilding_table = False

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._rebuilding_table:
            return
        if event.row_key is None:
            return
        entry_index = self._row_key_to_entry_index.get(str(event.row_key))
        if entry_index is None:
            return

        entries = self._presenter.state.entries
        if entry_index >= len(entries):
            return

        self._selected_index = entry_index
        entry = entries[entry_index]

        if entry.is_loading:
            self._show_streaming(entry)
        else:
            self._render_answer(entry)

    # -- Answer panel rendering --

    def _show_markdown(self) -> None:
        """Show Markdown widget, hide RichLog."""
        if not self._is_streaming_visible:
            return
        self._is_streaming_visible = False
        try:
            self.query_one("#qa-answer-md", Markdown).styles.display = "block"
            self.query_one("#qa-answer-stream", RichLog).styles.display = "none"
        except Exception:
            logger.warning("Could not toggle answer widgets", exc_info=True)

    def _show_stream(self) -> None:
        """Show RichLog for streaming, hide Markdown."""
        if self._is_streaming_visible:
            return
        self._is_streaming_visible = True
        try:
            self.query_one("#qa-answer-md", Markdown).styles.display = "none"
            self.query_one("#qa-answer-stream", RichLog).styles.display = "block"
        except Exception:
            logger.warning("Could not toggle answer widgets", exc_info=True)

    def _render_answer(self, entry: QAEntry) -> None:
        """Render a completed entry into the Markdown widget."""
        self._show_markdown()

        parts: list[str] = []

        # Question section
        parts.append(f"### \u2753 Question\n\n{entry.question}\n")

        # Sources section
        if entry.sources:
            source_lines = "\n".join(f"- **#{s.doc_id}** {s.title}" for s in entry.sources)
            parts.append(f"### \U0001f4da Sources ({len(entry.sources)})\n\n{source_lines}\n")

        parts.append("---\n")

        # Answer section
        parts.append(f"### \u2705 Answer\n\n{entry.answer.rstrip()}\n")

        # Footer with metadata badges
        footer_parts: list[str] = []
        if entry.elapsed_ms:
            secs = entry.elapsed_ms / 1000
            footer_parts.append(f"\u23f1 **{secs:.1f}s**")
        if entry.method:
            method_label = {"semantic": "Semantic", "keyword": "Keyword", "hybrid": "Hybrid"}
            label = method_label.get(entry.method.lower(), entry.method)
            footer_parts.append(f"\U0001f50d **{label}**")
        if entry.sources:
            footer_parts.append(f"\U0001f4c4 **{len(entry.sources)} sources**")
        if entry.error:
            footer_parts.append(f"\u26a0\ufe0f *{entry.error}*")

        if footer_parts:
            parts.append("\n---\n")
            parts.append(" \u00b7 ".join(footer_parts))

        content = _linkify_doc_refs("\n".join(parts))
        try:
            md_widget = self.query_one("#qa-answer-md", Markdown)
            md_widget.update(content)
        except Exception:
            logger.warning("Failed to update markdown", exc_info=True)

        # Scroll to top for new content
        try:
            self.query_one("#qa-answer-scroll", _AnswerScroll).scroll_home(animate=False)
        except Exception:
            pass

        self.query_one("#qa-answer-header", Static).update("ANSWER")

    def _show_welcome(self) -> None:
        welcome = (
            "# Welcome to Q&A\n\n"
            "Ask questions about your knowledge base in natural language.\n"
            "Answers are generated from your documents using Claude.\n\n"
            "**Examples:**\n\n"
            "- *What's our caching strategy?*\n"
            "- *How did we fix the auth bug?*\n"
            "- *Summarize the architecture decisions*\n\n"
            "*j/k to navigate history | / to type | s to save*"
        )
        self._show_markdown()
        try:
            self.query_one("#qa-answer-md", Markdown).update(welcome)
        except Exception:
            pass
        self.query_one("#qa-answer-header", Static).update("ANSWER")

    def _show_streaming(self, entry: QAEntry) -> None:
        """Show streaming state for an in-progress entry."""
        self._show_stream()
        try:
            log = self.query_one("#qa-answer-stream", RichLog)
            log.clear()
            log.write(f"[bold cyan]Q:[/bold cyan] {entry.question}")
            log.write("")

            if entry.sources:
                for s in entry.sources:
                    log.write(f"  [dim]#{s.doc_id} {s.title}[/dim]")
                log.write("")

            log.write("[bold green]A:[/bold green]")
        except Exception:
            pass
        self._stream_buffer = ""
        self.query_one("#qa-answer-header", Static).update("ANSWER (streaming...)")

    # -- State update / streaming --

    def _update_status(self, text: str) -> None:
        try:
            self.query_one("#qa-status", Static).update(text)
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "qa-input":
            return
        question = event.value.strip()
        if not question:
            return
        if not self._initialized:
            self.notify("Still loading — please wait", timeout=2)
            return
        if self._presenter.state.is_asking:
            self.notify("Still waiting — press Escape to cancel", timeout=2)
            return
        if not self._presenter.state.has_claude_cli:
            self.notify("Claude CLI not found", severity="error", timeout=3)
            return

        event.input.value = ""

        self._show_stream()
        try:
            log = self.query_one("#qa-answer-stream", RichLog)
            log.clear()
            log.write(f"[bold cyan]Q:[/bold cyan] {question}")
            log.write("")
            log.write("[dim]Searching knowledge base...[/dim]")
        except Exception:
            pass

        self._bg_task = asyncio.get_event_loop().create_task(self._presenter.ask(question))

    async def _on_state_update(self, state: QAStateVM) -> None:
        if not self._is_mounted_in_dom():
            return

        self._update_status(state.status_text)

        if state.is_asking and state.entries:
            entry = state.entries[-1]
            entry_index = len(state.entries) - 1

            if entry.is_loading:
                if len(entry.sources) > 0 and self._streaming_index is None:
                    self._streaming_index = entry_index
                    self._selected_index = entry_index
                    self._show_streaming(entry)
                    self._rebuild_history_table()
                elif self._streaming_index is None:
                    self._selected_index = entry_index
                    self._rebuild_history_table()

        if not state.is_asking and state.entries:
            latest = state.entries[-1]
            if not latest.is_loading:
                if self._stream_buffer:
                    try:
                        buf = self._stream_buffer
                        self.query_one("#qa-answer-stream", RichLog).write(
                            linkify_text(buf) if "http" in buf else buf
                        )
                    except Exception:
                        pass
                    self._stream_buffer = ""

                self._streaming_index = None
                self._selected_index = len(state.entries) - 1
                self._render_answer(latest)
                self._rebuild_history_table()

    async def _on_chunk(self, chunk: str) -> None:
        if not self._is_mounted_in_dom():
            return
        if self._selected_index != self._streaming_index:
            return

        self._stream_buffer += chunk
        while "\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split("\n", 1)
            try:
                log = self.query_one("#qa-answer-stream", RichLog)
                log.write(linkify_text(line) if "http" in line else line)
            except Exception:
                pass

    def _cancel_asking(self) -> None:
        self._presenter.cancel()
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        self._streaming_index = None
        self._stream_buffer = ""

        try:
            self.query_one("#qa-answer-stream", RichLog).write(
                "\n[dim italic]Cancelled[/dim italic]"
            )
        except Exception:
            pass

        self._rebuild_history_table()
        self._update_status("Cancelled | Ready")

    def _is_mounted_in_dom(self) -> bool:
        try:
            self.query_one("#qa-answer-md", Markdown)
            return True
        except Exception:
            return False

    # -- Actions --

    def action_submit_question(self) -> None:
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            return
        inp.focus()

    def action_focus_input(self) -> None:
        self.query_one("#qa-input", Input).focus()

    def action_toggle_input_focus(self) -> None:
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            self.query_one("#qa-history-table", DataTable).focus()
        else:
            inp.focus()

    def action_history_down(self) -> None:
        self.query_one("#qa-history-table", DataTable).action_cursor_down()

    def action_history_up(self) -> None:
        self.query_one("#qa-history-table", DataTable).action_cursor_up()

    def action_toggle_zoom(self) -> None:
        """Toggle zoom: hide history panel, expand answer to full height."""
        history_panel = self.query_one("#qa-history-panel")
        answer_panel = self.query_one("#qa-answer-panel")
        self._zoomed = not self._zoomed
        if self._zoomed:
            history_panel.add_class("zoom-hidden")
            answer_panel.add_class("zoom-full")
            self.query_one("#qa-answer-panel").focus()
        else:
            history_panel.remove_class("zoom-hidden")
            answer_panel.remove_class("zoom-full")
            self.query_one("#qa-history-table", DataTable).focus()

    def action_clear_history(self) -> None:
        self._presenter.clear_history()
        self._row_key_to_entry_index.clear()
        self._selected_index = None
        self._streaming_index = None
        self._stream_buffer = ""
        self.query_one("#qa-history-table", DataTable).clear()
        self.query_one("#qa-history-header", Static).update("HISTORY")
        self._show_welcome()
        self.notify("History cleared", timeout=1)

    def action_save_exchange(self) -> None:
        entries = self._presenter.state.entries
        if not entries:
            self.notify("Nothing to save", timeout=2)
            return

        if self._selected_index is not None and self._selected_index < len(entries):
            entry = entries[self._selected_index]
        else:
            entry = entries[-1]

        if entry.is_loading or not entry.answer:
            self.notify("Answer not ready yet", timeout=2)
            return

        if entry.saved_doc_id is not None:
            self.notify(f"Already saved as #{entry.saved_doc_id}", timeout=2)
            return

        content = f"# Q: {entry.question}\n\n{entry.answer}\n"
        if entry.sources:
            content += "\n## Sources\n\n"
            for s in entry.sources:
                content += f"- Document #{s.doc_id}: {s.title}\n"

        try:
            from emdx.models.documents import save_document

            doc_id = save_document(
                title=f"Q&A: {entry.question[:60]}",
                content=content,
                tags=["qa", "auto"],
                doc_type="qa",
            )
            entry.saved_doc_id = doc_id
            self.notify(f"Saved as document #{doc_id}", timeout=3)
        except Exception as e:
            logger.error(f"Failed to save Q&A: {e}")
            self.notify(f"Save failed: {e}", severity="error", timeout=3)

    async def action_exit_qa(self) -> None:
        if self._presenter.state.is_asking:
            self._cancel_asking()
            return
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    def on_key(self, event: events.Key) -> None:
        try:
            search_input = self.query_one("#qa-input", Input)
            if search_input.has_focus:
                pass_through_keys = {"s", "c", "j", "k", "z", "1", "2", "slash"}
                if event.key in pass_through_keys:
                    return
        except Exception:
            pass

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Intercept emdx:// links to open document previews."""
        if event.href.startswith("emdx://doc/"):
            event.prevent_default()
            try:
                doc_id = int(event.href.removeprefix("emdx://doc/"))
                self._open_doc_preview(doc_id)
            except ValueError:
                pass

    def _open_doc_preview(self, doc_id: int) -> None:
        from ..modals import DocumentPreviewScreen

        self.app.push_screen(DocumentPreviewScreen(doc_id))

    def set_query(self, query: str) -> None:
        inp = self.query_one("#qa-input", Input)
        inp.value = query
        inp.focus()

    def save_state(self) -> dict[str, Any]:
        return {
            "entry_count": len(self._presenter.state.entries),
            "is_asking": self._presenter.state.is_asking,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        pass
