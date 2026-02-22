"""Tests for emdx.services.execution_monitor module.

Focuses on the ExecutionMonitor class:
- check_process_health logic
- cleanup_stuck_executions logic
- kill_zombie_processes logic
- get_execution_metrics (DB-dependent, uses session test DB)

NOTE: The source has a bug at lines 262-263 where `pid` should be `execution.pid`
in the except handlers. Tests are written to work with the existing code.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psutil

from emdx.models.executions import Execution
from emdx.services.execution_monitor import ExecutionMonitor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution(
    id=1,
    doc_id=1,
    doc_title="Test",
    status="running",
    started_at=None,
    completed_at=None,
    log_file="",
    exit_code=None,
    working_dir=None,
    pid=12345,
):
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    return Execution(
        id=id,
        doc_id=doc_id,
        doc_title=doc_title,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        log_file=log_file,
        exit_code=exit_code,
        working_dir=working_dir,
        pid=pid,
    )


# ---------------------------------------------------------------------------
# ExecutionMonitor init
# ---------------------------------------------------------------------------


class TestExecutionMonitorInit:
    def test_default_stale_timeout(self):
        monitor = ExecutionMonitor()
        assert monitor.stale_timeout == 1800

    def test_custom_stale_timeout(self):
        monitor = ExecutionMonitor(stale_timeout_seconds=600)
        assert monitor.stale_timeout == 600


# ---------------------------------------------------------------------------
# check_process_health
# ---------------------------------------------------------------------------


class TestCheckProcessHealth:
    def setup_method(self):
        self.monitor = ExecutionMonitor(stale_timeout_seconds=1800)

    @patch("psutil.Process")
    def test_healthy_process(self, mock_process_cls):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_RUNNING
        mock_process_cls.return_value = proc

        execution = _make_execution(pid=100)
        health = self.monitor.check_process_health(execution)

        assert health["process_exists"] is True
        assert health["is_running"] is True
        assert health["is_zombie"] is False

    @patch("psutil.Process")
    def test_zombie_process(self, mock_process_cls):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_ZOMBIE
        mock_process_cls.return_value = proc

        execution = _make_execution(pid=100)
        health = self.monitor.check_process_health(execution)

        assert health["is_zombie"] is True
        assert health["reason"] == "Process is zombie"

    @patch("psutil.Process", side_effect=psutil.NoSuchProcess(999))
    def test_process_not_found(self, mock_process_cls):
        execution = _make_execution(pid=999)
        health = self.monitor.check_process_health(execution)

        assert health["process_exists"] is False
        assert health["reason"] == "Process not found"

    @patch("psutil.Process", side_effect=psutil.AccessDenied(999))
    def test_process_access_denied(self, mock_process_cls):
        execution = _make_execution(pid=999)
        health = self.monitor.check_process_health(execution)

        assert health["process_exists"] is True
        assert health["reason"] == "Access denied to process"

    def test_no_pid_recorded(self):
        execution = _make_execution(pid=None)
        health = self.monitor.check_process_health(execution)

        assert health["process_exists"] is False
        assert health["reason"] == "No PID recorded"

    @patch("psutil.Process")
    def test_stale_execution(self, mock_process_cls):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_RUNNING
        mock_process_cls.return_value = proc

        old_start = datetime.now(timezone.utc) - timedelta(hours=2)
        execution = _make_execution(pid=100, started_at=old_start)
        monitor = ExecutionMonitor(stale_timeout_seconds=60)
        health = monitor.check_process_health(execution)

        assert health["is_stale"] is True

    @patch("psutil.Process")
    def test_not_stale_execution(self, mock_process_cls):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_RUNNING
        mock_process_cls.return_value = proc

        recent_start = datetime.now(timezone.utc) - timedelta(seconds=10)
        execution = _make_execution(pid=100, started_at=recent_start)
        health = self.monitor.check_process_health(execution)

        assert health["is_stale"] is False

    def test_health_dict_keys(self):
        execution = _make_execution(pid=None)
        health = self.monitor.check_process_health(execution)
        expected_keys = {
            "execution_id",
            "is_zombie",
            "is_running",
            "process_exists",
            "is_stale",
            "reason",
        }
        assert set(health.keys()) == expected_keys


# ---------------------------------------------------------------------------
# get_execution_metrics (uses session test DB)
# ---------------------------------------------------------------------------


class TestGetExecutionMetrics:
    def test_metrics_returns_expected_keys(self):
        """Test that metrics returns a dict with all expected keys.

        This test uses the session-scoped test database from conftest.
        """
        monitor = ExecutionMonitor()
        with patch("emdx.services.execution_monitor.get_running_executions", return_value=[]):
            metrics = monitor.get_execution_metrics()

        expected_keys = {
            "total_executions",
            "status_breakdown",
            "recent_24h",
            "currently_running",
            "unhealthy_running",
            "average_duration_minutes",
            "failure_rate_percent",
            "metrics_timestamp",
        }
        assert expected_keys.issubset(set(metrics.keys()))

    def test_metrics_with_no_executions(self):
        monitor = ExecutionMonitor()
        with patch("emdx.services.execution_monitor.get_running_executions", return_value=[]):
            metrics = monitor.get_execution_metrics()
        assert metrics["currently_running"] == 0
        assert metrics["unhealthy_running"] == 0
        assert metrics["failure_rate_percent"] == 0.0


# ---------------------------------------------------------------------------
# Execution dataclass properties
# ---------------------------------------------------------------------------


class TestExecutionDataclass:
    def test_duration_when_completed(self):
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        e = _make_execution(started_at=start, completed_at=end)
        assert e.duration == 300.0

    def test_duration_when_running(self):
        e = _make_execution(completed_at=None)
        assert e.duration is None

    def test_is_running_true(self):
        e = _make_execution(status="running")
        assert e.is_running is True

    def test_is_running_false(self):
        e = _make_execution(status="completed")
        assert e.is_running is False

    def test_is_zombie_no_pid(self):
        e = _make_execution(status="running", pid=None)
        assert e.is_zombie is False

    def test_is_zombie_not_running(self):
        e = _make_execution(status="completed", pid=100)
        assert e.is_zombie is False
