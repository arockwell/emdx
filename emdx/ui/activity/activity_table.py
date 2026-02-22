"""ActivityTable — flat DataTable widget for the activity view.

Simple table showing documents in a flat list.

Columns: Icon | Title | Time | ID
"""

import logging
import time

from rich.text import Text
from textual.events import Click
from textual.message import Message
from textual.widgets import DataTable

from .activity_items import ActivityItem, DocumentItem

logger = logging.getLogger(__name__)

# Type alias for the key that uniquely identifies an item
ItemKey = tuple[str, int]  # (item_type, item_id)


def _item_key(item: ActivityItem) -> ItemKey:
    """Return a unique key for an ActivityItem."""
    return (item.item_type, item.item_id)


class ActivityTable(DataTable[str | Text]):
    """Flat table widget for the document browser.

    Each row maps to an ActivityItem. The table preserves cursor
    position across periodic refreshes by tracking item keys.
    """

    DOUBLE_CLICK_THRESHOLD = 0.4

    class DoubleClicked(Message):
        """Posted when a row is double-clicked."""

        def __init__(self, item: ActivityItem) -> None:
            self.item = item
            super().__init__()

    class ItemHighlighted(Message):
        """Posted when cursor moves to a new row."""

        def __init__(self, item: ActivityItem | None) -> None:
            self.item = item
            super().__init__()

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._items: list[ActivityItem] = []
        self._key_to_item: dict[ItemKey, ActivityItem] = {}
        self._last_click_time: float = 0.0
        self._last_click_row: str | None = None
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.show_header = False

    def on_mount(self) -> None:
        """Set up columns."""
        self.add_column("icon", key="icon", width=3)
        self.add_column("title", key="title")
        self.add_column("time", key="time", width=4)
        self.add_column("id", key="id", width=7)

    def _format_time(self, item: ActivityItem) -> str:
        """Format timestamp as compact relative time."""
        from .activity_view import format_time_ago

        return format_time_ago(item.timestamp)

    def _row_key(self, item: ActivityItem) -> str:
        """Generate a string row key from an item key."""
        key = _item_key(item)
        return f"{key[0]}:{key[1]}"

    def populate(self, items: list[ActivityItem]) -> None:
        """Full load: clear table and add all items."""
        self._items = items
        self._key_to_item = {_item_key(item): item for item in items}
        self.clear()

        for item in items:
            self._add_item_row(item)

    def _add_item_row(self, item: ActivityItem) -> None:
        """Add a single item row to the table."""
        icon = item.type_icon
        title = item.title.replace("\n", " ").strip()
        if len(title) > 80:
            title = title[:77] + "..."
        time_str = self._format_time(item)
        id_str = f"#{item.doc_id}" if item.doc_id else ""

        title_text = Text(title)

        # Add doc_type badge for wiki documents
        if isinstance(item, DocumentItem) and item.doc_type == "wiki":
            badge = Text(" wiki ", style="bold magenta")
            title_text = Text.assemble(badge, " ", title_text)

        self.add_row(
            icon,
            title_text,
            Text(time_str, style="dim"),
            Text(id_str, style="dim"),
            key=self._row_key(item),
        )

    def refresh_items(self, items: list[ActivityItem]) -> None:
        """Diff-based refresh: update existing rows, add/remove as needed.

        Preserves cursor position by re-selecting the same item key.
        """
        # Remember current selection
        current_key: str | None = None
        try:
            if self.cursor_row is not None and self.row_count > 0:
                current_key = str(self.ordered_rows[self.cursor_row].key.value)
        except (IndexError, AttributeError):
            pass

        # Check if structural change (adds/removes/reorder)
        old_order = [self._row_key(item) for item in self._items]
        new_order = [self._row_key(item) for item in items]

        if old_order != new_order:
            # Structural change — repopulate
            self.populate(items)
            # Restore cursor
            if current_key:
                self._select_row_by_key(current_key)
            return

        # No structural change — update values in place
        self._items = items
        self._key_to_item = {_item_key(item): item for item in items}

        for item in items:
            row_key = self._row_key(item)
            try:
                icon = item.type_icon
                title = item.title.replace("\n", " ").strip()
                if len(title) > 80:
                    title = title[:77] + "..."
                time_str = self._format_time(item)
                id_str = f"#{item.doc_id}" if item.doc_id else ""

                title_text = Text(title)

                self.update_cell(row_key, "icon", icon)
                self.update_cell(row_key, "title", title_text)
                self.update_cell(row_key, "time", Text(time_str, style="dim"))
                self.update_cell(row_key, "id", Text(id_str, style="dim"))
            except Exception:
                # Row may not exist yet
                pass

    def _select_row_by_key(self, key: str) -> None:
        """Move cursor to a row by its key string."""
        for i, row in enumerate(self.ordered_rows):
            if str(row.key.value) == key:
                self.move_cursor(row=i)
                return

    def get_selected_item(self) -> ActivityItem | None:
        """Get the ActivityItem for the currently highlighted row."""
        try:
            if self.cursor_row is None or self.row_count == 0:
                return None
            row_key = str(self.ordered_rows[self.cursor_row].key.value)
            # Parse key back to item_type:item_id
            parts = row_key.split(":", 1)
            if len(parts) == 2:
                item_type, item_id_str = parts
                item_key = (item_type, int(item_id_str))
                return self._key_to_item.get(item_key)
        except (IndexError, AttributeError, ValueError):
            pass
        return None

    def find_row_by_doc_id(self, doc_id: int) -> int | None:
        """Find row index for a document ID."""
        for i, row in enumerate(self.ordered_rows):
            key_str = str(row.key.value)
            if key_str == f"document:{doc_id}":
                return i
        return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Forward row highlight as ItemHighlighted message."""
        item = self.get_selected_item()
        self.post_message(self.ItemHighlighted(item))

    async def _on_click(self, event: Click) -> None:
        """Handle double-click detection."""
        current_time = time.monotonic()

        # Get clicked row
        try:
            meta = event.style.meta
            row_index = meta.get("row", -1) if meta else -1
        except Exception:
            await super()._on_click(event)
            return

        if row_index < 0:
            await super()._on_click(event)
            return

        try:
            row_key = str(self.ordered_rows[row_index].key.value)
        except (IndexError, AttributeError):
            await super()._on_click(event)
            return

        time_since_last = current_time - self._last_click_time

        if self._last_click_row == row_key and time_since_last < self.DOUBLE_CLICK_THRESHOLD:
            # Double-click
            item = self.get_selected_item()
            if item:
                self.post_message(self.DoubleClicked(item))
            self._last_click_time = 0.0
            self._last_click_row = None
            event.stop()
        else:
            self._last_click_time = current_time
            self._last_click_row = row_key
            await super()._on_click(event)
