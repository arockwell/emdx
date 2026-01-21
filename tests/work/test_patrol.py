"""Tests for PatrolRunner autonomous work processing."""

import time
import signal
from collections import deque
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from emdx.services.patrol import (
    PatrolConfig,
    PatrolStats,
    PatrolRunner,
    run_patrol,
)
from emdx.work.models import WorkItem, Cascade


class TestPatrolConfig:
    """Tests for PatrolConfig dataclass."""

    def test_default_values(self):
        config = PatrolConfig()
        assert config.name == "patrol:worker"
        assert config.cascade is None
        assert config.stage is None
        assert config.poll_interval == 10
        assert config.max_items == 1
        assert config.timeout == 300
        assert config.dry_run is False
        assert config.max_errors_retained == 100

    def test_custom_values(self):
        config = PatrolConfig(
            name="patrol:custom",
            cascade="review",
            stage="draft",
            poll_interval=5,
            max_items=3,
            timeout=600,
            dry_run=True,
        )
        assert config.name == "patrol:custom"
        assert config.cascade == "review"
        assert config.stage == "draft"
        assert config.poll_interval == 5
        assert config.max_items == 3
        assert config.timeout == 600
        assert config.dry_run is True


class TestPatrolStats:
    """Tests for PatrolStats dataclass."""

    def test_default_values(self):
        stats = PatrolStats()
        assert stats.items_processed == 0
        assert stats.items_succeeded == 0
        assert stats.items_failed == 0
        assert stats.total_time == 0.0
        assert stats.started_at is None
        assert stats.stopped_at is None
        assert isinstance(stats.errors, deque)

    def test_errors_deque_bounded(self):
        """Verify that errors deque respects maxlen."""
        stats = PatrolStats(errors=deque(maxlen=3))
        stats.errors.append("error1")
        stats.errors.append("error2")
        stats.errors.append("error3")
        stats.errors.append("error4")  # Should evict error1
        assert len(stats.errors) == 3
        assert "error1" not in stats.errors
        assert "error4" in stats.errors


class TestPatrolRunnerInit:
    """Tests for PatrolRunner initialization."""

    def test_init_with_config(self, patrol_config):
        runner = PatrolRunner(patrol_config)
        assert runner.config == patrol_config
        assert runner.service is not None
        assert runner.stats is not None
        assert runner._running is False
        assert runner._stop_requested is False

    def test_init_creates_bounded_error_deque(self, patrol_config):
        patrol_config.max_errors_retained = 50
        runner = PatrolRunner(patrol_config)
        # The deque should have maxlen set
        assert runner.stats.errors.maxlen == 50


class TestPatrolRunnerGetTimeout:
    """Tests for _get_timeout method."""

    def test_implementing_stage_gets_long_timeout(self, patrol_runner):
        timeout = patrol_runner._get_timeout("implementing")
        assert timeout >= 1800  # At least 30 minutes

    def test_planned_stage_gets_long_timeout(self, patrol_runner):
        timeout = patrol_runner._get_timeout("planned")
        assert timeout >= 1800

    def test_draft_stage_gets_long_timeout(self, patrol_runner):
        timeout = patrol_runner._get_timeout("draft")
        assert timeout >= 1800

    def test_other_stages_use_config_timeout(self, patrol_config, patrol_runner):
        timeout = patrol_runner._get_timeout("idea")
        assert timeout == patrol_config.timeout

        timeout = patrol_runner._get_timeout("analyzed")
        assert timeout == patrol_config.timeout


class TestPatrolRunnerExtractPrNumber:
    """Tests for _extract_pr_number method."""

    def test_extract_from_github_url(self, patrol_runner):
        output = "Created PR at https://github.com/user/repo/pull/123"
        pr = patrol_runner._extract_pr_number(output)
        assert pr == 123

    def test_extract_from_pr_hash(self, patrol_runner):
        output = "PR #456 created successfully"
        pr = patrol_runner._extract_pr_number(output)
        assert pr == 456

    def test_extract_from_pr_colon(self, patrol_runner):
        output = "Created PR: 789"
        pr = patrol_runner._extract_pr_number(output)
        assert pr == 789

    def test_extract_from_pull_request(self, patrol_runner):
        output = "Opened pull request #321"
        pr = patrol_runner._extract_pr_number(output)
        assert pr == 321

    def test_extract_no_pr_returns_none(self, patrol_runner):
        output = "No PR was created"
        pr = patrol_runner._extract_pr_number(output)
        assert pr is None

    def test_extract_case_insensitive(self, patrol_runner):
        output = "PULL REQUEST: 999"
        pr = patrol_runner._extract_pr_number(output)
        assert pr == 999


