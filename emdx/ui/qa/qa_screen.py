"""
QA Screen - Conversational Q&A over your knowledge base.

Delegates retrieval and answer generation to QAPresenter, which handles
terminal state save/restore around threaded operations to prevent
Textual's mouse/key handling from breaking.
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
from textual.widgets import Input, Markdown, RichLog, Static

from ..modals import HelpMixin
from .qa_presenter import QAEntry, QAPresenter, QASource, QAStateVM

logger = logging.getLogger(__name__)

_msg_counter = 0

_MD_SYNTAX = re.compile(r"#{1,6}\s+|[*_]{1,3}|`{1,3}|^-{3,}$|^\s*[-*+]\s", re.MULTILINE)


def _strip_md(text: str) -> str:
    """Strip markdown syntax for plain-text display."""
    return _MD_SYNTAX.sub("", text).strip()


def _next_msg_id() -> str:
    global _msg_counter
    _msg_counter += 1
    return f"qa-msg-{_msg_counter}"


class QAScreen(HelpMixin, Widget):
    """
    Conversational Q&A widget over your knowledge base.

    Layout: Input bar | Scrollable conversation | Status bar | Nav bar
    """

    HELP_TITLE = "Q&A"

    BINDINGS = [
        Binding("enter", "submit_question", "Ask", show=True),
        Binding("escape", "exit_qa", "Exit"),
        Binding("tab", "toggle_input_focus", "Input", show=False),
        Binding("shift+tab", "toggle_input_focus", "Input", show=False),
        Binding("slash", "focus_input", "Focus Input"),
        Binding("s", "save_exchange", "Save"),
        Binding("c", "clear_history", "Clear"),
        Binding("question_mark", "show_help", "Help"),
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

    #qa-conversation-panel {
        width: 60%;
        height: 100%;
    }

    #qa-conversation {
        height: 1fr;
        width: 100%;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #qa-source-panel {
        width: 40%;
        height: 100%;
        border-left: solid $primary;
    }

    #qa-source-header {
        height: 1;
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }

    #qa-source-scroll {
        height: 1fr;
        padding: 0;
    }

    .qa-source-item {
        width: 100%;
        margin: 0;
        padding: 1 1;
        border-bottom: solid $surface-darken-1;
    }

    .qa-source-item:hover {
        background: $boost;
    }

    #qa-source-preview-scroll {
        height: 1fr;
        display: none;
    }

    #qa-source-preview {
        padding: 0 1;
    }

    #qa-source-back {
        height: 1;
        background: $surface;
        padding: 0 1;
        display: none;
    }

    #qa-source-back:hover {
        background: $boost;
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

    #qa-stream {
        width: 100%;
        margin: 0;
        padding: 0;
        height: auto;
        max-height: 50%;
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
        self._source_ids: list[int] = []
        # Background task that survives widget unmount/remount
        self._bg_task: asyncio.Task[None] | None = None
        # Buffer for streaming text — accumulate until newline for RichLog
        self._stream_buffer: str = ""
        self._streaming_started: bool = False
        # Track whether source panel is showing a doc preview vs source list
        self._viewing_source: bool = False
        # Last sources for restoring after closing a preview
        self._last_sources: list[QASource] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="qa-input-bar"):
            yield Input(
                placeholder="Ask a question about your knowledge base...",
                id="qa-input",
            )
            yield Static("Q&A", id="qa-mode-label")

        with Horizontal(id="qa-main"):
            with Vertical(id="qa-conversation-panel"):
                yield ScrollableContainer(id="qa-conversation")
            with Vertical(id="qa-source-panel"):
                yield Static("SOURCES", id="qa-source-header")
                yield ScrollableContainer(id="qa-source-scroll")
                with ScrollableContainer(id="qa-source-preview-scroll"):
                    yield Markdown("", id="qa-source-preview")
                yield Static(
                    "[bold]< Back[/bold] to sources",
                    id="qa-source-back",
                )

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
        entries = self._presenter.state.entries
        has_state = bool(entries) or self._presenter.state.is_asking
        logger.info(
            "QAScreen mounted (entries=%d, asking=%s)",
            len(entries),
            self._presenter.state.is_asking,
        )

        if not has_state:
            # First mount — initialize presenter and show welcome
            await self._presenter.initialize()
            self._show_welcome()
            self._update_source_panel([])
        else:
            self._rebuild_conversation()
            # Restore source panel from latest entry
            latest = entries[-1] if entries else None
            self._update_source_panel(latest.sources if latest else [])

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
        """Rebuild conversation DOM from presenter state.

        Called on re-mount after switching screens.  The child widgets
        were destroyed by remove_children() but presenter state survived.
        """
        for entry in self._presenter.state.entries:
            self._append_message(f"\n[bold cyan]Q:[/bold cyan] {entry.question}\n")
            if entry.is_loading:
                self._set_thinking("[dim]Still generating answer...[/dim]")
            else:
                self._render_entry(entry)

    def _update_source_panel(self, sources: list[QASource]) -> None:
        """Update the source panel with the given sources."""
        self._last_sources = list(sources)  # defensive copy
        # If viewing a doc preview, just save sources — don't disturb the preview
        if self._viewing_source:
            logger.info("_update_source_panel: skipping (viewing source)")
            return
        logger.info(
            "_update_source_panel: rendering %d sources",
            len(sources),
        )
        try:
            scroll = self.query_one("#qa-source-scroll", ScrollableContainer)
            header = self.query_one("#qa-source-header", Static)
        except Exception:
            logger.warning("_update_source_panel: widgets not mounted")
            return
        scroll.remove_children()
        if not sources:
            header.update("SOURCES")
            scroll.mount(
                Static(
                    "[dim]No sources yet[/dim]",
                    classes="qa-source-item",
                    id=_next_msg_id(),
                )
            )
            return
        header.update(f"SOURCES ({len(sources)})")
        for i, src in enumerate(sources, 1):
            snippet = _strip_md(src.snippet).replace("[", "\\[") if src.snippet else ""
            # Collapse runs of blank lines but keep single newlines
            snippet = re.sub(r"\n{2,}", "\n", snippet).strip()
            if len(snippet) > 150:
                snippet = snippet[:150].rsplit(" ", 1)[0] + "..."
            title = src.title.replace("[", "\\[")
            label = f"[bold cyan]{i}.[/bold cyan] [bold]#{src.doc_id}[/bold] {title}"
            if snippet:
                label += f"\n[dim]{snippet}[/dim]"
            # Use unique IDs to avoid DuplicateIds when remove_children()
            # hasn't finished before we re-mount (it's async internally).
            item = Static(
                label,
                classes="qa-source-item",
                id=f"qa-src-{src.doc_id}-{_next_msg_id()}",
            )
            scroll.mount(item)
        logger.info(
            "_update_source_panel: mounted %d items into scroll",
            len(sources),
        )

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
        if self._presenter.state.is_asking:
            self.notify("Still waiting — press Escape to cancel", timeout=2)
            return

        if not self._presenter.state.has_claude_cli:
            self.notify("Claude CLI not found", severity="error", timeout=3)
            return

        # Clear input and unfocus
        event.input.value = ""
        self.query_one("#qa-conversation", ScrollableContainer).focus()

        # Show the question immediately
        self._append_message(f"\n[bold cyan]Q:[/bold cyan] {question}\n")
        self._set_thinking("[dim]Searching knowledge base...[/dim]")

        # Launch as a free-standing asyncio task so it survives widget
        # unmount/remount (run_worker gets cancelled on unmount).
        self._bg_task = asyncio.get_event_loop().create_task(self._presenter.ask(question))

    async def _on_state_update(self, state: QAStateVM) -> None:
        """React to presenter state changes."""
        if not self._is_mounted_in_dom():
            return

        self._update_status(state.status_text)

        if state.is_asking and state.entries:
            entry = state.entries[-1]
            if entry.is_loading:
                src_count = len(entry.sources)
                if src_count > 0 and not self._streaming_started:
                    # Replace thinking indicator with streaming widgets
                    self._remove_thinking()
                    self._start_streaming()
                    self._update_source_panel(entry.sources)

        # Entry just finished
        if not state.is_asking and state.entries:
            latest = state.entries[-1]
            if not latest.is_loading:
                self._stop_streaming()
                self._render_entry(latest)
                self._update_source_panel(latest.sources)

    def _start_streaming(self) -> None:
        """Mount the streaming RichLog widget for live answer display."""
        try:
            container = self.query_one("#qa-conversation", ScrollableContainer)
            label = Static("[bold green]A:[/bold green]", classes="qa-message", id=_next_msg_id())
            container.mount(label)
            stream_log = RichLog(id="qa-stream", wrap=True, markup=True)
            container.mount(stream_log)
            stream_log.scroll_visible()
            self._streaming_started = True
            self._stream_buffer = ""
        except Exception:
            pass  # Widget not mounted

    def _stop_streaming(self) -> None:
        """Remove the streaming RichLog and flush any remaining buffer."""
        # Flush remaining buffer
        if self._stream_buffer:
            try:
                stream_log = self.query_one("#qa-stream", RichLog)
                stream_log.write(self._stream_buffer)
            except Exception:
                pass
            self._stream_buffer = ""
        # Remove the streaming widget
        try:
            self.query_one("#qa-stream", RichLog).remove()
        except Exception:
            pass
        self._streaming_started = False

    async def _on_chunk(self, chunk: str) -> None:
        """Handle streaming answer chunk — write complete lines to RichLog."""
        if not self._is_mounted_in_dom():
            return

        self._stream_buffer += chunk
        # Write complete lines to RichLog, keep partial line in buffer
        while "\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split("\n", 1)
            try:
                stream_log = self.query_one("#qa-stream", RichLog)
                stream_log.write(line)
                stream_log.scroll_visible()
            except Exception:
                pass

    def _cancel_asking(self) -> None:
        """Cancel the current Q&A operation and reset state."""
        self._presenter.cancel()
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        self._remove_thinking()
        self._stop_streaming()
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

    def _render_entry(self, entry: QAEntry) -> None:
        """Render a single Q&A entry into the conversation DOM."""
        self._append_message("[bold green]A:[/bold green]")
        self._append_markdown(entry.answer)
        meta_parts: list[str] = []
        if entry.sources:
            self._source_ids = [s.doc_id for s in entry.sources]
            source_parts = [f"#{s.doc_id} {s.title}" for s in entry.sources]
            meta_parts.append(f"Sources: {' · '.join(source_parts)}")
        if entry.elapsed_ms:
            elapsed_s = entry.elapsed_ms / 1000
            meta_parts.append(f"{elapsed_s:.1f}s")
        if meta_parts:
            self._append_message(f"[dim]{' | '.join(meta_parts)}[/dim]")
        self._append_message("[dim]─────────────────────────────────────────[/dim]")

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
        """Toggle focus between input and conversation."""
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            self.query_one("#qa-conversation", ScrollableContainer).focus()
        else:
            inp.focus()

    def action_clear_history(self) -> None:
        """Clear conversation history."""
        container = self.query_one("#qa-conversation", ScrollableContainer)
        container.remove_children()
        self._presenter.clear_history()
        self._source_ids.clear()
        self._update_source_panel([])
        self._show_welcome()
        self.notify("History cleared", timeout=1)

    def action_save_exchange(self) -> None:
        """Save the most recent Q&A exchange as a document."""
        entries = self._presenter.state.entries
        if not entries:
            self.notify("Nothing to save", timeout=2)
            return

        entry = entries[-1]

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
            )
            self.notify(f"Saved as document #{doc_id}", timeout=3)
        except Exception as e:
            logger.error(f"Failed to save Q&A: {e}")
            self.notify(f"Save failed: {e}", severity="error", timeout=3)

    async def action_exit_qa(self) -> None:
        """Cancel current question if asking, close source preview, or exit."""
        if self._presenter.state.is_asking:
            self._cancel_asking()
            return
        if self._viewing_source:
            self._close_source_preview()
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

    def on_click(self, event: events.Click) -> None:
        """Handle clicks on source items or back button."""
        widget = event.widget
        if not isinstance(widget, Static):
            return

        # Back button — return to source list
        if widget.id == "qa-source-back":
            logger.info("Back button clicked")
            self._close_source_preview()
            return

        # Source item — show inline preview
        if "qa-source-item" not in widget.classes:
            return
        widget_id = widget.id or ""
        if not widget_id.startswith("qa-src-"):
            return
        try:
            # ID format: qa-src-{doc_id}-qa-msg-{n}
            rest = widget_id.removeprefix("qa-src-")
            doc_id_str = rest.split("-qa-msg-")[0]
            doc_id = int(doc_id_str)
        except (ValueError, IndexError):
            return
        logger.info("Source item clicked: #%d", doc_id)
        self._show_source_preview(doc_id)

    def _show_source_preview(self, doc_id: int) -> None:
        """Load and render a document in the source panel."""
        from emdx.database import db

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, content FROM documents WHERE id = ? AND is_deleted = 0",
                (doc_id,),
            )
            row = cursor.fetchone()

        if not row:
            logger.warning("Source preview: doc #%d not found", doc_id)
            return

        title, content = row[0], row[1]
        logger.info(
            "Showing source preview: #%d %s (%d chars)",
            doc_id,
            title,
            len(content),
        )

        # Build markdown content
        content_stripped = content.lstrip()
        has_title_header = content_stripped.startswith(f"# {title}") or content_stripped.startswith(
            "# "
        )
        if has_title_header:
            render_content = content
        else:
            render_content = f"# {title}\n\n{content}"
        if len(render_content) > 50000:
            render_content = render_content[:50000] + "\n\n[dim]... (truncated)[/dim]"

        # Swap containers: hide source list, show preview
        self.query_one("#qa-source-scroll", ScrollableContainer).display = False
        self.query_one("#qa-source-preview-scroll", ScrollableContainer).display = True
        self.query_one("#qa-source-back", Static).display = True
        self.query_one("#qa-source-header", Static).update(f"#{doc_id} {title}")

        # Update the Markdown widget content
        preview = self.query_one("#qa-source-preview", Markdown)
        preview.update(render_content)
        self._viewing_source = True

    def _close_source_preview(self) -> None:
        """Return from document preview to source list."""
        saved = self._last_sources
        logger.info(
            "Closing source preview, _last_sources has %d items: %s",
            len(saved),
            [f"#{s.doc_id} {s.title}" for s in saved],
        )
        # Swap containers: show source list, hide preview
        self.query_one("#qa-source-preview-scroll", ScrollableContainer).display = False
        self.query_one("#qa-source-scroll", ScrollableContainer).display = True
        self.query_one("#qa-source-back", Static).display = False
        self._viewing_source = False

        # Rebuild source list from saved state
        self._update_source_panel(saved)

    def set_query(self, query: str) -> None:
        """Set the input query programmatically (from command palette)."""
        inp = self.query_one("#qa-input", Input)
        inp.value = query
        inp.focus()

    def save_state(self) -> dict[str, Any]:
        """Save current state for restoration.

        Conversation data lives in the presenter which survives on the
        cached widget instance. on_mount rebuilds the DOM from presenter state.
        """
        return {
            "entry_count": len(self._presenter.state.entries),
            "is_asking": self._presenter.state.is_asking,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Called after re-mount. DOM is already rebuilt by on_mount."""
        pass
