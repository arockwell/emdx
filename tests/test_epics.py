"""Tests for the epics model and CLI."""

import re
from typing import Any

import pytest
from typer.testing import CliRunner

from emdx.commands.epics import app as epics_app
from emdx.commands.tasks import ICONS
from emdx.commands.tasks import app as tasks_app
from emdx.models import categories, tasks

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestCreateEpic:
    """Tests for create_epic."""

    def test_create_epic(self) -> None:
        epic_id = tasks.create_epic("Test Epic", "TEPC")
        epic = tasks.get_task(epic_id)
        assert epic is not None
        assert epic["type"] == "epic"
        assert epic["epic_key"] == "TEPC"
        assert epic["epic_seq"] == 1  # epics get KEY-N like regular tasks

    def test_create_epic_auto_creates_category(self) -> None:
        tasks.create_epic("Auto Cat Epic", "ACAT")
        cat = categories.get_category("ACAT")
        assert cat is not None


class TestTaskInEpic:
    """Tests for creating tasks within epics."""

    def test_create_task_in_epic(self) -> None:
        epic_id = tasks.create_epic("Parent Epic", "TPIC")  # takes seq 1
        task_id = tasks.create_task(
            "Do something",
            parent_task_id=epic_id,
            epic_key="TPIC",
        )
        task = tasks.get_task(task_id)
        assert task is not None
        assert task["parent_task_id"] == epic_id
        assert task["epic_key"] == "TPIC"
        assert task["epic_seq"] == 2  # epic took seq 1
        assert task["title"].startswith("TPIC-2: ")

    def test_epic_auto_numbers(self) -> None:
        categories.ensure_category("ENUM")
        t1 = tasks.create_task("First", epic_key="ENUM")
        t2 = tasks.create_task("Second", epic_key="ENUM")
        t3 = tasks.create_task("Third", epic_key="ENUM")

        task1, task2, task3 = tasks.get_task(t1), tasks.get_task(t2), tasks.get_task(t3)
        assert task1 is not None and task2 is not None and task3 is not None

        assert task1["epic_seq"] == 1
        assert task2["epic_seq"] == 2
        assert task3["epic_seq"] == 3

        assert task1["title"] == "ENUM-1: First"
        assert task2["title"] == "ENUM-2: Second"
        assert task3["title"] == "ENUM-3: Third"

    def test_numbering_spans_epics(self) -> None:
        """Numbering is category-scoped, so it continues across epics."""
        epic_a = tasks.create_epic("Epic A", "SPAN")  # SPAN-1
        tasks.create_task("Task in A", parent_task_id=epic_a, epic_key="SPAN")  # SPAN-2
        tasks.create_task("Another in A", parent_task_id=epic_a, epic_key="SPAN")  # SPAN-3

        epic_b = tasks.create_epic("Epic B", "SPAN")  # SPAN-4
        t5 = tasks.create_task("Task in B", parent_task_id=epic_b, epic_key="SPAN")  # SPAN-5

        epic_a_task = tasks.get_task(epic_a)
        epic_b_task = tasks.get_task(epic_b)
        task5 = tasks.get_task(t5)
        assert epic_a_task is not None and epic_b_task is not None and task5 is not None
        assert epic_a_task["epic_seq"] == 1
        assert epic_b_task["epic_seq"] == 4
        assert task5["epic_seq"] == 5  # continues from epic_b's seq 4
        assert task5["title"] == "SPAN-5: Task in B"


class TestEpicDone:
    """Tests for marking epics as done."""

    def test_epic_done(self) -> None:
        epic_id = tasks.create_epic("Done Epic", "EDNE")
        tasks.update_task(epic_id, status="done")
        epic = tasks.get_task(epic_id)
        assert epic is not None
        assert epic["status"] == "done"