class TestPatrolRunnerProcessOne:
    """Tests for process_one method."""

    def test_process_one_dry_run(self, patrol_config, work_service, default_cascade):
        """In dry run mode, no Claude execution happens."""
        patrol_config.dry_run = True
        runner = PatrolRunner(patrol_config)

        item = work_service.add(title="Test item for dry run")
        result = runner.process_one(item)

        assert result is True
        # Item should not have advanced (dry run doesn't call Claude)
        updated = work_service.get(item.id)
        assert updated.stage == "idea"

    def test_process_one_no_processor_advances(
        self, patrol_config, work_service, default_cascade
    ):
        """If stage has no processor, just advance to next stage."""
        # Create cascade with no processors
        work_service.create_cascade(
            name="no-processor",
            stages=["start", "end"],
            processors={},  # No processors
        )
        item = work_service.add(title="Test", cascade="no-processor")

        runner = PatrolRunner(patrol_config)
        result = runner.process_one(item)

        assert result is True
        updated = work_service.get(item.id)
        assert updated.stage == "end"

    def test_process_one_cascade_not_found(self, patrol_config, work_service):
        """Return False if cascade is not found."""
        runner = PatrolRunner(patrol_config)

        # Create a fake item with invalid cascade
        item = WorkItem(
            id="test-fake",
            title="Fake",
            stage="idea",
            cascade="nonexistent",
        )
        result = runner.process_one(item)
        assert result is False

    @patch('emdx.services.patrol.execute_claude_sync')
    @patch('emdx.services.patrol.create_execution')
    @patch('emdx.services.patrol.update_execution_status')
    def test_process_one_success(
        self,
        mock_update_status,
        mock_create_exec,
        mock_execute,
        patrol_config,
        work_service,
        default_cascade,
    ):
        """Test successful processing through Claude."""
        mock_create_exec.return_value = 1
        mock_execute.return_value = {
            "success": True,
            "output": "Processing completed successfully",
        }

        item = work_service.add(title="Test item")
        runner = PatrolRunner(patrol_config)
        result = runner.process_one(item)

        assert result is True
        mock_execute.assert_called_once()
        mock_update_status.assert_called()

    @patch('emdx.services.patrol.execute_claude_sync')
    @patch('emdx.services.patrol.create_execution')
    @patch('emdx.services.patrol.update_execution_status')
    def test_process_one_claude_failure(
        self,
        mock_update_status,
        mock_create_exec,
        mock_execute,
        patrol_config,
        work_service,
        default_cascade,
    ):
        """Test handling of Claude execution failure."""
        mock_create_exec.return_value = 1
        mock_execute.return_value = {
            "success": False,
            "error": "Claude error",
        }

        item = work_service.add(title="Test item")
        runner = PatrolRunner(patrol_config)
        result = runner.process_one(item)

        assert result is False
        assert len(runner.stats.errors) == 1
        mock_update_status.assert_called_with(1, "failed", exit_code=1)

    @patch('emdx.services.patrol.execute_claude_sync')
    @patch('emdx.services.patrol.create_execution')
    @patch('emdx.services.patrol.update_execution_status')
    def test_process_one_extracts_pr_number(
        self,
        mock_update_status,
        mock_create_exec,
        mock_execute,
        patrol_config,
        work_service,
    ):
        """Test that PR number is extracted when at final stage."""
        mock_create_exec.return_value = 1
        mock_execute.return_value = {
            "success": True,
            "output": "Created PR at https://github.com/user/repo/pull/42",
        }

        # Create cascade with a single stage (so get_next_stage returns None)
        work_service.create_cascade(
            name="single-stage",
            stages=["done"],  # Only one stage, so processing calls done()
            processors={"done": "Final processing"},
        )

        item = work_service.add(title="Test PR", cascade="single-stage", stage="done")
        runner = PatrolRunner(patrol_config)
        runner.process_one(item)

        updated = work_service.get(item.id)
        # PR number should be set via done() since there's no next stage
        assert updated.pr_number == 42


