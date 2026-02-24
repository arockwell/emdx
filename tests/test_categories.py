"""Tests for the categories model and CLI."""

import re

import pytest
from typer.testing import CliRunner

from emdx.commands.categories import app
from emdx.models import categories, tasks

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestCreateCategory:
    """Tests for create_category."""

    def test_create_category(self):
        key = categories.create_category("TEST", "Test Category", "A test")
        assert key == "TEST"
        cat = categories.get_category("TEST")
        assert cat is not None
        assert cat["name"] == "Test Category"
        assert cat["description"] == "A test"

    def test_create_category_uppercase(self):
        key = categories.create_category("low", "Lowercase Input")
        assert key == "LOW"
        cat = categories.get_category("low")
        assert cat is not None
        assert cat["key"] == "LOW"

    def test_create_category_validation_too_short(self):
        with pytest.raises(ValueError, match="2-8 uppercase letters"):
            categories.create_category("X", "Too Short")

    def test_create_category_validation_too_long(self):
        with pytest.raises(ValueError, match="2-8 uppercase letters"):
            categories.create_category("TOOLONGKEY", "Too Long")

    def test_create_category_validation_non_alpha(self):
        with pytest.raises(ValueError, match="2-8 uppercase letters"):
            categories.create_category("AB1", "Has Numbers")

    def test_create_category_validation_special_chars(self):
        with pytest.raises(ValueError, match="2-8 uppercase letters"):
            categories.create_category("AB-C", "Has Hyphen")


class TestEnsureCategory:
    """Tests for ensure_category."""

    def test_ensure_category_creates(self):
        key = categories.ensure_category("NEWCAT")
        assert key == "NEWCAT"
        cat = categories.get_category("NEWCAT")
        assert cat is not None
        assert cat["name"] == "NEWCAT"  # auto-name is the key

    def test_ensure_category_idempotent(self):
        categories.ensure_category("IDEM")
        # Should not raise on second call
        key = categories.ensure_category("IDEM")
        assert key == "IDEM"


class TestListCategories:
    """Tests for list_categories."""

    def test_list_categories_with_counts(self):
        categories.ensure_category("LCNT")
        # Create some tasks in this category
        tasks.create_task("LCNT-1: First task", epic_key="LCNT")
        tasks.create_task("LCNT-2: Second task", epic_key="LCNT", status="done")

        cats = categories.list_categories()
        lcnt = next((c for c in cats if c["key"] == "LCNT"), None)
        assert lcnt is not None
        assert lcnt["open_count"] >= 1
        assert lcnt["done_count"] >= 1
        assert lcnt["total_count"] >= 2


class TestDeleteCategory:
    """Tests for delete_category."""

    def test_delete_empty_category(self):
        categories.create_category("DEMP", "Empty Category")
        result = categories.delete_category("DEMP")
        assert result["tasks_cleared"] == 0
        assert result["epics_cleared"] == 0
        assert categories.get_category("DEMP") is None

    def test_delete_category_with_done_tasks(self):
        categories.create_category("DDNE", "Done Tasks")
        t1 = tasks.create_task("Task 1", epic_key="DDNE", status="done")
        result = categories.delete_category("DDNE")
        assert result["tasks_cleared"] == 1
        # Task still exists but epic_key is cleared
        task = tasks.get_task(t1)
        assert task is not None
        assert task["epic_key"] is None
        assert task["epic_seq"] is None

    def test_delete_category_refuses_open_tasks(self):
        categories.create_category("DREF", "Has Open Tasks")
        tasks.create_task("Open task", epic_key="DREF")
        with pytest.raises(ValueError, match="open/active task"):
            categories.delete_category("DREF")

    def test_delete_category_force_with_open_tasks(self):
        categories.create_category("DFRC", "Force Delete")
        t1 = tasks.create_task("Open task", epic_key="DFRC")
        result = categories.delete_category("DFRC", force=True)
        assert result["tasks_cleared"] == 1
        assert categories.get_category("DFRC") is None
        task = tasks.get_task(t1)
        assert task["epic_key"] is None

    def test_delete_category_clears_epics(self):
        categories.create_category("DEPC", "With Epics")
        epic_id = tasks.create_epic("Test Epic", "DEPC")
        tasks.update_task(epic_id, status="done")
        result = categories.delete_category("DEPC")
        assert result["epics_cleared"] == 1
        epic = tasks.get_task(epic_id)
        assert epic is not None
        assert epic["epic_key"] is None

    def test_delete_category_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            categories.delete_category("ZZZZ")

    def test_delete_category_case_insensitive(self):
        categories.create_category("DCAS", "Case Test")
        result = categories.delete_category("dcas")
        assert result["tasks_cleared"] == 0
        assert categories.get_category("DCAS") is None


