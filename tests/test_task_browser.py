"""Pilot-based tests for TaskBrowser / TaskView TUI widgets."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, RichLog, Static

from emdx.models.types import EpicTaskDict, TaskDict, TaskLogEntryDict
from emdx.ui.link_helpers import extract_urls as _extract_urls
from emdx.ui.link_helpers import linkify_text as _linkify_text
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
    epic_key: str | None = None,
    created_at: str | None = "2025-01-01T12:00:00",
    updated_at: str | None = None,
    completed_at: str | None = None,
    parent_task_id: int | None = None,
    type: str = "manual",
    epic_seq: int | None = None,
    **kwargs: object,
) -> TaskDict:
    base: TaskDict = {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "description": description,
        "epic_key": epic_key,
        "created_at": created_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "gameplan_id": None,
        "project": None,
        "current_step": None,
        "type": type,
        "source_doc_id": None,
        "parent_task_id": parent_task_id,
        "epic_seq": epic_seq,
    }
    return base


def make_epic(
    id: int = 1,
    epic_key: str = "AUTH",
    status: str = "open",
    child_count: int = 10,
    children_done: int = 7,
    children_open: int = 3,
    epic_seq: int = 1,
    **kwargs: object,
) -> EpicTaskDict:
    base = make_task(
        id=id,
        title=f"Epic: {epic_key}",
        status=status,
        epic_key=epic_key,
        type="epic",
        epic_seq=epic_seq,
    )
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


def _task_titles(table: DataTable[Any]) -> list[str]:
    """Get title texts for actual task rows only (skip headers/separators)."""
    titles: list[str] = []
    for row in table.ordered_rows:
        key = str(row.key.value)
        if key.startswith("task:"):
            try:
                val = table.get_cell(row.key, "title")
                titles.append(str(val))
            except Exception:
                pass
    return titles


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


def _make_list_tasks_side_effect(
    mock: MagicMock,
) -> Any:
    """Return a side_effect that filters by status like the real list_tasks.

    _load_tasks() calls list_tasks twice with different status filters.
    This side_effect reads ``mock.return_value`` (set by tests) and filters
    per-call so existing tests work unchanged.
    """

    def _side_effect(
        status: list[str] | None = None,
        **kwargs: object,
    ) -> list[TaskDict]:
        all_tasks: list[TaskDict] = mock.return_value
        if status is not None:
            return [t for t in all_tasks if t["status"] in status]
        return list(all_tasks)

    return _side_effect


@pytest.fixture()
def mock_task_data() -> Generator[MockDict, None, None]:
    """Patch all DB calls in task_view, defaulting to empty lists.

    Yields a dict of the mock objects so tests can customise return values.
    """
    with (
        patch(f"{_MOCK_BASE}.list_tasks") as m_list,
        patch(f"{_MOCK_BASE}.list_epics", return_value=[]) as m_epics,
        patch(f"{_MOCK_BASE}.count_tasks_by_status") as m_counts,
        patch(f"{_MOCK_BASE}.get_dependencies", return_value=[]) as m_deps,
        patch(f"{_MOCK_BASE}.get_dependents", return_value=[]) as m_depts,
        patch(f"{_MOCK_BASE}.get_task_log", return_value=[]) as m_log,
    ):
        m_list.return_value = []
        m_list.side_effect = _make_list_tasks_side_effect(m_list)

        def _count_side_effect() -> dict[str, int]:
            counts: dict[str, int] = {}
            for t in m_list.return_value:
                s = t["status"]
                counts[s] = counts.get(s, 0) + 1
            return counts

        m_counts.side_effect = _count_side_effect
        yield {
            "list_tasks": m_list,
            "list_epics": m_epics,
            "count_tasks_by_status": m_counts,
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
        """A single-status list renders the correct section header in status mode."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Switch to status grouping
            await pilot.press("g")
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("READY" in t for t in titles)

    @pytest.mark.asyncio
    async def test_multi_status_groups_in_order(self, mock_task_data: MockDict) -> None:
        """Multiple status groups render in STATUS_ORDER (in status grouping mode)."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="done"),
            make_task(id=2, status="open"),
            make_task(id=3, status="active"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Switch to status grouping to test status header ordering
            await pilot.press("g")
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # Filter to header rows only
            headers = [
                t for t in titles if any(label in t for label in ("READY", "ACTIVE", "DONE"))
            ]
            assert len(headers) == 3
            # STATUS_ORDER: active, open, blocked, done, failed
            assert "ACTIVE" in headers[0]
            assert "READY" in headers[1]
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
            # Switch to status grouping to see all statuses
            await pilot.press("g")
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            icons = _table_cell_texts(table, "icon")
            titles = _table_cell_texts(table, "title")
            # Check icon/title pairs (skip header rows which have empty icons)
            task_rows = [
                (icon, title) for icon, title in zip(icons, titles, strict=False) if icon.strip()
            ]
            assert any("⚪" in i and "Open task" in t for i, t in task_rows)
            assert any("🟢" in i and "Active task" in t for i, t in task_rows)
            assert any("🟡" in i and "Blocked task" in t for i, t in task_rows)
            assert any("✅" in i and "Done task" in t for i, t in task_rows)
            assert any("❌" in i and "Failed task" in t for i, t in task_rows)

    @pytest.mark.asyncio
    async def test_long_title_stored_in_full(self, mock_task_data: MockDict) -> None:
        """Full titles stored in cells; DataTable handles visual clipping."""
        long_title = "A" * 60
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title=long_title, status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            task_titles = [t for t in titles if "A" in t and "READY" not in t]
            assert len(task_titles) >= 1
            assert long_title in task_titles[0]

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
            make_task(id=42, title="My task", status="open", epic_key="AUTH", epic_seq=1),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            header = app.query_one("#task-detail-header", Static)
            assert "AUTH-1" in str(header.content) or "Task" in str(header.content)

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
            # Navigate past status header + cross-group epic header to task row
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "AUTH" in text
            assert "7/10 done" in text

    @pytest.mark.asyncio
    async def test_shows_relative_timestamps(self, mock_task_data: MockDict) -> None:
        """Detail pane shows formatted timestamps (relative or absolute date)."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open", created_at="2020-01-01T00:00:00"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            # Old date shows absolute format "Jan 01, 2020"
            assert "Created" in text
            assert "Jan 01, 2020" in text

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

    @pytest.mark.asyncio
    async def test_work_log_timeline_format(self, mock_task_data: MockDict) -> None:
        """Work log entries use ● marker, │ gutter, and ╵ terminal cap."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_task_log"].return_value = [
            make_log_entry(message="First note"),
            make_log_entry(id=2, message="Second note"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Work Log:" in text
            # Dot markers for each entry
            assert "●" in text
            # Body uses │ gutter
            assert "│ First note" in text
            assert "│ Second note" in text
            # Terminal cap on last entry
            assert "╵" in text

    @pytest.mark.asyncio
    async def test_work_log_shows_all_lines(self, mock_task_data: MockDict) -> None:
        """Multiline notes show every line, no truncation."""
        multiline_msg = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6"
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_task_log"].return_value = [
            make_log_entry(message=multiline_msg),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            for i in range(1, 7):
                assert f"Line {i}" in text
            assert "more lines" not in text


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
    async def test_help_bar_shows_key_hints(self, mock_task_data: MockDict) -> None:
        """TaskBrowser help bar shows task-context keybinding hints."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpBarApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpBarApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-help-bar", Static)
            content = str(bar.content)
            assert "Done" in content
            assert "Active" in content
            assert "Blocked" in content
            assert "Help" in content
            assert "Filter" in content


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
                epic_key=None,
                created_at=None,
                updated_at=None,
                completed_at=None,
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

    def test_format_time_ago_recent_days(self) -> None:
        """Days < 7 show relative like '3d ago'."""
        from datetime import datetime, timedelta

        three_days = datetime.now() - timedelta(days=3)
        result = _format_time_ago(three_days.isoformat())
        assert result == "3d ago"

    def test_format_time_ago_old_shows_date(self) -> None:
        """Days >= 7 show absolute date like 'Jan 15'."""
        from datetime import datetime, timedelta

        old = datetime.now() - timedelta(days=30)
        result = _format_time_ago(old.isoformat())
        # Should be a month abbreviation + day, not 'Xd ago'
        assert "ago" not in result
        assert old.strftime("%b") in result

    def test_task_label_short_title(self) -> None:
        task = make_task(title="Fix bug", status="open")
        label = _task_label(task)
        assert "⚪" in label
        assert "Fix bug" in label

    def test_task_label_long_title_truncated(self) -> None:
        task = make_task(title="A" * 60, status="active")
        label = _task_label(task)
        assert "🟢" in label
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
            task_titles = _task_titles(table)
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
            task_titles = _task_titles(table)
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
            task_titles = _task_titles(table)
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
            assert "Filter" in bar_text


