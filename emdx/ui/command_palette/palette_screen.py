"""
Command Palette Screen - VS Code-style modal overlay.

Provides quick access to documents, commands, and navigation
via keyboard-driven fuzzy search.
"""

import asyncio
import logging
import traceback
from typing import Any, Dict

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from emdx.config.constants import EMDX_CONFIG_DIR

from .palette_commands import CommandContext
from .palette_presenter import PalettePresenter, PaletteResultItem, PaletteState

logger = logging.getLogger(__name__)

# Debug log file for catching crashes
DEBUG_LOG = EMDX_CONFIG_DIR / "palette_debug.log"


def _debug_log(msg: str) -> None:
    """Write debug message to file."""
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


class PaletteResultWidget(ListItem):
    """Widget for a single palette result."""

    DEFAULT_CSS = """
    PaletteResultWidget {
        height: 2;
        padding: 0 1;
    }
    """

    def __init__(self, result: PaletteResultItem, **kwargs):
        super().__init__(**kwargs)
        self.result = result

    def compose(self) -> ComposeResult:
        # Format based on result type
        icon = self.result.icon
        title = self.result.title
        subtitle = self.result.subtitle

        # Truncate long titles
        if len(title) > 50:
            title = title[:47] + "..."

        # Truncate subtitle
        if len(subtitle) > 35:
            subtitle = subtitle[:32] + "..."

        yield Static(f"{icon} {title}  [dim]{subtitle}[/dim]")


class CommandPaletteScreen(ModalScreen):
    """
    Command palette modal overlay.

    Supports prefix-based routing:
    - (none) → Document search
    - > → Commands
    - @ → Tags
    - # → Document ID / semantic
    - : → Navigation
    """

    CSS = """
    CommandPaletteScreen {
        align: center top;
        padding-top: 5;
    }

    #palette-container {
        width: 80;
        height: auto;
        max-height: 30;
        background: $surface;
        border: solid $primary;
    }

    #palette-input {
        width: 100%;
        height: 3;
        border: none;
        border-bottom: solid $primary-darken-1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #palette-input:focus {
        border-bottom: solid $primary;
    }

    #palette-results {
        height: auto;
        max-height: 20;
        min-height: 5;
        padding: 0;
    }

    #palette-hints {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }

    ListItem {
        height: auto;
        padding: 0 1;
    }

    ListItem.--highlight {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("ctrl+n", "cursor_down", "Down", show=False),
        Binding("ctrl+p", "cursor_up", "Up", show=False),
        Binding("ctrl+k", "dismiss", "Close", show=False),
    ]

    class ResultSelected(Message):
        """Message when a result is selected."""

        def __init__(self, result: Dict[str, Any]):
            super().__init__()
            self.result = result

    def __init__(
        self,
        initial_query: str = "",
        context: CommandContext | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.initial_query = initial_query
        self.presenter = PalettePresenter(
            on_state_update=self._on_state_update,
            context=context or CommandContext.GLOBAL,
        )
        self._debounce_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-container"):
            yield Input(
                placeholder="Search documents, type > for commands, @ for tags...",
                id="palette-input",
            )
            yield ListView(id="palette-results")
            yield Static(
                "↑↓ Navigate │ Enter Select │ Esc Close │ > Commands │ @ Tags │ # ID/Semantic",
                id="palette-hints",
            )

    async def on_mount(self) -> None:
        """Initialize palette on mount."""
        _debug_log("=== CommandPaletteScreen.on_mount START ===")
        try:
            # Load initial state (recent items)
            _debug_log("Loading initial state...")
            await self.presenter.load_initial_state()
            _debug_log(f"Initial state loaded: {len(self.presenter.state.results)} results")

            # Set initial query if provided
            input_widget = self.query_one("#palette-input", Input)
            if self.initial_query:
                input_widget.value = self.initial_query
                await self.presenter.search(self.initial_query)

            # Focus input
            input_widget.focus()
            _debug_log("=== CommandPaletteScreen.on_mount END ===")
        except Exception as e:
            _debug_log(f"ERROR in on_mount: {e}\n{traceback.format_exc()}")
            raise

    def _on_state_update(self, state: PaletteState) -> None:
        """Handle state updates from presenter."""
        # Use unique render ID to avoid race conditions
        self._render_id = getattr(self, '_render_id', 0) + 1
        current_render = self._render_id
        self.call_later(lambda: asyncio.create_task(self._render_results(state, current_render)))

    async def _render_results(self, state: PaletteState, render_id: int) -> None:
        """Render results to the ListView."""
        # Skip if a newer render was requested
        if render_id != getattr(self, '_render_id', render_id):
            _debug_log(f"Skipping stale render {render_id}")
            return

        _debug_log(f"_render_results called with {len(state.results)} results (render_id={render_id})")
        try:
            results_view = self.query_one("#palette-results", ListView)
            await results_view.clear()

            if not state.results:
                # Show empty message
                results_view.append(
                    ListItem(Static("[dim]No results found[/dim]"))
                )
                return

            for i, result in enumerate(state.results):
                item = PaletteResultWidget(result)
                results_view.append(item)

            # Highlight selected
            if state.results:
                results_view.index = min(state.selected_index, len(state.results) - 1)

            _debug_log("_render_results completed successfully")
        except Exception as e:
            _debug_log(f"ERROR in _render_results: {e}\n{traceback.format_exc()}")
            logger.error(f"Error rendering results: {e}")

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes with debouncing."""
        if event.input.id != "palette-input":
            return

        query = event.value

        # Cancel pending search
        if self._debounce_timer:
            self._debounce_timer.stop()

        # Debounce search (100ms)
        self._debounce_timer = self.set_timer(
            0.1, lambda: asyncio.create_task(self.presenter.search(query))
        )

    def action_cursor_up(self) -> None:
        """Move selection up."""
        self.presenter.move_selection(-1)

    def action_cursor_down(self) -> None:
        """Move selection down."""
        self.presenter.move_selection(1)

    async def action_select(self) -> None:
        """Execute the selected item."""
        _debug_log(f"action_select called, selected_index={self.presenter._state.selected_index}")
        _debug_log(f"Results count: {len(self.presenter._state.results)}")
        selected = self.presenter.get_selected_result()
        _debug_log(f"Selected result: {selected}")
        result = await self.presenter.execute_selected(self.app)
        _debug_log(f"execute_selected returned: {result}")
        if result:
            self.dismiss(result)
        else:
            _debug_log("No result to dismiss with")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        # Update presenter selection
        if event.list_view.index is not None:
            self.presenter._state.selected_index = event.list_view.index

        # Execute selection
        result = await self.presenter.execute_selected(self.app)
        if result:
            self.dismiss(result)

    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        _debug_log(f"on_key: {key}")

        # Handle Enter explicitly since Input captures it
        if key == "enter":
            _debug_log("Enter key detected, calling action_select")
            event.stop()
            await self.action_select()
            return

        # Handle up/down for navigation
        if key in ("up", "ctrl+p"):
            event.stop()
            self.action_cursor_up()
            return
        elif key in ("down", "ctrl+n"):
            event.stop()
            self.action_cursor_down()
            return
        elif key == "tab":
            # Tab cycles through result types (could add prefix)
            event.stop()
