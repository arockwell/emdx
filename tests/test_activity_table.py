"""Pilot-based tests for ActivityTable widget."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from emdx.ui.activity.activity_items import (
    ActivityItem,
    DocumentItem,
)
from emdx.ui.activity.activity_table import ActivityTable, _item_key

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 21, 12, 0, 0)


def make_doc(
    item_id: int = 1,
    title: str = "Test doc",
    timestamp: datetime | None = None,
    doc_id: int | None = None,
) -> DocumentItem:
    return DocumentItem(
        item_id=item_id,
        title=title,
        timestamp=timestamp or _NOW,
        doc_id=doc_id or item_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_row_keys(table: DataTable[Any]) -> list[str]:
    """Get all row keys as strings."""
    return [str(row.key.value) for row in table.ordered_rows]


def _table_cell_texts(table: DataTable[Any], col_key: str) -> list[str]:
    """Get all cell values for a column as plain text."""
    texts: list[str] = []
    for row in table.ordered_rows:
        val = table.get_cell(row.key, col_key)
        texts.append(str(val))
    return texts


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------


class ActivityTestApp(App[None]):
    """Minimal app that mounts a single ActivityTable."""

    def compose(self) -> ComposeResult:
        yield ActivityTable(id="activity-table")


# ===================================================================
# A. Unit tests (no Textual app needed)
# ===================================================================


class TestItemKey:
    """Tests for _item_key helper."""

    def test_document_key(self) -> None:
        doc = make_doc(item_id=42)
        assert _item_key(doc) == ("document", 42)


# ===================================================================
# B. Rendering & populate
# ===================================================================


class TestPopulate:
    """Tests for ActivityTable.populate()."""

    @pytest.mark.asyncio
    async def test_empty_populate(self) -> None:
        """Populating with empty list results in zero rows."""
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate([])
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_populate_documents(self) -> None:
        """Populating with documents adds correct rows (no section headers)."""
        items: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="Second"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            # 2 document rows, no section headers
            assert table.row_count == 2
            keys = _table_row_keys(table)
            assert keys == ["document:1", "document:2"]

    @pytest.mark.asyncio
    async def test_title_not_text_truncated(self) -> None:
        """Full titles are stored in cells; column width handles visual clipping."""
        long_title = "A" * 100
        items: list[ActivityItem] = [make_doc(item_id=1, title=long_title)]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            titles = _table_cell_texts(table, "title")
            assert len(titles) == 1
            title_str = str(titles[0])
            # Full title is stored — no text-level truncation
            assert title_str == long_title

    @pytest.mark.asyncio
    async def test_id_column_document(self) -> None:
        """Document rows show #doc_id in the id column."""
        items: list[ActivityItem] = [make_doc(item_id=42, doc_id=42)]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            ids = _table_cell_texts(table, "id")
            assert "#42" in ids[0]


# ===================================================================
# C. Cursor & selection
# ===================================================================


