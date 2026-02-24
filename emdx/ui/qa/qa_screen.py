"""
QA Screen - Conversational Q&A over your knowledge base.

Layout: Input bar | History panel (left) + Answer panel (right) | Status | Nav

History panel shows a DataTable of past questions. Answer panel shows the
selected entry's full answer with inline sources. Clicking a #N doc ref
opens the DocumentPreviewScreen fullscreen modal.
"""

import asyncio
import logging
import re
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Input, Markdown, RichLog, Static

from ..modals import HelpMixin
from .qa_presenter import QAEntry, QAPresenter, QAStateVM

logger = logging.getLogger(__name__)

# Match #N doc references in answer text, but not inside markdown headings or code
_DOC_REF = re.compile(r"(?<![#\w])#(\d+)\b")


def _linkify_doc_refs(text: str, source_ids: set[int] | None = None) -> str:
    """Convert #N doc references into clickable markdown links.

    If source_ids is provided, only converts references matching those IDs.
    If None, converts all #N patterns.
    """

    def _replace(m: re.Match[str]) -> str:
        doc_id = int(m.group(1))
        if source_ids is not None and doc_id not in source_ids:
            return m.group(0)
        return f"[#{doc_id}](emdx://doc/{doc_id})"

    return _DOC_REF.sub(_replace, text)