# ===================================================================
# I. Status Filter Keys
# ===================================================================


class TestStatusFilter:
    """Tests for quick status filter keys (o/i/x/f/*)."""

    @pytest.mark.asyncio
    async def test_o_hides_open_tasks(self, mock_task_data: MockDict) -> None:
        """Pressing o hides open/ready tasks (toggle model)."""
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
            task_titles = _task_titles(table)
            assert not any("Open task" in t for t in task_titles)
            assert any("Active task" in t for t in task_titles)

    @pytest.mark.asyncio
    async def test_i_hides_active_tasks(self, mock_task_data: MockDict) -> None:
        """Pressing i hides active tasks (toggle model)."""
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
            task_titles = _task_titles(table)
            assert not any("Active task" in t for t in task_titles)
            assert any("Open task" in t for t in task_titles)

    @pytest.mark.asyncio
    async def test_x_hides_blocked_tasks(self, mock_task_data: MockDict) -> None:
        """Pressing x hides blocked tasks (toggle model)."""
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
            task_titles = _task_titles(table)
            assert not any("Blocked task" in t for t in task_titles)
            assert any("Open task" in t for t in task_titles)

    @pytest.mark.asyncio
    async def test_f_hides_finished_tasks(self, mock_task_data: MockDict) -> None:
        """Pressing f hides done/failed/wontdo/duplicate tasks (toggle model)."""
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
            task_titles = _task_titles(table)
            assert not any("Done task" in t for t in task_titles)
            assert not any("Failed task" in t for t in task_titles)
            assert any("Open task" in t for t in task_titles)

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
    async def test_status_filter_shows_hiding_label_in_status_bar(
        self, mock_task_data: MockDict
    ) -> None:
        """Status bar shows 'hiding: READY' when open tasks are hidden."""
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
            bar_text = str(bar.content)
            assert "hiding:" in bar_text
            assert "READY" in bar_text

    @pytest.mark.asyncio
    async def test_status_filter_composes_with_text_filter(self, mock_task_data: MockDict) -> None:
        """Status filter (hide) and text filter work together."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix auth bug", status="open"),
            make_task(id=2, title="Fix deploy bug", status="open"),
            make_task(id=3, title="Fix auth regression", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Hide finished tasks (done/failed/wontdo/duplicate)
            await pilot.press("f")
            await pilot.pause()

            # Add text filter for "auth"
            await pilot.press("slash")
            await pilot.pause()
            filter_input = app.query_one("#task-filter-input", Input)
            filter_input.value = "auth"
            await pilot.pause(0.3)

            table = app.query_one("#task-table", DataTable)
            task_titles = _task_titles(table)
            # Only "Fix auth bug" (open + matches "auth", done regression hidden)
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
        """Hiding all present statuses shows 'no matches'."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Hide open — the only status present
            await pilot.press("o")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            assert "no matches" in str(bar.content)

    @pytest.mark.asyncio
    async def test_multiple_toggles_combine(self, mock_task_data: MockDict) -> None:
        """Pressing o then i hides both open and active tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Active task", status="active"),
            make_task(id=3, title="Blocked task", status="blocked"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Hide open
            await pilot.press("o")
            await pilot.pause()
            # Also hide active
            await pilot.press("i")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            task_titles = _task_titles(table)
            assert not any("Open task" in t for t in task_titles)
            assert not any("Active task" in t for t in task_titles)
            assert any("Blocked task" in t for t in task_titles)

    @pytest.mark.asyncio
    async def test_toggle_unhide_after_hide(self, mock_task_data: MockDict) -> None:
        """Pressing f twice: first hides finished, second shows them again."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Done task", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            initial_count = table.row_count

            # Hide finished
            await pilot.press("f")
            await pilot.pause()
            assert table.row_count < initial_count

            # Unhide finished
            await pilot.press("f")
            await pilot.pause()
            assert table.row_count == initial_count

    @pytest.mark.asyncio
    async def test_clear_all_resets_hidden(self, mock_task_data: MockDict) -> None:
        """Pressing * clears all hidden statuses and epic filter."""
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

            # Hide multiple statuses
            await pilot.press("o")
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            assert table.row_count < initial_count

            # Clear all
            await pilot.press("asterisk")
            await pilot.pause()
            assert table.row_count == initial_count

    @pytest.mark.asyncio
    async def test_status_bar_shows_hiding_label(self, mock_task_data: MockDict) -> None:
        """Status bar shows 'hiding: DONE+...' when finished tasks are hidden."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open task", status="open"),
            make_task(id=2, title="Done task", status="done"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            bar_text = str(bar.content)
            assert "hiding:" in bar_text
            assert "DONE" in bar_text


# ===================================================================
# J. Epic Grouping Toggle
# ===================================================================


class TestEpicGrouping:
    """Tests for the g key epic/status grouping toggle."""

    @pytest.mark.asyncio
    async def test_g_toggles_to_status_grouping(self, mock_task_data: MockDict) -> None:
        """Pressing g switches from epic grouping (default) to status grouping."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Auth task", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="TUI task", status="open", epic_key="TUI", parent_task_id=101),
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
            # Default: grouped by epic — should have AUTH and TUI headers
            assert any("AUTH" in t for t in titles)
            assert any("TUI" in t for t in titles)

            await pilot.press("g")
            await pilot.pause()

            titles = _table_cell_texts(table, "title")
            # Now grouped by status — should have top-level READY header
            # (In epic mode READY appears as indented sub-header "  READY",
            # but in status mode it appears as top-level "READY (N)")
            assert any(t.strip().startswith("READY") for t in titles)

    @pytest.mark.asyncio
    async def test_g_toggles_back_to_epic(self, mock_task_data: MockDict) -> None:
        """Pressing g twice returns to epic grouping (default)."""
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
            # Back to epic grouping — UNGROUPED header visible
            # (task has no parent_task_id, so goes to ungrouped)
            assert any("UNGROUPED" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_shows_ungrouped(self, mock_task_data: MockDict) -> None:
        """Tasks without an epic appear under UNGROUPED (default view)."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Epic task", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="Loose task", status="open", epic_key=None),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("UNGROUPED" in t for t in titles)
            assert any("AUTH" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_shows_progress(self, mock_task_data: MockDict) -> None:
        """Epic headers show done/total progress in the age column."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open", epic_key="AUTH", parent_task_id=100),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH", child_count=10, children_done=7),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            ages = _table_cell_texts(table, "age")
            assert any("7/10" in a for a in ages)

    @pytest.mark.asyncio
    async def test_status_grouping_status_bar_indicator(self, mock_task_data: MockDict) -> None:
        """Status bar shows 'by status' when status grouping is active."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Task", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            bar = app.query_one("#task-status-bar", Static)
            assert "by status" in str(bar.content)

    @pytest.mark.asyncio
    async def test_epic_grouping_composes_with_filters(self, mock_task_data: MockDict) -> None:
        """Epic grouping (default) works together with status hide filters."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Fix auth", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="Fix deploy", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=3, title="Fix TUI", status="active", epic_key="TUI", parent_task_id=101),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
            make_epic(id=101, epic_key="TUI"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Hide active tasks (epic grouping is default)
            await pilot.press("i")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # AUTH tasks are open (visible), TUI task is active (hidden)
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
    async def test_done_epics_collapsed_at_bottom(self, mock_task_data: MockDict) -> None:
        """Done epics appear at bottom under COMPLETED, children hidden."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1, title="Active work", status="open", epic_key="LIVE", parent_task_id=200
            ),
            make_task(id=2, title="Old stuff", status="done", epic_key="DEAD", parent_task_id=201),
            make_task(id=3, title="Also old", status="failed", epic_key="DEAD", parent_task_id=201),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=200, epic_key="LIVE"),
            make_epic(
                id=201,
                epic_key="DEAD",
                status="done",
                child_count=2,
                children_done=2,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # LIVE epic with children at top
            assert any("LIVE" in t for t in titles)
            # COMPLETED section with DEAD epic header
            assert any("COMPLETED" in t for t in titles)
            # DEAD epic header visible but children are not
            assert any("DEAD" in t for t in titles)
            assert not any("Old stuff" in t for t in titles)
            assert not any("Also old" in t for t in titles)

    @pytest.mark.asyncio
    async def test_epic_grouping_hides_done_in_mixed_group(self, mock_task_data: MockDict) -> None:
        """Done/failed children are hidden behind a fold in active epics."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open work", status="open", epic_key="MIX", parent_task_id=300),
            make_task(
                id=2, title="Finished work", status="done", epic_key="MIX", parent_task_id=300
            ),
            make_task(
                id=3, title="Failed work", status="failed", epic_key="MIX", parent_task_id=300
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=300, epic_key="MIX", child_count=3, children_done=2, children_open=1),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("MIX" in t for t in titles)
            assert any("Open work" in t for t in titles)
            # Done/failed tasks hidden behind fold by default
            assert not any("Finished work" in t for t in titles)
            assert not any("Failed work" in t for t in titles)
            # Fold row shows count
            assert any("2 completed" in t for t in titles)

    @pytest.mark.asyncio
    async def test_done_fold_expands_on_enter(self, mock_task_data: MockDict) -> None:
        """Pressing Enter on the done-fold row reveals completed tasks."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Open work", status="open", epic_key="MIX", parent_task_id=300),
            make_task(
                id=2,
                title="Finished work",
                status="done",
                epic_key="MIX",
                parent_task_id=300,
                completed_at="2026-03-05 12:00:00",
            ),
            make_task(
                id=3,
                title="Old finish",
                status="done",
                epic_key="MIX",
                parent_task_id=300,
                completed_at="2026-03-01 12:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=300, epic_key="MIX"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            # Navigate to the done-fold row
            for row_idx, row in enumerate(table.ordered_rows):
                if str(row.key.value).startswith("done-fold:"):
                    table.move_cursor(row=row_idx)
                    break
            await pilot.pause()

            # Press Enter to expand
            await pilot.press("enter")
            await pilot.pause()

            titles = _table_cell_texts(table, "title")
            # Both done tasks now visible
            assert any("Finished work" in t for t in titles)
            assert any("Old finish" in t for t in titles)
            # Most recently completed appears first (check order)
            finished_idx = next(i for i, t in enumerate(titles) if "Finished work" in t)
            old_idx = next(i for i, t in enumerate(titles) if "Old finish" in t)
            assert finished_idx < old_idx

    @pytest.mark.asyncio
    async def test_epics_sorted_by_recent_child_activity(self, mock_task_data: MockDict) -> None:
        """Epics with more recently updated children appear first."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Old child",
                status="open",
                epic_key="STALE",
                parent_task_id=500,
                updated_at="2025-01-01T00:00:00",
            ),
            make_task(
                id=2,
                title="Recent child",
                status="open",
                epic_key="FRESH",
                parent_task_id=501,
                updated_at="2025-06-15T12:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=500, epic_key="STALE"),
            make_epic(id=501, epic_key="FRESH"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            fresh_idx = next(i for i, t in enumerate(titles) if "FRESH" in t)
            stale_idx = next(i for i, t in enumerate(titles) if "STALE" in t)
            assert fresh_idx < stale_idx, "Epic with recently-updated child should appear first"

    @pytest.mark.asyncio
    async def test_epics_with_active_children_float_to_top(self, mock_task_data: MockDict) -> None:
        """Epics with in-progress children appear before those without."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Idle child",
                status="open",
                epic_key="IDLE",
                parent_task_id=600,
                updated_at="2025-06-15T12:00:00",
            ),
            make_task(
                id=2,
                title="Active child",
                status="active",
                epic_key="BUSY",
                parent_task_id=601,
                updated_at="2025-01-01T00:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=600, epic_key="IDLE"),
            make_epic(id=601, epic_key="BUSY"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            busy_idx = next(i for i, t in enumerate(titles) if "BUSY" in t)
            idle_idx = next(i for i, t in enumerate(titles) if "IDLE" in t)
            assert busy_idx < idle_idx, "Epic with active child should float above idle epic"

    @pytest.mark.asyncio
    async def test_children_sorted_oldest_first(self, mock_task_data: MockDict) -> None:
        """Tasks within an epic are sorted oldest-first (queue discipline)."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Newest task",
                status="open",
                epic_key="Q",
                parent_task_id=700,
                created_at="2025-03-01T00:00:00",
            ),
            make_task(
                id=2,
                title="Middle task",
                status="open",
                epic_key="Q",
                parent_task_id=700,
                created_at="2025-02-01T00:00:00",
            ),
            make_task(
                id=3,
                title="Oldest task",
                status="open",
                epic_key="Q",
                parent_task_id=700,
                created_at="2025-01-01T00:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=700, epic_key="Q"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            task_titles = _task_titles(table)
            q_tasks = [t for t in task_titles if t in {"Oldest task", "Middle task", "Newest task"}]
            assert q_tasks == ["Oldest task", "Middle task", "Newest task"], (
                f"Expected oldest-first queue order, got {q_tasks}"
            )


# ===================================================================
# K. Won't Do Status
# ===================================================================


class TestWontdoStatus:
    """Tests for the wontdo status display and keybinding."""

    @pytest.mark.asyncio
    async def test_wontdo_icon_and_color(self, mock_task_data: MockDict) -> None:
        """Wontdo tasks show the 🚫 icon with dim styling."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Skipped task", status="wontdo"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Wontdo task visible by default (ungrouped, shown inline)
            table = app.query_one("#task-table", DataTable)
            icons = _table_cell_texts(table, "icon")
            task_icons = [i for i in icons if i.strip()]
            assert any("🚫" in i for i in task_icons)

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
    async def test_f_filter_hides_wontdo(self, mock_task_data: MockDict) -> None:
        """Pressing f hides wontdo tasks alongside done and failed."""
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
            task_titles = _task_titles(table)
            assert not any("Done task" in t for t in task_titles)
            assert not any("Wontdo task" in t for t in task_titles)
            assert any("Open task" in t for t in task_titles)

    @pytest.mark.asyncio
    async def test_wontdo_epic_collapsed_at_bottom(self, mock_task_data: MockDict) -> None:
        """Epics where all tasks are wontdo appear collapsed under COMPLETED."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1, title="Active work", status="open", epic_key="LIVE", parent_task_id=400
            ),
            make_task(id=2, title="Skipped", status="wontdo", epic_key="SKIP", parent_task_id=401),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=400, epic_key="LIVE"),
            make_epic(
                id=401,
                epic_key="SKIP",
                status="done",
                child_count=1,
                children_done=1,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("LIVE" in t for t in titles)
            # SKIP appears as collapsed header under COMPLETED
            assert any("COMPLETED" in t for t in titles)
            assert any("SKIP" in t for t in titles)
            # But children are not shown
            assert not any("Skipped" in t for t in titles)

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


# ===================================================================
# I. Cross-Group Epic Clustering
# ===================================================================


class TestCrossGroupEpicClustering:
    """Tests for visual epic grouping when epic is in a different status group."""

    @pytest.mark.asyncio
    async def test_cross_group_children_show_epic_header(self, mock_task_data: MockDict) -> None:
        """Children whose epic is in another status group show a reference header."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Child A", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="Child B", status="open", epic_key="AUTH", parent_task_id=100),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH", child_count=5, children_done=3),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            epics = _table_cell_texts(table, "epic")
            ages = _table_cell_texts(table, "age")
            # Epic header row should show AUTH badge and 3/5 progress
            assert any("AUTH" in t for t in epics)
            assert any("3/5" in t for t in ages)

    @pytest.mark.asyncio
    async def test_cross_group_children_have_tree_connectors(
        self, mock_task_data: MockDict
    ) -> None:
        """Children under a cross-group epic use tree connectors."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Child A", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="Child B", status="open", epic_key="AUTH", parent_task_id=100),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            icons = _table_cell_texts(table, "icon")
            # Should have tree connectors (├─ and └─)
            assert any("├─" in i for i in icons)
            assert any("└─" in i for i in icons)

    @pytest.mark.asyncio
    async def test_same_group_children_still_cluster_under_epic(
        self, mock_task_data: MockDict
    ) -> None:
        """Children whose epic IS in the same status group cluster normally."""
        epic_task = make_task(id=100, title="Auth Epic", status="open", epic_key="AUTH")
        epic_task["type"] = "epic"
        mock_task_data["list_tasks"].return_value = [
            epic_task,
            make_task(id=1, title="Child A", status="open", epic_key="AUTH", parent_task_id=100),
            make_task(id=2, title="Child B", status="open", epic_key="AUTH", parent_task_id=100),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            icons = _table_cell_texts(table, "icon")
            # Epic task should be rendered (no cross-group header needed)
            assert any("Auth Epic" in t for t in titles)
            # Children should have tree connectors
            assert any("├─" in i for i in icons)
            assert any("└─" in i for i in icons)
            # No cross-group header (no "done" in title rows since epic is present)
            assert not any("done" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_true_orphans_render_under_ungrouped(self, mock_task_data: MockDict) -> None:
        """Tasks with no parent_task_id render under UNGROUPED header."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="Orphan A", status="open"),
            make_task(id=2, title="Orphan B", status="open"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # Orphans should appear under UNGROUPED header
            assert any("UNGROUPED" in t for t in titles)
            task_titles = _task_titles(table)
            assert any("Orphan A" in t for t in task_titles)
            assert any("Orphan B" in t for t in task_titles)


# ===================================================================
# Long-line wrapping (Issue #868)
# ===================================================================


class TestLongLineWrapping:
    """Verify that long lines wrap within the panel and preserve the gutter."""

    LONG_URL = "https://example.com/" + "a" * 200

    @pytest.mark.asyncio
    async def test_long_description_stays_within_panel(self, mock_task_data: MockDict) -> None:
        """A long unbreakable description line is pre-wrapped, not raw."""
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open", description=self.LONG_URL),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Description:" in text
            # The full URL must NOT appear on a single RichLog line — it
            # should be broken across multiple lines by _write_wrapped.
            for line in detail.lines:
                assert len(line.text) <= 80

    @pytest.mark.asyncio
    async def test_long_work_log_preserves_gutter(self, mock_task_data: MockDict) -> None:
        """Work-log lines with long URLs keep the │ gutter on every line."""
        long_msg = "See " + self.LONG_URL
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_task_log"].return_value = [
            make_log_entry(message=long_msg),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Work Log:" in text
            # Every content line between ● and ╵ must contain the gutter
            in_log = False
            for line in detail.lines:
                lt = line.text
                if "●" in lt:
                    in_log = True
                    continue
                if "╵" in lt:
                    break
                if in_log and lt.strip():
                    assert "│" in lt, f"Gutter missing on line: {lt!r}"

    @pytest.mark.asyncio
    async def test_long_work_log_lines_fit_panel_width(self, mock_task_data: MockDict) -> None:
        """No pre-wrapped work-log line exceeds the terminal width."""
        long_msg = "x" * 300
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="active"),
        ]
        mock_task_data["get_task_log"].return_value = [
            make_log_entry(message=long_msg),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            for line in detail.lines:
                assert len(line.text) <= 80, f"Line exceeds panel width: {len(line.text)} chars"


class TestUrlLinkification:
    """Verify URL linkification and @click meta in the detail pane."""

    def test_linkify_text_basic_url(self) -> None:
        """_linkify_text wraps URLs with @click meta."""
        result = _linkify_text("Visit https://example.com for info")
        # Check plain text preserved
        assert result.plain == "Visit https://example.com for info"
        # Check that the URL segment has @click meta
        found_meta = False
        for span in result._spans:
            if span.style and hasattr(span.style, "meta") and span.style.meta:
                meta = span.style.meta
                if "@click" in meta:
                    assert "app.open_url" in meta["@click"]
                    assert "https://example.com" in meta["@click"]
                    found_meta = True
        assert found_meta, "No @click meta found on URL segment"

    def test_linkify_text_no_urls(self) -> None:
        """_linkify_text returns plain text when no URLs present."""
        result = _linkify_text("no urls here")
        assert result.plain == "no urls here"

    def test_linkify_text_multiple_urls(self) -> None:
        """_linkify_text handles multiple URLs."""
        text = "See https://a.com and https://b.com"
        result = _linkify_text(text)
        assert result.plain == text
        click_count = sum(
            1
            for span in result._spans
            if span.style
            and hasattr(span.style, "meta")
            and span.style.meta
            and "@click" in span.style.meta
        )
        assert click_count == 2

    def test_linkify_text_trailing_punctuation(self) -> None:
        """_linkify_text strips trailing punctuation from URLs."""
        result = _linkify_text("See https://example.com/path.")
        assert "https://example.com/path" in result.plain
        # The period should not be part of the URL
        for span in result._spans:
            if span.style and hasattr(span.style, "meta") and span.style.meta:
                meta = span.style.meta
                if "@click" in meta:
                    assert meta["@click"].endswith("')")

    def test_extract_urls_basic(self) -> None:
        """_extract_urls returns URLs from text."""
        urls = _extract_urls("Visit https://example.com and https://test.org/path")
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "https://test.org/path" in urls

    def test_extract_urls_empty(self) -> None:
        """_extract_urls returns empty list when no URLs."""
        assert _extract_urls("no urls here") == []

    @pytest.mark.asyncio
    async def test_description_urls_have_click_meta(self, mock_task_data: MockDict) -> None:
        """URLs in description render with @click meta in the RichLog."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                status="open",
                description="Bug: https://github.com/org/repo/issues/42",
            ),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            # Find line containing the URL
            found_click_meta = False
            for line in detail.lines:
                for seg in line._segments:
                    meta = seg.style.meta if seg.style else None
                    if meta and meta.get("@click"):
                        assert "app.open_url" in meta["@click"]
                        assert "github.com" in meta["@click"]
                        found_click_meta = True
            assert found_click_meta, "No @click meta found in rendered detail pane"

    @pytest.mark.asyncio
    async def test_multiline_description_wraps_each_line(self, mock_task_data: MockDict) -> None:
        """Multi-line descriptions wrap each paragraph independently."""
        desc = "Short line.\n" + "b" * 200 + "\nAnother short line."
        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, status="open", description=desc),
        ]
        app = TaskTestApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await _select_first_task(pilot)
            detail = app.query_one("#task-detail-log", RichLog)
            text = _richlog_text(detail)
            assert "Short line." in text
            assert "Another short line." in text
            for line in detail.lines:
                assert len(line.text) <= 80