class TestCursorSelection:
    """Tests for cursor movement and get_selected_item."""

    @pytest.mark.asyncio
    async def test_get_selected_item_empty(self) -> None:
        """get_selected_item returns None when table is empty."""
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate([])
            assert table.get_selected_item() is None

    @pytest.mark.asyncio
    async def test_get_selected_item_after_populate(self) -> None:
        """After populating, cursor starts on first item."""
        items: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="Second"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            table.focus()
            await pilot.pause()
            # Cursor starts on first item (no header rows)
            selected = table.get_selected_item()
            assert selected is not None
            assert selected.item_id == 1

    @pytest.mark.asyncio
    async def test_cursor_movement(self) -> None:
        """Moving cursor down selects items in order."""
        items: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="Second"),
            make_doc(item_id=3, title="Third"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            table.focus()
            await pilot.pause()

            # Move to second item
            await pilot.press("down")  # doc 1 -> doc 2
            await pilot.pause()
            selected = table.get_selected_item()
            assert selected is not None
            assert selected.item_id == 2


# ===================================================================
# D. Refresh (diff-based)
# ===================================================================


class TestRefreshItems:
    """Tests for refresh_items diff-based update."""

    @pytest.mark.asyncio
    async def test_refresh_same_order_updates_in_place(self) -> None:
        """When order is unchanged, values update without repopulating."""
        items_v1: list[ActivityItem] = [
            make_doc(item_id=1, title="Original"),
            make_doc(item_id=2, title="Second"),
        ]
        items_v2: list[ActivityItem] = [
            make_doc(item_id=1, title="Updated"),
            make_doc(item_id=2, title="Second"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items_v1)
            # 2 items, no headers
            assert table.row_count == 2

            table.refresh_items(items_v2)
            assert table.row_count == 2
            titles = _table_cell_texts(table, "title")
            assert "Updated" in titles[0]

    @pytest.mark.asyncio
    async def test_refresh_structural_change_repopulates(self) -> None:
        """When items are added/removed, the table repopulates."""
        items_v1: list[ActivityItem] = [make_doc(item_id=1, title="Only")]
        items_v2: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="New"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items_v1)
            # 1 item
            assert table.row_count == 1

            table.refresh_items(items_v2)
            # 2 items
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_refresh_preserves_cursor(self) -> None:
        """Cursor stays on the same item after structural refresh."""
        items: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="Second"),
            make_doc(item_id=3, title="Third"),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            table.focus()
            await pilot.pause()

            # Move cursor to doc 2
            await pilot.press("down")  # doc 1 -> doc 2
            await pilot.pause()
            assert table.get_selected_item() is not None
            assert table.get_selected_item().item_id == 2  # type: ignore[union-attr]

            # Refresh with new item added at beginning (structural change)
            new_items: list[ActivityItem] = [
                make_doc(item_id=99, title="Brand new"),
                make_doc(item_id=1, title="First"),
                make_doc(item_id=2, title="Second"),
                make_doc(item_id=3, title="Third"),
            ]
            table.refresh_items(new_items)
            await pilot.pause()

            # Cursor should still be on item_id=2
            selected = table.get_selected_item()
            assert selected is not None
            assert selected.item_id == 2


# ===================================================================
# E. find_row_by_doc_id
# ===================================================================


class TestFindRow:
    """Tests for find_row_by_doc_id."""

    @pytest.mark.asyncio
    async def test_find_document_row(self) -> None:
        """Finds a document row by its doc_id."""
        items: list[ActivityItem] = [
            make_doc(item_id=10, doc_id=10),
            make_doc(item_id=20, doc_id=20),
        ]
        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)

            # Row 0 and 1 are docs (no headers)
            assert table.find_row_by_doc_id(10) == 0
            assert table.find_row_by_doc_id(20) == 1
            assert table.find_row_by_doc_id(999) is None


# ===================================================================
# F. Messages (ItemHighlighted)
# ===================================================================


class TestMessages:
    """Tests for message posting."""

    @pytest.mark.asyncio
    async def test_item_highlighted_fires(self) -> None:
        """Moving cursor posts ItemHighlighted with the correct item."""
        items: list[ActivityItem] = [
            make_doc(item_id=1, title="First"),
            make_doc(item_id=2, title="Second"),
        ]
        received: list[ActivityItem | None] = []

        class CaptureApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ActivityTable(id="activity-table")

            def on_activity_table_item_highlighted(
                self, event: ActivityTable.ItemHighlighted
            ) -> None:
                received.append(event.item)

        app = CaptureApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#activity-table", ActivityTable)
            table.populate(items)
            table.focus()
            await pilot.pause()

            # Use down/up arrow keys
            await pilot.press("down")  # doc 1 -> doc 2
            await pilot.pause()
            await pilot.press("up")  # doc 2 -> doc 1
            await pilot.pause()

            # Filter to non-None highlights
            non_none = [r for r in received if r is not None]
            assert len(non_none) >= 1
            # Last non-None highlight should be first item (after up goes back)
            assert non_none[-1].item_id == 1
