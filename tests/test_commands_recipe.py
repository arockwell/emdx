"""Tests for recipe management commands."""

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.recipe import _find_recipe, app

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestFindRecipe:
    """Tests for _find_recipe helper."""

    @patch("emdx.commands.recipe.get_document")
    def test_find_by_numeric_id(self, mock_get):
        mock_get.return_value = {"id": 42, "title": "Security Audit", "content": "..."}
        result = _find_recipe("42")
        assert result is not None
        assert result["id"] == 42
        mock_get.assert_called_once_with(42)

    @patch("emdx.commands.recipe.get_document")
    def test_numeric_id_not_found_searches_tags(self, mock_get):
        mock_get.return_value = None
        with patch("emdx.commands.recipe.search_by_tags") as mock_tags:
            mock_tags.return_value = []
            result = _find_recipe("99999")
            assert result is None

    @patch("emdx.commands.recipe.get_document")
    @patch("emdx.commands.recipe.search_by_tags")
    def test_find_by_title_match(self, mock_tags, mock_get):
        mock_get.side_effect = ValueError("not numeric")
        mock_tags.return_value = [
            {"id": 10, "title": "Security Audit Recipe", "content": "..."},
            {"id": 11, "title": "Code Review Recipe", "content": "..."},
        ]
        result = _find_recipe("Security")
        assert result is not None
        assert result["id"] == 10

    @patch("emdx.commands.recipe.get_document")
    @patch("emdx.commands.recipe.search_by_tags")
    def test_find_no_match(self, mock_tags, mock_get):
        mock_get.side_effect = ValueError("not numeric")
        mock_tags.return_value = [
            {"id": 10, "title": "Security Audit Recipe", "content": "..."},
        ]
        with patch("emdx.commands.recipe.search_documents") as mock_search:
            mock_search.return_value = []
            result = _find_recipe("nonexistent")
            assert result is None


