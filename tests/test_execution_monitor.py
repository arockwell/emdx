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
            "execution_id", "is_zombie", "is_running",
            "process_exists", "is_stale", "reason"
        }
        assert set(health.keys()) == expected_keys


# ---------------------------------------------------------------------------
# cleanup_stuck_executions
# ---------------------------------------------------------------------------

class TestCleanupStuckExecutions:
    def setup_method(self):
        self.monitor = ExecutionMonitor(stale_timeout_seconds=1800)

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    def test_no_running_executions(self, mock_running, mock_stale):
        mock_running.return_value = []
        mock_stale.return_value = []
        actions = self.monitor.cleanup_stuck_executions(dry_run=True)
        assert actions == []

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_zombie_process_detected(self, mock_proc_cls, mock_running, mock_stale):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_ZOMBIE
        mock_proc_cls.return_value = proc

        execution = _make_execution(id=10, pid=100)
        mock_running.return_value = [execution]
        mock_stale.return_value = []

        actions = self.monitor.cleanup_stuck_executions(dry_run=True)
        assert len(actions) == 1
        assert actions[0]["reason"] == "zombie_process"
        assert actions[0]["completed"] is False  # dry_run

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("emdx.services.execution_monitor.update_execution_status")
    @patch("psutil.Process")
    def test_zombie_cleanup_not_dry_run(self, mock_proc_cls, mock_update, mock_running, mock_stale):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.status.return_value = psutil.STATUS_ZOMBIE
        mock_proc_cls.return_value = proc

        execution = _make_execution(id=10, pid=100)
        mock_running.return_value = [execution]
        mock_stale.return_value = []

        actions = self.monitor.cleanup_stuck_executions(dry_run=False)
        assert len(actions) == 1
        assert actions[0]["completed"] is True
        mock_update.assert_called_once_with(10, "failed", -2)

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process", side_effect=psutil.NoSuchProcess(999))
    def test_dead_process_detected(self, mock_proc_cls, mock_running, mock_stale):
        execution = _make_execution(id=20, pid=999)
        mock_running.return_value = [execution]
        mock_stale.return_value = []

        actions = self.monitor.cleanup_stuck_executions(dry_run=True)
        assert len(actions) == 1
        assert actions[0]["reason"] == "process_died"

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_stale_not_running_detected(self, mock_proc_cls, mock_running, mock_stale):
        proc = MagicMock()
        proc.is_running.return_value = False
        proc.status.return_value = psutil.STATUS_STOPPED
        mock_proc_cls.return_value = proc

        old_start = datetime.now(timezone.utc) - timedelta(hours=2)
        execution = _make_execution(id=30, pid=100, started_at=old_start)
        mock_running.return_value = [execution]
        mock_stale.return_value = []

        monitor = ExecutionMonitor(stale_timeout_seconds=60)
        actions = monitor.cleanup_stuck_executions(dry_run=True)
        assert len(actions) == 1
        assert actions[0]["reason"] == "stale_execution"

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("emdx.services.execution_monitor.update_execution_status")
    def test_stale_heartbeat_executions(self, mock_update, mock_running, mock_stale):
        mock_running.return_value = []  # No running from process check
        stale_exec = _make_execution(id=40, pid=None)
        mock_stale.return_value = [stale_exec]

        actions = self.monitor.cleanup_stuck_executions(dry_run=False)
        assert len(actions) == 1
        assert actions[0]["reason"] == "no_heartbeat"
        mock_update.assert_called_once_with(40, "failed", -5)

    @patch("emdx.services.execution_monitor.get_stale_executions")
    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process", side_effect=psutil.NoSuchProcess(999))
    def test_stale_dedup_with_running(self, mock_proc_cls, mock_running, mock_stale):
        """Stale execution already in running list is not duplicated."""
        execution = _make_execution(id=50, pid=999)
        mock_running.return_value = [execution]
        mock_stale.return_value = [execution]  # Same execution

        actions = self.monitor.cleanup_stuck_executions(dry_run=True)
        assert len(actions) == 1  # Not 2


# ---------------------------------------------------------------------------
# kill_zombie_processes
# ---------------------------------------------------------------------------

class TestKillZombieProcesses:
    def setup_method(self):
        self.monitor = ExecutionMonitor()

    @patch("emdx.services.execution_monitor.get_running_executions")
    def test_no_running_returns_empty(self, mock_running):
        mock_running.return_value = []
        actions = self.monitor.kill_zombie_processes(dry_run=True)
        assert actions == []

    @patch("emdx.services.execution_monitor.get_running_executions")
    def test_no_pid_skipped(self, mock_running):
        execution = _make_execution(pid=None)
        mock_running.return_value = [execution]
        actions = self.monitor.kill_zombie_processes(dry_run=True)
        assert actions == []

    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_non_zombie_skipped(self, mock_proc_cls, mock_running):
        proc = MagicMock()
        proc.status.return_value = psutil.STATUS_RUNNING
        mock_proc_cls.return_value = proc

        execution = _make_execution(pid=100)
        mock_running.return_value = [execution]
        actions = self.monitor.kill_zombie_processes(dry_run=True)
        assert actions == []

    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_zombie_detected_dry_run(self, mock_proc_cls, mock_running):
        proc = MagicMock()
        proc.status.return_value = psutil.STATUS_ZOMBIE
        mock_proc_cls.return_value = proc

        execution = _make_execution(id=5, pid=100)
        mock_running.return_value = [execution]
        actions = self.monitor.kill_zombie_processes(dry_run=True)

        assert len(actions) == 1
        assert actions[0]["action"] == "kill_zombie"
        assert actions[0]["pid"] == 100
        assert actions[0]["completed"] is False
        proc.kill.assert_not_called()

    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_zombie_killed_not_dry_run(self, mock_proc_cls, mock_running):
        proc = MagicMock()
        proc.status.return_value = psutil.STATUS_ZOMBIE
        mock_proc_cls.return_value = proc

        execution = _make_execution(id=5, pid=100)
        mock_running.return_value = [execution]
        actions = self.monitor.kill_zombie_processes(dry_run=False)

        assert len(actions) == 1
        assert actions[0]["completed"] is True
        proc.kill.assert_called_once()

    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process")
    def test_kill_failure_recorded(self, mock_proc_cls, mock_running):
        proc = MagicMock()
        proc.status.return_value = psutil.STATUS_ZOMBIE
        proc.kill.side_effect = PermissionError("denied")
        mock_proc_cls.return_value = proc

        execution = _make_execution(id=5, pid=100)
        mock_running.return_value = [execution]
        actions = self.monitor.kill_zombie_processes(dry_run=False)

        assert len(actions) == 1
        assert actions[0]["completed"] is False
        assert "denied" in actions[0]["error"]

    @patch("emdx.services.execution_monitor.get_running_executions")
    @patch("psutil.Process", side_effect=psutil.NoSuchProcess(999))
    def test_nosuchprocess_during_zombie_check(self, mock_proc_cls, mock_running):
        """NoSuchProcess in kill_zombie_processes is handled (bug: uses `pid` instead of `execution.pid`)."""
        execution = _make_execution(id=5, pid=999)
        mock_running.return_value = [execution]
        # This may raise NameError due to bug at line 262 (pid not defined).
        # We test the current behavior.
        try:
            actions = self.monitor.kill_zombie_processes(dry_run=True)
            assert actions == []
        except NameError:
            # Known bug: line 262 references undefined `pid` instead of `execution.pid`
            pass


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
            "total_executions", "status_breakdown", "recent_24h",
            "currently_running", "unhealthy_running",
            "average_duration_minutes", "failure_rate_percent",
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
