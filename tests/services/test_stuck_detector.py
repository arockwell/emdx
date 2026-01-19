"""Tests for the StuckDetector service."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from emdx.services.stuck_detector import (
    StuckDetector,
    StuckDiagnostic,
    StuckDocument,
    DEFAULT_STUCK_MULTIPLIER,
    STAGE_MAX_TIMEOUTS,
)
from emdx.services.stage_timing import ActiveTiming


class TestStuckDetector:
    """Tests for StuckDetector."""

    @pytest.fixture
    def mock_timing_service(self):
        """Create a mock timing service."""
        return MagicMock()

    @pytest.fixture
    def mock_execution_monitor(self):
        """Create a mock execution monitor."""
        return MagicMock()

    def test_init_with_default_multiplier(self):
        """Test initialization with default threshold multiplier."""
        detector = StuckDetector()
        assert detector.threshold_multiplier == DEFAULT_STUCK_MULTIPLIER

    def test_init_with_custom_multiplier(self):
        """Test initialization with custom threshold multiplier."""
        detector = StuckDetector(threshold_multiplier=3.0)
        assert detector.threshold_multiplier == 3.0

    def test_get_threshold_no_historical_data(self, mock_timing_service):
        """Test threshold calculation with no historical data."""
        mock_timing_service.get_stage_stats.return_value = None
        detector = StuckDetector(timing_service=mock_timing_service)

        threshold = detector.get_threshold_for_stage("idea", "prompt")

        # Should use default (60s) * multiplier (2.0) = 120s
        assert threshold == 60 * DEFAULT_STUCK_MULTIPLIER

    def test_get_threshold_with_historical_data(self, mock_timing_service):
        """Test threshold calculation with historical data."""
        mock_stats = MagicMock()
        mock_stats.count = 10
        mock_stats.median_seconds = 45.0
        mock_timing_service.get_stage_stats.return_value = mock_stats

        detector = StuckDetector(timing_service=mock_timing_service)
        threshold = detector.get_threshold_for_stage("idea", "prompt")

        # Should use median (45s) * multiplier (2.0) = 90s
        assert threshold == 45.0 * DEFAULT_STUCK_MULTIPLIER

    def test_get_threshold_insufficient_data(self, mock_timing_service):
        """Test threshold with insufficient historical data (< 3 samples)."""
        mock_stats = MagicMock()
        mock_stats.count = 2  # Not enough samples
        mock_stats.median_seconds = 45.0
        mock_timing_service.get_stage_stats.return_value = mock_stats

        detector = StuckDetector(timing_service=mock_timing_service)
        threshold = detector.get_threshold_for_stage("idea", "prompt")

        # Should fall back to default
        assert threshold == 60 * DEFAULT_STUCK_MULTIPLIER

    def test_is_stuck_below_threshold(self, mock_timing_service):
        """Test is_stuck returns False when below threshold."""
        mock_timing_service.get_stage_stats.return_value = None
        detector = StuckDetector(timing_service=mock_timing_service)

        result = detector.is_stuck(
            doc_id=1,
            from_stage="idea",
            to_stage="prompt",
            elapsed_seconds=50,  # Below threshold of 120
        )

        assert result is False

    def test_is_stuck_above_threshold(self, mock_timing_service):
        """Test is_stuck returns True when above threshold."""
        mock_timing_service.get_stage_stats.return_value = None
        detector = StuckDetector(timing_service=mock_timing_service)

        result = detector.is_stuck(
            doc_id=1,
            from_stage="idea",
            to_stage="prompt",
            elapsed_seconds=150,  # Above threshold of 120
        )

        assert result is True

    def test_get_stuck_documents_none_stuck(self, mock_timing_service):
        """Test getting stuck documents when none are stuck."""
        mock_timing_service.get_active_processing.return_value = []
        detector = StuckDetector(timing_service=mock_timing_service)

        stuck = detector.get_stuck_documents()

        assert stuck == []

    def test_get_stuck_documents_with_stuck_doc(self, mock_timing_service):
        """Test getting stuck documents with one stuck."""
        now = datetime.now(timezone.utc)
        mock_timing_service.get_active_processing.return_value = [
            ActiveTiming(
                timing_id=1,
                doc_id=42,
                from_stage="idea",
                to_stage="prompt",
                started_at=now - timedelta(seconds=400),
                elapsed_seconds=400,  # Over 5 minutes - exceeds max timeout (300)
                execution_id=None,
            )
        ]
        mock_timing_service.get_stage_stats.return_value = None

        detector = StuckDetector(timing_service=mock_timing_service)
        stuck = detector.get_stuck_documents()

        assert len(stuck) == 1
        assert stuck[0].doc_id == 42
        assert stuck[0].severity == "critical"  # Exceeds max timeout (300 for idea)

    def test_get_stuck_documents_warning_severity(self, mock_timing_service):
        """Test stuck document with warning severity (not critical)."""
        now = datetime.now(timezone.utc)
        # 150 seconds is above threshold (120) but below max timeout (300)
        mock_timing_service.get_active_processing.return_value = [
            ActiveTiming(
                timing_id=1,
                doc_id=42,
                from_stage="idea",
                to_stage="prompt",
                started_at=now - timedelta(seconds=150),
                elapsed_seconds=150,
                execution_id=None,
            )
        ]
        mock_timing_service.get_stage_stats.return_value = None

        detector = StuckDetector(timing_service=mock_timing_service)
        stuck = detector.get_stuck_documents()

        assert len(stuck) == 1
        assert stuck[0].severity == "warning"

    def test_get_stuck_documents_filter_by_stage(self, mock_timing_service):
        """Test filtering stuck documents by stage."""
        now = datetime.now(timezone.utc)
        mock_timing_service.get_active_processing.return_value = [
            ActiveTiming(
                timing_id=1,
                doc_id=42,
                from_stage="idea",
                to_stage="prompt",
                started_at=now - timedelta(seconds=300),
                elapsed_seconds=300,
                execution_id=None,
            ),
            ActiveTiming(
                timing_id=2,
                doc_id=43,
                from_stage="prompt",
                to_stage="analyzed",
                started_at=now - timedelta(seconds=300),
                elapsed_seconds=300,
                execution_id=None,
            ),
        ]
        mock_timing_service.get_stage_stats.return_value = None

        detector = StuckDetector(timing_service=mock_timing_service)
        stuck = detector.get_stuck_documents(stage="idea")

        assert len(stuck) == 1
        assert stuck[0].doc_id == 42

    def test_determine_stuck_reason_zombie_process(self, mock_timing_service, mock_execution_monitor):
        """Test stuck reason detection for zombie process."""
        detector = StuckDetector(
            timing_service=mock_timing_service,
            execution_monitor=mock_execution_monitor,
        )

        reason = detector._determine_stuck_reason(
            elapsed=200,
            threshold=120,
            execution_status="running",
            process_health={"is_zombie": True, "process_exists": True, "is_running": True},
        )

        assert "zombie" in reason.lower()

    def test_determine_stuck_reason_process_died(self, mock_timing_service, mock_execution_monitor):
        """Test stuck reason detection for dead process."""
        detector = StuckDetector(
            timing_service=mock_timing_service,
            execution_monitor=mock_execution_monitor,
        )

        reason = detector._determine_stuck_reason(
            elapsed=200,
            threshold=120,
            execution_status="running",
            process_health={"is_zombie": False, "process_exists": False, "is_running": False},
        )

        assert "died" in reason.lower()

    def test_determine_stuck_reason_exceeded_time(self, mock_timing_service, mock_execution_monitor):
        """Test stuck reason for exceeded time."""
        detector = StuckDetector(
            timing_service=mock_timing_service,
            execution_monitor=mock_execution_monitor,
        )

        # 3x over threshold
        reason = detector._determine_stuck_reason(
            elapsed=400,
            threshold=120,
            execution_status="running",
            process_health=None,
        )

        assert "exceeded" in reason.lower()
        assert "3.3x" in reason  # Ratio

    def test_get_stuck_summary(self, mock_timing_service):
        """Test getting stuck document summary."""
        now = datetime.now(timezone.utc)
        mock_timing_service.get_active_processing.return_value = [
            ActiveTiming(
                timing_id=1,
                doc_id=42,
                from_stage="idea",
                to_stage="prompt",
                started_at=now - timedelta(seconds=400),
                elapsed_seconds=400,  # Over max timeout (300) - critical
                execution_id=None,
            ),
            ActiveTiming(
                timing_id=2,
                doc_id=43,
                from_stage="idea",
                to_stage="prompt",
                started_at=now - timedelta(seconds=150),
                elapsed_seconds=150,  # Over threshold (120) but under max (300) - warning
                execution_id=None,
            ),
        ]
        mock_timing_service.get_stage_stats.return_value = None

        detector = StuckDetector(timing_service=mock_timing_service)
        summary = detector.get_stuck_summary()

        assert summary["total_stuck"] == 2
        assert summary["by_stage"]["idea"] == 2
        assert summary["by_severity"]["critical"] >= 1
        assert summary["by_severity"]["warning"] >= 1
        assert summary["oldest_stuck"]["doc_id"] == 42
