"""Unit tests for the execution system.

Tests the execution lifecycle: creating records, updating status,
timeout handling, and log recording.
"""

from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def clear_executions(isolate_test_database):
    """Clear executions table before each test."""
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM executions")
        conn.commit()
    yield


class TestExecutionDataclass:
    """Tests for the Execution dataclass and its properties."""

    def test_execution_duration_completed(self):
        """Test duration calculation for completed execution."""
        from emdx.models.executions import Execution

        started = datetime(2024, 1, 1, 10, 0, 0)
        completed = datetime(2024, 1, 1, 10, 5, 30)

        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="completed",
            started_at=started,
            completed_at=completed,
            log_file="/tmp/test.log",
        )

        assert exec_obj.duration == 330.0  # 5 min 30 sec

    def test_execution_duration_running(self):
        """Test duration is None when still running."""
        from emdx.models.executions import Execution

        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="running",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
        )

        assert exec_obj.duration is None

    def test_execution_is_running(self):
        """Test is_running property."""
        from emdx.models.executions import Execution

        running = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="running",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
        )
        completed = Execution(
            id=2,
            doc_id=100,
            doc_title="Test",
            status="completed",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
        )

        assert running.is_running is True
        assert completed.is_running is False

    def test_execution_is_zombie_no_pid(self):
        """Test is_zombie is False when no PID."""
        from emdx.models.executions import Execution

        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="running",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
            pid=None,
        )

        assert exec_obj.is_zombie is False

    def test_execution_is_zombie_not_running(self):
        """Test is_zombie is False when not running."""
        from emdx.models.executions import Execution

        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="completed",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
            pid=12345,
        )

        assert exec_obj.is_zombie is False

    def test_execution_is_zombie_with_dead_process(self):
        """Test is_zombie detects dead process."""
        from emdx.models.executions import Execution

        # Use a PID that definitely doesn't exist
        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="running",
            started_at=datetime.now(),
            log_file="/tmp/test.log",
            pid=999999999,  # Very unlikely to exist
        )

        assert exec_obj.is_zombie is True

    def test_execution_log_path(self):
        """Test log_path property returns Path object."""
        from pathlib import Path

        from emdx.models.executions import Execution

        exec_obj = Execution(
            id=1,
            doc_id=100,
            doc_title="Test",
            status="running",
            started_at=datetime.now(),
            log_file="~/logs/test.log",
        )

        log_path = exec_obj.log_path
        assert isinstance(log_path, Path)
        assert "logs/test.log" in str(log_path)


