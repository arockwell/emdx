"""Tests for ActivityView — document preview and streaming removal verification."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from emdx.ui.activity.activity_items import DocumentItem
from emdx.ui.activity.activity_view import ActivityView

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_doc_item(
    item_id: int = 100,
    title: str = "Test doc",
) -> DocumentItem:
    return DocumentItem(
        item_id=item_id,
        title=title,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        status="completed",
        doc_id=item_id,
    )


# ---------------------------------------------------------------------------
# Test App
# ---------------------------------------------------------------------------


_VIEW_MODULE = "emdx.ui.activity.activity_view"
_DATA_MODULE = "emdx.ui.activity.activity_data"


class ActivityTestApp(App[None]):
    """Minimal app that mounts a single ActivityView."""

    def compose(self) -> ComposeResult:
        yield ActivityView(id="activity-view")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_activity_deps() -> Generator[dict[str, MagicMock], None, None]:
    """Patch DB calls used by ActivityView and its data loader."""
    mock_loader = MagicMock()
    mock_loader.load_all = AsyncMock(return_value=[])

    with (
        patch(f"{_VIEW_MODULE}.doc_db") as m_doc_db,
        patch(f"{_VIEW_MODULE}.HAS_DOCS", True),
        patch(
            f"{_VIEW_MODULE}.ActivityDataLoader",
            return_value=mock_loader,
        ),
        patch(
            "emdx.ui.activity.activity_view.get_theme_indicator",
            create=True,
        ) as m_theme,
    ):
        m_doc_db.get_document.return_value = None
        m_theme.return_value = ""
        yield {
            "doc_db": m_doc_db,
            "loader": mock_loader,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _richlog_text(widget: RichLog) -> str:
    """Extract plain text from a RichLog widget."""
    return "\n".join(line.text for line in widget.lines)


# ===================================================================
# A. Streaming code removal verification
# ===================================================================


class TestStreamingRemoval:
    """Verify that dead streaming code has been removed."""

    def test_no_agent_log_subscriber_class(self) -> None:
        """AgentLogSubscriber should not exist in activity_view module."""
        import emdx.ui.activity.activity_view as mod

        assert not hasattr(mod, "AgentLogSubscriber")

    def test_no_log_stream_attribute(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """ActivityView instances should not have log_stream attribute."""
        view = ActivityView()
        assert not hasattr(view, "log_stream")

    def test_no_log_subscriber_attribute(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """ActivityView instances should not have log_subscriber attribute."""
        view = ActivityView()
        assert not hasattr(view, "log_subscriber")

    def test_no_streaming_item_id_attribute(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """ActivityView instances should not have streaming_item_id attribute."""
        view = ActivityView()
        assert not hasattr(view, "streaming_item_id")

    def test_no_show_live_log_method(self) -> None:
        """_show_live_log method should not exist."""
        assert not hasattr(ActivityView, "_show_live_log")

    def test_no_handle_log_content_method(self) -> None:
        """_handle_log_content method should not exist."""
        assert not hasattr(ActivityView, "_handle_log_content")

    def test_no_stop_stream_method(self) -> None:
        """_stop_stream method should not exist."""
        assert not hasattr(ActivityView, "_stop_stream")

    def test_no_log_stream_import(self) -> None:
        """LogStream should not be imported in activity_view."""
        import emdx.ui.activity.activity_view as mod

        assert not hasattr(mod, "LogStream")
        assert not hasattr(mod, "LogStreamSubscriber")

    @pytest.mark.asyncio
    async def test_document_preview_still_works(
        self, mock_activity_deps: dict[str, MagicMock]
    ) -> None:
        """Document preview rendering still works after streaming removal."""
        doc_item = make_doc_item(item_id=100, title="My Document")
        mock_activity_deps["loader"].load_all.return_value = [doc_item]
        mock_activity_deps["doc_db"].get_document.return_value = {
            "id": 100,
            "title": "My Document",
            "content": "# My Document\n\nHello world",
            "project": "test",
            "created_at": "2025-01-01T12:00:00",
            "access_count": 5,
        }

        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            header = app.query_one("#preview-header", Static)
            assert "100" in str(header.content)

    @pytest.mark.asyncio
    async def test_copy_mode_still_works(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Copy mode toggle still works after streaming removal."""
        doc_item = make_doc_item(item_id=100, title="My Document")
        mock_activity_deps["loader"].load_all.return_value = [doc_item]
        mock_activity_deps["doc_db"].get_document.return_value = {
            "id": 100,
            "title": "My Document",
            "content": "# My Document\n\nHello world",
            "project": "test",
            "created_at": "2025-01-01T12:00:00",
            "access_count": 1,
        }

        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Toggle copy mode
            await pilot.press("c")
            await pilot.pause()

            view = app.query_one(ActivityView)
            assert view._copy_mode is True

            # Toggle back
            await pilot.press("c")
            await pilot.pause()
            assert view._copy_mode is False
