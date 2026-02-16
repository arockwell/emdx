"""
QA Screen - Conversational Q&A over your knowledge base.

Features:
- Ask questions in natural language
- Answers streamed from Claude with source citations
- Clickable sources open document preview
- Save Q&A exchanges to the knowledge base
"""

import asyncio
import logging
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

from ..modals import HelpMixin
from .qa_presenter import QAPresenter, QAStateVM

logger = logging.getLogger(__name__)


class QAScreen(HelpMixin, Widget):
    """
    Conversational Q&A widget over your knowledge base.

    Layout:
    - Input bar at top for questions
    - Scrollable conversation area (RichLog)
    - Status bar showing retrieval method, timing, sources
    - Navigation bar
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
        self.presenter = QAPresenter(
            on_state_update=self._on_state_update,
            on_answer_chunk=self._on_answer_chunk,
        )
        self._current_entry_index: int = -1
        self._source_ids: list[int] = []  # Track source doc IDs for navigation

    def compose(self) -> ComposeResult:
        with Horizontal(id="qa-input-bar"):
            yield Input(
                placeholder="Ask a question about your knowledge base...",
                id="qa-input",
            )
            yield Static("Q&A", id="qa-mode-label")

        yield RichLog(id="qa-conversation", wrap=True, markup=True)

        yield Static("Ready | Type a question and press Enter", id="qa-status")
        yield Static(
            "[dim]1[/dim] Activity | [dim]2[/dim] Tasks | [bold]3[/bold] Q&A | "
            "[dim]/[/dim] input | [dim]s[/dim] save | [dim]c[/dim] clear",
            id="qa-nav",
        )

    async def on_mount(self) -> None:
        """Initialize the Q&A screen."""
        logger.info("QAScreen mounted")
        self.query_one("#qa-input", Input).focus()
        await self.presenter.initialize()
        self._show_welcome()

    def _show_welcome(self) -> None:
        """Show welcome message in the conversation area."""
        log = self.query_one("#qa-conversation", RichLog)
        log.write(
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

    async def _on_state_update(self, state: QAStateVM) -> None:
        """Handle state updates from presenter."""
        self.call_later(self._render_status, state)

    def _render_status(self, state: QAStateVM) -> None:
        """Update the status bar."""
        try:
            self.query_one("#qa-status", Static).update(state.status_text)
            # Update mode label
            if state.has_claude_cli:
                method = "semantic" if state.has_embeddings else "keyword"
                label = f"Q&A ({method})"
            else:
                label = "Q&A (no CLI)"
            self.query_one("#qa-mode-label", Static).update(label)
        except Exception as e:
            logger.error(f"Error rendering status: {e}")

    async def _on_answer_chunk(self, chunk: str) -> None:
        """Handle streaming answer chunks — update status to show progress."""

        def _update_status() -> None:
            try:
                entries = self.presenter.state.entries
                if entries and entries[-1].is_loading:
                    self.query_one("#qa-status", Static).update("Generating answer...")
            except Exception:
                pass

        self.call_later(_update_status)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter press in the input — submit the question."""
        if event.input.id != "qa-input":
            return
        question = event.value.strip()
        if not question:
            return

        # Clear input
        event.input.value = ""

        # Write the question to the conversation
        log = self.query_one("#qa-conversation", RichLog)
        log.write("")
        log.write(f"[bold cyan]Q:[/bold cyan] {question}")
        log.write("")

        # Start the answer (will stream into the log)
        self._current_entry_index = self.presenter.get_entry_count()
        asyncio.create_task(self._ask_and_render(question))

    async def _ask_and_render(self, question: str) -> None:
        """Ask the question and render the full answer when done."""
        log = self.query_one("#qa-conversation", RichLog)

        # Show loading indicator
        log.write("[dim]Thinking...[/dim]")

        await self.presenter.ask(question)

        # Get the entry that was just completed
        entries = self.presenter.state.entries
        if not entries:
            return

        entry = entries[-1]

        # Remove the "Thinking..." line by clearing and re-rendering
        # Actually, RichLog doesn't support removing lines easily.
        # Instead, just write the answer below.

        if entry.error and not entry.answer:
            log.write(f"[bold red]Error:[/bold red] {entry.error}")
        else:
            # Write the answer
            log.write(f"[bold green]A:[/bold green] {entry.answer}")

        # Write sources
        if entry.sources:
            self._source_ids = [s.doc_id for s in entry.sources]
            source_parts = []
            for src in entry.sources:
                source_parts.append(f"#{src.doc_id} {src.title}")
            sources_text = " · ".join(source_parts)
            log.write(f"\n[dim]Sources: {sources_text}[/dim]")
            log.write("[dim]  (press Enter on a source ID to view)[/dim]")

        log.write("[dim]─────────────────────────────────────────[/dim]")

    def action_submit_question(self) -> None:
        """Submit the current question (Enter key)."""
        inp = self.query_one("#qa-input", Input)
        if inp.has_focus:
            # Let the input's on_submitted handle it
            return
        # If focus is on the log, re-focus input
        inp.focus()

    def action_focus_input(self) -> None:
        """Focus the question input."""
        self.query_one("#qa-input", Input).focus()

    def action_clear_history(self) -> None:
        """Clear conversation history."""
        log = self.query_one("#qa-conversation", RichLog)
        log.clear()
        self.presenter.clear_history()
        self._source_ids.clear()
        self._show_welcome()
        self.notify("History cleared", timeout=1)

    def action_save_exchange(self) -> None:
        """Save the most recent Q&A exchange as a document."""
        entries = self.presenter.state.entries
        if not entries:
            self.notify("Nothing to save", timeout=2)
            return

        entry = entries[-1]
        if entry.is_loading:
            self.notify("Wait for the answer to finish", timeout=2)
            return

        # Build document content
        content = f"# Q: {entry.question}\n\n{entry.answer}\n"
        if entry.sources:
            content += "\n## Sources\n\n"
            for src in entry.sources:
                content += f"- Document #{src.doc_id}: {src.title}\n"

        # Save via emdx
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
        """Exit Q&A screen."""
        self.presenter.cancel()
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    def on_key(self, event: events.Key) -> None:
        """Handle key events — block vim keys when input is focused."""
        try:
            search_input = self.query_one("#qa-input", Input)
            if search_input.has_focus:
                pass_through_keys = {
                    "s",
                    "c",
                    "1",
                    "2",
                    "slash",
                }
                if event.key in pass_through_keys:
                    return
        except Exception:
            pass

    def set_query(self, query: str) -> None:
        """Set the input query programmatically (compatibility with command palette)."""
        inp = self.query_one("#qa-input", Input)
        inp.value = query
        inp.focus()

    def save_state(self) -> dict:
        """Save current state for restoration."""
        return {"entry_count": self.presenter.get_entry_count()}

    def restore_state(self, state: dict) -> None:
        """Restore saved state (conversation persists in memory)."""
        pass
