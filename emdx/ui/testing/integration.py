"""
Integration test utilities for browser testing with Textual's Pilot.

Provides utilities for running real Textual App tests with pytest-asyncio,
including snapshot testing, async message flow helpers, and panel query shortcuts.

Example:
    ```python
    import pytest
    from emdx.ui.testing import PilotIntegrationHarness, create_test_app

    @pytest.fixture
    async def harness():
        from emdx.ui.browsers.example_browser import ExampleBrowser
        async with PilotIntegrationHarness.create(ExampleBrowser) as h:
            yield h

    @pytest.mark.asyncio
    async def test_navigation(harness):
        await harness.press("j")
        assert harness.get_selected_index() == 1
    ```
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widget import Widget

from ..panels import ListPanel, ListItem, PreviewPanel

T = TypeVar("T", bound=Widget)


# =============================================================================
# Test App Wrapper
# =============================================================================


class TestApp(App, Generic[T]):
    """A minimal test app that wraps a browser widget.

    This app provides a simple container for testing browser widgets
    with the Textual pilot interface.
    """

    DEFAULT_CSS = """
    Screen {
        layout: vertical;
        height: 100%;
    }

    #test-browser {
        height: 100%;
    }
    """

    def __init__(
        self,
        browser_class: Type[T],
        browser_args: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Initialize test app with browser class.

        Args:
            browser_class: The browser widget class to test
            browser_args: Optional kwargs to pass to browser constructor
            **kwargs: Passed to App constructor
        """
        super().__init__(**kwargs)
        self._browser_class = browser_class
        self._browser_args = browser_args or {}

    def compose(self) -> ComposeResult:
        """Compose the test app with the browser widget."""
        yield self._browser_class(id="test-browser", **self._browser_args)


def create_test_app(
    browser_class: Type[T],
    browser_args: Optional[Dict[str, Any]] = None,
) -> TestApp[T]:
    """Create a test app wrapping a browser widget.

    Args:
        browser_class: The browser widget class to test
        browser_args: Optional kwargs to pass to browser constructor

    Returns:
        TestApp instance ready for testing
    """
    return TestApp(browser_class, browser_args)


# =============================================================================
# Widget State Snapshots
# =============================================================================


