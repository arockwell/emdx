"""Stuck document detection for cascade pipeline.

This service detects documents that appear to be stuck during processing:
- Documents that have been processing for longer than expected
- Documents with failed or unhealthy associated processes
- Documents that have exceeded configurable thresholds
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..database.connection import db_connection
from .execution_monitor import ExecutionMonitor
from .stage_timing import DEFAULT_STAGE_THRESHOLDS, StageTimingService

logger = logging.getLogger(__name__)

# Default multiplier for stuck detection
# A document is considered stuck if it exceeds median * multiplier
DEFAULT_STUCK_MULTIPLIER = 2.0

# Per-stage timeout overrides (in seconds)
# These are absolute maximums before a document is definitely considered stuck
STAGE_MAX_TIMEOUTS = {
    "idea": 300,  # 5 minutes
    "prompt": 600,  # 10 minutes
    "analyzed": 1800,  # 30 minutes
    "planned": 3600,  # 1 hour
}


@dataclass
class StuckDiagnostic:
    """Detailed diagnostic information for a stuck document."""

    doc_id: int
    from_stage: str
    to_stage: str
    time_at_stage_seconds: float
    average_time_seconds: Optional[float]
    threshold_seconds: float
    last_execution_id: Optional[int]
    last_execution_status: Optional[str]
    last_error_message: Optional[str]
    process_health: Optional[Dict]
    reason: str


@dataclass
class StuckDocument:
    """A document that appears to be stuck."""

    doc_id: int
    from_stage: str
    to_stage: str
    elapsed_seconds: float
    threshold_seconds: float
    severity: str  # "warning" or "critical"
    timing_id: int


class StuckDetector:
    """Service for detecting stuck documents in the cascade pipeline."""

    def __init__(
        self,
        threshold_multiplier: float = DEFAULT_STUCK_MULTIPLIER,
        timing_service: Optional[StageTimingService] = None,
        execution_monitor: Optional[ExecutionMonitor] = None,
    ):
        """Initialize the stuck detector.

        Args:
            threshold_multiplier: Multiplier applied to median time for stuck detection
            timing_service: Optional StageTimingService instance
            execution_monitor: Optional ExecutionMonitor instance
        """
        self.threshold_multiplier = threshold_multiplier
        self.timing_service = timing_service or StageTimingService()
        self.execution_monitor = execution_monitor or ExecutionMonitor()

    def get_threshold_for_stage(
        self, from_stage: str, to_stage: str
    ) -> float:
        """Get the stuck threshold for a stage transition.

        Uses historical median * multiplier if available,
        otherwise falls back to default thresholds.

        Args:
            from_stage: The source stage
            to_stage: The target stage

        Returns:
            Threshold in seconds
        """
        stats = self.timing_service.get_stage_stats(from_stage, to_stage)

        if stats and stats.count >= 3:  # Need at least 3 data points
            return stats.median_seconds * self.threshold_multiplier

        # Fall back to default thresholds
        return DEFAULT_STAGE_THRESHOLDS.get(from_stage, 300) * self.threshold_multiplier

    def is_stuck(
        self,
        doc_id: int,
        from_stage: str,
        to_stage: str,
        elapsed_seconds: Optional[float] = None,
    ) -> bool:
        """Check if a document is stuck.

        Args:
            doc_id: The document ID
            from_stage: The source stage
            to_stage: The target stage
            elapsed_seconds: Optional elapsed time (will be looked up if not provided)

        Returns:
            True if the document is considered stuck
        """
        if elapsed_seconds is None:
            # Look up active timing
            active = self.timing_service.get_active_for_doc(doc_id)
            if not active:
                return False
            elapsed_seconds = active.elapsed_seconds

        threshold = self.get_threshold_for_stage(from_stage, to_stage)
        return elapsed_seconds > threshold

    def get_stuck_documents(
        self, stage: Optional[str] = None
    ) -> List[StuckDocument]:
        """Get all documents that appear to be stuck.

        Args:
            stage: Optional stage filter (from_stage)

        Returns:
            List of StuckDocument objects
        """
        active_timings = self.timing_service.get_active_processing()
        stuck_docs = []

        for timing in active_timings:
            if stage and timing.from_stage != stage:
                continue

            threshold = self.get_threshold_for_stage(
                timing.from_stage, timing.to_stage
            )
            max_timeout = STAGE_MAX_TIMEOUTS.get(timing.from_stage, 3600)

            if timing.elapsed_seconds > threshold:
                # Determine severity
                if timing.elapsed_seconds > max_timeout:
                    severity = "critical"
                else:
                    severity = "warning"

                stuck_docs.append(
                    StuckDocument(
                        doc_id=timing.doc_id,
                        from_stage=timing.from_stage,
                        to_stage=timing.to_stage,
                        elapsed_seconds=timing.elapsed_seconds,
                        threshold_seconds=threshold,
                        severity=severity,
                        timing_id=timing.timing_id,
                    )
                )

        return stuck_docs

    def get_stuck_reason(self, doc_id: int) -> Optional[StuckDiagnostic]:
        """Get detailed diagnostic information for a stuck document.

        Args:
            doc_id: The document ID

        Returns:
            StuckDiagnostic if the document is being processed, None otherwise
        """
        active = self.timing_service.get_active_for_doc(doc_id)
        if not active:
            return None

        threshold = self.get_threshold_for_stage(active.from_stage, active.to_stage)
        stats = self.timing_service.get_stage_stats(active.from_stage, active.to_stage)

        # Get execution info if available
        execution_status = None
        error_message = None
        process_health = None

        if active.execution_id:
            with db_connection.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT status, exit_code, pid
                    FROM executions
                    WHERE id = ?
                    """,
                    (active.execution_id,),
                )
                row = cursor.fetchone()
                if row:
                    execution_status = row[0]

                    # Check process health if still running
                    if execution_status == "running" and row[2]:
                        from ..models.executions import Execution

                        # Minimal execution object for health check
                        exec_obj = Execution(
                            id=active.execution_id,
                            doc_id=doc_id,
                            doc_title="",
                            status=execution_status,
                            started_at=active.started_at,
                            log_file="",
                            pid=row[2],
                        )
                        process_health = self.execution_monitor.check_process_health(
                            exec_obj
                        )

        # Determine stuck reason
        reason = self._determine_stuck_reason(
            active.elapsed_seconds,
            threshold,
            execution_status,
            process_health,
        )

        return StuckDiagnostic(
            doc_id=doc_id,
            from_stage=active.from_stage,
            to_stage=active.to_stage,
            time_at_stage_seconds=active.elapsed_seconds,
            average_time_seconds=stats.avg_seconds if stats else None,
            threshold_seconds=threshold,
            last_execution_id=active.execution_id,
            last_execution_status=execution_status,
            last_error_message=error_message,
            process_health=process_health,
            reason=reason,
        )

    def _determine_stuck_reason(
        self,
        elapsed: float,
        threshold: float,
        execution_status: Optional[str],
        process_health: Optional[Dict],
    ) -> str:
        """Determine the reason a document is stuck.

        Args:
            elapsed: Time elapsed in seconds
            threshold: Expected threshold in seconds
            execution_status: Current execution status
            process_health: Process health check result

        Returns:
            Human-readable reason string
        """
        reasons = []

        # Check process health issues
        if process_health:
            if process_health.get("is_zombie"):
                return "Process is zombie (needs cleanup)"
            if not process_health.get("process_exists"):
                return "Process died unexpectedly"
            if not process_health.get("is_running"):
                return "Process stopped but not marked complete"

        # Check execution status
        if execution_status == "failed":
            return "Execution failed"

        # Check timing
        if elapsed > threshold:
            ratio = elapsed / threshold
            if ratio > 3:
                return f"Severely exceeded expected time ({ratio:.1f}x)"
            elif ratio > 2:
                return f"Significantly exceeded expected time ({ratio:.1f}x)"
            else:
                return f"Exceeded expected time ({ratio:.1f}x)"

        return "Unknown"

    def cleanup_stuck_timings(self, dry_run: bool = True) -> List[Dict]:
        """Mark stuck timing records as failed.

        This is useful for cleaning up timings where the process
        died without completing properly.

        Args:
            dry_run: If True, only report what would be done

        Returns:
            List of actions taken/would be taken
        """
        actions = []
        stuck_docs = self.get_stuck_documents()

        for stuck in stuck_docs:
            if stuck.severity == "critical":
                diagnostic = self.get_stuck_reason(stuck.doc_id)

                action = {
                    "doc_id": stuck.doc_id,
                    "timing_id": stuck.timing_id,
                    "from_stage": stuck.from_stage,
                    "to_stage": stuck.to_stage,
                    "elapsed_seconds": stuck.elapsed_seconds,
                    "reason": diagnostic.reason if diagnostic else "Unknown",
                    "action": "mark_failed",
                }

                if not dry_run:
                    self.timing_service.record_stage_complete(
                        stuck.timing_id,
                        success=False,
                        error_message=f"Stuck: {action['reason']}",
                    )
                    action["completed"] = True
                else:
                    action["completed"] = False

                actions.append(action)

        return actions

    def get_stuck_summary(self) -> Dict:
        """Get a summary of stuck documents.

        Returns:
            Summary dictionary with counts by stage and severity
        """
        stuck_docs = self.get_stuck_documents()

        summary = {
            "total_stuck": len(stuck_docs),
            "by_stage": {},
            "by_severity": {"warning": 0, "critical": 0},
            "oldest_stuck": None,
        }

        oldest_elapsed = 0
        for doc in stuck_docs:
            # By stage
            stage_key = doc.from_stage
            if stage_key not in summary["by_stage"]:
                summary["by_stage"][stage_key] = 0
            summary["by_stage"][stage_key] += 1

            # By severity
            summary["by_severity"][doc.severity] += 1

            # Track oldest
            if doc.elapsed_seconds > oldest_elapsed:
                oldest_elapsed = doc.elapsed_seconds
                summary["oldest_stuck"] = {
                    "doc_id": doc.doc_id,
                    "from_stage": doc.from_stage,
                    "elapsed_seconds": doc.elapsed_seconds,
                }

        return summary
