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

    def test_adopt_command(self):
        tasks.create_task("CADP-1: CLI adopt test")
        result = runner.invoke(app, ["adopt", "CADP"])
        assert result.exit_code == 0
        assert "Adopted" in _out(result)
