"""
Test harness for browser testing.

Provides a lightweight wrapper for testing browser widgets without
the full Textual runtime. Simulates key presses, tracks state, and
provides assertion helpers.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from ..panels import ListPanel, ListItem


class BrowserTestHarness:
    """Test harness for testing browsers without full Textual runtime.

    This harness wraps a browser widget and provides utilities for:
    - Mounting with mock panels
    - Simulating key presses
    - Accessing and asserting state
    - Tracking message history

    Example:
        ```python
        @pytest.fixture
        def harness():
            browser = MyBrowser()
            return BrowserTestHarness(browser)

        @pytest.mark.asyncio
        async def test_navigation(harness):
            await harness.mount()
            await harness.press("j")
            assert harness.get_selected_index() == 1
        ```
    """

    # Standard action mappings for vim-style navigation
    KEY_ACTIONS = {
        "j": "cursor_down",
        "k": "cursor_up",
        "g": "cursor_top",
        "G": "cursor_bottom",
        "enter": "activate_item",
        "r": "refresh",
        "/": "search",
        "?": "show_help",
        "escape": "cancel",
        "q": "quit",
    }

    def __init__(self, browser: Any):
        """Initialize harness with a browser instance.

        Args:
            browser: The browser widget to test
        """
        self.browser = browser
        self._app: Optional[MagicMock] = None
        self._mounted = False
        self._messages: List[Any] = []
        self._items: List[Dict[str, Any]] = []
        self._selected_index: int = 0

        # Setup message capturing
        self._setup_message_capture()

    def _setup_message_capture(self) -> None:
        """Setup message capturing on the browser."""
        original_post = getattr(self.browser, "post_message", None)

        def capture_message(msg):
            self._messages.append(msg)
            if original_post:
                return original_post(msg)

        self.browser.post_message = capture_message

    async def mount(self, items: Optional[List[Dict]] = None) -> None:
        """Mount the browser and optionally set items.

        Args:
            items: Optional list of items to use instead of load_items()
        """
        # Mock the app if needed - use object.__setattr__ to bypass property
        if self._app is None:
            self._app = MagicMock()
            self._app.notify = MagicMock()
            self._app.exit = MagicMock()
            try:
                # Try normal assignment first
                self.browser.app = self._app
            except AttributeError:
                # Widget.app is a property, use object.__setattr__
                object.__setattr__(self.browser, "_app", self._app)

        # Override load_items if items provided
        if items is not None:
            self._items = items
            if hasattr(self.browser, "load_items"):
                self.browser.load_items = AsyncMock(return_value=items)

        # Skip on_mount for now since it requires full Textual runtime
        # Instead, simulate the initialization
        self._mounted = True

    async def press(self, key: str) -> None:
        """Simulate a key press.

        Args:
            key: Key to press (e.g., "j", "k", "enter", "escape")
        """
        # Get action name from key
        action = self.KEY_ACTIONS.get(key, key)

        # Try to find action method on browser
        method_name = f"action_{action}"
        method = getattr(self.browser, method_name, None)

        if method:
            result = method()
            if hasattr(result, "__await__"):
                await result
        else:
            # Try to dispatch to focused panel
            await self._dispatch_to_panel(action)

    async def _dispatch_to_panel(self, action: str) -> None:
        """Dispatch action to focused panel."""
        # Try list panel first
        try:
            list_panel = self.browser.query_one(ListPanel)
            method = getattr(list_panel, f"action_{action}", None)
            if method:
                result = method()
                if hasattr(result, "__await__"):
                    await result
                return
        except Exception:
            pass

    async def type_text(self, text: str) -> None:
        """Simulate typing text.

        Args:
            text: Text to type
        """
        for char in text:
            await self.press(char)

    def get_selected_index(self) -> int:
        """Get the currently selected index."""
        # Try to get from browser's internal state
        if hasattr(self.browser, "_selected_index"):
            return self.browser._selected_index

        # Try to get from list panel
        try:
            list_panel = self.browser.query_one(ListPanel)
            return list_panel.get_selected_index() or 0
        except Exception:
            return self._selected_index

    def get_selected_item(self) -> Optional[Dict]:
        """Get the currently selected item."""
        idx = self.get_selected_index()

        # Try browser items
        if hasattr(self.browser, "_items"):
            items = self.browser._items
            if 0 <= idx < len(items):
                return items[idx]

        # Try list panel
        try:
            list_panel = self.browser.query_one(ListPanel)
            item = list_panel.get_selected_item()
            if item:
                return {"id": item.id, **dict(zip(["col" + str(i) for i in range(len(item.values))], item.values))}
        except Exception:
            pass

        return None

    def get_items(self) -> List[Dict]:
        """Get all items in the browser."""
        if hasattr(self.browser, "_items"):
            return self.browser._items

        try:
            list_panel = self.browser.query_one(ListPanel)
            return [{"id": item.id, "values": item.values, "data": item.data}
                    for item in list_panel.items]
        except Exception:
            return []

    def get_preview_content(self) -> str:
        """Get the current preview content."""
        # Try browser state
        if hasattr(self.browser, "_preview_content"):
            return self.browser._preview_content

        # Try preview panel
        try:
            from ..panels import PreviewPanel
            preview = self.browser.query_one(PreviewPanel)
            return preview.get_content()
        except Exception:
            return ""

    def get_status_text(self) -> str:
        """Get the current status bar text."""
        if hasattr(self.browser, "_status_text"):
            return self.browser._status_text

        try:
            list_panel = self.browser.query_one(ListPanel)
            return f"{list_panel.filtered_count}/{list_panel.item_count} items"
        except Exception:
            return ""

    def get_messages(self, message_type: Optional[type] = None) -> List[Any]:
        """Get captured messages, optionally filtered by type.

        Args:
            message_type: Optional message class to filter by

        Returns:
            List of messages
        """
        if message_type is None:
            return self._messages

        return [m for m in self._messages if isinstance(m, message_type)]

    def clear_messages(self) -> None:
        """Clear captured messages."""
        self._messages.clear()

    # =========================================================================
    # Assertion Helpers
    # =========================================================================

    def assert_item_count(self, expected: int) -> None:
        """Assert the number of items.

        Args:
            expected: Expected item count

        Raises:
            AssertionError: If count doesn't match
        """
        actual = len(self.get_items())
        assert actual == expected, f"Expected {expected} items, got {actual}"

    def assert_selected(self, index: int) -> None:
        """Assert the selected index.

        Args:
            index: Expected selected index

        Raises:
            AssertionError: If index doesn't match
        """
        actual = self.get_selected_index()
        assert actual == index, f"Expected selection at {index}, got {actual}"

    def assert_preview_contains(self, text: str) -> None:
        """Assert the preview contains text.

        Args:
            text: Text expected in preview

        Raises:
            AssertionError: If text not in preview
        """
        content = self.get_preview_content()
        assert text in content, f"Expected '{text}' in preview, got: {content[:100]}"

    def assert_status_contains(self, text: str) -> None:
        """Assert the status bar contains text.

        Args:
            text: Text expected in status

        Raises:
            AssertionError: If text not in status
        """
        status = self.get_status_text()
        assert text in status, f"Expected '{text}' in status, got: {status}"

    def assert_message_posted(self, message_type: type) -> None:
        """Assert a message of given type was posted.

        Args:
            message_type: Message class to check for

        Raises:
            AssertionError: If no matching message found
        """
        matching = self.get_messages(message_type)
        assert len(matching) > 0, f"Expected {message_type.__name__} message, none found"

    def assert_no_message(self, message_type: type) -> None:
        """Assert no message of given type was posted.

        Args:
            message_type: Message class to check for absence

        Raises:
            AssertionError: If matching message found
        """
        matching = self.get_messages(message_type)
        assert len(matching) == 0, f"Expected no {message_type.__name__} message, found {len(matching)}"