class TestExecutionCRUD:
    """Tests for execution CRUD operations."""

    def test_create_execution(self, isolate_test_database):
        """Test creating an execution record."""
        from emdx.models.executions import create_execution, get_execution

        # Use doc_id=None to avoid foreign key constraint
        exec_id = create_execution(
            doc_id=None,
            doc_title="Test Execution",
            log_file="/tmp/test.log",
            working_dir="/tmp",
            pid=12345,
        )

        assert exec_id is not None
        assert isinstance(exec_id, int)

        # Verify it was created
        exec_obj = get_execution(exec_id)
        assert exec_obj is not None
        assert exec_obj.doc_id is None
        assert exec_obj.doc_title == "Test Execution"
        assert exec_obj.status == "running"
        assert exec_obj.log_file == "/tmp/test.log"
        assert exec_obj.working_dir == "/tmp"
        assert exec_obj.pid == 12345

    def test_create_execution_without_doc_id(self, isolate_test_database):
        """Test creating execution without doc_id (standalone delegate)."""
        from emdx.models.executions import create_execution, get_execution

        exec_id = create_execution(
            doc_id=None,
            doc_title="Delegate: task",
            log_file="/tmp/delegate.log",
        )

        exec_obj = get_execution(exec_id)
        assert exec_obj is not None
        assert exec_obj.doc_id is None
        assert exec_obj.doc_title == "Delegate: task"

    def test_get_execution_not_found(self, isolate_test_database):
        """Test getting non-existent execution returns None."""
        from emdx.models.executions import get_execution

        result = get_execution(999999)
        assert result is None

    def test_update_execution_status_completed(self, isolate_test_database):
        """Test updating execution status to completed."""
        from emdx.models.executions import (
            create_execution,
            get_execution,
            update_execution_status,
        )

        exec_id = create_execution(
            doc_id=None,
            doc_title="Test",
            log_file="/tmp/test.log",
        )

        update_execution_status(exec_id, "completed", exit_code=0)

        exec_obj = get_execution(exec_id)
        assert exec_obj.status == "completed"
        assert exec_obj.exit_code == 0
        assert exec_obj.completed_at is not None

    def test_update_execution_status_failed(self, isolate_test_database):
        """Test updating execution status to failed."""
        from emdx.models.executions import (
            create_execution,
            get_execution,
            update_execution_status,
        )

        exec_id = create_execution(
            doc_id=None,
            doc_title="Test",
            log_file="/tmp/test.log",
        )

        update_execution_status(exec_id, "failed", exit_code=1)

        exec_obj = get_execution(exec_id)
        assert exec_obj.status == "failed"
        assert exec_obj.exit_code == 1
        assert exec_obj.completed_at is not None

    def test_update_execution_generic_fields(self, isolate_test_database):
        """Test updating arbitrary execution fields."""
        from emdx.database.connection import db_connection
        from emdx.models.executions import create_execution, update_execution

        exec_id = create_execution(
            doc_id=None,
            doc_title="Test",
            log_file="/tmp/test.log",
        )

        update_execution(exec_id, cost_usd=0.05, tokens_used=1000)

        # Verify with raw SQL since Execution dataclass doesn't have these fields
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT cost_usd, tokens_used FROM executions WHERE id = ?",
                (exec_id,),
            )
            row = cursor.fetchone()
            assert row[0] == 0.05
            assert row[1] == 1000

    def test_update_execution_pid(self, isolate_test_database):
        """Test updating execution PID."""
        from emdx.models.executions import (
            create_execution,
            get_execution,
            update_execution_pid,
        )

        exec_id = create_execution(
            doc_id=None,
            doc_title="Test",
            log_file="/tmp/test.log",
        )

        update_execution_pid(exec_id, 54321)

        exec_obj = get_execution(exec_id)
        assert exec_obj.pid == 54321


class TestExecutionQueries:
    """Tests for execution query operations."""

    def test_get_recent_executions(self, isolate_test_database):
        """Test getting recent executions."""
        from emdx.models.executions import create_execution, get_recent_executions

        # Create a few executions
        for i in range(5):
            create_execution(
                doc_id=None,
                doc_title=f"Exec {i}",
                log_file=f"/tmp/log{i}.log",
            )

        recent = get_recent_executions(limit=3)
        assert len(recent) == 3
        # Should be ordered by id DESC (most recent first)
        assert recent[0].doc_title == "Exec 4"
        assert recent[1].doc_title == "Exec 3"

    def test_get_running_executions(self, isolate_test_database):
        """Test getting running executions only."""
        from emdx.models.executions import (
            create_execution,
            get_running_executions,
            update_execution_status,
        )

        create_execution(doc_id=None, doc_title="Running", log_file="/tmp/1.log")
        exec2 = create_execution(doc_id=None, doc_title="Completed", log_file="/tmp/2.log")
        create_execution(doc_id=None, doc_title="Also Running", log_file="/tmp/3.log")

        update_execution_status(exec2, "completed", exit_code=0)

        running = get_running_executions()
        assert len(running) == 2
        titles = {e.doc_title for e in running}
        assert "Running" in titles
        assert "Also Running" in titles
        assert "Completed" not in titles

    def test_get_execution_stats(self, isolate_test_database):
        """Test getting execution statistics."""
        from emdx.models.executions import (
            create_execution,
            get_execution_stats,
            update_execution_status,
        )

        # Create executions with various statuses
        create_execution(doc_id=None, doc_title="T1", log_file="/tmp/1.log")
        exec2 = create_execution(doc_id=None, doc_title="T2", log_file="/tmp/2.log")
        exec3 = create_execution(doc_id=None, doc_title="T3", log_file="/tmp/3.log")

        update_execution_status(exec2, "completed", exit_code=0)
        update_execution_status(exec3, "failed", exit_code=1)

        stats = get_execution_stats()
        assert stats["total"] >= 3
        assert stats["running"] >= 1
        assert stats["completed"] >= 1
        assert stats["failed"] >= 1
        assert "recent_24h" in stats