# ===================================================================
# P. Collapse / Expand
# ===================================================================


class TestCollapseExpand:
    """Tests for Enter key toggling collapse/expand on epic parents."""

    @pytest.mark.asyncio
    async def test_enter_collapses_active_epic(self, mock_task_data: MockDict) -> None:
        """Pressing Enter on an active epic hides its children."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Child task",
                status="open",
                epic_key="EPIC",
                parent_task_id=100,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="EPIC"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("Child task" in t for t in titles)

            # Navigate to epic row and press Enter to collapse
            await pilot.press("j")
            await pilot.press("k")
            await pilot.pause()
            # Now press Enter to collapse
            await pilot.press("enter")
            await pilot.pause()

            titles = _table_cell_texts(table, "title")
            assert not any("Child task" in t for t in titles)

    @pytest.mark.asyncio
    async def test_enter_expands_collapsed_active_epic(
        self,
        mock_task_data: MockDict,
    ) -> None:
        """Pressing Enter twice toggles collapse then expand."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Child task",
                status="open",
                epic_key="EPIC",
                parent_task_id=100,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="EPIC"),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("j")
            await pilot.press("k")
            await pilot.pause()

            # Collapse
            await pilot.press("enter")
            await pilot.pause()
            # Expand
            await pilot.press("enter")
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            assert any("Child task" in t for t in titles)

    @pytest.mark.asyncio
    async def test_done_epic_auto_collapsed(self, mock_task_data: MockDict) -> None:
        """Done epics in COMPLETED section start collapsed."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Active work",
                status="open",
                epic_key="LIVE",
                parent_task_id=200,
            ),
            make_task(
                id=2,
                title="Done child",
                status="done",
                epic_key="DEAD",
                parent_task_id=201,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=200, epic_key="LIVE"),
            make_epic(
                id=201,
                epic_key="DEAD",
                status="done",
                child_count=1,
                children_done=1,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # COMPLETED section visible by default (no statuses hidden)
            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            # DEAD epic header visible but children hidden (collapsed)
            assert any("DEAD" in t for t in titles)
            assert not any("Done child" in t for t in titles)


# ===================================================================
# N. Help Modal Shows Filter Keybindings (FEAT-58)
# ===================================================================


class TestHelpModalFilterKeys:
    """Verify that pressing ? shows the new filter keybindings."""

    @pytest.mark.asyncio
    async def test_help_modal_shows_filter_keys(self, mock_task_data: MockDict) -> None:
        """Pressing ? opens help modal containing the new filter bindings."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()

            from emdx.ui.modals import KeybindingsHelpScreen

            screen = app.screen
            assert isinstance(screen, KeybindingsHelpScreen)

            help_rows = screen.query(".help-row")
            help_text = " ".join(str(row.content) for row in help_rows)

            assert "Toggle Open" in help_text
            assert "Toggle Active" in help_text
            assert "Toggle Blocked" in help_text
            assert "Toggle Finished" in help_text
            assert "Clear Filters" in help_text
            assert "Epic Filter" in help_text
            assert "Group By" in help_text
            assert "Open URLs" in help_text
            assert "Expand/Collapse" in help_text

    @pytest.mark.asyncio
    async def test_help_bar_includes_filter_keys(self, mock_task_data: MockDict) -> None:
        """Help bar text shows context-appropriate keys (task row default)."""
        from emdx.ui.task_browser import TaskBrowser

        class HelpBarApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = HelpBarApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            bar = app.query_one("#task-help-bar", Static)
            content = str(bar.content)
            # Default footer shows task-action keys
            assert "Done" in content
            assert "Blocked" in content
            assert "Navigate" in content


