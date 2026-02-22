"""Pilot-based tests for TaskBrowser / TaskView TUI widgets."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, RichLog, Static

from emdx.models.types import EpicTaskDict, TaskDict, TaskLogEntryDict
from emdx.ui.task_view import TaskView, _format_time_ago, _task_label

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_task(
    id: int = 1,
    title: str = "Test task",
    status: str = "open",
    priority: int = 5,
    description: str | None = None,
    error: str | None = None,
    epic_key: str | None = None,
    created_at: str | None = "2025-01-01T12:00:00",
    updated_at: str | None = None,
    completed_at: str | None = None,
    tags: str | None = None,
    execution_id: int | None = None,
    output_doc_id: int | None = None,
    parent_task_id: int | None = None,
    **kwargs: object,
) -> TaskDict:
    base: TaskDict = {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "description": description,
        "error": error,
        "epic_key": epic_key,
        "created_at": created_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "tags": tags,
        "execution_id": execution_id,
        "output_doc_id": output_doc_id,
        "gameplan_id": None,
        "project": None,
        "current_step": None,
        "prompt": None,
        "type": "manual",
        "source_doc_id": None,
        "parent_task_id": parent_task_id,
        "seq": None,
        "retry_of": None,
        "epic_seq": None,
    }
    return base


def make_epic(
    id: int = 1,
    epic_key: str = "AUTH",
    child_count: int = 10,
    children_done: int = 7,
    children_open: int = 3,
    **kwargs: object,
) -> EpicTaskDict:
    base = make_task(id=id, title=f"Epic: {epic_key}", status="open", epic_key=epic_key)
    epic: EpicTaskDict = {
        **base,  # type: ignore[typeddict-item]
        "child_count": child_count,
        "children_done": children_done,
        "children_open": children_open,
    }
    return epic


def make_log_entry(
    id: int = 1,
    task_id: int = 1,
    message: str = "Did something",
    created_at: str | None = "2025-01-01T12:00:00",
) -> TaskLogEntryDict:
    return {
        "id": id,
        "task_id": task_id,
        "message": message,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _richlog_text(widget: RichLog) -> str:
    """Extract plain text from a RichLog widget."""
    parts: list[str] = []
    for line in widget.lines:
        parts.append(line.text)
    return "\n".join(parts)


def _table_cell_texts(table: DataTable[Any], col_key: str) -> list[str]:
    """Get all cell values for a column as strings."""
    texts: list[str] = []
    for row in table.ordered_rows:
        try:
            val = table.get_cell(row.key, col_key)
            texts.append(str(val))
        except Exception:
            texts.append("")
    return texts


# ---------------------------------------------------------------------------
# Test app that mounts only TaskView (lighter than BrowserContainer)
# ---------------------------------------------------------------------------

_MOCK_BASE = "emdx.ui.task_view"

MockDict = dict[str, MagicMock]


class TaskTestApp(App[None]):
    """Minimal app that mounts a single TaskView."""

    def compose(self) -> ComposeResult:
        yield TaskView(id="task-view")


# ---------------------------------------------------------------------------
# Fixture: patch all DB functions used by TaskView
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_task_data() -> Generator[MockDict, None, None]:
    """Patch all DB calls in task_view, defaulting to empty lists.

    Yields a dict of the mock objects so tests can customise return values.
    """
    with (
        patch(f"{_MOCK_BASE}.list_tasks", return_value=[]) as m_list,
        patch(f"{_MOCK_BASE}.list_epics", return_value=[]) as m_epics,
        patch(f"{_MOCK_BASE}.get_dependencies", return_value=[]) as m_deps,
        patch(f"{_MOCK_BASE}.get_dependents", return_value=[]) as m_depts,
        patch(f"{_MOCK_BASE}.get_task_log", return_value=[]) as m_log,
    ):
        yield {
            "list_tasks": m_list,
            "list_epics": m_epics,
            "get_dependencies": m_deps,
            "get_dependents": m_depts,
            "get_task_log": m_log,
        }


# ---------------------------------------------------------------------------
# Shared helper: trigger highlight on the first selectable task
# ---------------------------------------------------------------------------


async def _select_first_task(pilot: Any) -> None:
    """Press j then k to ensure DataTable fires a highlight event."""
    await pilot.press("j")
    await pilot.pause()
    await pilot.press("k")
    await pilot.pause()


# ===================================================================
# A. Rendering & Layout
# ===================================================================


class TestRendering:
    """Tests for initial rendering of the task list and status bar."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_no_tasks(self, mock_task_data: MockDict) -> None:
        """Status bar shows 'no tasks' when list_tasks returns empty."""
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-status-bar", Static)
            assert "no tasks" in str(bar.content)

    @pytest.mark.asyncio
    async def test_single_status_group_header(self, mock_task_data: MockDict) -> None:
        """A single-status list renders the correct section header."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_multi_status_groups_in_order(self, mock_task_data: MockDict) -> None:
        """Multiple status groups render in STATUS_ORDER."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="done"),
            make_task(id=2, status="open"),
            make_task(id=3, status="active"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # Filter to header rows only
            headers = [
                t for t in titles if any(label in t for label in ("READY", "ACTIVE", "DONE"))
            ]
            assert len(headers) == 3
            # STATUS_ORDER: open, active, blocked, done, failed
            assert "READY" in headers[0]
            assert "ACTIVE" in headers[1]
            assert "DONE" in headers[2]

    @pytest.mark.asyncio
    async def test_task_labels_show_correct_icons(self, mock_task_data: MockDict) -> None:
        """Each status gets the correct icon in its row."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
            make_task(id=3, title="Blocked task", status="blocked"),
            make_task(id=4, title="Done task", status="done"),
            make_task(id=5, title="Failed task", status="failed"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            icons = _table_cell_texts(table, "icon")
            titles = _table_cell_texts(table, "title")
            # Check icon/title pairs (skip header rows which have empty icons)
            task_rows = [
                (icon, title) for icon, title in zip(icons, titles, strict=False) if icon.strip()
            ]
            assert any("○" in i and "Open task" in t for i, t in task_rows)
            assert any("●" in i and "Active task" in t for i, t in task_rows)
            assert any("⚠" in i and "Blocked task" in t for i, t in task_rows)
            assert any("✓" in i and "Done task" in t for i, t in task_rows)
            assert any("✗" in i and "Failed task" in t for i, t in task_rows)

    @pytest.mark.asyncio
    async def test_long_title_truncated(self, mock_task_data: MockDict) -> None:
        """Titles longer than 45 chars are truncated with '...'."""
        long_title = "A" * 60
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title=long_title, status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # Filter to task rows (contain "A"s but not section headers)
            task_titles = [t for t in titles if "A" in t and "READY" not in t]
            assert len(task_titles) >= 1
            assert "..." in task_titles[0]
            assert long_title not in task_titles[0]

    @pytest.mark.asyncio
    async def test_status_bar_shows_per_status_counts(self, mock_task_data: MockDict) -> None:
        """Status bar includes counts per status group."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open"),
            make_task(id=2, status="open"),
            make_task(id=3, status="active"),
            make_task(id=4, status="blocked"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-status-bar", Static)
            assert "2 ready" in str(bar.content)
            assert "1 active" in str(bar.content)
            assert "1 blocked" in str(bar.content)


# ===================================================================
# B. Keyboard Navigation
# ===================================================================


class TestKeyboardNavigation:
    """Tests for j/k navigation and refresh."""

    @pytest.mark.asyncio
    async def test_j_moves_highlight_down(self, mock_task_data: MockDict) -> None:
        """Pressing j moves the cursor down."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="First", status="open"),
            make_task(id=2, title="Second", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial = table.cursor_row
            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row is not None
            if initial is not None:
                assert table.cursor_row > initial

    @pytest.mark.asyncio
    async def test_k_moves_highlight_up(self, mock_task_data: MockDict) -> None:
        """Pressing k moves the cursor up."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="First", status="open"),
            make_task(id=2, title="Second", status="open"),
            make_task(id=3, title="Third", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            # Move down twice so we have room to go back up
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            pos_after_jj = table.cursor_row
            await pilot.press("k")
            await pilot.pause()
            assert table.cursor_row is not None
            assert pos_after_jj is not None
            assert table.cursor_row < pos_after_jj

    @pytest.mark.asyncio
    async def test_highlighting_task_updates_detail_header(self, mock_task_data: MockDict) -> None:
        """Highlighting a task updates the detail header."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=42, title="My task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            header = app.query_one("#task-detail-header", Static)
            assert "42" in str(header.content) or "DETAIL" in str(header.content)

    @pytest.mark.asyncio
    async def test_r_refreshes_task_list(self, mock_task_data: MockDict) -> None:
        """Pressing r re-calls list_tasks and updates the table."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Initial", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            # Change what list_tasks returns, then press r
            mock_task_data["list_tasks"].return_value = [
                make_task(id=1, title="Task A", status="open"),
                make_task(id=2, title="Task B", status="open"),
                make_task(id=3, title="Task C", status="active"),
            ]
            await pilot.press("r")
            await pilot.pause()

            new_count = table.row_count
            assert new_count > initial_count


# ===================================================================
# C. Detail Pane Content
# ===================================================================


class TestDetailPane:
    """Tests for the right-side detail pane content.

    Each test presses 'j' then 'k' to ensure the DataTable fires a
    highlight event, which triggers _render_task_detail.
    """

    @pytest.mark.asyncio
    async def test_shows_task_title(self, mock_task_data: MockDict) -> None:
        """Detail pane shows the task title."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Important task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Important task" in text

    @pytest.mark.asyncio
    async def test_shows_status_and_priority(self, mock_task_data: MockDict) -> None:
        """Detail pane shows status and priority."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active", priority=3),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "active" in text
            assert "3" in text

    @pytest.mark.asyncio
    async def test_shows_epic_info_with_progress(self, mock_task_data: MockDict) -> None:
        """Detail pane shows epic info with done/total progress."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=2, status="open", epic_key="AUTH", parent_task_id=100),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH", child_count=10, children_done=7),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "AUTH" in text
            assert "7/10 done" in text

    @pytest.mark.asyncio
    async def test_shows_relative_timestamps(self, mock_task_data: MockDict) -> None:
        """Detail pane shows relative timestamps."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open", created_at="2020-01-01T00:00:00"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            # Should show "Created Xd ago" (very old date)
            assert "Created" in text
            assert "ago" in text

    @pytest.mark.asyncio
    async def test_shows_dependencies(self, mock_task_data: MockDict) -> None:
        """Detail pane shows 'Depends on:' section."""
        dep_task = make_task(id=10, title="Prerequisite", status="done")
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="blocked"),
        ]
        mock_task_data["get_dependencies"].return_value = [dep_task]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Depends on:" in text
            assert "Prerequisite" in text

    @pytest.mark.asyncio
    async def test_shows_dependents(self, mock_task_data: MockDict) -> None:
        """Detail pane shows 'Blocks:' section."""
        dependent = make_task(id=20, title="Downstream work", status="open")
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_dependents"].return_value = [dependent]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Blocks:" in text
            assert "Downstream work" in text

    @pytest.mark.asyncio
    async def test_shows_description(self, mock_task_data: MockDict) -> None:
        """Detail pane shows description text."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, description="This explains what to do.", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Description:" in text
            assert "This explains what to do." in text

    @pytest.mark.asyncio
    async def test_shows_error_text(self, mock_task_data: MockDict) -> None:
        """Detail pane shows error info for failed tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="failed", error="Timeout after 30s"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Error:" in text
            assert "Timeout after 30s" in text

    @pytest.mark.asyncio
    async def test_shows_work_log_entries(self, mock_task_data: MockDict) -> None:
        """Detail pane shows work log entries."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_task_log"].return_value = [
            make_log_entry(message="Started analysis"),
            make_log_entry(id=2, message="Found root cause"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Work Log:" in text
            assert "Started analysis" in text
            assert "Found root cause" in text


# ===================================================================
# D. Mouse Interaction
# ===================================================================


class TestMouseInteraction:
    """Tests for mouse click behavior in the task table."""

    @pytest.mark.asyncio
    async def test_click_highlights_task(self, mock_task_data: MockDict) -> None:
        """Clicking on a task row highlights it."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
            make_task(id=2, title="Task B", status="open"),
            make_task(id=3, title="Task C", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            # Click at a y-offset that should hit a task row
            await pilot.click("#task-table", offset=(5, 3))
            await pilot.pause()
            assert table.cursor_row is not None

    @pytest.mark.asyncio
    async def test_click_updates_detail_pane(self, mock_task_data: MockDict) -> None:
        """Selecting a task updates the detail pane content."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Click me", status="open"),
            make_task(id=2, title="Another task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            # Use keyboard to select a task (more reliable than click offsets)
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert len(text.strip()) > 0


# ===================================================================
# E. Screen Switching (BrowserContainer)
# ===================================================================


class TestScreenSwitching:
    """Tests that 1/2/3 keys switch between browser screens.

    Uses the real BrowserContainer since the key bindings live there.
    """

    @pytest.fixture()
    def mock_browser_deps(self) -> Generator[None, None, None]:
        """Patch heavy BrowserContainer dependencies."""
        with (
            patch(
                "emdx.ui.browser_container.get_theme",
                return_value="textual-dark",
            ),
            patch(f"{_MOCK_BASE}.list_tasks", return_value=[]),
            patch(f"{_MOCK_BASE}.list_epics", return_value=[]),
            patch(f"{_MOCK_BASE}.get_dependencies", return_value=[]),
            patch(f"{_MOCK_BASE}.get_dependents", return_value=[]),
            patch(f"{_MOCK_BASE}.get_task_log", return_value=[]),
        ):
            yield

    @pytest.mark.asyncio
    async def test_press_2_switches_to_tasks(self, mock_browser_deps: None) -> None:
        """Pressing 2 switches to the task browser."""
        from emdx.ui.browser_container import BrowserContainer

        app = BrowserContainer()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            assert app.current_browser == "task"

    @pytest.mark.asyncio
    async def test_press_1_from_tasks_switches_to_activity(self, mock_browser_deps: None) -> None:
        """Pressing 1 from tasks switches to activity browser."""
        from emdx.ui.browser_container import BrowserContainer

        app = BrowserContainer()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            assert app.current_browser == "task"
            await pilot.press("1")
            await pilot.pause()
            assert app.current_browser == "activity"

    @pytest.mark.asyncio
    async def test_press_3_from_tasks_switches_to_qa(self, mock_browser_deps: None) -> None:
        """Pressing 3 from tasks switches to Q&A."""
        from emdx.ui.browser_container import BrowserContainer

        app = BrowserContainer()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("3")
            await pilot.pause()
            assert app.current_browser == "qa"

    @pytest.mark.asyncio
    async def test_help_bar_shows_key_hints(self, mock_task_data: MockDict) -> None:
        """TaskBrowser help bar shows screen-switching hints."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpBarApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpBarApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-help-bar", Static)
            assert "1" in str(bar.content)
            assert "2" in str(bar.content)
            assert "3" in str(bar.content)
            assert "Docs" in str(bar.content)
            assert "Tasks" in str(bar.content)
            assert "Q&A" in str(bar.content)