class TestDeleteEpic:
    """Tests for delete_epic."""

    def test_delete_epic_no_children(self) -> None:
        epic_id = tasks.create_epic("Empty Epic", "DENP")
        result = tasks.delete_epic(epic_id)
        assert result["children_unlinked"] == 0
        assert tasks.get_task(epic_id) is None

    def test_delete_epic_with_done_children(self) -> None:
        epic_id = tasks.create_epic("Done Children Epic", "DDCH")
        t1 = tasks.create_task("Done child", parent_task_id=epic_id, epic_key="DDCH", status="done")
        result = tasks.delete_epic(epic_id)
        assert result["children_unlinked"] == 1
        # Child still exists but parent_task_id is cleared
        child = tasks.get_task(t1)
        assert child is not None
        assert child["parent_task_id"] is None

    def test_delete_epic_refuses_open_children(self) -> None:
        epic_id = tasks.create_epic("Open Children Epic", "DOCH")
        tasks.create_task("Open child", parent_task_id=epic_id, epic_key="DOCH")
        with pytest.raises(ValueError, match="open/active child"):
            tasks.delete_epic(epic_id)

    def test_delete_epic_force_with_open_children(self) -> None:
        epic_id = tasks.create_epic("Force Delete Epic", "DFEP")
        t1 = tasks.create_task("Open child", parent_task_id=epic_id, epic_key="DFEP")
        result = tasks.delete_epic(epic_id, force=True)
        assert result["children_unlinked"] == 1
        assert tasks.get_task(epic_id) is None
        child = tasks.get_task(t1)
        assert child is not None
        assert child["parent_task_id"] is None

    def test_delete_epic_not_found(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            tasks.delete_epic(999999)

    def test_delete_non_epic_task(self) -> None:
        task_id = tasks.create_task("Regular task")
        with pytest.raises(ValueError, match="not found"):
            tasks.delete_epic(task_id)


class TestListEpics:
    """Tests for list_epics."""

    def test_list_epics_by_category(self) -> None:
        tasks.create_epic("Filtered Epic", "FILT")
        tasks.create_epic("Other Epic", "OTHR")

        result = tasks.list_epics(category_key="FILT")
        keys = [e["epic_key"] for e in result]
        assert "FILT" in keys
        assert "OTHR" not in keys

    def test_list_epics_by_status(self) -> None:
        e1 = tasks.create_epic("Open Epic", "ESTT")
        e2 = tasks.create_epic("Done Epic", "ESTT")
        tasks.update_task(e2, status="done")

        open_epics = tasks.list_epics(status=["open"])
        done_epics = tasks.list_epics(status=["done"])

        open_ids = [e["id"] for e in open_epics]
        done_ids = [e["id"] for e in done_epics]
        assert e1 in open_ids
        assert e2 in done_ids


class TestEpicView:
    """Tests for get_epic_view."""

    def test_epic_view_with_children(self) -> None:
        epic_id = tasks.create_epic("View Epic", "VIEW")
        tasks.create_task("Child 1", parent_task_id=epic_id, epic_key="VIEW")
        tasks.create_task("Child 2", parent_task_id=epic_id, epic_key="VIEW")

        view = tasks.get_epic_view(epic_id)
        assert view is not None
        assert view["title"] == "View Epic"
        assert len(view["children"]) == 2

    def test_epic_view_not_found(self) -> None:
        result = tasks.get_epic_view(999999)
        assert result is None


class TestBlockedIcon:
    """Tests for blocked status icon."""

    def test_blocked_icon_exists(self) -> None:
        assert "blocked" in ICONS
        assert ICONS["blocked"] == "⊘"


class TestEpicsCLI:
    """Tests for epic CLI commands."""

    def test_create_command(self) -> None:
        result = runner.invoke(epics_app, ["create", "CLI Epic", "--cat", "ECLI"])
        assert result.exit_code == 0
        assert "ECLI" in _out(result)

    def test_list_command(self) -> None:
        tasks.create_epic("List CLI Epic", "ELST")
        result = runner.invoke(epics_app, ["list"])
        assert result.exit_code == 0

    def test_view_command(self) -> None:
        epic_id = tasks.create_epic("View CLI Epic", "EVEW")
        tasks.create_task("View child", parent_task_id=epic_id, epic_key="EVEW")
        result = runner.invoke(epics_app, ["view", str(epic_id)])
        assert result.exit_code == 0
        out = _out(result)
        assert "View CLI Epic" in out
        assert "EVEW" in out

    def test_done_command(self) -> None:
        epic_id = tasks.create_epic("Done CLI Epic", "EDCL")
        result = runner.invoke(epics_app, ["done", str(epic_id)])
        assert result.exit_code == 0
        assert "Done" in _out(result)
        epic = tasks.get_task(epic_id)
        assert epic is not None
        assert epic["status"] == "done"

    def test_active_command(self) -> None:
        epic_id = tasks.create_epic("Active CLI Epic", "EACL")
        result = runner.invoke(epics_app, ["active", str(epic_id)])
        assert result.exit_code == 0
        assert "Active" in _out(result)
        epic = tasks.get_task(epic_id)
        assert epic is not None
        assert epic["status"] == "active"

    def test_view_not_found(self) -> None:
        result = runner.invoke(epics_app, ["view", "999999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_delete_command(self) -> None:
        epic_id = tasks.create_epic("Delete CLI Epic", "EDCL")
        tasks.update_task(epic_id, status="done")
        result = runner.invoke(epics_app, ["delete", str(epic_id)])
        assert result.exit_code == 0
        assert "Deleted" in _out(result)

    def test_delete_command_not_found(self) -> None:
        result = runner.invoke(epics_app, ["delete", "999999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_delete_command_refuses_open(self) -> None:
        epic_id = tasks.create_epic("Refuse CLI Epic", "ERCL")
        tasks.create_task("Open child", parent_task_id=epic_id, epic_key="ERCL")
        result = runner.invoke(epics_app, ["delete", str(epic_id)])
        assert result.exit_code == 1
        assert "open/active" in _out(result)

    def test_delete_command_force(self) -> None:
        epic_id = tasks.create_epic("Force CLI Epic", "EFCL")
        tasks.create_task("Open child", parent_task_id=epic_id, epic_key="EFCL")
        result = runner.invoke(epics_app, ["delete", str(epic_id), "--force"])
        assert result.exit_code == 0
        assert "Deleted" in _out(result)
        assert "Unlinked" in _out(result)


class TestTaskAddWithEpic:
    """Tests for task add with --epic and --cat flags."""

    def test_add_with_cat(self) -> None:
        result = runner.invoke(tasks_app, ["add", "Cat task", "--cat", "TADD"])
        assert result.exit_code == 0
        assert "TADD" in _out(result)

    def test_add_with_epic(self) -> None:
        epic_id = tasks.create_epic("Add Epic", "TAEP")
        result = runner.invoke(tasks_app, ["add", "Epic task", "--epic", str(epic_id)])
        assert result.exit_code == 0

    def test_add_with_epic_not_found(self) -> None:
        result = runner.invoke(tasks_app, ["add", "Bad epic", "--epic", "999999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)


class TestTaskListWithFilters:
    """Tests for task list with --epic and --cat filters."""

    def test_list_with_cat(self) -> None:
        categories.ensure_category("TLCT")
        tasks.create_task("Cat filter test", epic_key="TLCT")
        result = runner.invoke(tasks_app, ["list", "--cat", "TLCT"])
        assert result.exit_code == 0

    def test_list_with_epic(self) -> None:
        epic_id = tasks.create_epic("List Epic", "TLEP")
        tasks.create_task("Epic filter test", parent_task_id=epic_id, epic_key="TLEP")
        result = runner.invoke(tasks_app, ["list", "--epic", str(epic_id)])
        assert result.exit_code == 0
