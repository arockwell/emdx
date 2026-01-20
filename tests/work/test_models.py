"""Tests for work system data models."""

import json
import pytest
from datetime import datetime

from emdx.work.models import (
    Cascade,
    WorkItem,
    WorkDep,
    WorkTransition,
    _parse_datetime,
)


class TestParseDatetime:
    """Tests for the _parse_datetime helper function."""

    def test_parse_none_returns_none(self):
        assert _parse_datetime(None) is None

    def test_parse_datetime_returns_same(self):
        dt = datetime.now()
        assert _parse_datetime(dt) is dt

    def test_parse_iso_string(self):
        dt_str = "2024-01-15T10:30:00"
        result = _parse_datetime(dt_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_iso_string_with_microseconds(self):
        dt_str = "2024-01-15T10:30:00.123456"
        result = _parse_datetime(dt_str)
        assert isinstance(result, datetime)
        assert result.microsecond == 123456

    def test_parse_invalid_type_returns_none(self):
        assert _parse_datetime(12345) is None
        assert _parse_datetime([]) is None


class TestCascade:
    """Tests for the Cascade dataclass."""

    def test_cascade_creation(self):
        cascade = Cascade(
            name="test",
            stages=["idea", "done"],
            processors={"idea": "Process idea"},
        )
        assert cascade.name == "test"
        assert cascade.stages == ["idea", "done"]
        assert cascade.processors == {"idea": "Process idea"}
        assert cascade.description is None
        assert cascade.created_at is None

    def test_cascade_from_row(self, cascade_row):
        cascade = Cascade.from_row(cascade_row)
        assert cascade.name == "test-cascade"
        assert cascade.stages == ["stage1", "stage2", "stage3"]
        assert cascade.processors == {
            "stage1": "Process stage 1",
            "stage2": "Process stage 2",
        }
        assert cascade.description == "Test cascade description"
        assert isinstance(cascade.created_at, datetime)

    def test_cascade_from_row_empty_json(self):
        row = ("test", None, None, None, None)
        cascade = Cascade.from_row(row)
        assert cascade.stages == []
        assert cascade.processors == {}

    def test_get_next_stage(self):
        cascade = Cascade(
            name="test",
            stages=["a", "b", "c"],
            processors={},
        )
        assert cascade.get_next_stage("a") == "b"
        assert cascade.get_next_stage("b") == "c"
        assert cascade.get_next_stage("c") is None

    def test_get_next_stage_invalid_stage(self):
        cascade = Cascade(name="test", stages=["a", "b"], processors={})
        assert cascade.get_next_stage("invalid") is None

    def test_get_processor(self):
        cascade = Cascade(
            name="test",
            stages=["a", "b"],
            processors={"a": "Process A", "b": "Process B"},
        )
        assert cascade.get_processor("a") == "Process A"
        assert cascade.get_processor("b") == "Process B"
        assert cascade.get_processor("nonexistent") is None

    def test_is_terminal_stage(self):
        cascade = Cascade(name="test", stages=["a", "b", "c"], processors={})
        assert cascade.is_terminal_stage("c") is True
        assert cascade.is_terminal_stage("a") is False
        assert cascade.is_terminal_stage("b") is False

    def test_is_terminal_stage_empty_stages(self):
        cascade = Cascade(name="test", stages=[], processors={})
        # Empty stages returns falsy value (empty list)
        assert not cascade.is_terminal_stage("anything")


class TestWorkItem:
    """Tests for the WorkItem dataclass."""

    def test_work_item_creation_defaults(self):
        item = WorkItem(id="emdx-test", title="Test", stage="idea")
        assert item.id == "emdx-test"
        assert item.title == "Test"
        assert item.stage == "idea"
        assert item.cascade == "default"
        assert item.content is None
        assert item.priority == 3
        assert item.type == "task"
        assert item.is_blocked is False
        assert item.blocked_by == []

    def test_work_item_from_row(self, work_item_row):
        item = WorkItem.from_row(work_item_row)
        assert item.id == "emdx-abc123"
        assert item.title == "Test Item"
        assert item.content == "Test content"
        assert item.cascade == "default"
        assert item.stage == "idea"
        assert item.priority == 2
        assert item.type == "task"
        assert item.project == "test-project"
        assert isinstance(item.created_at, datetime)

    def test_priority_label(self):
        labels = [
            (0, "P0-CRITICAL"),
            (1, "P1-HIGH"),
            (2, "P2-MEDIUM"),
            (3, "P3-LOW"),
            (4, "P4-BACKLOG"),
            (5, "P4-BACKLOG"),  # Values > 4 should return P4
            (10, "P4-BACKLOG"),
        ]
        for priority, expected_label in labels:
            item = WorkItem(id="test", title="Test", stage="idea", priority=priority)
            assert item.priority_label == expected_label

    def test_is_done_terminal_stages(self):
        terminal_stages = ["done", "merged", "conclusion", "deployed", "completed"]
        for stage in terminal_stages:
            item = WorkItem(id="test", title="Test", stage=stage)
            assert item.is_done is True, f"Stage '{stage}' should be done"

    def test_is_done_non_terminal_stages(self):
        non_terminal = ["idea", "prompt", "analyzed", "planned", "implementing"]
        for stage in non_terminal:
            item = WorkItem(id="test", title="Test", stage=stage)
            assert item.is_done is False, f"Stage '{stage}' should not be done"

    def test_blocked_by_list_isolation(self):
        """Ensure blocked_by default list is not shared between instances."""
        item1 = WorkItem(id="test1", title="Test1", stage="idea")
        item2 = WorkItem(id="test2", title="Test2", stage="idea")
        item1.blocked_by.append("blocker")
        assert item2.blocked_by == []


class TestWorkDep:
    """Tests for the WorkDep dataclass."""

    def test_work_dep_creation(self):
        dep = WorkDep(work_id="a", depends_on="b")
        assert dep.work_id == "a"
        assert dep.depends_on == "b"
        assert dep.dep_type == "blocks"
        assert dep.created_at is None

    def test_work_dep_from_row(self, work_dep_row):
        dep = WorkDep.from_row(work_dep_row)
        assert dep.work_id == "emdx-abc123"
        assert dep.depends_on == "emdx-def456"
        assert dep.dep_type == "blocks"
        assert isinstance(dep.created_at, datetime)

    def test_work_dep_types(self):
        for dep_type in ["blocks", "related", "discovered-from"]:
            dep = WorkDep(work_id="a", depends_on="b", dep_type=dep_type)
            assert dep.dep_type == dep_type


class TestWorkTransition:
    """Tests for the WorkTransition dataclass."""

    def test_work_transition_creation(self):
        trans = WorkTransition(
            id=1,
            work_id="emdx-test",
            from_stage="idea",
            to_stage="prompt",
        )
        assert trans.id == 1
        assert trans.work_id == "emdx-test"
        assert trans.from_stage == "idea"
        assert trans.to_stage == "prompt"
        assert trans.transitioned_by is None
        assert trans.content_snapshot is None

    def test_work_transition_from_row(self, work_transition_row):
        trans = WorkTransition.from_row(work_transition_row)
        assert trans.id == 1
        assert trans.work_id == "emdx-abc123"
        assert trans.from_stage == "idea"
        assert trans.to_stage == "prompt"
        assert trans.transitioned_by == "patrol:test"
        assert trans.content_snapshot == "Transition content snapshot"
        assert isinstance(trans.created_at, datetime)

    def test_work_transition_null_from_stage(self):
        """from_stage can be None for initial creation."""
        row = (1, "emdx-test", None, "idea", "created", None, None)
        trans = WorkTransition.from_row(row)
        assert trans.from_stage is None
        assert trans.to_stage == "idea"