# ===================================================================
# F. Edge Cases
# ===================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_task_with_all_optional_fields_none(self, mock_task_data: MockDict) -> None:
        """A task with all optional fields as None renders without crashing."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                status="open",
                description=None,
                error=None,
                epic_key=None,
                created_at=None,
                updated_at=None,
                completed_at=None,
                tags=None,
                execution_id=None,
                output_doc_id=None,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Test task" in text

    @pytest.mark.asyncio
    async def test_very_long_description(self, mock_task_data: MockDict) -> None:
        """A task with a very long description renders without crashing."""
        long_desc = "x" * 5000
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open", description=long_desc),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Description:" in text

    @pytest.mark.asyncio
    async def test_list_tasks_exception_shows_empty(self, mock_task_data: MockDict) -> None:
        """If list_tasks raises, the view shows an empty state gracefully."""
        mock_task_data["list_tasks"].side_effect = RuntimeError("DB gone")
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-status-bar", Static)
            assert "no tasks" in str(bar.content)

    @pytest.mark.asyncio
    async def test_list_epics_exception_tasks_still_render(self, mock_task_data: MockDict) -> None:
        """If list_epics raises, tasks still render."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Still visible", status="open"),
        ]
        mock_task_data["list_epics"].side_effect = RuntimeError("Epics broken")
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            # Should have at least the header + 1 task row
            assert table.row_count >= 2

    @pytest.mark.asyncio
    async def test_refresh_replaces_old_data(self, mock_task_data: MockDict) -> None:
        """Refreshing fully replaces the old data."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Old task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            count_before = table.row_count

            # Refresh with different data
            mock_task_data["list_tasks"].return_value = [
                make_task(id=2, title="New task A", status="active"),
                make_task(id=3, title="New task B", status="active"),
            ]
            await pilot.press("r")
            await pilot.pause()

            # Old data replaced — row count should reflect new data
            count_after = table.row_count
            assert count_after != count_before


# ===================================================================
# G. Unit Tests for pure functions (no pilot needed)
# ===================================================================


class TestPureFunctions:
    """Unit tests for helper functions that need no TUI."""

    def test_format_time_ago_none(self) -> None:
        assert _format_time_ago(None) == ""

    def test_format_time_ago_invalid(self) -> None:
        assert _format_time_ago("not-a-date") == ""

    def test_task_label_short_title(self) -> None:
        task = make_task(title="Fix bug", status="open")
        label = _task_label(task)
        assert "○" in label
        assert "Fix bug" in label

    def test_task_label_long_title_truncated(self) -> None:
        task = make_task(title="A" * 60, status="active")
        label = _task_label(task)
        assert "●" in label
        assert "..." in label
        # Full 60-char title should NOT appear
        assert "A" * 51 not in label

    def test_task_label_unknown_status(self) -> None:
        task = make_task(status="weird")
        label = _task_label(task)
        assert "?" in label


# ===================================================================
# H. Filter Bar
# ===================================================================


class TestFilterBar:
    """Tests for the live filter bar (/ to show, Escape to hide)."""

    @pytest.mark.asyncio
    async def test_slash_shows_filter_input(self, mock_task_data: MockDict) -> None:
        """Pressing / shows the filter input and focuses it."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            assert filter_input.display is False

            await pilot.press("slash")
            await pilot.pause()
            assert filter_input.display is True
            assert filter_input.has_focus

    @pytest.mark.asyncio
    async def test_escape_hides_filter_input(self, mock_task_data: MockDict) -> None:
        """Pressing Escape clears and hides the filter input."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            assert filter_input.display is True

            await pilot.press("escape")
            await pilot.pause()
            assert filter_input.display is False
            assert filter_input.value == ""

    @pytest.mark.asyncio
    async def test_filter_by_title(self, mock_task_data: MockDict) -> None:
        """Typing a filter narrows tasks by title."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix authentication bug", status="open"),
            make_task(id=2, title="Add logging", status="open"),
            make_task(id=3, title="Update docs", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            await pilot.press("slash")
            await pilot.pause()
            # Type "auth" into the filter
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "auth"
            await pilot.pause(0.3)  # Wait for debounce

            # Should have fewer rows
            assert table.row_count < initial_count
            # The matching task should still be visible
            titles = _table_cell_texts(table, "title")
            assert any("auth" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_filter_by_epic_key(self, mock_task_data: MockDict) -> None:
        """Filter matches against epic_key."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open", epic_key="AUTH"),
            make_task(id=2, title="Task B", status="open", epic_key="TUI"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "AUTH"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if t.strip() and "READY" not in t]
            assert len(task_titles) == 1
            assert "Task A" in task_titles[0]

    @pytest.mark.asyncio
    async def test_filter_by_description(self, mock_task_data: MockDict) -> None:
        """Filter matches against description text."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Task A",
                status="open",
                description="Implement OAuth flow",
            ),
            make_task(
                id=2,
                title="Task B",
                status="open",
                description="Write unit tests",
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "OAuth"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if t.strip() and "READY" not in t]
            assert len(task_titles) == 1
            assert "Task A" in task_titles[0]

    @pytest.mark.asyncio
    async def test_filter_by_tags(self, mock_task_data: MockDict) -> None:
        """Filter matches against tags."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open", tags="security,auth"),
            make_task(id=2, title="Task B", status="open", tags="frontend,css"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "security"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if t.strip() and "READY" not in t]
            assert len(task_titles) == 1
            assert "Task A" in task_titles[0]

    @pytest.mark.asyncio
    async def test_filter_no_matches(self, mock_task_data: MockDict) -> None:
        """Filter with no matches shows 'no matches' in status bar."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "zzzznotfound"
            await pilot.pause(0.3)

            bar = app.query_one("#task-status-bar", Static)
            assert "no matches" in str(bar.content)

    @pytest.mark.asyncio
    async def test_filter_status_bar_shows_count(self, mock_task_data: MockDict) -> None:
        """Status bar shows filter: N/M when filter is active."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix bug", status="open"),
            make_task(id=2, title="Add feature", status="open"),
            make_task(id=3, title="Fix typo", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "Fix"
            await pilot.pause(0.3)

            bar = app.query_one("#task-status-bar", Static)
            bar_text = str(bar.content)
            assert "filter:" in bar_text
            assert "2/3" in bar_text

    @pytest.mark.asyncio
    async def test_vim_keys_dont_trigger_while_filtering(self, mock_task_data: MockDict) -> None:
        """Vim keys (j, k, d, a, b, r) don't trigger actions while filter is focused."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
            make_task(id=2, title="Task B", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            assert filter_input.has_focus

            # Type vim keys — they should go into the input, not trigger actions
            await pilot.press("j")
            await pilot.press("k")
            await pilot.press("d")
            await pilot.press("a")
            await pilot.press("b")
            await pilot.press("r")
            await pilot.pause()

            # The input should contain the typed characters
            assert filter_input.value == "jkdabr"

    @pytest.mark.asyncio
    async def test_escape_restores_all_tasks(self, mock_task_data: MockDict) -> None:
        """Pressing Escape after filtering restores all tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
            make_task(id=2, title="Task B", status="open"),
            make_task(id=3, title="Task C", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            # Filter down
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "Task A"
            await pilot.pause(0.3)
            assert table.row_count < initial_count

            # Escape to clear
            await pilot.press("escape")
            await pilot.pause()
            assert table.row_count == initial_count

    @pytest.mark.asyncio
    async def test_filter_case_insensitive(self, mock_task_data: MockDict) -> None:
        """Filter matching is case-insensitive."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix Authentication Bug", status="open"),
            make_task(id=2, title="Add logging", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "authentication"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if t.strip() and "READY" not in t]
            assert len(task_titles) == 1
            assert "Authentication" in task_titles[0]

    @pytest.mark.asyncio
    async def test_help_bar_shows_filter_hint(self, mock_task_data: MockDict) -> None:
        """TaskBrowser help bar includes the / filter hint."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpBarApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpBarApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-help-bar", Static)
            bar_text = str(bar.content)
            assert "filter" in bar_text


# ===================================================================
# I. Status Filter Keys
# ===================================================================


class TestStatusFilter:
    """Tests for quick status filter keys (o/i/x/f/*)."""

    @pytest.mark.asyncio
    async def test_o_filters_to_open_only(self, mock_task_data: MockDict) -> None:
        """Pressing o shows only open/ready tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
            make_task(id=3, title="Done task", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            await pilot.press("o")
            await pilot.pause()

            assert table.row_count < initial_count
            titles = _table_cell_texts(table, "title")
            assert any("READY" in t for t in titles)
            assert not any("ACTIVE" in t for t in titles)
            assert not any("DONE" in t for t in titles)

    @pytest.mark.asyncio
    async def test_i_filters_to_active_only(self, mock_task_data: MockDict) -> None:
        """Pressing i shows only active tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
            make_task(id=3, title="Done task", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("ACTIVE" in t for t in titles)
            assert not any("READY" in t for t in titles)
            assert not any("DONE" in t for t in titles)

    @pytest.mark.asyncio
    async def test_x_filters_to_blocked_only(self, mock_task_data: MockDict) -> None:
        """Pressing x shows only blocked tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Blocked task", status="blocked"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("BLOCKED" in t for t in titles)
            assert not any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_f_filters_to_done_and_failed(self, mock_task_data: MockDict) -> None:
        """Pressing f shows done and failed tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Done task", status="done"),
            make_task(id=3, title="Failed task", status="failed"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("DONE" in t for t in titles)
            assert any("FAILED" in t for t in titles)
            assert not any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_asterisk_clears_status_filter(self, mock_task_data: MockDict) -> None:
        """Pressing * clears the status filter, showing all tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
            make_task(id=3, title="Done task", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            # Filter down
            await pilot.press("o")
            await pilot.pause()
            assert table.row_count < initial_count

            # Clear with *
            await pilot.press("asterisk")
            await pilot.pause()
            assert table.row_count == initial_count

    @pytest.mark.asyncio
    async def test_toggle_same_key_clears_filter(self, mock_task_data: MockDict) -> None:
        """Pressing the same status filter key again clears it."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            await pilot.press("o")
            await pilot.pause()
            assert table.row_count < initial_count

            # Press o again to clear
            await pilot.press("o")
            await pilot.pause()
            assert table.row_count == initial_count

    @pytest.mark.asyncio
    async def test_status_filter_shows_label_in_status_bar(self, mock_task_data: MockDict) -> None:
        """Status bar shows the active status filter label."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            assert "READY" in str(bar.content)

    @pytest.mark.asyncio
    async def test_status_filter_composes_with_text_filter(self, mock_task_data: MockDict) -> None:
        """Status filter and text filter work together."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix auth bug", status="open"),
            make_task(id=2, title="Fix deploy bug", status="open"),
            make_task(id=3, title="Fix auth regression", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Filter to open only
            await pilot.press("o")
            await pilot.pause()

            # Add text filter for "auth"
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "auth"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if t.strip() and "READY" not in t]
            # Only "Fix auth bug" (open + matches "auth")
            assert len(task_titles) == 1
            assert "auth" in task_titles[0].lower()

    @pytest.mark.asyncio
    async def test_status_keys_blocked_in_filter_input(self, mock_task_data: MockDict) -> None:
        """Status filter keys don't trigger while typing in filter input."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task A", status="open"),
            make_task(id=2, title="Task B", status="active"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)

            await pilot.press("o")
            await pilot.press("i")
            await pilot.press("x")
            await pilot.press("f")
            await pilot.pause()

            # Keys went into the input, not triggering status filter
            assert filter_input.value == "oixf"

    @pytest.mark.asyncio
    async def test_status_filter_no_matches(self, mock_task_data: MockDict) -> None:
        """Status filter with no matching tasks shows 'no matches'."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Filter to active — but there are none
            await pilot.press("i")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            assert "no matches" in str(bar.content)


# ===================================================================
# J. Epic Grouping Toggle
# ===================================================================


class TestEpicGrouping:
    """Tests for the g key epic/status grouping toggle."""

    @pytest.mark.asyncio
    async def test_g_toggles_to_epic_grouping(self, mock_task_data: MockDict) -> None:
        """Pressing g switches from status grouping to epic grouping."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Auth task", status="open", epic_key="AUTH"),
            make_task(id=2, title="TUI task", status="open", epic_key="TUI"),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
            make_epic(id=101, epic_key="TUI"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # Default: grouped by status — should have READY header
            assert any("READY" in t for t in titles)

            await pilot.press("g")
            await pilot.pause()

            titles = _table_cell_texts(table, "title")
            # Now grouped by epic — should have AUTH and TUI headers
            assert any("AUTH" in t for t in titles)
            assert any("TUI" in t for t in titles)
            # Should NOT have status headers
            assert not any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_g_toggles_back_to_status(self, mock_task_data: MockDict) -> None:
        """Pressing g twice returns to status grouping."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Auth task", status="open", epic_key="AUTH"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_shows_ungrouped(self, mock_task_data: MockDict) -> None:
        """Tasks without an epic appear under UNGROUPED."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Epic task", status="open", epic_key="AUTH"),
            make_task(id=2, title="Loose task", status="open", epic_key=None),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("UNGROUPED" in t for t in titles)
            assert any("AUTH" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_shows_progress(self, mock_task_data: MockDict) -> None:
        """Epic headers show done/total progress when epic info is available."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open", epic_key="AUTH"),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(epic_key="AUTH", child_count=10, children_done=7),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("7/10 done" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_status_bar_indicator(self, mock_task_data: MockDict) -> None:
        """Status bar shows 'by epic' when epic grouping is active."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            assert "by epic" in str(bar.content)

    @pytest.mark.asyncio
    async def test_epic_grouping_composes_with_filters(self, mock_task_data: MockDict) -> None:
        """Epic grouping works together with status and text filters."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix auth", status="open", epic_key="AUTH"),
            make_task(id=2, title="Fix deploy", status="open", epic_key="AUTH"),
            make_task(id=3, title="Fix TUI", status="active", epic_key="TUI"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Switch to epic grouping
            await pilot.press("g")
            await pilot.pause()
            # Filter to open only
            await pilot.press("o")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # AUTH tasks are open, TUI task is active — TUI should be gone
            assert any("AUTH" in t for t in titles)
            assert not any("TUI" in t for t in titles)

    @pytest.mark.asyncio
    async def test_g_blocked_in_filter_input(self, mock_task_data: MockDict) -> None:
        """Pressing g in the filter input types 'g' instead of toggling."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)

            await pilot.press("g")
            await pilot.pause()

            assert filter_input.value == "g"

    @pytest.mark.asyncio
    async def test_help_bar_shows_group_hint(self, mock_task_data: MockDict) -> None:
        """Help bar includes the g group hint."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpBarApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpBarApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-help-bar", Static)
            assert "group" in str(bar.content)

    @pytest.mark.asyncio
    async def test_epic_grouping_hides_all_done_epics(self, mock_task_data: MockDict) -> None:
        """Epics where all tasks are done/failed are hidden in epic grouping."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Active work", status="open", epic_key="LIVE"),
            make_task(id=2, title="Old stuff", status="done", epic_key="DEAD"),
            make_task(id=3, title="Also old", status="failed", epic_key="DEAD"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("LIVE" in t for t in titles)
            assert not any("DEAD" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_hides_done_tasks_in_mixed_group(
        self, mock_task_data: MockDict
    ) -> None:
        """Done tasks within an epic that has open tasks are hidden."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open work", status="open", epic_key="MIX"),
            make_task(id=2, title="Finished work", status="done", epic_key="MIX"),
            make_task(id=3, title="Failed work", status="failed", epic_key="MIX"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("MIX" in t for t in titles)
            assert any("Open work" in t for t in titles)
            assert not any("Finished work" in t for t in titles)
            assert not any("Failed work" in t for t in titles)


# ===================================================================
# K. Won't Do Status
# ===================================================================


class TestWontdoStatus:
    """Tests for the wontdo status display and keybinding."""

    @pytest.mark.asyncio
    async def test_wontdo_icon_and_color(self, mock_task_data: MockDict) -> None:
        """Wontdo tasks show the ⊘ icon with dim styling."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Skipped task", status="wontdo"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            icons = _table_cell_texts(table, "icon")
            task_icons = [i for i in icons if i.strip()]
            assert any("⊘" in i for i in task_icons)

    @pytest.mark.asyncio
    async def test_w_key_marks_task_wontdo(self, mock_task_data: MockDict) -> None:
        """Pressing w marks the selected task as wontdo."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Skip this", status="open"),
            make_task(id=2, title="Another", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Move past header to first task row, then back
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()

            with patch(f"{_MOCK_BASE}.update_task") as m_update:
                await pilot.press("w")
                await pilot.pause()
                m_update.assert_called_once_with(1, status="wontdo")

    @pytest.mark.asyncio
    async def test_f_filter_includes_wontdo(self, mock_task_data: MockDict) -> None:
        """Pressing f shows wontdo tasks alongside done and failed."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Done task", status="done"),
            make_task(id=3, title="Wontdo task", status="wontdo"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("DONE" in t for t in titles)
            assert any("WON'T DO" in t for t in titles)
            assert not any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_wontdo_hidden_in_epic_grouping(self, mock_task_data: MockDict) -> None:
        """Epics where all tasks are wontdo are hidden in epic grouping."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Active work", status="open", epic_key="LIVE"),
            make_task(id=2, title="Skipped", status="wontdo", epic_key="SKIP"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("LIVE" in t for t in titles)
            assert not any("SKIP" in t for t in titles)

    @pytest.mark.asyncio
    async def test_w_blocked_in_filter_input(self, mock_task_data: MockDict) -> None:
        """Pressing w in the filter input types 'w' instead of marking wontdo."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)

            await pilot.press("w")
            await pilot.pause()

            assert filter_input.value == "w"