class TestRecipeList:
    """Tests for recipe list command."""

    @patch("emdx.commands.recipe.search_by_tags")
    def test_list_no_recipes(self, mock_tags):
        mock_tags.return_value = []
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No recipes found" in _out(result)

    @patch("emdx.commands.recipe.search_by_tags")
    def test_list_shows_recipes(self, mock_tags):
        mock_tags.return_value = [
            {
                "id": 42, "title": "Security Audit",
                "content": "# Security Audit\nCheck all endpoints",
            },
            {
                "id": 43, "title": "Code Review",
                "content": "Review code quality",
            },
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Security Audit" in out
        assert "Code Review" in out
        assert "#42" in out
        assert "#43" in out

    @patch("emdx.commands.recipe.search_by_tags")
    def test_list_shows_steps_badge_for_structured(self, mock_tags):
        mock_tags.return_value = [
            {
                "id": 42, "title": "Multi-Step",
                "content": "# Multi-Step\n\n## Step 1: Scan\nDo it.\n",
            },
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "(steps)" in _out(result)


class TestRecipeRun:
    """Tests for recipe run command."""

    @patch("emdx.commands.recipe._find_recipe")
    def test_run_not_found(self, mock_find):
        mock_find.return_value = None
        result = runner.invoke(app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "Recipe not found" in _out(result)

    @patch("emdx.commands.recipe.subprocess")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_simple_builds_delegate_command(self, mock_find, mock_subprocess):
        """Simple recipes (no steps) still delegate via subprocess."""
        mock_find.return_value = {
            "id": 42, "title": "My Recipe", "content": "Just do it.",
        }
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        runner.invoke(app, ["run", "42"])
        call_args = mock_subprocess.run.call_args[0][0]
        assert "delegate" in call_args
        assert "--doc" in call_args
        assert "42" in call_args

    @patch("emdx.commands.recipe.subprocess")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_simple_with_pr_flag(self, mock_find, mock_subprocess):
        mock_find.return_value = {
            "id": 42, "title": "My Recipe", "content": "Just do it.",
        }
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        runner.invoke(app, ["run", "42", "--pr"])
        call_args = mock_subprocess.run.call_args[0][0]
        assert "--pr" in call_args

    @patch("emdx.commands.recipe.subprocess")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_simple_with_extra_args(self, mock_find, mock_subprocess):
        mock_find.return_value = {
            "id": 42, "title": "My Recipe", "content": "Just do it.",
        }
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        runner.invoke(app, ["run", "42", "--", "analyze", "auth"])
        call_args = mock_subprocess.run.call_args[0][0]
        prompt_args = [a for a in call_args if "analyze" in a or "auth" in a]
        assert len(prompt_args) > 0

    @patch("emdx.commands.recipe._run_structured")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_structured_detected(self, mock_find, mock_run_structured):
        """Structured recipes (with steps) use the recipe executor."""
        mock_find.return_value = {
            "id": 42, "title": "Multi-Step",
            "content": "# Multi\n\n## Step 1: Scan\nScan.\n\n## Step 2: Fix\nFix.\n",
        }
        runner.invoke(app, ["run", "42"])
        mock_run_structured.assert_called_once()

    @patch("emdx.commands.recipe._run_structured")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_structured_with_inputs(self, mock_find, mock_run_structured):
        mock_find.return_value = {
            "id": 42, "title": "Multi-Step",
            "content": "# Multi\n\n## Step 1: Scan\nScan {{target}}.\n",
        }
        runner.invoke(app, ["run", "42", "--input", "target=api"])
        call_kwargs = mock_run_structured.call_args.kwargs
        assert call_kwargs["inputs"] == {"target": "api"}


class TestRecipeShow:
    """Tests for recipe show command."""

    @patch("emdx.commands.recipe._find_recipe")
    def test_show_not_found(self, mock_find):
        mock_find.return_value = None
        result = runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1

    @patch("emdx.commands.recipe._find_recipe")
    def test_show_simple_recipe(self, mock_find):
        mock_find.return_value = {
            "id": 42, "title": "Simple", "content": "No steps here.",
        }
        result = runner.invoke(app, ["show", "42"])
        assert result.exit_code == 0
        assert "simple" in _out(result).lower()

    @patch("emdx.commands.recipe._find_recipe")
    def test_show_structured_recipe(self, mock_find):
        mock_find.return_value = {
            "id": 42, "title": "Multi",
            "content": (
                "---\n"
                "inputs:\n"
                "  - name: target\n"
                "    required: true\n"
                "---\n\n"
                "# Multi\n\n"
                "## Step 1: Scan\nScan {{target}}.\n\n"
                "## Step 2: Fix [--pr]\nFix issues.\n"
            ),
        }
        result = runner.invoke(app, ["show", "42"])
        assert result.exit_code == 0
        out = _out(result)
        assert "target" in out
        assert "required" in out.lower()
        assert "Scan" in out
        assert "Fix" in out
        assert "--pr" in out


class TestRecipeCreate:
    """Tests for recipe create command."""

    def test_create_file_not_found(self, tmp_path):
        result = runner.invoke(app, ["create", str(tmp_path / "nonexistent.md")])
        assert result.exit_code == 1
        assert "File not found" in _out(result)

    @patch("emdx.commands.recipe.subprocess")
    def test_create_calls_save(self, mock_subprocess, tmp_path):
        recipe_file = tmp_path / "recipe.md"
        recipe_file.write_text("# My Recipe\nDo stuff")
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        runner.invoke(app, ["create", str(recipe_file)])
        call_args = mock_subprocess.run.call_args[0][0]
        assert "save" in call_args
        assert "--tags" in call_args
        assert "recipe" in call_args


class TestRecipeInstall:
    """Tests for recipe install command."""

    @patch("emdx.commands.recipe.subprocess")
    def test_install_builtin(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")
        result = runner.invoke(app, ["install", "idea-to-pr"])
        assert result.exit_code == 0
        assert "Installed" in _out(result)

    def test_install_nonexistent(self):
        result = runner.invoke(app, ["install", "nonexistent-recipe"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_install_no_name_lists(self):
        result = runner.invoke(app, ["install"])
        assert result.exit_code == 0
        out = _out(result)
        assert "idea-to-pr" in out
        assert "security-audit" in out