@dataclass
class WidgetSnapshot:
    """A snapshot of a widget's state at a point in time.

    Used for comparing widget states before and after operations.
    """

    widget_id: str
    widget_class: str
    properties: Dict[str, Any] = field(default_factory=dict)
    children: List["WidgetSnapshot"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "id": self.widget_id,
            "class": self.widget_class,
            "properties": self.properties,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WidgetSnapshot":
        """Create snapshot from dictionary."""
        return cls(
            widget_id=data["id"],
            widget_class=data["class"],
            properties=data.get("properties", {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    def diff(self, other: "WidgetSnapshot") -> List[str]:
        """Compare with another snapshot and return differences.

        Returns:
            List of difference descriptions
        """
        diffs = []

        if self.widget_id != other.widget_id:
            diffs.append(f"ID changed: {self.widget_id} -> {other.widget_id}")

        if self.widget_class != other.widget_class:
            diffs.append(f"Class changed: {self.widget_class} -> {other.widget_class}")

        # Compare properties
        all_keys = set(self.properties.keys()) | set(other.properties.keys())
        for key in all_keys:
            old_val = self.properties.get(key)
            new_val = other.properties.get(key)
            if old_val != new_val:
                diffs.append(f"Property '{key}' changed: {old_val} -> {new_val}")

        # Compare children count
        if len(self.children) != len(other.children):
            diffs.append(
                f"Children count changed: {len(self.children)} -> {len(other.children)}"
            )

        return diffs


class SnapshotManager:
    """Manager for capturing and comparing widget state snapshots."""

    def __init__(self, snapshot_dir: Optional[Path] = None):
        """Initialize snapshot manager.

        Args:
            snapshot_dir: Directory to save/load snapshots (optional)
        """
        self.snapshot_dir = snapshot_dir

    def capture(
        self,
        widget: Widget,
        properties: Optional[List[str]] = None,
        recursive: bool = False,
    ) -> WidgetSnapshot:
        """Capture a snapshot of widget state.

        Args:
            widget: Widget to capture
            properties: List of property names to capture (None for defaults)
            recursive: Whether to capture child widgets

        Returns:
            WidgetSnapshot of current state
        """
        # Default properties to capture
        if properties is None:
            properties = ["display", "visible", "disabled", "has_focus"]

        # Capture properties
        props = {}
        for prop in properties:
            try:
                value = getattr(widget, prop, None)
                # Make sure value is serializable
                if isinstance(value, (str, int, float, bool, type(None))):
                    props[prop] = value
                elif hasattr(value, "name"):  # Enum-like
                    props[prop] = value.name
                else:
                    props[prop] = str(value)
            except Exception:
                pass

        # Capture children if recursive
        children = []
        if recursive:
            for child in widget.children:
                if isinstance(child, Widget):
                    children.append(self.capture(child, properties, recursive=True))

        return WidgetSnapshot(
            widget_id=widget.id or "",
            widget_class=widget.__class__.__name__,
            properties=props,
            children=children,
        )

    def capture_list_panel(self, panel: ListPanel) -> WidgetSnapshot:
        """Capture snapshot of ListPanel state.

        Args:
            panel: ListPanel to capture

        Returns:
            WidgetSnapshot with list-specific properties
        """
        properties = {
            "item_count": panel.item_count,
            "filtered_count": panel.filtered_count,
            "mode": panel.mode,
            "search_query": panel.search_query,
            "selected_index": panel.get_selected_index(),
            "has_more": panel.has_more,
        }

        # Capture first few item IDs for comparison
        items = panel.filtered_items[:5] if panel.filtered_items else []
        properties["first_item_ids"] = [item.id for item in items]

        return WidgetSnapshot(
            widget_id=panel.id or "",
            widget_class="ListPanel",
            properties=properties,
        )

    def capture_preview_panel(self, panel: PreviewPanel) -> WidgetSnapshot:
        """Capture snapshot of PreviewPanel state.

        Args:
            panel: PreviewPanel to capture

        Returns:
            WidgetSnapshot with preview-specific properties
        """
        properties = {
            "mode": panel.mode.name if hasattr(panel.mode, "name") else str(panel.mode),
            "has_content": panel.has_content,
            "title": panel.get_title(),
            "content_length": len(panel.get_content()),
            "content_preview": panel.get_content()[:100] if panel.get_content() else "",
        }

        return WidgetSnapshot(
            widget_id=panel.id or "",
            widget_class="PreviewPanel",
            properties=properties,
        )

    def save_snapshot(self, snapshot: WidgetSnapshot, name: str) -> None:
        """Save snapshot to file.

        Args:
            snapshot: Snapshot to save
            name: Name for the snapshot file
        """
        if self.snapshot_dir is None:
            raise ValueError("snapshot_dir not set")

        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_dir / f"{name}.json"
        path.write_text(json.dumps(snapshot.to_dict(), indent=2))

    def load_snapshot(self, name: str) -> WidgetSnapshot:
        """Load snapshot from file.

        Args:
            name: Name of the snapshot file

        Returns:
            Loaded WidgetSnapshot
        """
        if self.snapshot_dir is None:
            raise ValueError("snapshot_dir not set")

        path = self.snapshot_dir / f"{name}.json"
        data = json.loads(path.read_text())
        return WidgetSnapshot.from_dict(data)

    def assert_matches(
        self,
        snapshot: WidgetSnapshot,
        name: str,
        update: bool = False,
    ) -> None:
        """Assert snapshot matches saved snapshot.

        Args:
            snapshot: Current snapshot to compare
            name: Name of saved snapshot
            update: If True, update saved snapshot instead of comparing

        Raises:
            AssertionError: If snapshots don't match (and update=False)
        """
        if self.snapshot_dir is None:
            raise ValueError("snapshot_dir not set")

        path = self.snapshot_dir / f"{name}.json"

        if update or not path.exists():
            self.save_snapshot(snapshot, name)
            return

        expected = self.load_snapshot(name)
        diffs = expected.diff(snapshot)

        if diffs:
            raise AssertionError(
                f"Snapshot '{name}' mismatch:\n" + "\n".join(f"  - {d}" for d in diffs)
            )


# =============================================================================
# Message Capture and Assertions
# =============================================================================


@dataclass
class CapturedMessage:
    """A captured message with metadata."""

    message: Any
    timestamp: float
    source_id: Optional[str] = None


class MessageCapture:
    """Utility for capturing and asserting on message flows."""

    def __init__(self):
        """Initialize message capture."""
        self._messages: List[CapturedMessage] = []
        self._start_time: float = 0

    def start(self) -> None:
        """Start capturing (resets capture)."""
        import time

        self._messages = []
        self._start_time = time.time()

    def record(self, message: Any, source_id: Optional[str] = None) -> None:
        """Record a message.

        Args:
            message: Message object to record
            source_id: Optional source widget ID
        """
        import time

        self._messages.append(
            CapturedMessage(
                message=message,
                timestamp=time.time() - self._start_time,
                source_id=source_id,
            )
        )

    @property
    def messages(self) -> List[CapturedMessage]:
        """Get all captured messages."""
        return list(self._messages)

    def get_by_type(self, message_type: type) -> List[CapturedMessage]:
        """Get messages of a specific type.

        Args:
            message_type: Type of messages to filter

        Returns:
            List of matching captured messages
        """
        return [m for m in self._messages if isinstance(m.message, message_type)]

    def assert_has_message(self, message_type: type, count: Optional[int] = None) -> None:
        """Assert at least one (or exact count) of message type was captured.

        Args:
            message_type: Expected message type
            count: Optional exact count to expect

        Raises:
            AssertionError: If assertion fails
        """
        matching = self.get_by_type(message_type)

        if count is not None:
            assert len(matching) == count, (
                f"Expected {count} {message_type.__name__} messages, "
                f"got {len(matching)}"
            )
        else:
            assert len(matching) > 0, f"Expected at least one {message_type.__name__} message"

    def assert_no_message(self, message_type: type) -> None:
        """Assert no messages of type were captured.

        Args:
            message_type: Message type to check for absence

        Raises:
            AssertionError: If any matching messages found
        """
        matching = self.get_by_type(message_type)
        assert len(matching) == 0, (
            f"Expected no {message_type.__name__} messages, "
            f"got {len(matching)}"
        )

    def assert_order(self, *message_types: type) -> None:
        """Assert messages occurred in a specific order.

        Args:
            *message_types: Message types in expected order

        Raises:
            AssertionError: If order doesn't match
        """
        type_indices = []
        for msg_type in message_types:
            for idx, captured in enumerate(self._messages):
                if isinstance(captured.message, msg_type):
                    type_indices.append((idx, msg_type))
                    break
            else:
                raise AssertionError(f"Message type {msg_type.__name__} not found")

        for i in range(len(type_indices) - 1):
            current_idx, current_type = type_indices[i]
            next_idx, next_type = type_indices[i + 1]
            assert current_idx < next_idx, (
                f"{current_type.__name__} (index {current_idx}) should come "
                f"before {next_type.__name__} (index {next_idx})"
            )

    def clear(self) -> None:
        """Clear captured messages."""
        self._messages = []


# =============================================================================
# Mock Data Generators
# =============================================================================


class MockDataGenerator:
    """Generator for common test data scenarios."""

    @staticmethod
    def list_items(
        count: int = 10,
        statuses: Optional[List[str]] = None,
        with_content: bool = True,
    ) -> List[ListItem]:
        """Generate ListItem instances for testing.

        Args:
            count: Number of items to generate
            statuses: List of status values to cycle through
            with_content: Whether to include content in data dict

        Returns:
            List of ListItem instances
        """
        if statuses is None:
            statuses = ["Active", "Pending", "Done", "Error"]

        items = []
        for i in range(1, count + 1):
            status = statuses[(i - 1) % len(statuses)]
            data = {
                "description": f"Description for item {i}",
            }
            if with_content:
                data["content"] = f"# Item {i}\n\nThis is the content for item {i}.\n\n## Details\n\nStatus: {status}"

            items.append(
                ListItem(
                    id=i,
                    values=[str(i), f"Item {i}", status],
                    data=data,
                )
            )

        return items

    @staticmethod
    def documents(count: int = 5) -> List[ListItem]:
        """Generate document-like ListItems.

        Args:
            count: Number of documents to generate

        Returns:
            List of document ListItems
        """
        tags = ["python", "rust", "docs", "notes", "todo"]
        items = []

        for i in range(1, count + 1):
            tag = tags[(i - 1) % len(tags)]
            items.append(
                ListItem(
                    id=i,
                    values=[str(i), tag, f"Document {i}: Getting Started with {tag.title()}"],
                    data={
                        "content": f"# {tag.title()} Guide\n\nThis is a guide for {tag}.\n\n## Introduction\n\nWelcome to the {tag} guide.",
                        "tags": [tag],
                        "created": f"2024-01-{i:02d}",
                    },
                )
            )

        return items

    @staticmethod
    def searchable_items() -> List[ListItem]:
        """Generate items specifically designed for search testing.

        Returns:
            List of items with distinct searchable content
        """
        return [
            ListItem(
                id=1,
                values=["1", "Alpha Project", "Active"],
                data={"content": "# Alpha\n\nThis is the alpha project."},
            ),
            ListItem(
                id=2,
                values=["2", "Beta Release", "Pending"],
                data={"content": "# Beta\n\nThe beta release notes."},
            ),
            ListItem(
                id=3,
                values=["3", "Gamma Testing", "Active"],
                data={"content": "# Gamma\n\nGamma testing procedures."},
            ),
            ListItem(
                id=4,
                values=["4", "Alpha Documentation", "Done"],
                data={"content": "# Alpha Docs\n\nDocumentation for alpha."},
            ),
            ListItem(
                id=5,
                values=["5", "Delta Config", "Error"],
                data={"content": "# Delta\n\nDelta configuration files."},
            ),
        ]


# =============================================================================
# Pilot Integration Harness
# =============================================================================


class PilotIntegrationHarness(Generic[T]):
    """Integration test harness using Textual's Pilot.

    This harness wraps a browser widget in a test app and provides
    convenient methods for testing with the Pilot interface.

    Example:
        ```python
        async with PilotIntegrationHarness.create(ExampleBrowser) as harness:
            await harness.press("j")
            assert harness.get_selected_index() == 1

            await harness.type_text("search term")
            harness.assert_item_count(3)
        ```
    """

    def __init__(
        self,
        app: TestApp[T],
        pilot: Pilot,
    ):
        """Initialize harness with app and pilot.

        Use PilotIntegrationHarness.create() instead of direct instantiation.

        Args:
            app: The test app instance
            pilot: The Textual pilot
        """
        self.app = app
        self.pilot = pilot
        self._messages = MessageCapture()
        self._snapshots = SnapshotManager()

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        browser_class: Type[T],
        browser_args: Optional[Dict[str, Any]] = None,
        snapshot_dir: Optional[Path] = None,
    ):
        """Create and run a harness as an async context manager.

        Args:
            browser_class: Browser widget class to test
            browser_args: Optional args for browser constructor
            snapshot_dir: Optional directory for snapshot storage

        Yields:
            PilotIntegrationHarness instance
        """
        app = create_test_app(browser_class, browser_args)

        try:
            async with app.run_test() as pilot:
                harness = cls(app, pilot)
                if snapshot_dir:
                    harness._snapshots.snapshot_dir = snapshot_dir
                harness._messages.start()
                yield harness
        except ValueError as e:
            # Ignore context token errors during teardown
            # These can occur when pytest-asyncio's event loop handling
            # conflicts with Textual's context management
            if "was created in a different Context" not in str(e):
                raise

    # -------------------------------------------------------------------------
    # Browser Access
    # -------------------------------------------------------------------------

    @property
    def browser(self) -> T:
        """Get the browser widget under test."""
        return self.app.query_one("#test-browser")

    # -------------------------------------------------------------------------
    # Panel Query Shortcuts
    # -------------------------------------------------------------------------

    def get_list_panel(self, panel_id: Optional[str] = None) -> ListPanel:
        """Get a ListPanel from the browser.

        Args:
            panel_id: Optional panel ID to query (finds first if None)

        Returns:
            The ListPanel instance
        """
        if panel_id:
            return self.browser.query_one(f"#{panel_id}", ListPanel)
        return self.browser.query_one(ListPanel)

    def get_preview_panel(self, panel_id: Optional[str] = None) -> PreviewPanel:
        """Get a PreviewPanel from the browser.

        Args:
            panel_id: Optional panel ID to query (finds first if None)

        Returns:
            The PreviewPanel instance
        """
        if panel_id:
            return self.browser.query_one(f"#{panel_id}", PreviewPanel)
        return self.browser.query_one(PreviewPanel)

    # -------------------------------------------------------------------------
    # Input Simulation
    # -------------------------------------------------------------------------

    async def press(self, key: str) -> None:
        """Press a key.

        Args:
            key: Key to press (e.g., "j", "k", "enter", "escape")
        """
        await self.pilot.press(key)

    async def press_keys(self, *keys: str) -> None:
        """Press multiple keys in sequence.

        Args:
            *keys: Keys to press
        """
        for key in keys:
            await self.pilot.press(key)

    async def type_text(self, text: str) -> None:
        """Type text character by character.

        Args:
            text: Text to type
        """
        for char in text:
            await self.pilot.press(char)

    async def wait_for_idle(self, timeout: float = 1.0) -> None:
        """Wait for app to become idle.

        Args:
            timeout: Maximum time to wait in seconds
        """
        await self.pilot.pause(timeout)

    async def click(self, selector: str) -> None:
        """Click on a widget by selector.

        Args:
            selector: CSS selector for the widget
        """
        widget = self.app.query_one(selector)
        await self.pilot.click(widget.__class__, offset=(0, 0))

    # -------------------------------------------------------------------------
    # State Inspection
    # -------------------------------------------------------------------------

    def get_selected_index(self) -> Optional[int]:
        """Get the currently selected index in the list panel."""
        try:
            panel = self.get_list_panel()
            return panel.get_selected_index()
        except Exception:
            return None

    def get_selected_item(self) -> Optional[ListItem]:
        """Get the currently selected item."""
        try:
            panel = self.get_list_panel()
            return panel.get_selected_item()
        except Exception:
            return None

    def get_items(self) -> List[ListItem]:
        """Get all items in the list panel."""
        try:
            panel = self.get_list_panel()
            return panel.filtered_items
        except Exception:
            return []

    def get_item_count(self) -> int:
        """Get the number of items in the list."""
        try:
            panel = self.get_list_panel()
            return panel.filtered_count
        except Exception:
            return 0

    def get_preview_content(self) -> str:
        """Get the current preview panel content."""
        try:
            panel = self.get_preview_panel()
            return panel.get_content()
        except Exception:
            return ""

    def get_preview_title(self) -> str:
        """Get the current preview panel title."""
        try:
            panel = self.get_preview_panel()
            return panel.get_title()
        except Exception:
            return ""

    def get_list_mode(self) -> str:
        """Get the current list panel mode."""
        try:
            panel = self.get_list_panel()
            return panel.mode
        except Exception:
            return ""

    def get_search_query(self) -> str:
        """Get the current search query."""
        try:
            panel = self.get_list_panel()
            return panel.search_query
        except Exception:
            return ""

    # -------------------------------------------------------------------------
    # Snapshot Testing
    # -------------------------------------------------------------------------

    def capture_list_snapshot(self) -> WidgetSnapshot:
        """Capture a snapshot of the list panel state."""
        panel = self.get_list_panel()
        return self._snapshots.capture_list_panel(panel)

    def capture_preview_snapshot(self) -> WidgetSnapshot:
        """Capture a snapshot of the preview panel state."""
        panel = self.get_preview_panel()
        return self._snapshots.capture_preview_panel(panel)

    def assert_list_matches_snapshot(self, name: str, update: bool = False) -> None:
        """Assert list panel matches a saved snapshot.

        Args:
            name: Snapshot name
            update: If True, update the snapshot
        """
        snapshot = self.capture_list_snapshot()
        self._snapshots.assert_matches(snapshot, f"list_{name}", update)

    def assert_preview_matches_snapshot(self, name: str, update: bool = False) -> None:
        """Assert preview panel matches a saved snapshot.

        Args:
            name: Snapshot name
            update: If True, update the snapshot
        """
        snapshot = self.capture_preview_snapshot()
        self._snapshots.assert_matches(snapshot, f"preview_{name}", update)

    # -------------------------------------------------------------------------
    # Message Testing
    # -------------------------------------------------------------------------

    @property
    def messages(self) -> MessageCapture:
        """Get the message capture utility."""
        return self._messages

    # -------------------------------------------------------------------------
    # Assertion Helpers
    # -------------------------------------------------------------------------

    def assert_selected_index(self, expected: int) -> None:
        """Assert the selected index.

        Args:
            expected: Expected index

        Raises:
            AssertionError: If index doesn't match
        """
        actual = self.get_selected_index()
        assert actual == expected, f"Expected selected index {expected}, got {actual}"

    def assert_item_count(self, expected: int) -> None:
        """Assert the number of items.

        Args:
            expected: Expected count

        Raises:
            AssertionError: If count doesn't match
        """
        actual = self.get_item_count()
        assert actual == expected, f"Expected {expected} items, got {actual}"

    def assert_preview_contains(self, text: str) -> None:
        """Assert the preview contains specific text.

        Args:
            text: Expected text

        Raises:
            AssertionError: If text not found
        """
        content = self.get_preview_content()
        assert text in content, f"Expected '{text}' in preview, got: {content[:200]}"

    def assert_preview_title(self, expected: str) -> None:
        """Assert the preview title.

        Args:
            expected: Expected title

        Raises:
            AssertionError: If title doesn't match
        """
        actual = self.get_preview_title()
        assert actual == expected, f"Expected title '{expected}', got '{actual}'"

    def assert_list_mode(self, expected: str) -> None:
        """Assert the list panel mode.

        Args:
            expected: Expected mode (e.g., "NORMAL", "SEARCH")

        Raises:
            AssertionError: If mode doesn't match
        """
        actual = self.get_list_mode()
        assert actual == expected, f"Expected mode '{expected}', got '{actual}'"

    def assert_search_query(self, expected: str) -> None:
        """Assert the search query.

        Args:
            expected: Expected query

        Raises:
            AssertionError: If query doesn't match
        """
        actual = self.get_search_query()
        assert actual == expected, f"Expected query '{expected}', got '{actual}'"


# =============================================================================
# Async Test Helpers
# =============================================================================


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 1.0,
    interval: float = 0.05,
    message: str = "Condition not met",
) -> None:
    """Wait for a condition to become true.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        message: Error message if timeout

    Raises:
        TimeoutError: If condition not met within timeout
    """
    elapsed = 0.0
    while elapsed < timeout:
        if condition():
            return
        await asyncio.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"{message} (waited {timeout}s)")


async def wait_for_message(
    capture: MessageCapture,
    message_type: type,
    timeout: float = 1.0,
) -> Any:
    """Wait for a specific message type to be captured.

    Args:
        capture: MessageCapture instance
        message_type: Type of message to wait for
        timeout: Maximum time to wait

    Returns:
        The captured message

    Raises:
        TimeoutError: If message not received within timeout
    """
    initial_count = len(capture.get_by_type(message_type))

    await wait_for_condition(
        lambda: len(capture.get_by_type(message_type)) > initial_count,
        timeout=timeout,
        message=f"No {message_type.__name__} message received",
    )

    messages = capture.get_by_type(message_type)
    return messages[-1].message


class AsyncTestContext:
    """Context manager for async test setup/teardown.

    Example:
        ```python
        async with AsyncTestContext() as ctx:
            ctx.add_cleanup(lambda: some_cleanup())
            # ... run tests ...
        # Cleanup runs automatically
        ```
    """

    def __init__(self):
        """Initialize test context."""
        self._cleanup_tasks: List[Callable] = []

    def add_cleanup(self, func: Callable) -> None:
        """Add a cleanup function to run on exit.

        Args:
            func: Cleanup function (can be sync or async)
        """
        self._cleanup_tasks.append(func)

    async def __aenter__(self) -> "AsyncTestContext":
        """Enter context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and run cleanup."""
        for task in reversed(self._cleanup_tasks):
            try:
                result = task()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Suppress cleanup errors
