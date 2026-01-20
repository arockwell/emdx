"""Tests for work CLI commands."""

import json
import pytest
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from emdx.commands.work import app, get_service
from emdx.work.service import WorkService


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def reset_service_singleton():
    """Reset the work service singleton before each test."""
    import emdx.commands.work as work_module
    work_module._service = None
    yield
    work_module._service = None


class TestWorkAddCommand:
    """Tests for 'emdx work add' command."""

    def test_add_basic(self, cli_runner, default_cascade):
        result = cli_runner.invoke(app, ["add", "Test work item"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "emdx-" in result.output

    def test_add_with_options(self, cli_runner, default_cascade):
        result = cli_runner.invoke(app, [
            "add", "Feature work",
            "--cascade", "default",
            "--stage", "planned",
            "--priority", "1",
            "--type", "feature",
        ])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "P1-HIGH" in result.output

    def test_add_with_content(self, cli_runner, default_cascade):
        result = cli_runner.invoke(app, [
            "add", "Work with content",
            "--content", "This is detailed content",
        ])
        assert result.exit_code == 0

    def test_add_invalid_cascade(self, cli_runner):
        result = cli_runner.invoke(app, [
            "add", "Invalid cascade",
            "--cascade", "nonexistent",
        ])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_add_invalid_stage(self, cli_runner, default_cascade):
        result = cli_runner.invoke(app, [
            "add", "Invalid stage",
            "--stage", "nonexistent",
        ])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestWorkReadyCommand:
    """Tests for 'emdx work ready' command."""

    def test_ready_empty(self, cli_runner, work_service):
        # Filter to a cascade that doesn't exist to ensure empty results
        result = cli_runner.invoke(app, ["ready", "--cascade", "nonexistent-xyz"])
        assert result.exit_code == 0
        assert "No ready work items" in result.output

    def test_ready_with_items(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["ready"])
        assert result.exit_code == 0
        assert "Ready Work" in result.output

    def test_ready_json_output(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["ready", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        if data:
            assert "id" in data[0]
            assert "title" in data[0]

    def test_ready_filter_cascade(self, cli_runner, sample_work_items, review_cascade, work_service):
        # Add a review item
        work_service.add(title="Review item", cascade="review")

        result = cli_runner.invoke(app, ["ready", "--cascade", "default"])
        assert result.exit_code == 0

    def test_ready_with_limit(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["ready", "--limit", "1"])
        assert result.exit_code == 0


class TestWorkShowCommand:
    """Tests for 'emdx work show' command."""

    def test_show_item(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["show", sample_work_item.id])
        assert result.exit_code == 0
        assert sample_work_item.id in result.output
        assert sample_work_item.title in result.output

    def test_show_not_found(self, cli_runner):
        result = cli_runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_show_with_transitions(self, cli_runner, sample_work_item, work_service):
        # Create some transitions
        work_service.advance(sample_work_item.id)

        result = cli_runner.invoke(app, ["show", sample_work_item.id, "--transitions"])
        assert result.exit_code == 0
        assert "Transitions" in result.output


class TestWorkAdvanceCommand:
    """Tests for 'emdx work advance' command."""

    def test_advance_item(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["advance", sample_work_item.id])
        assert result.exit_code == 0
        assert "Advanced" in result.output

    def test_advance_with_by(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, [
            "advance", sample_work_item.id,
            "--by", "test-script",
        ])
        assert result.exit_code == 0

    def test_advance_at_terminal(self, cli_runner, sample_work_item, work_service):
        work_service.done(sample_work_item.id)
        result = cli_runner.invoke(app, ["advance", sample_work_item.id])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestWorkStartCommand:
    """Tests for 'emdx work start' command."""

    def test_start_item(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["start", sample_work_item.id])
        assert result.exit_code == 0
        assert "Started" in result.output

    def test_start_with_claim(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, [
            "start", sample_work_item.id,
            "--claim-as", "patrol:test",
        ])
        assert result.exit_code == 0
        assert "Claimed by" in result.output


class TestWorkDoneCommand:
    """Tests for 'emdx work done' command."""

    def test_done_item(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["done", sample_work_item.id])
        assert result.exit_code == 0
        assert "Completed" in result.output

    def test_done_with_pr(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, [
            "done", sample_work_item.id,
            "--pr", "123",
        ])
        assert result.exit_code == 0
        assert "PR" in result.output

    def test_done_without_doc(self, cli_runner, sample_work_item):
        # Note: --doc requires a valid document ID (foreign key constraint)
        # Testing without doc since we don't have documents in the test DB
        result = cli_runner.invoke(app, ["done", sample_work_item.id])
        assert result.exit_code == 0


class TestWorkListCommand:
    """Tests for 'emdx work list' command."""

    def test_list_items(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Work Items" in result.output

    def test_list_filter_cascade(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["list", "--cascade", "default"])
        assert result.exit_code == 0

    def test_list_filter_stage(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["list", "--stage", "idea"])
        assert result.exit_code == 0

    def test_list_include_done(self, cli_runner, sample_work_items, work_service):
        work_service.done(sample_work_items[0].id)
        result = cli_runner.invoke(app, ["list", "--all"])
        assert result.exit_code == 0
        # Should include done items
        assert "done" in result.output.lower()

    def test_list_with_limit(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["list", "--limit", "1"])
        assert result.exit_code == 0

    def test_list_empty(self, cli_runner, work_service):
        # Clear all items
        items = work_service.list(include_done=True)
        for item in items:
            work_service.delete(item.id)

        result = cli_runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No work items found" in result.output


class TestWorkClaimCommand:
    """Tests for 'emdx work claim' command."""

    def test_claim_item(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, [
            "claim", sample_work_item.id,
            "--as", "patrol:test",
        ])
        assert result.exit_code == 0
        assert "Claimed" in result.output

    def test_claim_already_claimed(self, cli_runner, claimed_work_item):
        result = cli_runner.invoke(app, [
            "claim", claimed_work_item.id,
            "--as", "patrol:other",
        ])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestWorkReleaseCommand:
    """Tests for 'emdx work release' command."""

    def test_release_claimed(self, cli_runner, claimed_work_item):
        result = cli_runner.invoke(app, ["release", claimed_work_item.id])
        assert result.exit_code == 0
        assert "Released" in result.output

    def test_release_unclaimed(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["release", sample_work_item.id])
        assert result.exit_code == 0


class TestWorkDepCommand:
    """Tests for 'emdx work dep' command."""

    def test_dep_show_empty(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, ["dep", sample_work_item.id])
        assert result.exit_code == 0
        assert "No dependencies" in result.output

    def test_dep_show_with_deps(self, cli_runner, blocked_work_item):
        blocked, blocker = blocked_work_item
        result = cli_runner.invoke(app, ["dep", blocked.id])
        assert result.exit_code == 0
        assert blocker.id in result.output

    def test_dep_add(self, cli_runner, sample_work_items):
        item1, item2 = sample_work_items[:2]
        result = cli_runner.invoke(app, [
            "dep", item1.id,
            "--add", item2.id,
        ])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_dep_add_with_type(self, cli_runner, sample_work_items):
        item1, item2 = sample_work_items[:2]
        result = cli_runner.invoke(app, [
            "dep", item1.id,
            "--add", item2.id,
            "--type", "related",
        ])
        assert result.exit_code == 0
        assert "related" in result.output

    def test_dep_remove(self, cli_runner, blocked_work_item):
        blocked, blocker = blocked_work_item
        result = cli_runner.invoke(app, [
            "dep", blocked.id,
            "--remove", blocker.id,
        ])
        assert result.exit_code == 0
        assert "Removed" in result.output


class TestWorkCascadesCommand:
    """Tests for 'emdx work cascades' command."""

    def test_list_cascades(self, cli_runner, default_cascade, review_cascade):
        result = cli_runner.invoke(app, ["cascades"])
        assert result.exit_code == 0
        assert "Available Cascades" in result.output
        assert "default" in result.output


class TestWorkStatusCommand:
    """Tests for 'emdx work status' command."""

    def test_status_overview(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Work Status" in result.output

    def test_status_filter_cascade(self, cli_runner, sample_work_items):
        result = cli_runner.invoke(app, ["status", "--cascade", "default"])
        assert result.exit_code == 0

    def test_status_empty(self, cli_runner, work_service):
        # Clear all items
        items = work_service.list(include_done=True)
        for item in items:
            work_service.delete(item.id)

        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No work items found" in result.output


class TestWorkRunCommand:
    """Tests for 'emdx work run' command."""

    @patch('emdx.services.patrol.run_patrol')
    def test_run_basic(self, mock_run_patrol, cli_runner, default_cascade):
        from emdx.services.patrol import PatrolStats
        mock_run_patrol.return_value = PatrolStats(
            items_processed=2,
            items_succeeded=2,
            items_failed=0,
        )

        result = cli_runner.invoke(app, ["run", "--once", "--dry-run"])
        assert result.exit_code == 0
        mock_run_patrol.assert_called_once()

    @patch('emdx.services.patrol.run_patrol')
    def test_run_with_options(self, mock_run_patrol, cli_runner, default_cascade):
        from emdx.services.patrol import PatrolStats
        mock_run_patrol.return_value = PatrolStats()

        result = cli_runner.invoke(app, [
            "run",
            "--cascade", "default",
            "--stage", "idea",
            "--interval", "5",
            "--max", "10",
            "--name", "test-runner",
            "--dry-run",
        ])
        assert result.exit_code == 0
        mock_run_patrol.assert_called_once_with(
            cascade="default",
            stage="idea",
            poll_interval=5,
            max_iterations=10,
            dry_run=True,
            name="test-runner",
        )


class TestWorkProcessCommand:
    """Tests for 'emdx work process' command."""

    def test_process_dry_run(self, cli_runner, sample_work_item):
        result = cli_runner.invoke(app, [
            "process", sample_work_item.id,
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_process_not_found(self, cli_runner):
        result = cli_runner.invoke(app, ["process", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestWorkTestCommand:
    """Tests for 'emdx work test' command."""

    def test_test_basic(self, cli_runner, default_cascade):
        result = cli_runner.invoke(app, ["test"])
        assert result.exit_code == 0
        assert "Work System Test" in result.output
        assert "Database connection OK" in result.output


class TestGetService:
    """Tests for the get_service singleton function."""

    def test_returns_work_service(self):
        import emdx.commands.work as work_module
        work_module._service = None

        service = get_service()
        assert isinstance(service, WorkService)

    def test_returns_singleton(self):
        import emdx.commands.work as work_module
        work_module._service = None

        service1 = get_service()
        service2 = get_service()
        assert service1 is service2
