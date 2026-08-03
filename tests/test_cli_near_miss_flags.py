"""Tests for near-miss flag handling (issue #1105).

Covers: `find --tag`/`--tag-search` aliasing to `--tags`, and `task list`
giving a clear error (instead of Click's bare "No such option") for
--search/--tag/--project, which don't exist on that command.
"""

from unittest.mock import patch

from typer.testing import CliRunner

from emdx.main import app

runner = CliRunner()


class TestFindTagAliases:
    """`find --tag`/`--tag-search` should behave like `find --tags`."""

    @patch("emdx.commands.core.search_by_tags")
    def test_tag_flag_matches_tags_flag(self, mock_search_by_tags):
        mock_search_by_tags.return_value = []

        tags_result = runner.invoke(app, ["find", "--tags", "notes"])
        tag_result = runner.invoke(app, ["find", "--tag", "notes"])

        assert tags_result.exit_code == 0
        assert tag_result.exit_code == tags_result.exit_code
        assert mock_search_by_tags.call_count == 2

    @patch("emdx.commands.core.search_by_tags")
    def test_tag_search_flag_matches_tags_flag(self, mock_search_by_tags):
        mock_search_by_tags.return_value = []

        tags_result = runner.invoke(app, ["find", "--tags", "notes"])
        tag_search_result = runner.invoke(app, ["find", "--tag-search", "notes"])

        assert tags_result.exit_code == 0
        assert tag_search_result.exit_code == tags_result.exit_code
        assert mock_search_by_tags.call_count == 2


class TestTaskListNearMissFlags:
    """`task list --search/--tag/--project` should give a clear pointer, not a bare Click error."""

    def test_search_flag_gives_clear_error(self):
        result = runner.invoke(app, ["task", "list", "--search", "foo"])

        assert result.exit_code == 1
        assert "no such option" not in result.output.lower()
        assert "emdx find" in result.output

    def test_tag_flag_gives_clear_error(self):
        result = runner.invoke(app, ["task", "list", "--tag", "foo"])

        assert result.exit_code == 1
        assert "no such option" not in result.output.lower()
        assert "emdx find" in result.output

    def test_project_flag_gives_clear_error(self):
        result = runner.invoke(app, ["task", "list", "--project", "foo"])

        assert result.exit_code == 1
        assert "no such option" not in result.output.lower()
        assert "emdx find" in result.output

    @patch("emdx.models.tasks.list_tasks")
    def test_plain_list_unaffected(self, mock_list_tasks):
        mock_list_tasks.return_value = []

        result = runner.invoke(app, ["task", "list"])

        assert result.exit_code == 0
