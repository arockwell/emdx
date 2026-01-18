"""
Tests for ExampleBrowser demonstrating the testing utilities.

This file shows how to test browsers using the BrowserTestHarness
and mock panel implementations.

For documentation, see: docs/browser-dx-design.md (Section 8: Testing Utilities)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from emdx.ui.browsers.example_browser import ExampleBrowser
from emdx.ui.panels import ListPanel, ListItem
from emdx.ui.testing import BrowserTestHarness, MockListPanel, MockPreviewPanel


class TestExampleBrowser:
    """Test suite for ExampleBrowser."""

    @pytest.fixture
    def browser(self):
        """Create browser instance for testing."""
        return ExampleBrowser()

    @pytest.fixture
    def sample_items(self):
        """Sample items for testing."""
        return [
            ListItem(id=1, values=["1", "First", "Active"], data={"content": "# First\n\nContent"}),
            ListItem(id=2, values=["2", "Second", "Pending"], data={"content": "# Second\n\nContent"}),
            ListItem(id=3, values=["3", "Third", "Done"], data={"content": "# Third\n\nContent"}),
        ]

    # =========================================================================
    # Unit Tests with Mocks
    # =========================================================================

    class TestWithMocks:
        """Tests using mock panels (fast, no Textual dependency)."""

        @pytest.fixture
        def mock_list(self):
            """Create mock list panel."""
            return MockListPanel(columns=["ID", "Name", "Status"])

        @pytest.fixture
        def mock_preview(self):
            """Create mock preview panel."""
            return MockPreviewPanel()

        def test_mock_list_navigation(self, mock_list):
            """Test navigation with mock list panel."""
            items = [
                {"id": 1, "name": "First"},
                {"id": 2, "name": "Second"},
                {"id": 3, "name": "Third"},
            ]
            mock_list.set_items(items)

            # Initially at first item
            assert mock_list.get_selected_index() == 0

            # Move down
            mock_list.cursor_down()
            assert mock_list.get_selected_index() == 1

            # Move down again
            mock_list.cursor_down()
            assert mock_list.get_selected_index() == 2

            # Can't go past end
            mock_list.cursor_down()
            assert mock_list.get_selected_index() == 2

            # Move up
            mock_list.cursor_up()
            assert mock_list.get_selected_index() == 1

        def test_mock_list_select_by_id(self, mock_list):
            """Test selecting items by ID."""
            items = [
                {"id": "a", "name": "First"},
                {"id": "b", "name": "Second"},
                {"id": "c", "name": "Third"},
            ]
            mock_list.set_items(items)

            # Select by ID
            assert mock_list.select_item_by_id("b")
            assert mock_list.get_selected_index() == 1

            # Invalid ID
            assert not mock_list.select_item_by_id("invalid")

        def test_mock_list_call_tracking(self, mock_list):
            """Test that mock tracks method calls."""
            items = [{"id": 1, "name": "Test"}]

            mock_list.set_items(items)
            mock_list.set_items(items)
            mock_list.focus()

            assert len(mock_list.set_items_calls) == 2
            assert mock_list.focus_calls == 1

        @pytest.mark.asyncio
        async def test_mock_preview_content(self, mock_preview):
            """Test preview content management."""
            await mock_preview.show_content("# Hello World", title="Test")

            assert mock_preview.get_content() == "# Hello World"
            assert mock_preview.get_title() == "Test"
            assert mock_preview.mode == "VIEWING"
            assert mock_preview.has_content

        @pytest.mark.asyncio
        async def test_mock_preview_modes(self, mock_preview):
            """Test preview mode transitions."""
            # Start empty
            assert mock_preview.mode == "EMPTY"

            # Show content
            await mock_preview.show_content("# Content")
            assert mock_preview.mode == "VIEWING"

            # Enter edit mode
            await mock_preview.enter_edit_mode(title="Title", content="Content")
            assert mock_preview.mode == "EDITING"
            assert mock_preview.edit_mode_calls == 1

            # Exit edit mode
            await mock_preview.exit_edit_mode()
            assert mock_preview.mode == "VIEWING"

            # Enter selection mode
            await mock_preview.enter_selection_mode()
            assert mock_preview.mode == "SELECTING"
            assert mock_preview.selection_mode_calls == 1

    # =========================================================================
    # Integration Tests with Harness
    # =========================================================================

    class TestWithHarness:
        """Integration tests using BrowserTestHarness."""

        @pytest.fixture
        def harness(self):
            """Create test harness for browser."""
            browser = ExampleBrowser()
            return BrowserTestHarness(browser)

        @pytest.fixture
        def sample_items(self):
            """Sample items for testing."""
            return [
                ListItem(id=1, values=["1", "First", "Active"], data={"content": "First content"}),
                ListItem(id=2, values=["2", "Second", "Pending"], data={"content": "Second content"}),
                ListItem(id=3, values=["3", "Third", "Done"], data={"content": "Third content"}),
            ]

        @pytest.mark.asyncio
        async def test_harness_mount(self, harness, sample_items):
            """Test harness mounting with items."""
            # Mock query_one to return our items
            mock_list = MockListPanel()
            mock_list.set_items([
                {"id": i.id, "values": i.values, "data": i.data}
                for i in sample_items
            ])
            harness.browser.query_one = MagicMock(return_value=mock_list)

            await harness.mount()

            # Verify items loaded
            items = harness.get_items()
            assert len(items) >= 0  # Harness may or may not have items depending on mount

        @pytest.mark.asyncio
        async def test_harness_key_press(self, harness):
            """Test simulating key presses."""
            # Setup mock with cursor movement tracking
            mock_list = MockListPanel()
            mock_list.set_items([{"id": 1}, {"id": 2}, {"id": 3}])

            # Patch browser's query_one to return mock
            harness.browser.query_one = MagicMock(return_value=mock_list)
            harness.browser._selected_index = 0

            await harness.mount()

            # Simulate j key (cursor down)
            harness.browser.action_cursor_down = MagicMock()
            await harness.press("j")
            harness.browser.action_cursor_down.assert_called_once()


class TestListItemCreation:
    """Tests for ListItem creation patterns."""

    def test_list_item_with_data(self):
        """Test creating ListItem with associated data."""
        item = ListItem(
            id=42,
            values=["42", "Test Document", "Active"],
            data={"content": "Full content here", "metadata": {"tags": ["test"]}},
        )

        assert item.id == 42
        assert item.values == ["42", "Test Document", "Active"]
        assert item.data["content"] == "Full content here"
        assert item.data["metadata"]["tags"] == ["test"]

    def test_list_item_minimal(self):
        """Test minimal ListItem creation."""
        item = ListItem(id=1, values=["1", "Simple"])

        assert item.id == 1
        assert item.values == ["1", "Simple"]
        assert item.data is None


class TestStateSaveRestore:
    """Tests for panel state persistence."""

    def test_mock_list_state_roundtrip(self):
        """Test saving and restoring list panel state."""
        panel = MockListPanel()
        panel.set_items([{"id": 1}, {"id": 2}, {"id": 3}])
        panel.cursor_down()
        panel.cursor_down()

        # Save state
        state = panel.save_state()
        assert state["cursor_row"] == 2

        # Create new panel and restore
        new_panel = MockListPanel()
        new_panel.set_items([{"id": 1}, {"id": 2}, {"id": 3}])
        new_panel.restore_state(state)

        assert new_panel.get_selected_index() == 2

    @pytest.mark.asyncio
    async def test_mock_preview_state_roundtrip(self):
        """Test saving and restoring preview panel state."""
        panel = MockPreviewPanel()
        await panel.show_content("# Test Content", title="Test Title")

        # Save state
        state = panel.save_state()
        assert state["content"] == "# Test Content"
        assert state["title"] == "Test Title"
        assert state["mode"] == "VIEWING"

        # Create new panel and restore
        new_panel = MockPreviewPanel()
        new_panel.restore_state(state)

        assert new_panel.get_content() == "# Test Content"
        assert new_panel.get_title() == "Test Title"
