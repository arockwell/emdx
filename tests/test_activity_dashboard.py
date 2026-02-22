"""Tests for unified dashboard: TaskItem, deduplication, and three-tier sorting."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from emdx.models.types import TaskDict
from emdx.ui.activity.activity_data import (
    TIER_RECENT,
    TIER_RUNNING,
    TIER_TASKS,
    ActivityDataLoader,
)
from emdx.ui.activity.activity_items import (
    TASK_STATUS_ICONS,
    AgentExecutionItem,
    DocumentItem,
    TaskItem,
)
from emdx.ui.activity.activity_table import _get_tier

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_task_dict(
    id: int = 1,
    title: str = "Test task",
    status: str = "open",
    priority: int = 5,
    description: str | None = None,
    epic_key: str | None = None,
    epic_seq: int | None = None,
    created_at: str | None = "2025-01-01T12:00:00",
    updated_at: str | None = None,
    completed_at: str | None = None,
    execution_id: int | None = None,
    output_doc_id: int | None = None,
) -> TaskDict:
    return {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "description": description,
        "error": None,
        "epic_key": epic_key,
        "created_at": created_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "tags": None,
        "execution_id": execution_id,
        "output_doc_id": output_doc_id,
        "gameplan_id": None,
        "project": None,
        "current_step": None,
        "prompt": None,
        "type": "manual",
        "source_doc_id": None,
        "parent_task_id": None,
        "seq": None,
        "retry_of": None,
        "epic_seq": epic_seq,
    }


def make_task_item(
    id: int = 1,
    title: str = "Test task",
    status: str = "open",
    priority: int = 5,
    **kwargs: Any,
) -> TaskItem:
    task_data = make_task_dict(id=id, title=title, status=status, priority=priority, **kwargs)
    return TaskItem(
        item_id=id,
        title=title,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        status=status,
        task_data=task_data,
    )


def make_doc_item(id: int = 100, title: str = "Doc", doc_id: int | None = None) -> DocumentItem:
    return DocumentItem(
        item_id=id,
        title=title,
        timestamp=datetime(2025, 1, 1, 10, 0, 0),
        status="completed",
        doc_id=doc_id or id,
    )


def make_exec_item(
    id: int = 200,
    title: str = "Exec",
    status: str = "running",
) -> AgentExecutionItem:
    return AgentExecutionItem(
        item_id=id,
        title=title,
        timestamp=datetime(2025, 1, 1, 11, 0, 0),
        status=status,
        execution={"id": id, "status": status},
    )


# ---------------------------------------------------------------------------
# TaskItem tests
# ---------------------------------------------------------------------------


class TestTaskItem:
    def test_item_type(self) -> None:
        item = make_task_item()
        assert item.item_type == "task"

    def test_type_icon_open(self) -> None:
        item = make_task_item(status="open")
        assert item.type_icon == "."

    def test_type_icon_active(self) -> None:
        item = make_task_item(status="active")
        assert item.type_icon == ">"

    def test_type_icon_done(self) -> None:
        item = make_task_item(status="done")
        assert item.type_icon == "v"

    def test_type_icon_failed(self) -> None:
        item = make_task_item(status="failed")
        assert item.type_icon == "x"

    def test_type_icon_blocked(self) -> None:
        item = make_task_item(status="blocked")
        assert item.type_icon == "-"

    def test_status_icon_matches_type_icon(self) -> None:
        for status, expected in TASK_STATUS_ICONS.items():
            item = make_task_item(status=status)
            assert item.status_icon == expected

    def test_context_lines_basic(self) -> None:
        item = make_task_item(status="active", priority=2)
        lines = item.get_context_lines()
        assert "Status: active" in lines
        assert "Priority: 2" in lines

    def test_context_lines_with_epic(self) -> None:
        item = make_task_item(epic_key="AUTH", epic_seq=3)
        lines = item.get_context_lines()
        assert "Epic: AUTH-3" in lines

    def test_context_lines_epic_no_seq(self) -> None:
        item = make_task_item(epic_key="AUTH")
        lines = item.get_context_lines()
        assert "Epic: AUTH" in lines

    def test_context_lines_no_task_data(self) -> None:
        item = TaskItem(
            item_id=1,
            title="test",
            timestamp=datetime.now(),
            status="open",
            task_data=None,
        )
        assert item.get_context_lines() == []

    @pytest.mark.asyncio
    async def test_preview_content_basic(self) -> None:
        item = make_task_item(
            title="My Task",
            description="A detailed description",
        )
        content, header = await item.get_preview_content(None)
        assert "# My Task" in content
        assert "A detailed description" in content
        assert "Task #1" in header

    @pytest.mark.asyncio
    async def test_preview_content_no_task_data(self) -> None:
        item = TaskItem(
            item_id=5,
            title="test",
            timestamp=datetime.now(),
            status="open",
            task_data=None,
        )
        content, header = await item.get_preview_content(None)
        assert content == ""
        assert "Task #5" in header


# ---------------------------------------------------------------------------
# Three-tier sorting tests
# ---------------------------------------------------------------------------


class TestThreeTierSorting:
    def test_tier_assignment_running_execution(self) -> None:
        item = make_exec_item(status="running")
        assert _get_tier(item) == TIER_RUNNING

    def test_tier_assignment_open_task(self) -> None:
        item = make_task_item(status="open")
        assert _get_tier(item) == TIER_TASKS

    def test_tier_assignment_active_task(self) -> None:
        item = make_task_item(status="active")
        assert _get_tier(item) == TIER_TASKS

    def test_tier_assignment_done_task(self) -> None:
        item = make_task_item(status="done")
        assert _get_tier(item) == TIER_RECENT

    def test_tier_assignment_document(self) -> None:
        item = make_doc_item()
        assert _get_tier(item) == TIER_RECENT

    def test_tier_assignment_completed_execution(self) -> None:
        item = make_exec_item(status="completed")
        assert _get_tier(item) == TIER_RECENT


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_task_with_execution_id_deduped(self) -> None:
        """Task whose execution_id matches an AgentExecutionItem is skipped."""
        loader = ActivityDataLoader()

        exec_item = make_exec_item(id=42, status="running")
        task_with_exec = make_task_item(id=10, execution_id=42)

        with (
            patch.object(loader, "_load_documents", new_callable=AsyncMock, return_value=[]),
            patch.object(
                loader, "_load_agent_executions", new_callable=AsyncMock, return_value=[exec_item]
            ),
            patch.object(
                loader,
                "_load_tasks",
                new_callable=AsyncMock,
                return_value=[task_with_exec],
            ),
        ):
            items = await loader.load_all()

        # The task should be deduped — only the execution remains
        types = [item.item_type for item in items]
        assert "task" not in types
        assert "agent_execution" in types

    @pytest.mark.asyncio
    async def test_task_with_output_doc_removes_document(self) -> None:
        """Document whose ID matches a task's output_doc_id is removed."""
        loader = ActivityDataLoader()

        doc_item = make_doc_item(id=99, doc_id=99)
        task_with_output = make_task_item(id=10, output_doc_id=99, status="done")

        with (
            patch.object(
                loader, "_load_documents", new_callable=AsyncMock, return_value=[doc_item]
            ),
            patch.object(loader, "_load_agent_executions", new_callable=AsyncMock, return_value=[]),
            patch.object(
                loader,
                "_load_tasks",
                new_callable=AsyncMock,
                return_value=[task_with_output],
            ),
        ):
            items = await loader.load_all()

        types = [item.item_type for item in items]
        assert "document" not in types
        assert "task" in types

    @pytest.mark.asyncio
    async def test_no_dedup_when_no_overlap(self) -> None:
        """Items without overlapping IDs all survive."""
        loader = ActivityDataLoader()

        doc = make_doc_item(id=1)
        exe = make_exec_item(id=2, status="completed")
        task = make_task_item(id=3)

        with (
            patch.object(loader, "_load_documents", new_callable=AsyncMock, return_value=[doc]),
            patch.object(
                loader, "_load_agent_executions", new_callable=AsyncMock, return_value=[exe]
            ),
            patch.object(loader, "_load_tasks", new_callable=AsyncMock, return_value=[task]),
        ):
            items = await loader.load_all()

        types = sorted(item.item_type for item in items)
        assert types == ["agent_execution", "document", "task"]

    @pytest.mark.asyncio
    async def test_sort_order_running_first(self) -> None:
        """Running executions sort before tasks, tasks before documents."""
        loader = ActivityDataLoader()

        now = datetime.now()
        doc = make_doc_item(id=1)
        doc.timestamp = now - timedelta(hours=1)

        running_exec = make_exec_item(id=2, status="running")
        running_exec.timestamp = now

        open_task = make_task_item(id=3, status="open")
        open_task.timestamp = now - timedelta(minutes=30)

        with (
            patch.object(loader, "_load_documents", new_callable=AsyncMock, return_value=[doc]),
            patch.object(
                loader,
                "_load_agent_executions",
                new_callable=AsyncMock,
                return_value=[running_exec],
            ),
            patch.object(loader, "_load_tasks", new_callable=AsyncMock, return_value=[open_task]),
        ):
            items = await loader.load_all()

        types = [item.item_type for item in items]
        assert types == ["agent_execution", "task", "document"]

    @pytest.mark.asyncio
    async def test_tasks_sorted_by_priority(self) -> None:
        """Within the task tier, items sort by priority (lower = higher priority)."""
        loader = ActivityDataLoader()

        low_prio = make_task_item(id=1, status="open", priority=5)
        high_prio = make_task_item(id=2, status="open", priority=1)

        with (
            patch.object(loader, "_load_documents", new_callable=AsyncMock, return_value=[]),
            patch.object(loader, "_load_agent_executions", new_callable=AsyncMock, return_value=[]),
            patch.object(
                loader,
                "_load_tasks",
                new_callable=AsyncMock,
                return_value=[low_prio, high_prio],
            ),
        ):
            items = await loader.load_all()

        task_items = [i for i in items if i.item_type == "task"]
        assert task_items[0].item_id == 2  # high priority first
        assert task_items[1].item_id == 1