# ===================================================================
# O. Done-Fold Recency Hint (FEAT-61)
# ===================================================================


class TestDoneFoldRecency:
    """Tests for the recency hint on collapsed done-fold rows."""

    @pytest.mark.asyncio
    async def test_done_fold_shows_recency_hint(self, mock_task_data: MockDict) -> None:
        """Collapsed done epic shows fold row with 'latest:' recency hint."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Active work",
                status="open",
                epic_key="LIVE",
                parent_task_id=200,
            ),
            make_task(
                id=2,
                title="Done child",
                status="done",
                epic_key="DEAD",
                parent_task_id=201,
                completed_at="2025-01-01T12:00:00",
            ),
            make_task(
                id=3,
                title="Also done",
                status="done",
                epic_key="DEAD",
                parent_task_id=201,
                completed_at="2025-01-02T12:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=200, epic_key="LIVE"),
            make_epic(
                id=201,
                epic_key="DEAD",
                status="done",
                child_count=2,
                children_done=2,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            fold_rows = [t for t in titles if "completed" in t and "▸" in t]
            assert len(fold_rows) >= 1, f"No fold row found in: {titles}"
            assert "latest:" in fold_rows[0]

    @pytest.mark.asyncio
    async def test_done_fold_without_completed_at(self, mock_task_data: MockDict) -> None:
        """Fold row falls back to updated_at when completed_at is missing."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Active work",
                status="open",
                epic_key="LIVE",
                parent_task_id=200,
            ),
            make_task(
                id=2,
                title="Done child",
                status="done",
                epic_key="DEAD",
                parent_task_id=201,
                completed_at=None,
                updated_at="2025-01-01T12:00:00",
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=200, epic_key="LIVE"),
            make_epic(
                id=201,
                epic_key="DEAD",
                status="done",
                child_count=1,
                children_done=1,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            fold_rows = [t for t in titles if "completed" in t and "▸" in t]
            assert len(fold_rows) >= 1
            assert "latest:" in fold_rows[0]

    @pytest.mark.asyncio
    async def test_done_fold_no_dates(self, mock_task_data: MockDict) -> None:
        """Fold row without any dates shows count but no 'latest:' hint."""
        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Active work",
                status="open",
                epic_key="LIVE",
                parent_task_id=200,
            ),
            make_task(
                id=2,
                title="Done child",
                status="done",
                epic_key="DEAD",
                parent_task_id=201,
                completed_at=None,
                updated_at=None,
                created_at=None,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=200, epic_key="LIVE"),
            make_epic(
                id=201,
                epic_key="DEAD",
                status="done",
                child_count=1,
                children_done=1,
                children_open=0,
            ),
        ]
        app = TaskTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            table = app.query_one("#task-table", DataTable)
            titles = _table_cell_texts(table, "title")
            fold_rows = [t for t in titles if "completed" in t and "▸" in t]
            assert len(fold_rows) >= 1
            assert "latest:" not in fold_rows[0]