def _truncate(text: str, max_len: int = 35) -> str:
    """Truncate text for history panel display."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


class QAScreen(HelpMixin, Widget):
    """
    Conversational Q&A widget over your knowledge base.

    Layout: Input bar | History (left) + Answer (right) | Status bar | Nav bar
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

    #qa-answer-stream-scroll {
        height: 1fr;
        padding: 0 1;
    }

    #qa-answer-md-scroll {
        height: 1fr;
        padding: 0 1;
        display: none;
    }

    #qa-answer-log {
        width: 100%;
    }

    #qa-answer-md {
        width: 100%;
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
        # Background task that survives widget unmount/remount
        self._bg_task: asyncio.Task[None] | None = None
        # Set when presenter is initialized (embeddings preloaded)
        self._initialized = False
        # Buffer for streaming text — accumulate until newline for RichLog
        self._stream_buffer: str = ""
        # Maps DataTable row key string to presenter entries index
        self._row_key_to_entry_index: dict[str, int] = {}
        # Currently selected entry index (in presenter.state.entries)
        self._selected_index: int | None = None
        # Entry index currently being streamed
        self._streaming_index: int | None = None
        self._zoomed: bool = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="qa-input-bar"):
            yield Input(
                placeholder="Ask a question about your knowledge base...",
                id="qa-input",
            )
            yield Static("Q&A", id="qa-mode-label")

        with Vertical(id="qa-main"):
            with Vertical(id="qa-history-panel"):
                yield Static("HISTORY", id="qa-history-header")
                yield DataTable(
                    id="qa-history-table",
                    cursor_type="row",
                    show_header=False,
                    zebra_stripes=True,
                )
            with Vertical(id="qa-answer-panel"):
                with ScrollableContainer(id="qa-answer-stream-scroll"):
                    yield RichLog(id="qa-answer-log", wrap=True, markup=True)
                with ScrollableContainer(id="qa-answer-md-scroll"):
                    yield Markdown("", id="qa-answer-md", open_links=False)

        yield Static("Ready | Type a question and press Enter", id="qa-status")
        yield Static(
            "[dim]1[/dim] Docs | [dim]2[/dim] Tasks | [bold]3[/bold] Q&A | "
            "[dim]/[/dim] type | [dim]j/k[/dim] history | "
            "[dim]Enter[/dim] ask | [dim]s[/dim] save | [dim]c[/dim] clear | "
            "[dim]z[/dim] zoom",
            id="qa-nav",
        )

    async def on_mount(self) -> None:
        """Initialize or restore the Q&A screen."""
        # Fast sync init — loads history from DB, checks CLI. No heavy imports.
        if not self._presenter.state.entries and not self._presenter.state.is_asking:
            self._presenter.initialize_sync()

        entries = self._presenter.state.entries
        logger.info(
            "QAScreen mounted (entries=%d, asking=%s)",
            len(entries),
            self._presenter.state.is_asking,
        )

        # Set up the history table column
        table = self.query_one("#qa-history-table", DataTable)
        if not table.columns:
            table.add_column("question", key="question")

        if entries:
            self._restore_existing_state(entries)
        else:
            self._show_welcome()

        # Preload sentence-transformers in the background (~2-3s).
        # Questions are blocked until this finishes.
        if not self._initialized:
            self._update_status("Loading embeddings...")
            asyncio.get_event_loop().create_task(self._preload_embeddings())

        # Focus the history table so j/k work immediately
        table.focus()

    async def _preload_embeddings(self) -> None:
        """Preload sentence-transformers, then mark ready."""
        await self._presenter.preload_embeddings()
        self._initialized = True
        self._update_status(self._presenter.state.status_text)

    def _restore_existing_state(self, entries: list[QAEntry]) -> None:
        """Populate the UI from existing presenter state."""
        self._rebuild_history_table()
        self._selected_index = len(entries) - 1
        latest = entries[-1]
        if latest.is_loading:
            self._streaming_index = self._selected_index
            self._show_stream_scroll()
        else:
            self._render_answer_panel(latest)

    # -- History panel --

    def _rebuild_history_table(self) -> None:
        """Rebuild the history DataTable from presenter state."""
        table = self.query_one("#qa-history-table", DataTable)
        table.clear()
        self._row_key_to_entry_index.clear()

        entries = self._presenter.state.entries
        for i, entry in enumerate(entries):
            icon = "\u2026" if entry.is_loading else "\u2714"
            label = f"{icon} {_truncate(entry.question)}"
            row_key = table.add_row(label, key=f"entry-{i}")
            self._row_key_to_entry_index[str(row_key)] = i

        # Update header
        header = self.query_one("#qa-history-header", Static)
        count = len(entries)
        header.update(f"HISTORY ({count})" if count else "HISTORY")

        # Move cursor to selected or last row
        if entries:
            target = self._selected_index if self._selected_index is not None else len(entries) - 1
            try:
                table.move_cursor(row=target)
            except Exception:
                logger.warning("Could not move cursor to row %d", target)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """When a history row is highlighted, show its answer."""
        if event.row_key is None:
            return
        key_str = str(event.row_key)
        entry_index = self._row_key_to_entry_index.get(key_str)
        if entry_index is None:
            return

        # Don't re-render if selecting the currently streaming entry
        if entry_index == self._streaming_index:
            self._selected_index = entry_index
            self._show_stream_scroll()
            return

        entries = self._presenter.state.entries
        if entry_index >= len(entries):
            return

        entry = entries[entry_index]
        self._selected_index = entry_index

        if entry.is_loading:
            # Still loading — show stream scroll
            self._show_stream_scroll()
        else:
            self._render_answer_panel(entry)

    # -- Answer panel rendering --

    def _show_stream_scroll(self) -> None:
        """Show the streaming RichLog, hide the Markdown scroll."""
        self.query_one("#qa-answer-stream-scroll").display = True
        self.query_one("#qa-answer-md-scroll").display = False

    def _show_md_scroll(self) -> None:
        """Show the Markdown scroll, hide the streaming RichLog."""
        self.query_one("#qa-answer-stream-scroll").display = False
        self.query_one("#qa-answer-md-scroll").display = True

    def _render_answer_panel(self, entry: QAEntry) -> None:
        """Render a completed entry in the answer panel Markdown widget."""
        logger.info(
            "_render_answer_panel: sources=%d, answer_len=%d, elapsed=%dms",
            len(entry.sources),
            len(entry.answer),
            entry.elapsed_ms,
        )
        self._show_md_scroll()

        parts: list[str] = []

        # Question
        parts.append(f"**Q:** {entry.question}\n")

        # Sources block at top — bulleted list for clickability
        if entry.sources:
            source_lines = "\n".join(
                f"- [#{s.doc_id} {s.title}](emdx://doc/{s.doc_id})" for s in entry.sources
            )
            parts.append(f"**Sources:**\n\n{source_lines}\n")

        parts.append("***\n")

        # Answer with linkified doc refs
        answer_text = _linkify_doc_refs(entry.answer).rstrip()
        parts.append(answer_text)

        # Footer with clickable source links
        has_footer = entry.sources or entry.elapsed_ms or entry.error
        if has_footer:
            parts.append("\n***\n")
        if entry.sources:
            elapsed = f" *({entry.elapsed_ms / 1000:.1f}s)*" if entry.elapsed_ms else ""
            footer_source_lines = "\n".join(
                f"- [#{s.doc_id} {s.title}](emdx://doc/{s.doc_id})" for s in entry.sources
            )
            parts.append(f"**Sources:**{elapsed}\n\n{footer_source_lines}")
        elif entry.elapsed_ms:
            parts.append(f"*{entry.elapsed_ms / 1000:.1f}s*")
        if entry.error:
            parts.append(f"\n*Error: {entry.error}*")

        content = "\n".join(parts)
        md = self.query_one("#qa-answer-md", Markdown)
        md.update(content)

    def _show_welcome(self) -> None:
        """Show welcome message in the RichLog."""
        self._show_stream_scroll()
        log = self.query_one("#qa-answer-log", RichLog)
        log.clear()
        log.write("[bold]Welcome to Q&A[/bold]")
        log.write("")
        log.write("Ask questions about your knowledge base in natural language.")
        log.write("Answers are generated from your documents using Claude.")
        log.write("")
        log.write("[dim]Examples:[/dim]")
        log.write("  [italic]What's our caching strategy?[/italic]")
        log.write("  [italic]How did we fix the auth bug?[/italic]")
        log.write("  [italic]Summarize the architecture decisions[/italic]")
        log.write("")
        log.write("[dim]Tip: Reference docs directly with #42 syntax[/dim]")
        log.write("[dim]j/k to navigate history[/dim]")

    def _start_streaming_in_answer_panel(self, entry: QAEntry) -> None:
        """Set up the answer panel for streaming an in-progress entry."""
        self._show_stream_scroll()
        log = self.query_one("#qa-answer-log", RichLog)
        log.clear()
        log.write(f"[bold cyan]Q:[/bold cyan] {entry.question}")
        log.write("")

        if entry.sources:
            for s in entry.sources:
                log.write(f"  [dim]#{s.doc_id} {s.title}[/dim]")
            log.write("")

        log.write("[bold green]A:[/bold green]")
        self._stream_buffer = ""

    # -- State update / streaming --

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
        if not self._initialized:
            self.notify("Still loading — please wait", timeout=2)
            return
        if self._presenter.state.is_asking:
            self.notify("Still waiting — press Escape to cancel", timeout=2)
            return

        if not self._presenter.state.has_claude_cli:
            self.notify("Claude CLI not found", severity="error", timeout=3)
            return

        # Clear input
        event.input.value = ""

        # Show searching state in the RichLog
        self._show_stream_scroll()
        log = self.query_one("#qa-answer-log", RichLog)
        log.clear()
        log.write(f"[bold cyan]Q:[/bold cyan] {question}")
        log.write("")
        log.write("[dim]Searching knowledge base...[/dim]")

        # Launch the ask task
        self._bg_task = asyncio.get_event_loop().create_task(self._presenter.ask(question))

        # Rebuild history after entry is added (next tick)
        # The entry gets created inside presenter.ask(), so we schedule
        # the rebuild to happen after the first state update.

    async def _on_state_update(self, state: QAStateVM) -> None:
        """React to presenter state changes."""
        if not self._is_mounted_in_dom():
            return

        self._update_status(state.status_text)

        if state.is_asking and state.entries:
            entry = state.entries[-1]
            entry_index = len(state.entries) - 1

            if entry.is_loading:
                src_count = len(entry.sources)
                if src_count > 0 and self._streaming_index is None:
                    # Sources arrived — start streaming display
                    self._streaming_index = entry_index
                    self._selected_index = entry_index
                    self._start_streaming_in_answer_panel(entry)
                    self._rebuild_history_table()

                elif self._streaming_index is None:
                    # Entry created but no sources yet — rebuild history
                    self._selected_index = entry_index
                    self._rebuild_history_table()

        # Entry just finished
        if not state.is_asking and state.entries:
            latest = state.entries[-1]
            if not latest.is_loading:
                # Flush remaining stream buffer
                if self._stream_buffer:
                    try:
                        log = self.query_one("#qa-answer-log", RichLog)
                        log.write(self._stream_buffer)
                    except Exception:
                        pass
                    self._stream_buffer = ""

                self._streaming_index = None
                self._selected_index = len(state.entries) - 1
                self._render_answer_panel(latest)
                self._rebuild_history_table()

    async def _on_chunk(self, chunk: str) -> None:
        """Handle streaming answer chunk — write complete lines to RichLog."""
        if not self._is_mounted_in_dom():
            return

        # Only write to RichLog if the user is viewing the streaming entry
        if self._selected_index != self._streaming_index:
            return

        self._stream_buffer += chunk
        while "\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split("\n", 1)
            try:
                log = self.query_one("#qa-answer-log", RichLog)
                log.write(line)
                log.scroll_visible()
            except Exception:
                pass

    def _cancel_asking(self) -> None:
        """Cancel the current Q&A operation and reset state."""
        self._presenter.cancel()
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        self._streaming_index = None
        self._stream_buffer = ""

        # Show cancelled in the RichLog
        try:
            log = self.query_one("#qa-answer-log", RichLog)
            log.write("")
            log.write("[dim italic]Cancelled[/dim italic]")
        except Exception:
            pass

        self._rebuild_history_table()
        self._update_status("Cancelled | Ready")

    def _is_mounted_in_dom(self) -> bool:
        """Check if this widget is currently in the live DOM."""
        try:
            self.query_one("#qa-answer-log", RichLog)
            return True
        except Exception:
            return False

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

    def action_toggle_input_focus(self) -> None:
        """Toggle focus between input and history table."""
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            self.query_one("#qa-history-table", DataTable).focus()
        else:
            inp.focus()

    def action_history_down(self) -> None:
        """Move down in history table."""
        table = self.query_one("#qa-history-table", DataTable)
        table.action_cursor_down()

    def action_history_up(self) -> None:
        """Move up in history table."""
        table = self.query_one("#qa-history-table", DataTable)
        table.action_cursor_up()

    def action_toggle_zoom(self) -> None:
        """Toggle zoom: hide history panel, expand answer to full height."""
        history_panel = self.query_one("#qa-history-panel")
        answer_panel = self.query_one("#qa-answer-panel")
        self._zoomed = not self._zoomed
        if self._zoomed:
            history_panel.add_class("zoom-hidden")
            answer_panel.add_class("zoom-full")
        else:
            history_panel.remove_class("zoom-hidden")
            answer_panel.remove_class("zoom-full")
            self.query_one("#qa-history-table", DataTable).focus()

    def action_clear_history(self) -> None:
        """Clear conversation history."""
        self._presenter.clear_history()
        self._row_key_to_entry_index.clear()
        self._selected_index = None
        self._streaming_index = None
        self._stream_buffer = ""
        table = self.query_one("#qa-history-table", DataTable)
        table.clear()
        self.query_one("#qa-history-header", Static).update("HISTORY")
        self._show_welcome()
        self.notify("History cleared", timeout=1)

    def action_save_exchange(self) -> None:
        """Save the selected Q&A exchange as a document."""
        entries = self._presenter.state.entries
        if not entries:
            self.notify("Nothing to save", timeout=2)
            return

        # Save selected entry, fall back to latest
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
        """Cancel current question if asking, or exit."""
        if self._presenter.state.is_asking:
            self._cancel_asking()
            return
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    def on_key(self, event: events.Key) -> None:
        """Block action keys when input is focused (let user type freely)."""
        try:
            search_input = self.query_one("#qa-input", Input)
            if search_input.has_focus:
                pass_through_keys = {"s", "c", "j", "k", "z", "1", "2", "slash"}
                if event.key in pass_through_keys:
                    return
        except Exception:
            pass

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Handle clicks on doc ref links — open fullscreen preview."""
        event.prevent_default()
        href = event.href
        # emdx://doc/N — open fullscreen document preview
        if href.startswith("emdx://doc/"):
            try:
                doc_id = int(href.removeprefix("emdx://doc/"))
            except ValueError:
                return
            logger.info("Doc ref link clicked: #%d", doc_id)
            self._open_doc_preview(doc_id)
            return
        # Inline #N refs that got linkified — same pattern
        if href.startswith("#") and href[1:].isdigit():
            doc_id = int(href[1:])
            logger.info("Hash ref link clicked: #%d", doc_id)
            self._open_doc_preview(doc_id)
            return
        # External URLs — open in browser
        if href.startswith(("http://", "https://")):
            import webbrowser

            webbrowser.open(href)
            return
        logger.debug("Ignoring link click: %s", href)

    def _open_doc_preview(self, doc_id: int) -> None:
        """Open the fullscreen DocumentPreviewScreen for a doc."""
        from ..modals import DocumentPreviewScreen

        self.app.push_screen(DocumentPreviewScreen(doc_id))

    def set_query(self, query: str) -> None:
        """Set the input query programmatically (from command palette)."""
        inp = self.query_one("#qa-input", Input)
        inp.value = query
        inp.focus()

    def save_state(self) -> dict[str, Any]:
        """Save current state for restoration."""
        return {
            "entry_count": len(self._presenter.state.entries),
            "is_asking": self._presenter.state.is_asking,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Called after re-mount. DOM is already rebuilt by on_mount."""
        pass