class TestTimeoutHandling:
    """Tests for stale execution detection (timeout handling)."""

    def test_get_stale_executions_validates_timeout(self, isolate_test_database):
        """Test that invalid timeout values raise error."""
        from emdx.models.executions import get_stale_executions

        with pytest.raises(ValueError):
            get_stale_executions(timeout_seconds=-1)

    @pytest.mark.skip(reason="last_heartbeat column removed in migration 013")
    def test_get_stale_executions_no_stale(self, isolate_test_database):
        """Test no stale executions when all are fresh.

        Note: This test is skipped because migration 013 removed the
        last_heartbeat column from the executions table.
        """
        from emdx.models.executions import create_execution, get_stale_executions

        # Create a fresh execution
        create_execution(
            doc_id=None,
            doc_title="Fresh",
            log_file="/tmp/fresh.log",
        )

        # With a very long timeout, nothing should be stale
        stale = get_stale_executions(timeout_seconds=86400)  # 24 hours
        assert len(stale) == 0

    @pytest.mark.skip(reason="last_heartbeat column removed in migration 013")
    def test_update_execution_heartbeat(self, isolate_test_database):
        """Test updating execution heartbeat.

        Note: This test is skipped because migration 013 removed the
        last_heartbeat column from the executions table.
        """
        from emdx.database.connection import db_connection
        from emdx.models.executions import (
            create_execution,
            update_execution_heartbeat,
        )

        exec_id = create_execution(
            doc_id=None,
            doc_title="Heartbeat Test",
            log_file="/tmp/hb.log",
        )

        update_execution_heartbeat(exec_id)

        # Verify heartbeat was updated
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT last_heartbeat FROM executions WHERE id = ?",
                (exec_id,),
            )
            row = cursor.fetchone()
            assert row[0] is not None


class TestExecutionService:
    """Tests for the execution service facade."""

    def test_get_agent_executions(self, isolate_test_database):
        """Test getting standalone executions."""
        from emdx.models.executions import create_execution
        from emdx.services.execution_service import get_agent_executions

        # Create various executions (all standalone)
        create_execution(
            doc_id=None,
            doc_title="Agent: test task",
            log_file="/tmp/agent.log",
        )
        create_execution(
            doc_id=None,
            doc_title="Delegate: another task",
            log_file="/tmp/delegate.log",
        )
        create_execution(
            doc_id=None,
            doc_title="Any Type Analysis [1/5]",
            log_file="/tmp/analysis.log",
        )

        # Get all standalone executions from recent time
        from datetime import datetime, timezone

        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        agents = get_agent_executions(cutoff, limit=10)

        # Should get all standalone executions regardless of title
        titles = [a["doc_title"] for a in agents]
        assert any("Agent:" in t for t in titles)
        assert any("Delegate:" in t for t in titles)
        assert any("Any Type Analysis" in t for t in titles)

    def test_get_execution_log_file(self, isolate_test_database):
        """Test getting log file for running execution."""
        from emdx.models.executions import create_execution, update_execution_status
        from emdx.services.execution_service import get_execution_log_file

        exec_id = create_execution(
            doc_id=None,
            doc_title="Agent: log test",
            log_file="/tmp/agent_log.log",
        )

        # Should find running execution
        log_file = get_execution_log_file("Agent: log%")
        assert log_file == "/tmp/agent_log.log"

        # Complete the execution
        update_execution_status(exec_id, "completed", exit_code=0)

        # Should not find it anymore (not running)
        log_file = get_execution_log_file("Agent: log%")
        assert log_file is None