# ===================================================================
# P. Context-Sensitive Footer (FEAT-59)
# ===================================================================


class TestContextSensitiveFooter:
    """Tests for the dynamic footer bar that changes with selection."""

    @pytest.mark.asyncio
    async def test_footer_shows_task_context_keys(self, mock_task_data: MockDict) -> None:
        """Footer shows task-action keys when a normal task row is selected."""
        from emdx.ui.task_browser import TaskBrowser

        mock_task_data["list_tasks"].return_value = [
            make_task(id=1, title="My task", status="open"),
        ]

        class FooterApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = FooterApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Navigate down until we land on a task: row
            table = app.query_one("#task-table", DataTable)
            for _i in range(table.row_count):
                await pilot.press("j")
                await pilot.pause()
                if table.cursor_row is not None:
                    key = str(table.ordered_rows[table.cursor_row].key.value)
                    if key.startswith("task:"):
                        break

            bar = app.query_one("#task-help-bar", Static)
            content = str(bar.content)
            assert "Done" in content
            assert "Active" in content
            assert "Blocked" in content
            assert "Navigate" in content
            assert "Help" in content
            # Should NOT show epic-header keys
            assert "Expand/Collapse" not in content

    @pytest.mark.asyncio
    async def test_footer_shows_epic_context_keys(self, mock_task_data: MockDict) -> None:
        """Footer shows epic keys when an epic header row is highlighted."""
        from emdx.ui.task_browser import TaskBrowser

        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=100,
                title="Epic: AUTH",
                status="open",
                epic_key="AUTH",
                type="epic",
            ),
            make_task(
                id=1,
                title="Child task",
                status="open",
                epic_key="AUTH",
                parent_task_id=100,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(id=100, epic_key="AUTH"),
        ]

        class FooterApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = FooterApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)
            # Navigate to the epic row (task:100 with type="epic")
            for _ in range(table.row_count):
                await pilot.press("k")
                await pilot.pause()
            # Scan for the epic task row
            found_epic = False
            for _i in range(table.row_count):
                if table.cursor_row is not None:
                    key = str(table.ordered_rows[table.cursor_row].key.value)
                    if key == "task:100":
                        found_epic = True
                        # Press j then k to trigger highlight event
                        await pilot.press("j")
                        await pilot.pause()
                        await pilot.press("k")
                        await pilot.pause()
                        break
                await pilot.press("j")
                await pilot.pause()

            assert found_epic, "Epic row task:100 not found"
            bar = app.query_one("#task-help-bar", Static)
            content = str(bar.content)
            assert "Expand/Collapse" in content
            assert "Epic Filter" in content
            assert "Group By" in content
            # Should NOT show task-action keys
            assert "Done" not in content
            assert "Active" not in content

    @pytest.mark.asyncio
    async def test_footer_shows_done_fold_context(self, mock_task_data: MockDict) -> None:
        """Footer shows expand hint when a done-fold row is highlighted."""
        from emdx.ui.task_browser import TaskBrowser

        mock_task_data["list_tasks"].return_value = [
            make_task(
                id=1,
                title="Open task",
                status="open",
                epic_key="AUTH",
                parent_task_id=100,
            ),
            make_task(
                id=2,
                title="Done task 1",
                status="done",
                epic_key="AUTH",
                parent_task_id=100,
            ),
            make_task(
                id=3,
                title="Done task 2",
                status="done",
                epic_key="AUTH",
                parent_task_id=100,
            ),
        ]
        mock_task_data["list_epics"].return_value = [
            make_epic(
                id=100,
                epic_key="AUTH",
                child_count=3,
                children_done=2,
                children_open=1,
            ),
        ]

        class FooterApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TaskBrowser()

        app = FooterApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Navigate down to find the done-fold row
            table = app.query_one("#task-table", DataTable)
            found_fold = False
            for _i in range(table.row_count):
                await pilot.press("j")
                await pilot.pause()
                if table.cursor_row is not None:
                    key = str(table.ordered_rows[table.cursor_row].key.value)
                    if key.startswith("done-fold:"):
                        found_fold = True
                        break

            if found_fold:
                bar = app.query_one("#task-help-bar", Static)
                content = str(bar.content)
                assert "Expand" in content
                assert "Filter" in content
                assert "Help" in content
                # Should NOT show task-action keys
                assert "Done" not in content
