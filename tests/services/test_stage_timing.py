"""Tests for the StageTimingService."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from emdx.services.stage_timing import (
    StageTimingService,
    StageStats,
    TimingRecord,
    ActiveTiming,
    DEFAULT_STAGE_THRESHOLDS,
)


class TestStageTimingService:
    """Tests for StageTimingService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        with patch("emdx.services.stage_timing.db_connection") as mock:
            yield mock

    def test_record_stage_start(self, mock_db):
        """Test recording a stage start."""
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 123
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        timing_id = service.record_stage_start(
            doc_id=1,
            from_stage="idea",
            to_stage="prompt",
        )

        assert timing_id == 123
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_record_stage_start_with_execution_id(self, mock_db):
        """Test recording a stage start with execution ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 456
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        timing_id = service.record_stage_start(
            doc_id=1,
            from_stage="prompt",
            to_stage="analyzed",
            execution_id=789,
        )

        assert timing_id == 456
        # Verify execution_id was passed
        call_args = mock_conn.execute.call_args[0]
        assert 789 in call_args[1]

    def test_record_stage_complete(self, mock_db):
        """Test recording a stage completion."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Return a started_at time
        mock_cursor.fetchone.return_value = (
            datetime.now(timezone.utc).isoformat(),
        )
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        service.record_stage_complete(timing_id=123, success=True)

        # Should have called execute twice (SELECT and UPDATE)
        assert mock_conn.execute.call_count == 2
        mock_conn.commit.assert_called_once()

    def test_record_stage_complete_with_error(self, mock_db):
        """Test recording a failed stage completion."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            datetime.now(timezone.utc).isoformat(),
        )
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        service.record_stage_complete(
            timing_id=123,
            success=False,
            error_message="Test error",
        )

        # Verify error message was passed
        update_call = mock_conn.execute.call_args_list[-1]
        assert "Test error" in update_call[0][1]

    def test_get_stage_stats_no_data(self, mock_db):
        """Test getting stats when no data is available."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        stats = service.get_stage_stats("idea", "prompt")

        assert stats is None

    def test_get_stage_stats_with_data(self, mock_db):
        """Test getting stats with historical data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Return durations: [10, 20, 30, 40, 50]
        mock_cursor.fetchall.side_effect = [
            [(10,), (20,), (30,), (40,), (50,)],  # durations
        ]
        mock_cursor.fetchone.return_value = (5,)  # total count
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        stats = service.get_stage_stats("idea", "prompt")

        assert stats is not None
        assert stats.count == 5
        assert stats.avg_seconds == 30.0
        assert stats.median_seconds == 30.0  # Middle value
        assert stats.min_seconds == 10
        assert stats.max_seconds == 50

    def test_get_document_timing(self, mock_db):
        """Test getting timing records for a document."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        now = datetime.now(timezone.utc)
        mock_cursor.fetchall.return_value = [
            (1, 42, "idea", "prompt", now.isoformat(), now.isoformat(), 30.0, 1, None, 100),
            (2, 42, "prompt", "analyzed", now.isoformat(), None, None, 0, "Error", 101),
        ]
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        records = service.get_document_timing(doc_id=42)

        assert len(records) == 2
        assert records[0].from_stage == "idea"
        assert records[0].success is True
        assert records[1].error_message == "Error"

    def test_get_active_processing(self, mock_db):
        """Test getting active (in-progress) timings."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        started = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        mock_cursor.fetchall.return_value = [
            (1, 42, "analyzed", "planned", started, 100),
        ]
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        active = service.get_active_processing()

        assert len(active) == 1
        assert active[0].doc_id == 42
        assert active[0].from_stage == "analyzed"
        assert active[0].elapsed_seconds >= 60  # At least 60 seconds elapsed

    def test_estimate_remaining_time_no_stats(self, mock_db):
        """Test ETA estimation when no historical data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        service = StageTimingService()
        remaining = service.estimate_remaining_time(
            from_stage="idea",
            to_stage="prompt",
            elapsed_seconds=10,
        )

        # Should use default threshold (60s for idea) minus elapsed
        expected = DEFAULT_STAGE_THRESHOLDS["idea"] - 10
        assert remaining == expected

    def test_format_duration_seconds(self):
        """Test formatting short durations."""
        service = StageTimingService()
        assert service.format_duration(30) == "30s"
        assert service.format_duration(59) == "59s"

    def test_format_duration_minutes(self):
        """Test formatting durations in minutes."""
        service = StageTimingService()
        assert service.format_duration(60) == "1m"
        assert service.format_duration(90) == "1m 30s"
        assert service.format_duration(120) == "2m"

    def test_format_duration_hours(self):
        """Test formatting durations in hours."""
        service = StageTimingService()
        assert service.format_duration(3600) == "1h 0m"
        assert service.format_duration(3660) == "1h 1m"
        assert service.format_duration(7200) == "2h 0m"
