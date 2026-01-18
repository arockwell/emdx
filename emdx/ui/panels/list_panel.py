#!/usr/bin/env python3
"""
ListPanel - A reusable DataTable-based list panel with vim-style navigation.

This panel extracts the DataTable functionality from DocumentBrowser into a
standalone, configurable component that can be used by any browser widget.

Features:
- Configurable columns with widths
- Vim-style navigation (j/k/g/G)
- Search/filter support with / binding
- Selection events via Textual messages
- Cursor state save/restore
- Lazy loading support with load-more callback

Example usage:
    class MyBrowser(Widget):
        def compose(self):
            yield ListPanel(
                columns=[
                    ColumnDef("ID", 5),
                    ColumnDef("Name", 40),
                    ColumnDef("Status", 10),
                ],
                id="my-list",
            )

        def on_list_panel_item_selected(self, event: ListPanel.ItemSelected):
            # Handle selection
            item = event.item
            self.show_preview(item)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static

logger = logging.getLogger(__name__)


@dataclass
class ColumnDef:
    """Definition for a column in the ListPanel.

    Attributes:
        name: Column header text
        width: Column width in characters (None for auto)
        key: Optional unique key for the column (defaults to lowercase name)
    """
    name: str
    width: Optional[int] = None
    key: Optional[str] = None

    def __post_init__(self):
        if self.key is None:
            self.key = self.name.lower().replace(" ", "_")


@dataclass
class ListItem:
    """A single item in the ListPanel.

    Attributes:
        id: Unique identifier for the item
        values: List of cell values (must match column count)
        data: Optional arbitrary data associated with this item
    """
    id: Any
    values: List[str]
    data: Optional[Any] = None


@dataclass
class ListPanelConfig:
    """Configuration for ListPanel behavior.

    Attributes:
        show_header: Whether to show column headers
        cursor_type: Cursor type ("row", "cell", "column")
        zebra_stripes: Whether to alternate row backgrounds
        cell_padding: Padding between cells
        show_search: Whether to enable search/filter (/ key)
        search_placeholder: Placeholder text for search input
        lazy_load_threshold: Load more when cursor is within N rows of end
        status_format: Format string for status (supports {filtered}, {total})
    """
    show_header: bool = True
    cursor_type: str = "row"
    zebra_stripes: bool = False
    cell_padding: int = 0
    show_search: bool = True
    search_placeholder: str = "Search..."
    lazy_load_threshold: int = 20
    status_format: str = "{filtered}/{total} items"


class ListPanel(Widget):
    """Reusable list panel with DataTable, vim navigation, and search.

    This widget wraps a DataTable and provides:
    - Configurable columns
    - Vim-style navigation (j/k/g/G)
    - Search/filter with / key
    - Selection events
    - Lazy loading support
    - State save/restore

    Messages:
        ItemSelected: Fired when a row is highlighted/selected
        ItemActivated: Fired when Enter is pressed on a row
        SearchSubmitted: Fired when search is submitted
        LoadMoreRequested: Fired when cursor approaches end of list
    """

    DEFAULT_CSS = """
    ListPanel {
        layout: vertical;
        height: 100%;
        layers: base overlay;
    }

    ListPanel #list-search-input {
        layer: overlay;
        display: none;
        height: 3;
        margin: 1;
        border: solid $primary;
        dock: top;
    }

    ListPanel #list-search-input.visible {
        display: block;
    }

    ListPanel #list-table-container {
        height: 1fr;
        layer: base;
    }

    ListPanel #list-table {
        height: 100%;
    }

    ListPanel #list-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: right;
        layer: base;
        display: none;
    }

    ListPanel #list-status.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("slash", "search", "Search", show=False),
        Binding("enter", "activate_item", "Select", show=False),
        Binding("escape", "cancel_search", "Cancel", show=False),
    ]

    # Reactive properties
    mode = reactive("NORMAL")
    search_query = reactive("")
    item_count = reactive(0)
    filtered_count = reactive(0)

    # Messages
    class ItemSelected(Message):
        """Fired when a row is highlighted."""
        def __init__(self, item: ListItem, index: int) -> None:
            self.item = item
            self.index = index
            super().__init__()

    class ItemActivated(Message):
        """Fired when Enter is pressed on a row."""
        def __init__(self, item: ListItem, index: int) -> None:
            self.item = item
            self.index = index
            super().__init__()

    class SearchSubmitted(Message):
        """Fired when search query is submitted."""
        def __init__(self, query: str) -> None:
            self.query = query
            super().__init__()

    class LoadMoreRequested(Message):
        """Fired when cursor approaches end of list."""
        def __init__(self, current_index: int, total_count: int) -> None:
            self.current_index = current_index
            self.total_count = total_count
            super().__init__()

    def __init__(
        self,
        columns: Sequence[Union[ColumnDef, Tuple[str, int], str]],
        config: Optional[ListPanelConfig] = None,
        items: Optional[List[ListItem]] = None,
        show_status: bool = False,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the ListPanel.

        Args:
            columns: Column definitions. Can be:
                - ColumnDef objects
                - Tuples of (name, width)
                - Strings (name only, auto width)
            config: Optional configuration object
            items: Optional initial items to populate
            show_status: Whether to show status bar
            *args, **kwargs: Passed to Widget
        """
        super().__init__(*args, **kwargs)

        # Normalize column definitions
        self._columns: List[ColumnDef] = []
        for col in columns:
            if isinstance(col, ColumnDef):
                self._columns.append(col)
            elif isinstance(col, tuple):
                self._columns.append(ColumnDef(col[0], col[1] if len(col) > 1 else None))
            else:
                self._columns.append(ColumnDef(col))

        self._config = config or ListPanelConfig()
        self._items: List[ListItem] = items or []
        self._show_status = show_status

        # Internal state
        self._filter_func: Optional[Callable[[ListItem], bool]] = None
        self._filtered_items: List[ListItem] = []
        self._has_more: bool = False

    def compose(self) -> ComposeResult:
        """Compose the list panel UI."""
        # Search input (hidden by default)
        if self._config.show_search:
            yield Input(
                placeholder=self._config.search_placeholder,
                id="list-search-input",
            )

        # Table container
        with Vertical(id="list-table-container"):
            yield DataTable(id="list-table")

        # Status bar (hidden by default)
        if self._show_status:
            yield Static("", id="list-status", classes="visible")

    async def on_mount(self) -> None:
        """Initialize the list panel."""
        # Setup table
        table = self.query_one("#list-table", DataTable)

        # Add columns
        for col in self._columns:
            if col.width:
                table.add_column(col.name, width=col.width, key=col.key)
            else:
                table.add_column(col.name, key=col.key)

        # Configure table
        table.cursor_type = self._config.cursor_type
        table.show_header = self._config.show_header
        table.zebra_stripes = self._config.zebra_stripes
        table.cell_padding = self._config.cell_padding

        # Populate initial items
        if self._items:
            await self._render_items()

        # Setup search input
        if self._config.show_search:
            search_input = self.query_one("#list-search-input", Input)
            search_input.can_focus = False

        # Focus table
        table.focus()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_items(self, items: List[ListItem], has_more: bool = False) -> None:
        """Set the items to display.

        Args:
            items: List of items to display
            has_more: Whether more items can be loaded
        """
        self._items = items
        self._has_more = has_more
        self._apply_filter()
        self.call_later(self._render_items_sync)

    def append_items(self, items: List[ListItem], has_more: bool = False) -> None:
        """Append items to the existing list.

        Args:
            items: Items to append
            has_more: Whether more items can be loaded
        """
        self._items.extend(items)
        self._has_more = has_more
        self._apply_filter()
        self.call_later(self._render_items_sync)

    def clear_items(self) -> None:
        """Clear all items."""
        self._items = []
        self._filtered_items = []
        self._has_more = False
        try:
            table = self.query_one("#list-table", DataTable)
            table.clear()
        except Exception:
            pass
        self._update_counts()

    def get_selected_item(self) -> Optional[ListItem]:
        """Get the currently selected item."""
        try:
            table = self.query_one("#list-table", DataTable)
            if table.cursor_row is not None and 0 <= table.cursor_row < len(self._filtered_items):
                return self._filtered_items[table.cursor_row]
        except Exception:
            pass
        return None

    def get_selected_index(self) -> Optional[int]:
        """Get the index of the currently selected item in the filtered list."""
        try:
            table = self.query_one("#list-table", DataTable)
            return table.cursor_row
        except Exception:
            return None

    def get_item_at_index(self, index: int) -> Optional[ListItem]:
        """Get item at a specific index in the filtered list."""
        if 0 <= index < len(self._filtered_items):
            return self._filtered_items[index]
        return None

    def get_item_by_id(self, item_id: Any) -> Optional[ListItem]:
        """Get an item by its ID."""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def select_item_by_id(self, item_id: Any) -> bool:
        """Select an item by its ID.

        Returns:
            True if item was found and selected, False otherwise.
        """
        for idx, item in enumerate(self._filtered_items):
            if item.id == item_id:
                try:
                    table = self.query_one("#list-table", DataTable)
                    table.move_cursor(row=idx)
                    return True
                except Exception:
                    pass
        return False

    def select_index(self, index: int) -> bool:
        """Select an item by index.

        Returns:
            True if index was valid and selected, False otherwise.
        """
        if 0 <= index < len(self._filtered_items):
            try:
                table = self.query_one("#list-table", DataTable)
                table.move_cursor(row=index)
                return True
            except Exception:
                pass
        return False

    def set_filter(self, filter_func: Optional[Callable[[ListItem], bool]]) -> None:
        """Set a filter function for items.

        Args:
            filter_func: Function that returns True for items to include,
                        or None to show all items.
        """
        self._filter_func = filter_func
        self._apply_filter()
        self.call_later(self._render_items_sync)

    def set_search_filter(self, query: str) -> None:
        """Set a simple text search filter.

        This creates a filter that matches items where any cell value
        contains the query string (case-insensitive).

        Args:
            query: Search string (empty to clear filter)
        """
        self.search_query = query
        if not query:
            self._filter_func = None
        else:
            query_lower = query.lower()
            self._filter_func = lambda item: any(
                query_lower in str(v).lower() for v in item.values
            )
        self._apply_filter()
        self.call_later(self._render_items_sync)

    @property
    def has_more(self) -> bool:
        """Whether more items can be loaded."""
        return self._has_more

    @property
    def items(self) -> List[ListItem]:
        """All items (unfiltered)."""
        return self._items

    @property
    def filtered_items(self) -> List[ListItem]:
        """Currently visible items (after filtering)."""
        return self._filtered_items

    def save_state(self) -> Dict[str, Any]:
        """Save panel state for restoration.

        Returns:
            State dict with cursor position and search query.
        """
        state: Dict[str, Any] = {
            "mode": self.mode,
            "search_query": self.search_query,
        }

        try:
            table = self.query_one("#list-table", DataTable)
            state["cursor_row"] = table.cursor_row
            state["cursor_column"] = table.cursor_column
        except Exception:
            pass

        return state

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state.

        Args:
            state: State dict from save_state()
        """
        self.mode = state.get("mode", "NORMAL")

        if state.get("search_query"):
            self.set_search_filter(state["search_query"])

        if "cursor_row" in state:
            try:
                table = self.query_one("#list-table", DataTable)
                row = state["cursor_row"]
                if row is not None and 0 <= row < len(self._filtered_items):
                    table.move_cursor(row=row)
            except Exception:
                pass

    def focus_table(self) -> None:
        """Set focus to the table."""
        try:
            table = self.query_one("#list-table", DataTable)
            table.focus()
        except Exception:
            pass

    def update_status(self, text: str) -> None:
        """Update the status bar text.

        Args:
            text: Status text to display
        """
        if self._show_status:
            try:
                status = self.query_one("#list-status", Static)
                status.update(text)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _apply_filter(self) -> None:
        """Apply the current filter to items."""
        if self._filter_func:
            self._filtered_items = [item for item in self._items if self._filter_func(item)]
        else:
            self._filtered_items = list(self._items)
        self._update_counts()

    def _update_counts(self) -> None:
        """Update item count reactives."""
        self.item_count = len(self._items)
        self.filtered_count = len(self._filtered_items)

        # Update status bar if visible
        if self._show_status:
            status_text = self._config.status_format.format(
                filtered=self.filtered_count,
                total=self.item_count,
            )
            self.update_status(status_text)

    def _render_items_sync(self) -> None:
        """Synchronous wrapper for _render_items."""
        import asyncio
        asyncio.create_task(self._render_items())

    async def _render_items(self) -> None:
        """Render items to the table."""
        try:
            table = self.query_one("#list-table", DataTable)
            table.clear()

            for item in self._filtered_items:
                table.add_row(*item.values, key=str(item.id))

            self._update_counts()

        except Exception as e:
            logger.error(f"Error rendering items: {e}")

    def _should_load_more(self, row_idx: int) -> bool:
        """Check if we should request more items."""
        if not self._has_more:
            return False
        threshold = self._config.lazy_load_threshold
        return row_idx >= len(self._filtered_items) - threshold

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#list-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#list-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to first item."""
        table = self.query_one("#list-table", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to last item."""
        table = self.query_one("#list-table", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)

    def action_search(self) -> None:
        """Enter search mode."""
        if not self._config.show_search:
            return

        self.mode = "SEARCH"
        try:
            search_input = self.query_one("#list-search-input", Input)
            search_input.add_class("visible")
            search_input.can_focus = True
            search_input.focus()
        except Exception:
            pass

    def action_cancel_search(self) -> None:
        """Cancel search mode and return to normal."""
        if self.mode != "SEARCH":
            return

        self.mode = "NORMAL"
        try:
            search_input = self.query_one("#list-search-input", Input)
            search_input.remove_class("visible")
            search_input.can_focus = False
            search_input.value = ""
        except Exception:
            pass

        self.focus_table()

    def action_activate_item(self) -> None:
        """Activate (select with Enter) the current item."""
        item = self.get_selected_item()
        index = self.get_selected_index()
        if item is not None and index is not None:
            self.post_message(self.ItemActivated(item, index))

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    async def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Handle row highlight (selection change)."""
        row_idx = event.cursor_row

        # Check if we should load more
        if self._should_load_more(row_idx):
            self.post_message(self.LoadMoreRequested(row_idx, len(self._filtered_items)))

        # Get selected item and post message
        if 0 <= row_idx < len(self._filtered_items):
            item = self._filtered_items[row_idx]
            self.post_message(self.ItemSelected(item, row_idx))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "list-search-input":
            query = event.input.value.strip()
            self.post_message(self.SearchSubmitted(query))

            # Apply search filter
            self.set_search_filter(query)

            # Exit search mode
            self.action_cancel_search()

    async def on_key(self, event) -> None:
        """Handle key events."""
        # Handle escape in search mode
        if event.key == "escape" and self.mode == "SEARCH":
            self.action_cancel_search()
            event.stop()


# =============================================================================
# Example: SimpleBrowser using ListPanel
# =============================================================================

class SimpleBrowser(Widget):
    """Example browser demonstrating ListPanel usage.

    This shows how to use ListPanel in a real widget:
    - Define columns
    - Populate data
    - Handle selection events
    - Implement search
    """

    DEFAULT_CSS = """
    SimpleBrowser {
        layout: horizontal;
        height: 100%;
    }

    SimpleBrowser #simple-list {
        width: 1fr;
        min-width: 40;
    }

    SimpleBrowser #simple-preview {
        width: 1fr;
        min-width: 40;
        padding: 1;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the simple browser UI."""
        yield ListPanel(
            columns=[
                ColumnDef("ID", width=5),
                ColumnDef("Name", width=40),
                ColumnDef("Status", width=10),
            ],
            config=ListPanelConfig(
                show_search=True,
                search_placeholder="Search items...",
                status_format="{filtered}/{total} items",
            ),
            show_status=True,
            id="simple-list",
        )
        yield Static("Select an item to preview", id="simple-preview")

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.load_data()

    async def load_data(self) -> None:
        """Load sample data into the list."""
        items = [
            ListItem(id=1, values=["1", "First Item", "Active"], data={"desc": "The first item"}),
            ListItem(id=2, values=["2", "Second Item", "Pending"], data={"desc": "The second item"}),
            ListItem(id=3, values=["3", "Third Item", "Done"], data={"desc": "The third item"}),
            ListItem(id=4, values=["4", "Fourth Item", "Active"], data={"desc": "The fourth item"}),
            ListItem(id=5, values=["5", "Fifth Item", "Error"], data={"desc": "The fifth item"}),
        ]

        list_panel = self.query_one("#simple-list", ListPanel)
        list_panel.set_items(items)

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Handle item selection."""
        preview = self.query_one("#simple-preview", Static)
        item = event.item

        # Show item details in preview
        if item.data:
            preview.update(
                f"[bold]{item.values[1]}[/bold]\n\n"
                f"ID: {item.id}\n"
                f"Status: {item.values[2]}\n\n"
                f"Description: {item.data.get('desc', 'N/A')}"
            )
        else:
            preview.update(f"Selected: {item.values[1]}")

    async def on_list_panel_item_activated(
        self, event: ListPanel.ItemActivated
    ) -> None:
        """Handle item activation (Enter key)."""
        self.notify(f"Activated: {event.item.values[1]}")

    async def on_list_panel_search_submitted(
        self, event: ListPanel.SearchSubmitted
    ) -> None:
        """Handle search submission."""
        if event.query:
            self.notify(f"Searching for: {event.query}")
        else:
            self.notify("Search cleared")

    def action_refresh(self) -> None:
        """Refresh the list."""
        import asyncio
        asyncio.create_task(self.load_data())
        self.notify("Refreshed")


# =============================================================================
# Example: DocumentListBrowser - More complex example
# =============================================================================

class DocumentListBrowser(Widget):
    """Example showing how to wrap ListPanel for document browsing.

    This demonstrates:
    - Custom data loading
    - Lazy loading with LoadMoreRequested
    - Integration with a presenter pattern
    - Custom search handling
    """

    DEFAULT_CSS = """
    DocumentListBrowser {
        layout: horizontal;
        height: 100%;
    }

    DocumentListBrowser #doc-list {
        width: 50%;
    }

    DocumentListBrowser #doc-detail {
        width: 50%;
        padding: 1 2;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._current_offset = 0
        self._page_size = 50
        self._has_more = True

    def compose(self) -> ComposeResult:
        """Compose the document browser UI."""
        yield ListPanel(
            columns=[
                ColumnDef("ID", width=4),
                ColumnDef("Tags", width=8),
                ColumnDef("Title", width=60),
            ],
            config=ListPanelConfig(
                show_search=True,
                search_placeholder="Search documents (try tags:python)...",
                lazy_load_threshold=20,
            ),
            show_status=True,
            id="doc-list",
        )
        yield Static("Select a document", id="doc-detail")

    async def on_mount(self) -> None:
        """Load initial documents."""
        await self._load_documents(offset=0, append=False)

    async def _load_documents(self, offset: int = 0, append: bool = False) -> None:
        """Load documents from database.

        This is a stub - replace with actual database calls.
        """
        # Simulate loading documents
        items = []
        for i in range(offset, min(offset + self._page_size, 200)):
            items.append(ListItem(
                id=i + 1,
                values=[str(i + 1), "py", f"Document {i + 1}"],
                data={"content": f"Content for document {i + 1}"},
            ))

        self._has_more = offset + self._page_size < 200
        self._current_offset = offset + len(items)

        list_panel = self.query_one("#doc-list", ListPanel)
        if append:
            list_panel.append_items(items, has_more=self._has_more)
        else:
            list_panel.set_items(items, has_more=self._has_more)

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Show document preview."""
        detail = self.query_one("#doc-detail", Static)
        item = event.item

        content = item.data.get("content", "") if item.data else ""
        detail.update(
            f"[bold]#{item.id}: {item.values[2]}[/bold]\n\n"
            f"Tags: {item.values[1]}\n\n"
            f"{content}"
        )

    async def on_list_panel_load_more_requested(
        self, event: ListPanel.LoadMoreRequested
    ) -> None:
        """Load more documents when scrolling near end."""
        if self._has_more:
            await self._load_documents(offset=self._current_offset, append=True)
