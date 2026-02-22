"""Tests for ActivityView — task action keybindings and streaming removal.

Phase 2 of the Unified Dashboard Data Model:
- Part A: Task action keybindings (d/a/b/x) in ActivityView
- Part B: Verify dead live-streaming code was removed
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from emdx.ui.activity.activity_items import (
    AgentExecutionItem,
    DocumentItem,
    TaskItem,
)
from emdx.ui.activity.activity_view import ActivityView

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_task_item(
    item_id: int = 1,
    title: str = "Test task",
    status: str = "open",
    priority: int = 5,
    epic_key: str | None = None,
    description: str | None = None,
) -> TaskItem:
    """Create a TaskItem for testing."""
    task_dict: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "status": status,
        "priority": priority,
        "epic_key": epic_key,
        "description": description,
        "error": None,
        "epic_seq": None,
        "created_at": "2025-01-01T12:00:00",
        "updated_at": None,
        "completed_at": None,
        "tags": None,
        "execution_id": None,
        "output_doc_id": None,
        "gameplan_id": None,
        "project": None,
        "current_step": None,
        "prompt": None,
        "type": "manual",
        "source_doc_id": None,
        "parent_task_id": None,
        "seq": None,
        "retry_of": None,
    }
    return TaskItem(
        item_id=item_id,
        title=title,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        status=status,
        task_data=task_dict,  # type: ignore[arg-type]
    )


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


def make_exec_item(
    item_id: int = 200,
    title: str = "Test execution",
    status: str = "running",
) -> AgentExecutionItem:
    return AgentExecutionItem(
        item_id=item_id,
        title=title,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        status=status,
        execution={},  # type: ignore[arg-type]
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
# A. TaskItem unit tests
# ===================================================================


class TestTaskItem:
    """Tests for the TaskItem dataclass."""

    def test_item_type(self) -> None:
        item = make_task_item()
        assert item.item_type == "task"

    def test_type_icon_open(self) -> None:
        item = make_task_item(status="open")
        assert item.type_icon == "."

    def test_type_icon_active(self) -> None:
        item = make_task_item(status="active")
        assert item.type_icon == ">"

    def test_type_icon_blocked(self) -> None:
        item = make_task_item(status="blocked")
        assert item.type_icon == "-"

    def test_type_icon_done(self) -> None:
        item = make_task_item(status="done")
        assert item.type_icon == "v"

    def test_type_icon_failed(self) -> None:
        item = make_task_item(status="failed")
        assert item.type_icon == "x"

    @pytest.mark.asyncio
    async def test_preview_content_basic(self) -> None:
        item = make_task_item(title="Fix auth bug", status="open", priority=2)
        content, header = await item.get_preview_content(None)
        assert "Fix auth bug" in content
        assert "open" in content
        assert "2" in content
        assert "Task #1" in header

    @pytest.mark.asyncio
    async def test_preview_content_with_description(self) -> None:
        item = make_task_item(description="Detailed explanation here")
        content, _ = await item.get_preview_content(None)
        assert "Detailed explanation here" in content

    @pytest.mark.asyncio
    async def test_preview_content_with_epic(self) -> None:
        task_dict = make_task_item(epic_key="AUTH").task_data
        assert task_dict is not None
        task_dict["epic_seq"] = 3
        item = TaskItem(
            item_id=1,
            title="Task",
            timestamp=datetime(2025, 1, 1),
            status="open",
            task_data=task_dict,  # type: ignore[arg-type]
        )
        content, _ = await item.get_preview_content(None)
        assert "AUTH-3" in content


# ===================================================================
# B. Task action keybindings in ActivityView
# ===================================================================


class TestTaskActions:
    """Tests for d/a/b task status keybindings."""

    @pytest.mark.asyncio
    async def test_d_marks_task_done(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing d on a task item calls update_task with 'done'."""
        task_item = make_task_item(item_id=42, status="open")
        mock_activity_deps["loader"].load_all.return_value = [task_item]

        with patch("emdx.models.tasks.update_task") as m_update:
            app = ActivityTestApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                # Select the task
                # Jump to TASKS section (past headers)
                await pilot.press("T")
                await pilot.pause()

                await pilot.press("d")
                await pilot.pause()

                m_update.assert_called_once_with(42, status="done")

    @pytest.mark.asyncio
    async def test_a_marks_task_active(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing a on a task item calls update_task with 'active'."""
        task_item = make_task_item(item_id=42, status="open")
        mock_activity_deps["loader"].load_all.return_value = [task_item]

        with patch("emdx.models.tasks.update_task") as m_update:
            app = ActivityTestApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to TASKS section (past headers)
                await pilot.press("T")
                await pilot.pause()

                await pilot.press("a")
                await pilot.pause()

                m_update.assert_called_once_with(42, status="active")

    @pytest.mark.asyncio
    async def test_b_marks_task_blocked(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing b on a task item calls update_task with 'blocked'."""
        task_item = make_task_item(item_id=42, status="open")
        mock_activity_deps["loader"].load_all.return_value = [task_item]

        with patch("emdx.models.tasks.update_task") as m_update:
            app = ActivityTestApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to TASKS section (past headers)
                await pilot.press("T")
                await pilot.pause()

                await pilot.press("b")
                await pilot.pause()

                m_update.assert_called_once_with(42, status="blocked")

    @pytest.mark.asyncio
    async def test_d_noop_on_document(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing d on a document item does not call update_task."""
        doc_item = make_doc_item()
        mock_activity_deps["loader"].load_all.return_value = [doc_item]

        with patch("emdx.models.tasks.update_task") as m_update:
            app = ActivityTestApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to DOCS section to select the document
                await pilot.press("D")
                await pilot.pause()

                await pilot.press("d")
                await pilot.pause()

                m_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_d_noop_when_already_done(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing d on an already-done task does not call update_task."""
        task_item = make_task_item(item_id=42, status="done")
        mock_activity_deps["loader"].load_all.return_value = [task_item]

        with patch("emdx.models.tasks.update_task") as m_update:
            app = ActivityTestApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                # Jump to TASKS section (past headers)
                await pilot.press("T")
                await pilot.pause()

                await pilot.press("d")
                await pilot.pause()

                m_update.assert_not_called()


# ===================================================================
# C. Dismiss/kill (x key) behavior
# ===================================================================


class TestDismissAction:
    """Tests for x key behavior on different item types."""

    @pytest.mark.asyncio
    async def test_x_noop_on_task(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing x on a task is a silent no-op."""
        task_item = make_task_item(item_id=42, status="open")
        mock_activity_deps["loader"].load_all.return_value = [task_item]

        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Jump to TASKS section (past headers)
            await pilot.press("T")
            await pilot.pause()

            # x should not raise or show error
            await pilot.press("x")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_x_noop_on_document(self, mock_activity_deps: dict[str, MagicMock]) -> None:
        """Pressing x on a document is a silent no-op."""
        doc_item = make_doc_item()
        mock_activity_deps["loader"].load_all.return_value = [doc_item]

        app = ActivityTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Jump to DOCS section (past headers)
            await pilot.press("D")
            await pilot.pause()

            await pilot.press("x")
            await pilot.pause()


# ===================================================================
# D. Streaming code removal verification
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
            # Jump to DOCS section (past headers)
            await pilot.press("D")
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
            # Jump to DOCS section (past headers)
            await pilot.press("D")
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
