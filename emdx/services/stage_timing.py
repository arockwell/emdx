"""Stage timing service for tracking cascade stage transition performance.

This service provides:
- Recording stage start/complete events
- Historical statistics (average, median, percentiles)
- ETA estimation based on historical data
- Active processing tracking
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..database.connection import db_connection

logger = logging.getLogger(__name__)

# Default stage timeout thresholds (in seconds)
# These are used when no historical data is available
DEFAULT_STAGE_THRESHOLDS = {
    "idea": 60,  # 1 minute - typically fast
    "prompt": 120,  # 2 minutes - light processing
    "analyzed": 300,  # 5 minutes - substantial analysis
    "planned": 1800,  # 30 minutes - implementation planning may be long
}

# Rolling window for statistics (days)
TIMING_WINDOW_DAYS = 30


@dataclass
class StageStats:
    """Statistics for a cascade stage transition."""

    from_stage: str
    to_stage: str
    count: int
    avg_seconds: float
    median_seconds: float
    p95_seconds: float
    min_seconds: float
    max_seconds: float
    success_rate: float


@dataclass
class TimingRecord:
    """A single stage timing record."""

    id: int
    doc_id: int
    from_stage: str
    to_stage: str
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    success: bool
    error_message: Optional[str]
    execution_id: Optional[int]


@dataclass
class ActiveTiming:
    """An active (in-progress) stage timing."""

    timing_id: int
    doc_id: int
    from_stage: str
    to_stage: str
    started_at: datetime
    elapsed_seconds: float
    execution_id: Optional[int]


class StageTimingService:
    """Service for tracking and analyzing cascade stage timing."""

    def __init__(self, window_days: int = TIMING_WINDOW_DAYS):
        """Initialize the stage timing service.

        Args:
            window_days: Number of days of history to consider for statistics
        """
        self.window_days = window_days

    def record_stage_start(
        self,
        doc_id: int,
        from_stage: str,
        to_stage: str,
        execution_id: Optional[int] = None,
    ) -> int:
        """Record the start of a stage transition.

        Args:
            doc_id: The document being processed
            from_stage: The stage the document is transitioning from
            to_stage: The stage the document is transitioning to
            execution_id: Optional execution ID for correlation

        Returns:
            The timing record ID
        """
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cascade_stage_timings
                (doc_id, from_stage, to_stage, started_at, execution_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc_id, from_stage, to_stage, datetime.now(timezone.utc), execution_id),
            )
            conn.commit()
            timing_id = cursor.lastrowid
            logger.debug(
                f"Recorded stage start: doc={doc_id}, {from_stage} → {to_stage}, timing_id={timing_id}"
            )
            return timing_id

    def record_stage_complete(
        self,
        timing_id: int,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Record the completion of a stage transition.

        Args:
            timing_id: The timing record ID from record_stage_start
            success: Whether the transition was successful
            error_message: Optional error message if failed
        """
        now = datetime.now(timezone.utc)
        with db_connection.get_connection() as conn:
            # Get the start time to calculate duration
            cursor = conn.execute(
                "SELECT started_at FROM cascade_stage_timings WHERE id = ?",
                (timing_id,),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Timing record {timing_id} not found for completion")
                return

            started_at = datetime.fromisoformat(row[0])
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)

            duration_seconds = (now - started_at).total_seconds()

            conn.execute(
                """
                UPDATE cascade_stage_timings
                SET completed_at = ?, duration_seconds = ?, success = ?, error_message = ?
                WHERE id = ?
                """,
                (now, duration_seconds, success, error_message, timing_id),
            )
            conn.commit()
            logger.debug(
                f"Recorded stage complete: timing_id={timing_id}, duration={duration_seconds:.1f}s, success={success}"
            )

    def get_stage_stats(self, from_stage: str, to_stage: str) -> Optional[StageStats]:
        """Get statistics for a stage transition.

        Args:
            from_stage: The source stage
            to_stage: The target stage

        Returns:
            StageStats if data is available, None otherwise
        """
        with db_connection.get_connection() as conn:
            # Get all successful timings within the window
            cursor = conn.execute(
                """
                SELECT duration_seconds
                FROM cascade_stage_timings
                WHERE from_stage = ? AND to_stage = ?
                AND completed_at IS NOT NULL
                AND success = 1
                AND completed_at > datetime('now', ?)
                ORDER BY duration_seconds
                """,
                (from_stage, to_stage, f"-{self.window_days} days"),
            )
            durations = [row[0] for row in cursor.fetchall()]

            if not durations:
                return None

            # Calculate statistics
            count = len(durations)
            avg_seconds = sum(durations) / count
            min_seconds = min(durations)
            max_seconds = max(durations)

            # Median
            mid = count // 2
            if count % 2 == 0:
                median_seconds = (durations[mid - 1] + durations[mid]) / 2
            else:
                median_seconds = durations[mid]

            # 95th percentile
            p95_idx = int(count * 0.95)
            p95_seconds = durations[min(p95_idx, count - 1)]

            # Success rate
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM cascade_stage_timings
                WHERE from_stage = ? AND to_stage = ?
                AND completed_at IS NOT NULL
                AND completed_at > datetime('now', ?)
                """,
                (from_stage, to_stage, f"-{self.window_days} days"),
            )
            total_count = cursor.fetchone()[0]
            success_rate = count / total_count if total_count > 0 else 1.0

            return StageStats(
                from_stage=from_stage,
                to_stage=to_stage,
                count=count,
                avg_seconds=avg_seconds,
                median_seconds=median_seconds,
                p95_seconds=p95_seconds,
                min_seconds=min_seconds,
                max_seconds=max_seconds,
                success_rate=success_rate,
            )

    def get_all_stage_stats(self) -> Dict[str, StageStats]:
        """Get statistics for all stage transitions.

        Returns:
            Dictionary mapping "from_stage→to_stage" to StageStats
        """
        stage_pairs = [
            ("idea", "prompt"),
            ("prompt", "analyzed"),
            ("analyzed", "planned"),
            ("planned", "done"),
        ]

        stats = {}
        for from_stage, to_stage in stage_pairs:
            key = f"{from_stage}→{to_stage}"
            stage_stats = self.get_stage_stats(from_stage, to_stage)
            if stage_stats:
                stats[key] = stage_stats

        return stats

    def get_document_timing(self, doc_id: int) -> List[TimingRecord]:
        """Get all timing records for a document.

        Args:
            doc_id: The document ID

        Returns:
            List of TimingRecord objects
        """
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, doc_id, from_stage, to_stage, started_at,
                       completed_at, duration_seconds, success, error_message, execution_id
                FROM cascade_stage_timings
                WHERE doc_id = ?
                ORDER BY started_at DESC
                """,
                (doc_id,),
            )
            results = []
            for row in cursor.fetchall():
                started_at = datetime.fromisoformat(row[4])
                completed_at = datetime.fromisoformat(row[5]) if row[5] else None

                results.append(
                    TimingRecord(
                        id=row[0],
                        doc_id=row[1],
                        from_stage=row[2],
                        to_stage=row[3],
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_seconds=row[6],
                        success=bool(row[7]),
                        error_message=row[8],
                        execution_id=row[9],
                    )
                )
            return results

    def get_active_processing(self) -> List[ActiveTiming]:
        """Get all currently active (in-progress) stage timings.

        Returns:
            List of ActiveTiming objects
        """
        now = datetime.now(timezone.utc)
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, doc_id, from_stage, to_stage, started_at, execution_id
                FROM cascade_stage_timings
                WHERE completed_at IS NULL
                ORDER BY started_at DESC
                """
            )
            results = []
            for row in cursor.fetchall():
                started_at = datetime.fromisoformat(row[4])
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                elapsed_seconds = (now - started_at).total_seconds()

                results.append(
                    ActiveTiming(
                        timing_id=row[0],
                        doc_id=row[1],
                        from_stage=row[2],
                        to_stage=row[3],
                        started_at=started_at,
                        elapsed_seconds=elapsed_seconds,
                        execution_id=row[5],
                    )
                )
            return results

    def get_active_for_doc(self, doc_id: int) -> Optional[ActiveTiming]:
        """Get active timing for a specific document.

        Args:
            doc_id: The document ID

        Returns:
            ActiveTiming if the document is being processed, None otherwise
        """
        now = datetime.now(timezone.utc)
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, doc_id, from_stage, to_stage, started_at, execution_id
                FROM cascade_stage_timings
                WHERE doc_id = ? AND completed_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (doc_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            started_at = datetime.fromisoformat(row[4])
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)

            elapsed_seconds = (now - started_at).total_seconds()

            return ActiveTiming(
                timing_id=row[0],
                doc_id=row[1],
                from_stage=row[2],
                to_stage=row[3],
                started_at=started_at,
                elapsed_seconds=elapsed_seconds,
                execution_id=row[5],
            )

    def estimate_remaining_time(
        self, from_stage: str, to_stage: str, elapsed_seconds: float
    ) -> Optional[float]:
        """Estimate remaining time for a stage transition.

        Args:
            from_stage: The source stage
            to_stage: The target stage
            elapsed_seconds: Time already elapsed

        Returns:
            Estimated remaining seconds, or None if no data available
        """
        stats = self.get_stage_stats(from_stage, to_stage)
        if not stats:
            # Use default threshold as fallback
            default_time = DEFAULT_STAGE_THRESHOLDS.get(from_stage, 300)
            remaining = max(0, default_time - elapsed_seconds)
            return remaining if elapsed_seconds < default_time else None

        # Use median as the expected completion time
        expected_total = stats.median_seconds
        remaining = max(0, expected_total - elapsed_seconds)

        # If we've exceeded the median, estimate based on p95
        if elapsed_seconds > expected_total:
            remaining = max(0, stats.p95_seconds - elapsed_seconds)

        return remaining if remaining > 0 else None

    def get_default_threshold(self, from_stage: str) -> float:
        """Get the default stuck threshold for a stage.

        Args:
            from_stage: The stage being processed

        Returns:
            Default threshold in seconds
        """
        return DEFAULT_STAGE_THRESHOLDS.get(from_stage, 300)

    def format_duration(self, seconds: float) -> str:
        """Format a duration in human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable string like "1m 23s" or "~2m"
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            if secs > 0:
                return f"{minutes}m {secs}s"
            return f"{minutes}m"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
