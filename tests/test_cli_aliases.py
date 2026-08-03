"""Tests for CLI verb aliases (issue #1104).

Covers: top-level `list`/`recent` -> `find`, `task show` -> `task view`,
and the top-level `epic` command forwarding to `task epic`.
"""

from unittest.mock import patch

from typer.testing import CliRunner

from emdx.main import app

runner = CliRunner()


def _body(output: str) -> str:
    """Strip the 'Usage: emdx <name> ...' line, which legitimately differs
    between an alias and its canonical command (Click echoes the name
    actually invoked)."""
    return "\n".join(line for line in output.splitlines() if "Usage:" not in line)


class TestTopLevelAliases:
    """Top-level verb aliases registered via register_aliases()."""

    def test_list_help_matches_find_help(self):
        """`emdx list --help` should show find's help (list -> find)."""
        list_result = runner.invoke(app, ["list", "--help"])
        find_result = runner.invoke(app, ["find", "--help"])

        assert list_result.exit_code == 0
        assert _body(list_result.stdout) == _body(find_result.stdout)

    def test_recent_help_matches_find_help(self):
        """`emdx recent --help` should show find's help (recent -> find)."""
        recent_result = runner.invoke(app, ["recent", "--help"])
        find_result = runner.invoke(app, ["find", "--help"])

        assert recent_result.exit_code == 0
        assert _body(recent_result.stdout) == _body(find_result.stdout)

    @patch("emdx.models.documents.list_documents")
    def test_list_all_invokes_find(self, mock_list_docs):
        """`emdx list --all` should behave like `emdx find --all`."""
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list", "--all"])

        assert result.exit_code == 0
        mock_list_docs.assert_called_once()

    def test_show_help_matches_view_help(self):
        """`emdx show --help` should show view's help (pre-existing alias)."""
        show_result = runner.invoke(app, ["show", "--help"])
        view_result = runner.invoke(app, ["view", "--help"])

        assert show_result.exit_code == 0
        assert _body(show_result.stdout) == _body(view_result.stdout)


class TestTopLevelEpicCommand:
    """Top-level `epic` should forward into the same app as `task epic`."""

    def test_epic_help_matches_task_epic_help(self):
        epic_result = runner.invoke(app, ["epic", "--help"])
        task_epic_result = runner.invoke(app, ["task", "epic", "--help"])

        assert epic_result.exit_code == 0
        assert _body(epic_result.stdout) == _body(task_epic_result.stdout)

    def test_epic_list_subcommand_available(self):
        result = runner.invoke(app, ["epic", "list", "--help"])
        assert result.exit_code == 0


class TestTaskShowAlias:
    """`task show` should alias to `task view` (issue #1104)."""

    def test_task_show_help_matches_task_view_help(self):
        show_result = runner.invoke(app, ["task", "show", "--help"])
        view_result = runner.invoke(app, ["task", "view", "--help"])

        assert show_result.exit_code == 0
        assert _body(show_result.stdout) == _body(view_result.stdout)

    def test_task_create_alias_still_works(self):
        """Pre-existing alias (create -> add) shouldn't regress."""
        create_result = runner.invoke(app, ["task", "create", "--help"])
        add_result = runner.invoke(app, ["task", "add", "--help"])

        assert create_result.exit_code == 0
        assert _body(create_result.stdout) == _body(add_result.stdout)