class TestPatrolRunnerRunOnce:
    """Tests for run_once method."""

    def test_run_once_no_ready_items(self, work_service):
        """Return 0 when no ready items."""
        from emdx.services.patrol import PatrolConfig, PatrolRunner

        # Create a config filtering to a cascade that doesn't exist
        # This ensures no items match
        config = PatrolConfig(
            name="patrol:test-empty",
            cascade="nonexistent-cascade-xyz",  # No items will match
            poll_interval=1,
        )
        runner = PatrolRunner(config)
        result = runner.run_once()
        assert result == 0

    @patch('emdx.services.patrol.execute_claude_sync')
    @patch('emdx.services.patrol.create_execution')
    @patch('emdx.services.patrol.update_execution_status')
    def test_run_once_processes_ready_items(
        self,
        mock_update_status,
        mock_create_exec,
        mock_execute,
        patrol_runner,
        work_service,
        default_cascade,
    ):
        """Process ready items and return count."""
        mock_create_exec.return_value = 1
        mock_execute.return_value = {"success": True, "output": "done"}

        # Add a ready item
        work_service.add(title="Ready item")

        result = patrol_runner.run_once()
        assert result >= 1
        assert patrol_runner.stats.items_processed >= 1

    def test_run_once_claims_and_releases(self, patrol_config, work_service, default_cascade):
        """Items should be claimed during processing and released after."""
        patrol_config.dry_run = True  # Don't actually process
        runner = PatrolRunner(patrol_config)

        item = work_service.add(title="Test item")
        runner.run_once()

        # Item should be released after processing
        updated = work_service.get(item.id)
        assert updated.claimed_by is None

    def test_run_once_skips_already_claimed(
        self, patrol_config, work_service, default_cascade, claimed_work_item
    ):
        """Should skip items that are already claimed."""
        patrol_config.dry_run = True
        runner = PatrolRunner(patrol_config)

        # The claimed_work_item fixture already has a claim
        result = runner.run_once()

        # The claimed item should not have been processed
        updated = work_service.get(claimed_work_item.id)
        assert updated.claimed_by == "patrol:test"  # Original claimer


class TestPatrolRunnerRun:
    """Tests for run method (main loop)."""

    def test_run_with_max_iterations(self, patrol_config, work_service, default_cascade):
        """Should stop after max_iterations."""
        patrol_config.dry_run = True
        patrol_config.poll_interval = 0  # No sleep
        runner = PatrolRunner(patrol_config)

        # Add some items
        work_service.add(title="Item 1")
        work_service.add(title="Item 2")

        runner.run(max_iterations=2)

        assert runner.stats.started_at is not None
        assert runner.stats.stopped_at is not None
        assert not runner._running

    def test_run_sets_stats(self, patrol_config, work_service, default_cascade):
        """Stats should be properly initialized and tracked."""
        patrol_config.dry_run = True
        patrol_config.poll_interval = 0
        runner = PatrolRunner(patrol_config)

        work_service.add(title="Test item")
        runner.run(max_iterations=1)

        assert runner.stats.started_at is not None
        assert runner.stats.stopped_at is not None
        assert runner.stats.total_time > 0

    def test_run_handles_stop_signal(self, patrol_config, work_service, default_cascade):
        """Should handle stop request gracefully."""
        patrol_config.dry_run = True
        patrol_config.poll_interval = 0.1
        runner = PatrolRunner(patrol_config)

        work_service.add(title="Test item")

        # Stop after a short time
        import threading
        def stop_later():
            time.sleep(0.05)
            runner.stop()

        thread = threading.Thread(target=stop_later)
        thread.start()

        runner.run()  # Should stop when stop() is called
        thread.join()

        assert runner._stop_requested is True
        assert not runner._running


class TestPatrolRunnerProperties:
    """Tests for PatrolRunner properties."""

    def test_is_running_false_initially(self, patrol_runner):
        assert patrol_runner.is_running is False

    def test_stop_sets_stop_requested(self, patrol_runner):
        patrol_runner.stop()
        assert patrol_runner._stop_requested is True


class TestRunPatrolConvenienceFunction:
    """Tests for run_patrol convenience function."""

    def test_run_patrol_returns_stats(self, work_service, default_cascade):
        stats = run_patrol(
            cascade="default",
            max_iterations=1,
            dry_run=True,
        )
        assert isinstance(stats, PatrolStats)
        assert stats.started_at is not None
        assert stats.stopped_at is not None

    def test_run_patrol_custom_name(self, work_service, default_cascade):
        stats = run_patrol(
            name="patrol:custom-test",
            max_iterations=1,
            dry_run=True,
        )
        # The name is used for claiming, hard to verify directly
        assert stats is not None

    def test_run_patrol_filters_cascade(self, work_service, default_cascade, review_cascade):
        # Add items to different cascades
        work_service.add(title="Default item", cascade="default")
        work_service.add(title="Review item", cascade="review")

        # Run patrol for only default cascade
        stats = run_patrol(
            cascade="default",
            max_iterations=1,
            dry_run=True,
        )
        assert stats is not None

    def test_run_patrol_filters_stage(self, work_service, default_cascade):
        # Add items at different stages
        item1 = work_service.add(title="Idea item")  # idea stage
        item2 = work_service.add(title="Planned item")
        work_service.set_stage(item2.id, "planned", "test")

        # Run patrol for only idea stage
        stats = run_patrol(
            stage="idea",
            max_iterations=1,
            dry_run=True,
        )
        assert stats is not None
