"""Tests for group management CLI commands."""

import re
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.groups import app

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# create command
# ---------------------------------------------------------------------------
class TestGroupCreateCommand:
    """Tests for the group create command."""

    @patch("emdx.commands.groups.groups")
    def test_create_basic(self, mock_groups):
        """Create a basic group."""
        mock_groups.create_group.return_value = 1

        result = runner.invoke(app, ["create", "My Group"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Created group #1" in out
        assert "My Group" in out
        mock_groups.create_group.assert_called_once_with(
            name="My Group",
            group_type="batch",
            parent_group_id=None,
            project=None,
            description=None,
        )

    @patch("emdx.commands.groups.groups")
    def test_create_with_options(self, mock_groups):
        """Create a group with type, project, description."""
        mock_groups.create_group.return_value = 2

        result = runner.invoke(app, [
            "create", "Initiative X",
            "--type", "initiative",
            "--project", "my-proj",
            "--description", "Big initiative",
        ])
        out = _out(result)
        assert result.exit_code == 0
        assert "Created group #2" in out
        mock_groups.create_group.assert_called_once_with(
            name="Initiative X",
            group_type="initiative",
            parent_group_id=None,
            project="my-proj",
            description="Big initiative",
        )

    @patch("emdx.commands.groups.groups")
    def test_create_with_parent(self, mock_groups):
        """Create a nested group with --parent."""
        mock_groups.get_group.return_value = {"id": 1, "name": "Parent Group"}
        mock_groups.create_group.return_value = 3

        result = runner.invoke(app, ["create", "Child", "--parent", "1"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Created group #3" in out
        assert "Parent" in out

    @patch("emdx.commands.groups.groups")
    def test_create_parent_not_found(self, mock_groups):
        """Create with non-existent parent shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["create", "Orphan", "--parent", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    def test_create_missing_name(self):
        """Create with no name should fail."""
        result = runner.invoke(app, ["create"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# add command
# ---------------------------------------------------------------------------
class TestGroupAddCommand:
    """Tests for the group add command."""

    @patch("emdx.commands.groups.get_document")
    @patch("emdx.commands.groups.groups")
    def test_add_documents(self, mock_groups, mock_get_doc):
        """Add documents to a group."""
        mock_groups.get_group.return_value = {"id": 1, "name": "Group 1"}
        mock_groups.add_document_to_group.return_value = True
        mock_get_doc.return_value = {"id": 10, "title": "My Doc"}

        result = runner.invoke(app, ["add", "1", "10"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Added 1 document" in out
        mock_groups.add_document_to_group.assert_called_once_with(1, 10, role="member")

    @patch("emdx.commands.groups.get_document")
    @patch("emdx.commands.groups.groups")
    def test_add_with_role(self, mock_groups, mock_get_doc):
        """Add document with custom role."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.add_document_to_group.return_value = True
        mock_get_doc.return_value = {"id": 5, "title": "Doc 5"}

        result = runner.invoke(app, ["add", "1", "5", "--role", "primary"])
        assert result.exit_code == 0
        mock_groups.add_document_to_group.assert_called_once_with(1, 5, role="primary")

    @patch("emdx.commands.groups.groups")
    def test_add_group_not_found(self, mock_groups):
        """Add to non-existent group shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["add", "999", "1"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.groups.get_document")
    @patch("emdx.commands.groups.groups")
    def test_add_doc_not_found(self, mock_groups, mock_get_doc):
        """Add non-existent document reports not found."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["add", "1", "999"])
        assert result.exit_code == 0
        assert "not found" in _out(result)

    @patch("emdx.commands.groups.get_document")
    @patch("emdx.commands.groups.groups")
    def test_add_already_in_group(self, mock_groups, mock_get_doc):
        """Add document already in group shows already-in message."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.add_document_to_group.return_value = False  # already exists
        mock_get_doc.return_value = {"id": 5, "title": "D"}

        result = runner.invoke(app, ["add", "1", "5"])
        assert result.exit_code == 0
        assert "Already in group" in _out(result)


# ---------------------------------------------------------------------------
# remove command
# ---------------------------------------------------------------------------
class TestGroupRemoveCommand:
    """Tests for the group remove command."""

    @patch("emdx.commands.groups.groups")
    def test_remove_document(self, mock_groups):
        """Remove a document from a group."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.remove_document_from_group.return_value = True

        result = runner.invoke(app, ["remove", "1", "10"])
        assert result.exit_code == 0
        assert "Removed 1 document" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_remove_not_in_group(self, mock_groups):
        """Remove document not in group shows not-in message."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.remove_document_from_group.return_value = False

        result = runner.invoke(app, ["remove", "1", "999"])
        assert result.exit_code == 0
        assert "Not in group" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_remove_group_not_found(self, mock_groups):
        """Remove from non-existent group shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["remove", "999", "1"])
        assert result.exit_code != 0
        assert "not found" in _out(result)


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------
class TestGroupListCommand:
    """Tests for the group list command."""

    @patch("emdx.commands.groups.groups")
    def test_list_empty(self, mock_groups):
        """List groups with no groups shows message."""
        mock_groups.list_groups.return_value = []

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No groups found" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_list_with_groups(self, mock_groups):
        """List groups shows table."""
        mock_groups.list_groups.return_value = [
            {
                "id": 1,
                "name": "Group A",
                "group_type": "batch",
                "parent_group_id": None,
                "doc_count": 5,
                "project": "proj",
            },
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Group A" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_list_filter_by_type(self, mock_groups):
        """List with --type filter."""
        mock_groups.list_groups.return_value = []

        runner.invoke(app, ["list", "--type", "initiative"])
        mock_groups.list_groups.assert_called_once_with(
            parent_group_id=None,
            project=None,
            group_type="initiative",
            include_inactive=False,
            top_level_only=False,
        )

    @patch("emdx.commands.groups.groups")
    def test_list_top_level_only(self, mock_groups):
        """List with --parent -1 for top-level only."""
        mock_groups.list_groups.return_value = []

        runner.invoke(app, ["list", "--parent", "-1"])
        mock_groups.list_groups.assert_called_once_with(
            parent_group_id=None,
            project=None,
            group_type=None,
            include_inactive=False,
            top_level_only=True,
        )


# ---------------------------------------------------------------------------
# show command
# ---------------------------------------------------------------------------
class TestGroupShowCommand:
    """Tests for the group show command."""

    @patch("emdx.commands.groups.groups")
    def test_show_group(self, mock_groups):
        """Show a group."""
        mock_groups.get_group.return_value = {
            "id": 1,
            "name": "My Group",
            "group_type": "batch",
            "description": "A test group",
            "project": "proj",
            "parent_group_id": None,
            "created_at": "2024-01-01",
            "created_by": "user",
            "doc_count": 3,
            "total_tokens": 1000,
            "total_cost_usd": 0.05,
        }
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = [
            {"id": 10, "title": "Doc A", "role": "primary"},
            {"id": 11, "title": "Doc B", "role": "member"},
        ]

        result = runner.invoke(app, ["show", "1"])
        out = _out(result)
        assert result.exit_code == 0
        assert "My Group" in out
        assert "Doc A" in out
        assert "primary" in out

    @patch("emdx.commands.groups.groups")
    def test_show_not_found(self, mock_groups):
        """Show non-existent group shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["show", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_show_empty_group(self, mock_groups):
        """Show group with no members."""
        mock_groups.get_group.return_value = {
            "id": 2,
            "name": "Empty Group",
            "group_type": "batch",
            "description": None,
            "project": None,
            "parent_group_id": None,
            "created_at": "2024-01-01",
            "created_by": None,
            "doc_count": 0,
            "total_tokens": None,
            "total_cost_usd": None,
        }
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []

        result = runner.invoke(app, ["show", "2"])
        assert result.exit_code == 0
        assert "No documents" in _out(result)


# ---------------------------------------------------------------------------
# delete command
# ---------------------------------------------------------------------------
class TestGroupDeleteCommand:
    """Tests for the group delete command."""

    @patch("emdx.commands.groups.groups")
    def test_delete_with_force(self, mock_groups):
        """Delete a group with --force."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []
        mock_groups.delete_group.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Deleted group #1" in out
        mock_groups.delete_group.assert_called_once_with(1, hard=False)

    @patch("emdx.commands.groups.groups")
    def test_delete_hard(self, mock_groups):
        """Hard delete a group."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []
        mock_groups.delete_group.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force", "--hard"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)
        mock_groups.delete_group.assert_called_once_with(1, hard=True)

    @patch("emdx.commands.groups.groups")
    def test_delete_not_found(self, mock_groups):
        """Delete non-existent group shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["delete", "999", "--force"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_delete_with_confirmation(self, mock_groups):
        """Delete with confirmation prompt."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []
        mock_groups.delete_group.return_value = True

        result = runner.invoke(app, ["delete", "1"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_delete_cancelled(self, mock_groups):
        """Delete cancelled by user."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []

        result = runner.invoke(app, ["delete", "1"], input="n\n")
        assert "Cancelled" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_delete_failure(self, mock_groups):
        """Delete that fails shows error."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.get_child_groups.return_value = []
        mock_groups.get_group_members.return_value = []
        mock_groups.delete_group.return_value = False

        result = runner.invoke(app, ["delete", "1", "--force"])
        out = _out(result)
        assert result.exit_code != 0
        assert "Failed" in out or "Error" in out


# ---------------------------------------------------------------------------
# edit command
# ---------------------------------------------------------------------------
class TestGroupEditCommand:
    """Tests for the group edit command."""

    @patch("emdx.commands.groups.groups")
    def test_edit_name(self, mock_groups):
        """Edit group name."""
        mock_groups.get_group.return_value = {"id": 1, "name": "Old"}
        mock_groups.update_group.return_value = True

        result = runner.invoke(app, ["edit", "1", "--name", "New Name"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Updated group #1" in out
        mock_groups.update_group.assert_called_once_with(1, name="New Name")

    @patch("emdx.commands.groups.groups")
    def test_edit_multiple_fields(self, mock_groups):
        """Edit multiple fields at once."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.update_group.return_value = True

        result = runner.invoke(app, [
            "edit", "1",
            "--name", "Updated",
            "--description", "New desc",
            "--type", "initiative",
        ])
        assert result.exit_code == 0
        mock_groups.update_group.assert_called_once_with(
            1,
            name="Updated",
            description="New desc",
            group_type="initiative",
        )

    @patch("emdx.commands.groups.groups")
    def test_edit_no_changes(self, mock_groups):
        """Edit with no changes shows message."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}

        result = runner.invoke(app, ["edit", "1"])
        assert result.exit_code == 0
        assert "No changes" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_edit_not_found(self, mock_groups):
        """Edit non-existent group shows error."""
        mock_groups.get_group.return_value = None

        result = runner.invoke(app, ["edit", "999", "--name", "X"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.groups.groups")
    def test_edit_remove_parent(self, mock_groups):
        """Edit with --parent 0 removes parent."""
        mock_groups.get_group.return_value = {"id": 2, "name": "Child"}
        mock_groups.update_group.return_value = True

        result = runner.invoke(app, ["edit", "2", "--parent", "0"])
        assert result.exit_code == 0
        mock_groups.update_group.assert_called_once_with(2, parent_group_id=None)

    @patch("emdx.commands.groups.groups")
    def test_edit_failure(self, mock_groups):
        """Edit that fails shows error."""
        mock_groups.get_group.return_value = {"id": 1, "name": "G"}
        mock_groups.update_group.return_value = False

        result = runner.invoke(app, ["edit", "1", "--name", "New"])
        out = _out(result)
        assert result.exit_code != 0
        assert "Failed" in out or "Error" in out
