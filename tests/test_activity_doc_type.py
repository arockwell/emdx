"""Tests for doc_type badge/icon and filtering in the Activity browser."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult

from emdx.ui.activity.activity_data import ActivityDataLoader
from emdx.ui.activity.activity_items import DocumentItem
from emdx.ui.activity.activity_table import ActivityTable
from emdx.ui.activity.activity_view import ActivityView

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_doc_row(
    id: int = 1,
    title: str = "Test doc",
    doc_type: str = "user",
    created_at: str = "2025-01-20T12:00:00",
) -> dict[str, Any]:
    """Create a fake document row matching DocumentRow shape."""
    return {
        "id": id,
        "title": title,
        "content": "some content",
        "project": None,
        "created_at": created_at,
        "updated_at": None,
        "accessed_at": None,
        "access_count": 1,
        "deleted_at": None,
        "is_deleted": 0,
        "parent_id": None,
        "relationship": None,
        "archived_at": None,
        "stage": None,
        "doc_type": doc_type,
    }


# ---------------------------------------------------------------------------
# A. DocumentItem doc_type field and icon
# ---------------------------------------------------------------------------


class TestDocumentItemDocType:
    """Tests for the doc_type field on DocumentItem."""

    def test_default_doc_type_is_user(self) -> None:
        item = DocumentItem(item_id=1, title="Note", timestamp=datetime.now(), doc_id=1)
        assert item.doc_type == "user"

    def test_user_doc_icon(self) -> None:
        item = DocumentItem(
            item_id=1,
            title="Note",
            timestamp=datetime.now(),
            doc_id=1,
            doc_type="user",
        )
        assert item.type_icon == "📄"

    def test_wiki_doc_icon(self) -> None:
        item = DocumentItem(
            item_id=1,
            title="Wiki article",
            timestamp=datetime.now(),
            doc_id=1,
            doc_type="wiki",
        )
        assert item.type_icon == "📚"


# ---------------------------------------------------------------------------
# B. ActivityDataLoader doc_type filtering
# ---------------------------------------------------------------------------

_DATA_LOADER_BASE = "emdx.ui.activity.activity_data"


class TestDataLoaderDocTypeFilter:
    """Tests for doc_type_filter parameter in ActivityDataLoader."""

    @pytest.mark.asyncio
    async def test_filter_user_only(self) -> None:
        """Filter 'user' excludes wiki docs."""
        docs = [
            make_doc_row(id=1, title="User doc", doc_type="user"),
            make_doc_row(id=2, title="Wiki article", doc_type="wiki"),
        ]
        with (
            patch(f"{_DATA_LOADER_BASE}.doc_svc") as mock_svc,
            patch(f"{_DATA_LOADER_BASE}.HAS_DOCS", True),
        ):
            mock_svc.list_recent_documents.return_value = docs
            loader = ActivityDataLoader()
            items = await loader._load_documents(doc_type_filter="user")

        assert len(items) == 1
        assert isinstance(items[0], DocumentItem)
        assert items[0].title == "User doc"
        assert items[0].doc_type == "user"

    @pytest.mark.asyncio
    async def test_filter_wiki_only(self) -> None:
        """Filter 'wiki' excludes user docs."""
        docs = [
            make_doc_row(id=1, title="User doc", doc_type="user"),
            make_doc_row(id=2, title="Wiki article", doc_type="wiki"),
        ]
        with (
            patch(f"{_DATA_LOADER_BASE}.doc_svc") as mock_svc,
            patch(f"{_DATA_LOADER_BASE}.HAS_DOCS", True),
        ):
            mock_svc.list_recent_documents.return_value = docs
            loader = ActivityDataLoader()
            items = await loader._load_documents(doc_type_filter="wiki")

        assert len(items) == 1
        assert isinstance(items[0], DocumentItem)
        assert items[0].title == "Wiki article"
        assert items[0].doc_type == "wiki"

    @pytest.mark.asyncio
    async def test_filter_all_shows_both(self) -> None:
        """Filter 'all' includes both user and wiki docs."""
        docs = [
            make_doc_row(id=1, title="User doc", doc_type="user"),
            make_doc_row(id=2, title="Wiki article", doc_type="wiki"),
        ]
        with (
            patch(f"{_DATA_LOADER_BASE}.doc_svc") as mock_svc,
            patch(f"{_DATA_LOADER_BASE}.HAS_DOCS", True),
        ):
            mock_svc.list_recent_documents.return_value = docs
            loader = ActivityDataLoader()
            items = await loader._load_documents(doc_type_filter="all")

        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_doc_type_defaults_to_user(self) -> None:
        """Documents without doc_type field default to 'user'."""
        docs = [make_doc_row(id=1, title="Old doc")]
        docs[0]["doc_type"] = None  # Simulate missing doc_type
        with (
            patch(f"{_DATA_LOADER_BASE}.doc_svc") as mock_svc,
            patch(f"{_DATA_LOADER_BASE}.HAS_DOCS", True),
        ):
            mock_svc.list_recent_documents.return_value = docs
            loader = ActivityDataLoader()
            items = await loader._load_documents(doc_type_filter="user")

        assert len(items) == 1
        assert isinstance(items[0], DocumentItem)
        assert items[0].doc_type == "user"


# ---------------------------------------------------------------------------
# C. ActivityTable badge rendering for wiki docs
# ---------------------------------------------------------------------------


class ActivityTableTestApp(App[None]):
    """Minimal app for testing ActivityTable in isolation."""

    def compose(self) -> ComposeResult:
        yield ActivityTable(id="table")


class TestActivityTableBadge:
    """Tests for wiki badge in ActivityTable."""

    @pytest.mark.asyncio
    async def test_wiki_doc_shows_badge_in_title(self) -> None:
        """Wiki documents should show a 'wiki' badge in the title column."""
        wiki_item = DocumentItem(
            item_id=1,
            title="Wiki Article",
            timestamp=datetime.now(),
            doc_id=1,
            doc_type="wiki",
        )
        app = ActivityTableTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", ActivityTable)
            table.populate([wiki_item])
            await pilot.pause()

            # Get title cell for the data row (skip header)
            for row in table.ordered_rows:
                key_str = str(row.key.value)
                if key_str.startswith("header:"):
                    continue
                val = table.get_cell(row.key, "title")
                title_str = str(val)
                assert "wiki" in title_str.lower()
                break

    @pytest.mark.asyncio
    async def test_user_doc_no_badge(self) -> None:
        """User documents should NOT show a wiki badge."""
        user_item = DocumentItem(
            item_id=2,
            title="User Note",
            timestamp=datetime.now(),
            doc_id=2,
            doc_type="user",
        )
        app = ActivityTableTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", ActivityTable)
            table.populate([user_item])
            await pilot.pause()

            for row in table.ordered_rows:
                key_str = str(row.key.value)
                if key_str.startswith("header:"):
                    continue
                val = table.get_cell(row.key, "title")
                title_str = str(val)
                # Should not have "wiki" badge prefix
                assert "wiki" not in title_str.lower() or "User Note" in title_str
                break

    @pytest.mark.asyncio
    async def test_wiki_doc_uses_book_icon(self) -> None:
        """Wiki documents should use the 📚 icon instead of 📄."""
        wiki_item = DocumentItem(
            item_id=1,
            title="Wiki Article",
            timestamp=datetime.now(),
            doc_id=1,
            doc_type="wiki",
        )
        app = ActivityTableTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", ActivityTable)
            table.populate([wiki_item])
            await pilot.pause()

            for row in table.ordered_rows:
                key_str = str(row.key.value)
                if key_str.startswith("header:"):
                    continue
                val = table.get_cell(row.key, "icon")
                assert "📚" in str(val)
                break


# ---------------------------------------------------------------------------
# D. ActivityView doc_type filter cycling
# ---------------------------------------------------------------------------

_VIEW_BASE = "emdx.ui.activity.activity_view"


class ActivityViewTestApp(App[None]):
    """Minimal app for testing ActivityView."""

    def compose(self) -> ComposeResult:
        yield ActivityView(id="activity-view")


@pytest.fixture()
def mock_activity_data() -> Generator[dict[str, MagicMock], None, None]:
    """Patch DB calls used by ActivityView."""
    with (
        patch(f"{_DATA_LOADER_BASE}.doc_svc") as mock_svc,
        patch(f"{_DATA_LOADER_BASE}.HAS_DOCS", True),
        patch(f"{_VIEW_BASE}.HAS_DOCS", True),
        patch(f"{_VIEW_BASE}.doc_db") as mock_doc_db,
        patch("emdx.ui.themes.get_theme_indicator", return_value=""),
    ):
        mock_svc.list_recent_documents.return_value = [
            make_doc_row(id=1, title="User note", doc_type="user"),
            make_doc_row(id=2, title="Wiki article", doc_type="wiki"),
        ]
        mock_doc_db.get_document.return_value = None
        yield {
            "doc_svc": mock_svc,
            "doc_db": mock_doc_db,
        }


class TestActivityViewDocTypeFilter:
    """Tests for the 'w' keybinding that cycles doc_type filter."""

    @pytest.mark.asyncio
    async def test_default_filter_is_user(self, mock_activity_data: dict[str, MagicMock]) -> None:
        """ActivityView defaults to showing user docs only."""
        app = ActivityViewTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.query_one("#activity-view", ActivityView)
            assert view.doc_type_filter == "user"

    @pytest.mark.asyncio
    async def test_w_cycles_to_wiki(self, mock_activity_data: dict[str, MagicMock]) -> None:
        """Pressing 'w' once cycles filter from user -> wiki."""
        app = ActivityViewTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.query_one("#activity-view", ActivityView)
            assert view.doc_type_filter == "user"
            await pilot.press("w")
            await pilot.pause()
            assert view.doc_type_filter == "wiki"

    @pytest.mark.asyncio
    async def test_w_cycles_to_all(self, mock_activity_data: dict[str, MagicMock]) -> None:
        """Pressing 'w' twice cycles filter from user -> wiki -> all."""
        app = ActivityViewTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.query_one("#activity-view", ActivityView)
            await pilot.press("w")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert view.doc_type_filter == "all"

    @pytest.mark.asyncio
    async def test_w_cycles_back_to_user(self, mock_activity_data: dict[str, MagicMock]) -> None:
        """Pressing 'w' three times cycles back to user."""
        app = ActivityViewTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.query_one("#activity-view", ActivityView)
            await pilot.press("w")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert view.doc_type_filter == "user"
