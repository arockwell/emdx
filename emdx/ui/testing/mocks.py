"""
Mock panel implementations for testing.

These mocks simulate panel behavior without Textual dependencies,
allowing for fast unit tests of browser logic.
"""

from typing import Any, Callable, Dict, List, Optional


class MockListPanel:
    """Mock ListPanel for testing.

    Simulates ListPanel behavior without Textual widgets.
    Tracks all method calls for assertion.

    Example:
        ```python
        mock = MockListPanel(columns=["ID", "Name"])
        mock.set_items([{"id": 1, "name": "Test"}])
        assert mock.get_selected()["id"] == 1
        assert len(mock.set_items_calls) == 1
        ```
    """

    def __init__(
        self,
        columns: Optional[List[str]] = None,
        **kwargs,
    ):
        """Initialize mock list panel.

        Args:
            columns: Column names
            **kwargs: Ignored (for compatibility)
        """
        self.columns = columns or ["ID"]
        self._items: List[Dict] = []
        self._cursor_row: int = 0
        self.id = kwargs.get("id", "mock-list")
        self._filter_func: Optional[Callable] = None
        self._has_more: bool = False

        # Call tracking
        self.set_items_calls: List[List[Dict]] = []
        self.append_items_calls: List[List[Dict]] = []
        self.focus_calls: int = 0
        self.clear_calls: int = 0

    def set_items(self, items: List[Dict], has_more: bool = False) -> None:
        """Set items to display.

        Args:
            items: Items to display
            has_more: Whether more items available
        """
        self._items = list(items)
        self._has_more = has_more
        self.set_items_calls.append(items)
        if self._cursor_row >= len(items):
            self._cursor_row = max(0, len(items) - 1)

    def append_items(self, items: List[Dict], has_more: bool = False) -> None:
        """Append items to existing list.

        Args:
            items: Items to append
            has_more: Whether more items available
        """
        self._items.extend(items)
        self._has_more = has_more
        self.append_items_calls.append(items)

    def clear_items(self) -> None:
        """Clear all items."""
        self._items = []
        self._cursor_row = 0
        self.clear_calls += 1

    def get_selected(self) -> Optional[Dict]:
        """Get currently selected item."""
        if 0 <= self._cursor_row < len(self._items):
            return self._items[self._cursor_row]
        return None

    def get_selected_item(self) -> Optional[Dict]:
        """Alias for get_selected."""
        return self.get_selected()

    def get_selected_index(self) -> int:
        """Get index of selected item."""
        return self._cursor_row

    @property
    def cursor_row(self) -> int:
        """Current cursor row."""
        return self._cursor_row

    @property
    def items(self) -> List[Dict]:
        """All items."""
        return self._items

    @property
    def filtered_items(self) -> List[Dict]:
        """Filtered items (no filtering in mock)."""
        return self._items

    @property
    def item_count(self) -> int:
        """Total item count."""
        return len(self._items)

    @property
    def filtered_count(self) -> int:
        """Filtered item count."""
        return len(self._items)

    @property
    def has_more(self) -> bool:
        """Whether more items available."""
        return self._has_more

    def cursor_down(self) -> None:
        """Move cursor down."""
        if self._cursor_row < len(self._items) - 1:
            self._cursor_row += 1

    def cursor_up(self) -> None:
        """Move cursor up."""
        if self._cursor_row > 0:
            self._cursor_row -= 1

    def action_cursor_down(self) -> None:
        """Action wrapper for cursor_down."""
        self.cursor_down()

    def action_cursor_up(self) -> None:
        """Action wrapper for cursor_up."""
        self.cursor_up()

    def action_cursor_top(self) -> None:
        """Move to first item."""
        self._cursor_row = 0

    def action_cursor_bottom(self) -> None:
        """Move to last item."""
        if self._items:
            self._cursor_row = len(self._items) - 1

    def select_index(self, index: int) -> bool:
        """Select item at index.

        Args:
            index: Index to select

        Returns:
            True if valid index
        """
        if 0 <= index < len(self._items):
            self._cursor_row = index
            return True
        return False

    def select_item_by_id(self, item_id: Any) -> bool:
        """Select item by ID.

        Args:
            item_id: ID of item to select

        Returns:
            True if item found
        """
        for idx, item in enumerate(self._items):
            if item.get("id") == item_id:
                self._cursor_row = idx
                return True
        return False

    def focus(self) -> None:
        """Receive focus."""
        self.focus_calls += 1

    def save_state(self) -> Dict[str, Any]:
        """Save panel state."""
        return {
            "cursor_row": self._cursor_row,
            "item_count": len(self._items),
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        self._cursor_row = state.get("cursor_row", 0)


class MockPreviewPanel:
    """Mock PreviewPanel for testing.

    Simulates PreviewPanel behavior without Textual widgets.

    Example:
        ```python
        mock = MockPreviewPanel()
        await mock.show_content("# Hello World")
        assert mock.get_content() == "# Hello World"
        ```
    """

    def __init__(self, **kwargs):
        """Initialize mock preview panel."""
        self._content: str = ""
        self._title: str = ""
        self._mode: str = "EMPTY"
        self.id = kwargs.get("id", "mock-preview")

        # Call tracking
        self.show_content_calls: List[str] = []
        self.clear_calls: int = 0
        self.edit_mode_calls: int = 0
        self.selection_mode_calls: int = 0

    async def show_content(
        self,
        content: str,
        title: str = "",
        render_markdown: bool = True,
    ) -> None:
        """Display content.

        Args:
            content: Content to display
            title: Optional title
            render_markdown: Whether to render markdown
        """
        self._content = content
        self._title = title
        self._mode = "VIEWING" if content.strip() else "EMPTY"
        self.show_content_calls.append(content)

    async def show_empty(self, message: Optional[str] = None) -> None:
        """Show empty state."""
        self._content = ""
        self._title = ""
        self._mode = "EMPTY"
        self.clear_calls += 1

    async def enter_edit_mode(
        self,
        title: str = "",
        content: str = "",
        is_new: bool = False,
    ) -> None:
        """Enter edit mode."""
        self._title = title
        self._content = content
        self._mode = "EDITING"
        self.edit_mode_calls += 1

    async def exit_edit_mode(self, save: bool = False) -> None:
        """Exit edit mode."""
        self._mode = "VIEWING" if self._content else "EMPTY"

    async def enter_selection_mode(self, content: str = "") -> None:
        """Enter selection mode."""
        if content:
            self._content = content
        self._mode = "SELECTING"
        self.selection_mode_calls += 1

    async def exit_selection_mode(self) -> None:
        """Exit selection mode."""
        self._mode = "VIEWING" if self._content else "EMPTY"

    def get_content(self) -> str:
        """Get current content."""
        return self._content

    def get_title(self) -> str:
        """Get current title."""
        return self._title

    @property
    def mode(self) -> str:
        """Current mode."""
        return self._mode

    @property
    def has_content(self) -> bool:
        """Whether panel has content."""
        return bool(self._content.strip())

    def save_state(self) -> Dict[str, Any]:
        """Save panel state."""
        return {
            "mode": self._mode,
            "content": self._content,
            "title": self._title,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        self._mode = state.get("mode", "EMPTY")
        self._content = state.get("content", "")
        self._title = state.get("title", "")


class MockStatusPanel:
    """Mock StatusPanel for testing.

    Example:
        ```python
        mock = MockStatusPanel()
        mock.set_text("5 items loaded")
        assert mock.get_text() == "5 items loaded"
        ```
    """

    def __init__(self, **kwargs):
        """Initialize mock status panel."""
        self._text: str = ""
        self.id = kwargs.get("id", "mock-status")

        # Call tracking
        self.set_text_calls: List[str] = []

    def set_text(self, text: str) -> None:
        """Set status text.

        Args:
            text: Status text
        """
        self._text = text
        self.set_text_calls.append(text)

    def update(self, text: str) -> None:
        """Alias for set_text."""
        self.set_text(text)

    def get_text(self) -> str:
        """Get current status text."""
        return self._text

    def clear(self) -> None:
        """Clear status text."""
        self._text = ""

    def save_state(self) -> Dict[str, Any]:
        """Save panel state."""
        return {"text": self._text}

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        self._text = state.get("text", "")
