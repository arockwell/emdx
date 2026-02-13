"""Tests for recipe management commands."""

import re
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from emdx.commands.recipe import app, _find_recipe

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
            {"id": 42, "title": "Security Audit", "content": "# Security Audit\nCheck all endpoints"},
            {"id": 43, "title": "Code Review", "content": "Review code quality"},
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Security Audit" in out
        assert "Code Review" in out
        assert "#42" in out
        assert "#43" in out


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
    def test_run_builds_delegate_command(self, mock_find, mock_subprocess):
        mock_find.return_value = {"id": 42, "title": "My Recipe", "content": "..."}
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        result = runner.invoke(app, ["run", "42"])
        # Verify delegate was called with --doc 42
        call_args = mock_subprocess.run.call_args[0][0]
        assert "delegate" in call_args
        assert "--doc" in call_args
        assert "42" in call_args

    @patch("emdx.commands.recipe.subprocess")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_with_pr_flag(self, mock_find, mock_subprocess):
        mock_find.return_value = {"id": 42, "title": "My Recipe", "content": "..."}
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        result = runner.invoke(app, ["run", "42", "--pr"])
        call_args = mock_subprocess.run.call_args[0][0]
        assert "--pr" in call_args

    @patch("emdx.commands.recipe.subprocess")
    @patch("emdx.commands.recipe._find_recipe")
    def test_run_with_extra_args(self, mock_find, mock_subprocess):
        mock_find.return_value = {"id": 42, "title": "My Recipe", "content": "..."}
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        result = runner.invoke(app, ["run", "42", "--", "analyze", "auth"])
        call_args = mock_subprocess.run.call_args[0][0]
        # Extra args should be incorporated into the prompt
        prompt_args = [a for a in call_args if "analyze" in a or "auth" in a]
        assert len(prompt_args) > 0


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
        result = runner.invoke(app, ["create", str(recipe_file)])
        call_args = mock_subprocess.run.call_args[0][0]
        assert "save" in call_args
        assert "--tags" in call_args
        assert "recipe" in call_args
