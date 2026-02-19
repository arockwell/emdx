"""
Search Screen - Full-featured document search with live results.

Features:
- Persistent search bar at top
- Live search with mode-specific debouncing
- Search-engine style results with rich snippets
- Enter to view document in modal
"""

import asyncio
import logging
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from ..modals import HelpMixin
from .search_presenter import SearchMode, SearchPresenter, SearchResultItem, SearchStateVM

logger = logging.getLogger(__name__)


class SearchScreen(HelpMixin, Widget):
    """
    Full-screen search widget with persistent search bar.

    Layout:
    - Search bar at top with mode buttons
    - Scrollable list of search results (search-engine style)
    - Status bar at bottom
    - Enter to view document in modal
    """

    HELP_TITLE = "Search"

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "view_document", "View"),
        Binding("e", "edit_document", "Edit"),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags"),
        Binding("tab", "cycle_mode", "Mode"),
        Binding("ctrl+s", "toggle_semantic", "Semantic"),
        Binding("space", "toggle_select", "Select", show=False),
        Binding("ctrl+a", "select_all", "Select All", show=False),
        Binding("escape", "exit_search", "Exit"),
        Binding("slash", "focus_search", "Search"),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    SearchScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: 3 1fr 1 1;
    }

    #search-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #search-input {
        width: 1fr;
        border: solid $primary-darken-1;
    }

    #search-input:focus {
        border: solid $primary;
    }

    #mode-buttons {
        width: auto;
        height: 3;
        padding: 0 1;
    }

    .mode-btn {
        width: auto;
        min-width: 6;
        height: 1;
        margin: 1 0 0 1;
        padding: 0 1;
        background: $surface-darken-1;
        color: $text-muted;
    }

    .mode-btn.active {
        background: $primary;
        color: $text;
    }

    #results-list {
        height: 1fr;
        width: 100%;
        scrollbar-gutter: stable;
    }

    #results-list > .option-list--option {
        padding: 1 2;
    }

    #search-status {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #search-nav {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    # Reactive state
    current_mode = reactive(SearchMode.FTS)
    is_empty_state = reactive(True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.presenter = SearchPresenter(on_state_update=self._on_state_update)
        self._debounce_timer: Timer | None = None
        self._current_vm: SearchStateVM | None = None

    def compose(self) -> ComposeResult:
        # Search bar
        with Horizontal(id="search-bar"):
            yield Input(
                placeholder="Search... (@tag, tags:name, after:2024-01-01)",
                id="search-input",
            )
            with Horizontal(id="mode-buttons"):
                yield Static("FTS", id="mode-fts", classes="mode-btn active")
                yield Static("Tags", id="mode-tags", classes="mode-btn")
                yield Static("AI", id="mode-semantic", classes="mode-btn")

        # Results list (Google-style with rich content)
        yield OptionList(id="results-list")

        # Status bar (dynamic)
        yield Static("Type to search...", id="search-status")
        # Navigation bar (fixed)
        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Tasks │ "
            "[dim]Tab[/dim] mode │ [dim]Enter[/dim] view │ [dim]/[/dim] search",
            id="search-nav",
        )

    async def on_mount(self) -> None:
        """Initialize the search screen."""
        logger.info("SearchScreen mounted")

        # Focus search input
        self.query_one("#search-input", Input).focus()

        # Load initial state
        await self.presenter.load_initial_state()

    async def _on_state_update(self, state: SearchStateVM) -> None:
        """Handle state updates from presenter."""
        self._current_vm = state
        # Use call_later to ensure we're on the main thread for UI updates
        self.call_later(self._render_state_sync, state)

    def _render_state_sync(self, state: SearchStateVM) -> None:
        """Render the current state to the UI (synchronous)."""
        try:
            # Update mode buttons
            self._update_mode_buttons(state.mode)

            # Update results (also updates status bar)
            self._render_results_sync(state)

            # Update empty state visibility
            self.is_empty_state = not state.query.strip()

        except Exception as e:
            logger.error(f"Error rendering state: {e}")

    def _update_mode_buttons(self, mode: SearchMode) -> None:
        """Update mode button highlighting."""
        mode_map = {
            SearchMode.FTS: "mode-fts",
            SearchMode.TAGS: "mode-tags",
            SearchMode.SEMANTIC: "mode-semantic",
            SearchMode.COMBINED: "mode-combined",
        }

        for m, btn_id in mode_map.items():
            try:
                btn = self.query_one(f"#{btn_id}", Static)
                if m == mode:
                    btn.add_class("active")
                else:
                    btn.remove_class("active")
            except Exception:
                pass

    def _render_results_sync(self, state: SearchStateVM) -> None:
        """Render results to OptionList with rich, Google-style formatting."""
        try:
            results_list = self.query_one("#results-list", OptionList)
            results_list.clear_options()

            # Limit to 10 results for readability
            results_to_show = state.results[:10]
            total_found = len(state.results)

            if not results_to_show:
                self.query_one("#search-status", Static).update("No results | Type to search")
                return

            # Add options with rich multi-line content
            for result in results_to_show:
                content = self._format_result_card(result)
                # Use doc_id as the option id for later retrieval
                results_list.add_option(Option(content, id=str(result.doc_id)))

            # Update status
            shown = len(results_to_show)
            count_text = f"{shown} of {total_found}" if total_found > shown else str(shown)
            self.query_one("#search-status", Static).update(
                f"{count_text} results | {state.mode.value.upper()} | {state.search_time_ms}ms | j/k=nav | Enter=view"  # noqa: E501
            )
        except Exception as e:
            logger.error(f"Error rendering results: {e}")

    def _format_result_card(self, result: SearchResultItem) -> str:
        """Format a single result as a rich multi-line card (Google-style)."""
        icon = self._get_match_icon(result.source)

        # Line 1: Icon + Title (bold, full width)
        title = result.title[:80] if len(result.title) <= 80 else result.title[:77] + "..."
        line1 = f"{icon} [bold]{title}[/bold]"

        # Line 2: Metadata (dim) - ID, tags, time, project
        meta_parts = [f"#{result.doc_id}"]
        if result.project:
            meta_parts.append(f"[cyan]{result.project}[/cyan]")
        if result.tags:
            tags_str = " ".join(result.tags[:4])
            meta_parts.append(tags_str)
        if result.updated_at:
            meta_parts.append(self._format_time(result.updated_at))
        line2 = f"[dim]{' · '.join(meta_parts)}[/dim]"

        # Line 3: Why it matched (the snippet with highlights)
        line3 = self._format_snippet_rich(result)

        return f"{line1}\n{line2}\n{line3}"

    def _format_snippet_rich(self, result: SearchResultItem) -> str:
        """Format the snippet showing WHY this matched, with rich highlighting."""
        if result.snippet:
            # Convert <b> tags to rich markup highlights
            snippet = result.snippet.replace("<b>", "[yellow bold]").replace(
                "</b>", "[/yellow bold]"
            )  # noqa: E501
            # Clean up whitespace but keep it readable
            snippet = " ".join(snippet.split())
            # Allow longer snippets now that we have more space
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            return snippet

        # Fallback explanations for different match types
        if "semantic" in result.source:
            score_pct = int(result.score * 100)
            return f"[magenta]🧠 {score_pct}% semantic similarity[/magenta] - conceptually related to your search"  # noqa: E501
        if "tags" in result.source:
            return f"[cyan]🏷️ Matched tags:[/cyan] {' '.join(result.tags[:5])}"
        if "fuzzy" in result.source:
            return "[blue]🔍 Title matches your search terms[/blue]"
        if "recent" in result.source:
            return "[dim]📅 Recently accessed document[/dim]"
        if "id" in result.source:
            return f"[green]🆔 Direct ID match: #{result.doc_id}[/green]"
        return "[dim]Matched your search criteria[/dim]"

    def _get_match_icon(self, source: str) -> str:
        """Get icon based on match source."""
        if "+" in source:
            return "🔀"
        return {
            "fts": "📝",
            "tags": "🏷️",
            "semantic": "🧠",
            "fuzzy": "🔍",
            "recent": "🕐",
            "id": "🆔",
        }.get(source, "📄")  # noqa: E501

    def _format_time(self, time_str: str) -> str:
        """Format timestamp as relative time."""
        if not time_str:
            return ""
        try:
            from datetime import datetime

            if "T" in time_str:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                return time_str[:10]
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            delta = now - dt
            if delta.days == 0:
                hours = delta.seconds // 3600
                return f"{hours}h" if hours > 0 else f"{delta.seconds // 60}m"
            elif delta.days < 7:
                return f"{delta.days}d"
            elif delta.days < 30:
                return f"{delta.days // 7}w"
            return time_str[:10]
        except Exception:
            return ""

    def _update_selection(self) -> None:
        """Not needed for OptionList - it handles selection."""
        pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes with debouncing."""
        if event.input.id != "search-input":
            return

        query = event.value

        # Cancel pending search
        if self._debounce_timer:
            try:
                self._debounce_timer.stop()
            except Exception:
                pass
            self._debounce_timer = None

        # Get debounce time for current mode
        debounce_ms = self.presenter.get_debounce_time()

        # Schedule search after debounce delay
        def do_search() -> None:
            self._debounce_timer = None
            asyncio.create_task(self.presenter.search(query))

        self._debounce_timer = self.set_timer(debounce_ms / 1000, do_search)

    async def _safe_search(self, query: str) -> None:
        """Execute search with error handling."""
        try:
            await self.presenter.search(query)
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.notify(f"Search error: {e}", severity="error", timeout=3)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter press in search input - focus results list."""
        if event.input.id == "search-input":
            results_list = self.query_one("#results-list", OptionList)
            if results_list.option_count > 0:
                results_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle when an option is selected (Enter pressed on OptionList)."""
        if event.option_list.id == "results-list" and event.option.id:
            doc_id = int(event.option.id)
            from ..modals import DocumentPreviewScreen

            self.app.push_screen(DocumentPreviewScreen(doc_id))

    def action_cursor_down(self) -> None:
        """Move cursor down and focus results list."""
        results_list = self.query_one("#results-list", OptionList)
        if not results_list.has_focus:
            results_list.focus()
        results_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up and focus results list."""
        results_list = self.query_one("#results-list", OptionList)
        if not results_list.has_focus:
            results_list.focus()
        results_list.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        results_list = self.query_one("#results-list", OptionList)
        results_list.action_first()

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        results_list = self.query_one("#results-list", OptionList)
        results_list.action_last()

    def action_cycle_mode(self) -> None:
        """Cycle through search modes."""
        new_mode = self.presenter.cycle_mode()
        self.current_mode = new_mode

        # Re-run search with new mode if we have a query
        if self._current_vm and self._current_vm.query:
            asyncio.create_task(self.presenter.search(self._current_vm.query))

        self.notify(f"Mode: {new_mode.value.upper()}", timeout=1)

    def action_toggle_semantic(self) -> None:
        """Toggle semantic search mode."""
        if self.current_mode == SearchMode.SEMANTIC:
            self.presenter.set_mode(SearchMode.FTS)
            self.current_mode = SearchMode.FTS
        else:
            # Check if embeddings are available before enabling semantic search
            if not self.presenter.search_service.has_embeddings():
                self.notify(
                    "No embeddings indexed. Run 'emdx embed build' first.",
                    severity="warning",
                    timeout=3,
                )  # noqa: E501
                return
            self.presenter.set_mode(SearchMode.SEMANTIC)
            self.current_mode = SearchMode.SEMANTIC
            self.notify("Semantic search may be slow on first use", timeout=2)

        # Re-run search
        if self._current_vm and self._current_vm.query:
            asyncio.create_task(self.presenter.search(self._current_vm.query))

    def action_toggle_select(self) -> None:
        """Toggle selection of current row."""
        results_list = self.query_one("#results-list", OptionList)
        if results_list.highlighted is not None:
            self.presenter.toggle_selection(results_list.highlighted)

    def action_select_all(self) -> None:
        """Select all results."""
        self.presenter.select_all()
        if self._current_vm:
            self._render_results_sync(self._current_vm)

    def action_clear_search(self) -> None:
        """Clear search and show recent docs."""
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        self.presenter.clear_results()
        if self._current_vm:
            self._render_state_sync(self._current_vm)

    async def action_exit_search(self) -> None:
        """Exit search screen and go back to activity."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    async def action_view_document(self) -> None:
        """View the selected document in a modal."""
        results_list = self.query_one("#results-list", OptionList)
        if results_list.highlighted is not None:
            # Get the doc_id from the option's id attribute
            option = results_list.get_option_at_index(results_list.highlighted)
            if option and option.id:
                doc_id = int(option.id)
                from ..modals import DocumentPreviewScreen

                await self.app.push_screen(DocumentPreviewScreen(doc_id))

    async def action_edit_document(self) -> None:
        """Edit the selected document."""
        # For now, view document - editing requires more integration
        await self.action_view_document()

    def action_add_tags(self) -> None:
        """Add tags to selected document(s)."""
        # TODO: Implement tag modal
        self.notify("Tag editing coming soon", timeout=2)

    def action_remove_tags(self) -> None:
        """Remove tags from selected document(s)."""
        # TODO: Implement tag modal
        self.notify("Tag editing coming soon", timeout=2)

    async def action_refresh(self) -> None:
        """Refresh search results."""
        if self._current_vm and self._current_vm.query:
            await self.presenter.search(self._current_vm.query)
        else:
            await self.presenter.load_initial_state()

    def set_query(self, query: str) -> None:
        """Set the search query programmatically."""
        search_input = self.query_one("#search-input", Input)
        search_input.value = query
        asyncio.create_task(self.presenter.search(query))

    def update_status(self, message: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one("#search-status", Static)
            status.update(message)
        except Exception:
            pass

    def save_state(self) -> dict:
        """Save current state for restoration."""
        return {
            "query": self._current_vm.query if self._current_vm else "",
            "mode": self.current_mode.value,
        }

    def restore_state(self, state: dict) -> None:
        """Restore saved state."""
        if "mode" in state:
            try:
                self.presenter.set_mode(SearchMode(state["mode"]))
                self.current_mode = SearchMode(state["mode"])
            except ValueError:
                pass

        if "query" in state and state["query"]:
            self.set_query(state["query"])

    def on_key(self, event: events.Key) -> None:
        """Handle key events - block vim keys when input is focused."""
        # Check if the search input has focus
        try:
            search_input = self.query_one("#search-input", Input)
            if search_input.has_focus:
                # When input is focused, don't let vim keys trigger actions
                # Let them pass through to the input widget
                vim_keys = {
                    "j",
                    "k",
                    "g",
                    "G",
                    "e",
                    "t",
                    "T",
                    "r",
                    "space",
                    "slash",
                    "1",
                    "2",
                }
                if event.key in vim_keys:
                    # Don't stop - let the input handle it
                    return
        except Exception:
            pass