class TestAdoptCategory:
    """Tests for adopt_category."""

    def test_adopt_backfills(self):
        # Create tasks with KEY-N: pattern in their title (no epic_key set)
        t1 = tasks.create_task("ADPT-1: First adopted task")
        t2 = tasks.create_task("ADPT-2: Second adopted task")

        result = categories.adopt_category("ADPT")
        assert result["adopted"] == 2
        assert result["skipped"] == 0

        # Verify tasks now have epic_key/epic_seq
        task1 = tasks.get_task(t1)
        assert task1["epic_key"] == "ADPT"
        assert task1["epic_seq"] == 1

        task2 = tasks.get_task(t2)
        assert task2["epic_key"] == "ADPT"
        assert task2["epic_seq"] == 2

    def test_adopt_skips_already_adopted(self):
        # Create a task that already has epic_key
        tasks.create_task("SKIP-1: Already adopted", epic_key="SKIP")

        # Adopt should not try to re-adopt
        result = categories.adopt_category("SKIP")
        assert result["adopted"] == 0

    def test_adopt_with_name(self):
        categories.ensure_category("ANME")
        categories.adopt_category("ANME", name="Adopted Name")
        cat = categories.get_category("ANME")
        assert cat["name"] == "Adopted Name"


class TestRenameCategory:
    """Tests for rename_category."""

    def test_rename_simple(self):
        """Rename with no target existing — creates target, moves tasks, deletes source."""
        categories.create_category("RNOLD", "Old Name")
        t1 = tasks.create_task("Task 1", epic_key="RNOLD")
        t2 = tasks.create_task("Task 2", epic_key="RNOLD")

        result = categories.rename_category("RNOLD", "RNNEW")
        assert result["tasks_moved"] == 2
        assert result["old_category_deleted"] is True

        # Source gone, target exists
        assert categories.get_category("RNOLD") is None
        new_cat = categories.get_category("RNNEW")
        assert new_cat is not None
        assert new_cat["name"] == "Old Name"  # inherited

        # Tasks moved and retitled
        task1 = tasks.get_task(t1)
        assert task1["epic_key"] == "RNNEW"
        assert "RNNEW-" in task1["title"]

        task2 = tasks.get_task(t2)
        assert task2["epic_key"] == "RNNEW"
        assert "RNNEW-" in task2["title"]

    def test_rename_merge_renumbers(self):
        """Merge into existing category — renumbers to avoid seq conflicts."""
        categories.create_category("MROLD", "Old")
        categories.create_category("MRNEW", "New")
        t_old = tasks.create_task("Task A", epic_key="MROLD")
        t_new = tasks.create_task("Task B", epic_key="MRNEW")

        # t_new should have seq 1, t_old should get seq 2 after merge
        result = categories.rename_category("MROLD", "MRNEW")
        assert result["tasks_moved"] == 1

        task_old = tasks.get_task(t_old)
        assert task_old["epic_key"] == "MRNEW"
        assert task_old["epic_seq"] == 2  # after existing seq 1

        # Original target task unchanged
        task_new = tasks.get_task(t_new)
        assert task_new["epic_key"] == "MRNEW"
        assert task_new["epic_seq"] == 1

    def test_rename_with_name_override(self):
        """--name overrides the target category name."""
        categories.create_category("NMOLD", "Old Name")
        tasks.create_task("Task", epic_key="NMOLD")

        categories.rename_category("NMOLD", "NMNEW", name="Better Name")
        cat = categories.get_category("NMNEW")
        assert cat["name"] == "Better Name"

    def test_rename_moves_epics(self):
        """Epics are moved along with regular tasks."""
        categories.create_category("EPOLD", "Old")
        epic_id = tasks.create_epic("Test Epic", "EPOLD")
        tasks.create_task("Task 1", epic_key="EPOLD")

        result = categories.rename_category("EPOLD", "EPNEW")
        assert result["epics_moved"] == 1
        assert result["tasks_moved"] == 1

        epic = tasks.get_task(epic_id)
        assert epic["epic_key"] == "EPNEW"

    def test_rename_same_key_raises(self):
        categories.create_category("SAME", "Same")
        with pytest.raises(ValueError, match="same"):
            categories.rename_category("SAME", "SAME")

    def test_rename_source_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            categories.rename_category("NOPE", "DEST")

    def test_rename_invalid_target_key(self):
        categories.create_category("VOLD", "Valid Old")
        with pytest.raises(ValueError, match="2-8 uppercase letters"):
            categories.rename_category("VOLD", "X")

    def test_rename_case_insensitive(self):
        categories.create_category("CSOLD", "Case Test")
        tasks.create_task("Task", epic_key="CSOLD")
        result = categories.rename_category("csold", "csnew")
        assert result["tasks_moved"] == 1
        assert categories.get_category("CSNEW") is not None


