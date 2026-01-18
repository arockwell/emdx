"""
Integration tests for ExampleBrowser.

These tests use PilotIntegrationHarness to test the ExampleBrowser
with real Textual App rendering and message flows.

Run with:
    pytest emdx/ui/testing/test_example_browser.py -v

Or with coverage:
    pytest emdx/ui/testing/test_example_browser.py -v --cov=emdx.ui.browsers
"""

import pytest
import pytest_asyncio

from ..browsers.example_browser import ExampleBrowser
from ..panels import ListPanel
from .integration import (
    PilotIntegrationHarness,
    MockDataGenerator,
    wait_for_condition,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def harness():
    """Create a test harness with ExampleBrowser."""
    async with PilotIntegrationHarness.create(ExampleBrowser) as h:
        # Wait for initial data load
        await h.wait_for_idle(0.2)
        yield h


@pytest_asyncio.fixture
async def empty_harness():
    """Create a test harness with ExampleBrowser but clear items."""
    async with PilotIntegrationHarness.create(ExampleBrowser) as h:
        await h.wait_for_idle(0.2)
        # Clear the items
        panel = h.get_list_panel()
        panel.clear_items()
        await h.wait_for_idle(0.1)
        yield h


# =============================================================================
# Navigation Tests
# =============================================================================


class TestNavigation:
    """Test vim-style navigation in ExampleBrowser."""

    @pytest.mark.asyncio
    async def test_j_moves_cursor_down(self, harness):
        """Pressing j should move cursor down one item."""
        initial_index = harness.get_selected_index()
        await harness.press("j")
        await harness.wait_for_idle(0.1)

        # Should have moved down by 1
        expected = (initial_index or 0) + 1
        harness.assert_selected_index(expected)

    @pytest.mark.asyncio
    async def test_k_moves_cursor_up(self, harness):
        """Pressing k should move cursor up one item."""
        # First move down so we have room to move up
        await harness.press("j")
        await harness.press("j")
        await harness.wait_for_idle(0.1)

        current = harness.get_selected_index()
        await harness.press("k")
        await harness.wait_for_idle(0.1)

        harness.assert_selected_index(current - 1)

    @pytest.mark.asyncio
    async def test_k_at_top_stays_at_top(self, harness):
        """Pressing k at the top should not go negative."""
        # Go to top first
        await harness.press("g")
        await harness.wait_for_idle(0.1)

        # Try to go up
        await harness.press("k")
        await harness.wait_for_idle(0.1)

        # Should still be at 0
        harness.assert_selected_index(0)

    @pytest.mark.asyncio
    async def test_g_moves_to_top(self, harness):
        """Pressing g should move to the first item."""
        # First move down
        await harness.press_keys("j", "j", "j")
        await harness.wait_for_idle(0.1)

        # Now go to top
        await harness.press("g")
        await harness.wait_for_idle(0.1)

        harness.assert_selected_index(0)

    @pytest.mark.asyncio
    async def test_G_moves_to_bottom(self, harness):
        """Pressing G should move to the last item."""
        await harness.press("G")
        await harness.wait_for_idle(0.1)

        # Get item count
        item_count = harness.get_item_count()
        harness.assert_selected_index(item_count - 1)

    @pytest.mark.asyncio
    async def test_multiple_j_presses(self, harness):
        """Multiple j presses should move cursor down multiple times."""
        await harness.press("g")  # Start at top
        await harness.wait_for_idle(0.1)

        # Press j 3 times
        for _ in range(3):
            await harness.press("j")
        await harness.wait_for_idle(0.1)

        harness.assert_selected_index(3)

    @pytest.mark.asyncio
    async def test_j_at_bottom_stays_at_bottom(self, harness):
        """Pressing j at the bottom should not go past last item."""
        # Go to bottom
        await harness.press("G")
        await harness.wait_for_idle(0.1)

        bottom_index = harness.get_selected_index()

        # Try to go further
        await harness.press("j")
        await harness.wait_for_idle(0.1)

        # Should still be at bottom
        harness.assert_selected_index(bottom_index)


# =============================================================================
# Search Tests
# =============================================================================


class TestSearch:
    """Test search functionality in ExampleBrowser."""

    @pytest.mark.asyncio
    async def test_slash_enters_search_mode(self, harness):
        """Pressing / should enter search mode."""
        await harness.press("slash")
        await harness.wait_for_idle(0.1)

        harness.assert_list_mode("SEARCH")

    @pytest.mark.asyncio
    async def test_escape_exits_search_mode(self, harness):
        """Pressing escape should exit search mode."""
        # Enter search mode
        await harness.press("slash")
        await harness.wait_for_idle(0.1)

        # Exit with escape
        await harness.press("escape")
        await harness.wait_for_idle(0.1)

        harness.assert_list_mode("NORMAL")

    @pytest.mark.asyncio
    async def test_search_filters_items(self, harness):
        """Submitting a search query should filter items."""
        initial_count = harness.get_item_count()

        # Enter search mode and search for "Navigation"
        await harness.press("slash")
        await harness.wait_for_idle(0.1)
        await harness.type_text("Navigation")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        # Should have fewer items (only 1 match for "Navigation")
        new_count = harness.get_item_count()
        assert new_count < initial_count
        assert new_count == 1

    @pytest.mark.asyncio
    async def test_empty_search_shows_all(self, harness):
        """Submitting an empty search should show all items."""
        # First filter
        await harness.press("slash")
        await harness.type_text("Navigation")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        filtered_count = harness.get_item_count()

        # Now clear with empty search
        await harness.press("slash")
        await harness.press("enter")  # Submit empty
        await harness.wait_for_idle(0.2)

        # Should show all items again
        full_count = harness.get_item_count()
        assert full_count > filtered_count

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(self, harness):
        """Search should be case insensitive."""
        # Search with lowercase
        await harness.press("slash")
        await harness.type_text("navigation")  # lowercase
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        # Should find "Navigation" item
        assert harness.get_item_count() == 1
        item = harness.get_selected_item()
        assert item is not None
        assert "Navigation" in item.values[1]

    @pytest.mark.asyncio
    async def test_search_no_results(self, harness):
        """Search with no matches should show empty list."""
        await harness.press("slash")
        await harness.type_text("xyznonexistent")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        harness.assert_item_count(0)


# =============================================================================
# Selection and Preview Tests
# =============================================================================


class TestSelectionAndPreview:
    """Test item selection and preview updates."""

    @pytest.mark.asyncio
    async def test_initial_selection_updates_preview(self, harness):
        """Initial selection should show content in preview."""
        # The first item should be selected and preview should have content
        content = harness.get_preview_content()
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_navigation_updates_preview(self, harness):
        """Moving to a new item should update the preview."""
        initial_content = harness.get_preview_content()

        # Move to next item
        await harness.press("j")
        await harness.wait_for_idle(0.2)

        new_content = harness.get_preview_content()

        # Content should be different (different items)
        assert new_content != initial_content

    @pytest.mark.asyncio
    async def test_preview_contains_item_content(self, harness):
        """Preview should contain the selected item's content."""
        # Select first item (Getting Started)
        await harness.press("g")
        await harness.wait_for_idle(0.2)

        # The content should contain text from the item
        harness.assert_preview_contains("Getting Started")

    @pytest.mark.asyncio
    async def test_preview_title_matches_selection(self, harness):
        """Preview title should match selected item name."""
        # Go to second item
        await harness.press("g")
        await harness.press("j")
        await harness.wait_for_idle(0.2)

        title = harness.get_preview_title()
        assert "Navigation" in title


# =============================================================================
# Message Flow Tests
# =============================================================================


class TestMessageFlow:
    """Test message communication between panels.

    Note: These tests verify that the browser responds correctly to messages.
    Direct message capture from the Textual runtime requires additional setup,
    so we test the observable effects of message handling instead.
    """

    @pytest.mark.asyncio
    async def test_item_selected_updates_preview_on_navigation(self, harness):
        """Navigation should trigger preview update (ItemSelected handling)."""
        # Get initial preview content
        initial_content = harness.get_preview_content()

        # Move cursor - this should trigger ItemSelected -> preview update
        await harness.press("j")
        await harness.wait_for_idle(0.2)

        # Verify the observable effect: preview content changed
        new_content = harness.get_preview_content()
        assert new_content != initial_content, "Preview should update when selection changes"

    @pytest.mark.asyncio
    async def test_item_activated_triggers_notification(self, harness):
        """Pressing Enter should trigger ItemActivated handling."""
        # Note: The ExampleBrowser.on_list_panel_item_activated calls self.notify()
        # We can't easily capture notifications in the test, but we verify
        # that pressing enter doesn't raise an error and the app remains stable
        initial_index = harness.get_selected_index()

        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        # App should still be functional after activation
        current_index = harness.get_selected_index()
        assert current_index == initial_index, "Selection should not change on enter"

    @pytest.mark.asyncio
    async def test_search_submitted_filters_items(self, harness):
        """Submitting search should filter items (SearchSubmitted handling)."""
        initial_count = harness.get_item_count()

        await harness.press("slash")
        await harness.type_text("Testing")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        # Verify the observable effect: item count changed
        new_count = harness.get_item_count()
        assert new_count == 1, "Search should filter to items containing 'Testing'"
        assert new_count < initial_count, "Filtered count should be less than total"

    @pytest.mark.asyncio
    async def test_message_flow_search_then_navigate(self, harness):
        """Complex flow: search then navigate should work correctly."""
        # Search for "Active" status items
        await harness.press("slash")
        await harness.type_text("Active")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        filtered_count = harness.get_item_count()
        assert filtered_count > 0, "Should find Active items"

        # Navigate within filtered results
        await harness.press("g")  # Go to first
        await harness.wait_for_idle(0.1)

        first_content = harness.get_preview_content()

        # Try to move down (if there are multiple results)
        if filtered_count > 1:
            await harness.press("j")
            await harness.wait_for_idle(0.2)

            second_content = harness.get_preview_content()
            assert second_content != first_content, "Navigation should update preview"


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and complex scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_navigation(self, harness):
        """Rapid key presses should not break navigation."""
        # Press j multiple times rapidly
        for _ in range(10):
            await harness.press("j")

        await harness.wait_for_idle(0.2)

        # Should be at a valid index (not negative, not past end)
        index = harness.get_selected_index()
        item_count = harness.get_item_count()

        assert 0 <= index < item_count

    @pytest.mark.asyncio
    async def test_navigation_after_search(self, harness):
        """Navigation should work on filtered results."""
        # Filter to 1 item
        await harness.press("slash")
        await harness.type_text("Navigation")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        # Should be at index 0 of filtered results
        harness.assert_selected_index(0)

        # j should not move past the single item
        await harness.press("j")
        await harness.wait_for_idle(0.1)

        harness.assert_selected_index(0)

    @pytest.mark.asyncio
    async def test_g_G_with_filtered_results(self, harness):
        """g and G should work with filtered results."""
        # Filter to a subset
        await harness.press("slash")
        await harness.type_text("Active")
        await harness.press("enter")
        await harness.wait_for_idle(0.2)

        filtered_count = harness.get_item_count()
        assert filtered_count > 0

        # G should go to last of filtered
        await harness.press("G")
        await harness.wait_for_idle(0.1)
        harness.assert_selected_index(filtered_count - 1)

        # g should go to first
        await harness.press("g")
        await harness.wait_for_idle(0.1)
        harness.assert_selected_index(0)

    @pytest.mark.asyncio
    async def test_empty_list_navigation(self, empty_harness):
        """Navigation on empty list should not crash."""
        # These should not raise
        await empty_harness.press("j")
        await empty_harness.press("k")
        await empty_harness.press("g")
        await empty_harness.press("G")
        await empty_harness.wait_for_idle(0.1)

        # For an empty DataTable, cursor_row can be -1, None, or 0
        # The important thing is it doesn't crash
        index = empty_harness.get_selected_index()
        assert index is None or index <= 0, f"Empty list index should be None, 0, or -1, got {index}"


# =============================================================================
# Snapshot Tests
# =============================================================================


class TestSnapshots:
    """Test snapshot capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_list_snapshot(self, harness):
        """Should be able to capture list panel snapshot."""
        snapshot = harness.capture_list_snapshot()

        assert snapshot.widget_class == "ListPanel"
        assert "item_count" in snapshot.properties
        assert snapshot.properties["item_count"] == 5  # ExampleBrowser has 5 items

    @pytest.mark.asyncio
    async def test_capture_preview_snapshot(self, harness):
        """Should be able to capture preview panel snapshot."""
        snapshot = harness.capture_preview_snapshot()

        assert snapshot.widget_class == "PreviewPanel"
        assert "has_content" in snapshot.properties
        assert snapshot.properties["has_content"] is True

    @pytest.mark.asyncio
    async def test_snapshot_changes_on_navigation(self, harness):
        """Snapshot should reflect state changes."""
        snapshot1 = harness.capture_list_snapshot()

        await harness.press("j")
        await harness.wait_for_idle(0.1)

        snapshot2 = harness.capture_list_snapshot()

        # Selected index should be different
        assert snapshot1.properties["selected_index"] != snapshot2.properties["selected_index"]

    @pytest.mark.asyncio
    async def test_snapshot_diff(self, harness):
        """Snapshot diff should detect changes."""
        snapshot1 = harness.capture_list_snapshot()

        await harness.press("j")
        await harness.wait_for_idle(0.1)

        snapshot2 = harness.capture_list_snapshot()

        diffs = snapshot1.diff(snapshot2)
        assert len(diffs) > 0
        assert any("selected_index" in d for d in diffs)


# =============================================================================
# Mock Data Generator Tests
# =============================================================================


class TestMockDataGenerator:
    """Test the mock data generator utilities."""

    def test_list_items_generates_correct_count(self):
        """list_items should generate the requested number of items."""
        items = MockDataGenerator.list_items(count=15)
        assert len(items) == 15

    def test_list_items_have_unique_ids(self):
        """Generated items should have unique IDs."""
        items = MockDataGenerator.list_items(count=10)
        ids = [item.id for item in items]
        assert len(ids) == len(set(ids))

    def test_list_items_cycle_statuses(self):
        """Items should cycle through provided statuses."""
        statuses = ["A", "B", "C"]
        items = MockDataGenerator.list_items(count=6, statuses=statuses)

        item_statuses = [item.values[2] for item in items]
        assert item_statuses == ["A", "B", "C", "A", "B", "C"]

    def test_list_items_with_content(self):
        """Items should include content when requested."""
        items = MockDataGenerator.list_items(count=3, with_content=True)

        for item in items:
            assert "content" in item.data

    def test_searchable_items_are_distinct(self):
        """searchable_items should return items with distinct names."""
        items = MockDataGenerator.searchable_items()

        names = [item.values[1] for item in items]
        assert len(names) == len(set(names))

    def test_documents_have_tags(self):
        """documents should include tag data."""
        docs = MockDataGenerator.documents(count=3)

        for doc in docs:
            assert "tags" in doc.data
            assert len(doc.data["tags"]) > 0