class TestCategoriesCLI:
    """Tests for category CLI commands."""

    def test_create_command(self):
        result = runner.invoke(app, ["create", "CLIC", "CLI Category"])
        assert result.exit_code == 0
        assert "CLIC" in _out(result)

    def test_create_duplicate(self):
        runner.invoke(app, ["create", "CDUP", "First"])
        result = runner.invoke(app, ["create", "CDUP", "Second"])
        assert result.exit_code == 1
        assert "already exists" in _out(result)

    def test_list_command(self):
        categories.ensure_category("CLST")
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        # Should show a table with our category
        assert "CLST" in _out(result)

    def test_delete_command(self):
        categories.create_category("CDEL", "CLI Delete")
        result = runner.invoke(app, ["delete", "CDEL"])
        assert result.exit_code == 0
        assert "Deleted" in _out(result)

    def test_delete_command_not_found(self):
        result = runner.invoke(app, ["delete", "XXXX"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_delete_command_refuses_open(self):
        categories.create_category("CDRJ", "CLI Refuse")
        tasks.create_task("Open task", epic_key="CDRJ")
        result = runner.invoke(app, ["delete", "CDRJ"])
        assert result.exit_code == 1
        assert "open/active" in _out(result)

    def test_delete_command_force(self):
        categories.create_category("CDFF", "CLI Force")
        tasks.create_task("Open task", epic_key="CDFF")
        result = runner.invoke(app, ["delete", "CDFF", "--force"])
        assert result.exit_code == 0
        assert "Deleted" in _out(result)
        assert "Unlinked" in _out(result)

    def test_adopt_command(self):
        tasks.create_task("CADP-1: CLI adopt test")
        result = runner.invoke(app, ["adopt", "CADP"])
        assert result.exit_code == 0
        assert "Adopted" in _out(result)

    def test_rename_command(self):
        categories.create_category("CRNO", "CLI Rename Old")
        tasks.create_task("Task", epic_key="CRNO")
        result = runner.invoke(app, ["rename", "CRNO", "CRNN"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Moved" in out
        assert "CRNO" in out
        assert "CRNN" in out
        assert "Deleted" in out

    def test_rename_command_not_found(self):
        result = runner.invoke(app, ["rename", "ZZZZ", "YYYY"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_rename_command_same_key(self):
        categories.create_category("CRSM", "Same Key")
        result = runner.invoke(app, ["rename", "CRSM", "CRSM"])
        assert result.exit_code == 1
        assert "same" in _out(result)
