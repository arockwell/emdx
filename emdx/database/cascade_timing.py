"""Cascade stage timing utilities for progress tracking and diagnostics.

This module provides functions to:
- Record timing data for stage transitions
- Calculate historical timing statistics
- Detect stuck documents based on expected timing
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .connection import db_connection

# Default timing estimates (seconds) when no historical data is available
DEFAULT_TIMINGS = {
    ("idea", "prompt"): 30,
    ("prompt", "analyzed"): 60,
    ("analyzed", "planned"): 120,
    ("planned", "done"): 300,  # PR creation takes longer
}

# Cascade stages in order
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
NEXT_STAGE = {
    "idea": "prompt",
    "prompt": "analyzed",
    "analyzed": "planned",
    "planned": "done",
}


def record_timing_start(
    doc_id: int,
    from_stage: str,
    to_stage: str,
    execution_id: Optional[int] = None,
) -> int:
    """Record the start of a stage transition.

    Args:
        doc_id: Document being processed
        from_stage: Current stage (e.g., "idea")
        to_stage: Target stage (e.g., "prompt")
        execution_id: Optional linked execution ID

    Returns:
        timing_id: ID of the created timing record
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO cascade_stage_timings
            (doc_id, from_stage, to_stage, started_at, execution_id)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (doc_id, from_stage, to_stage, execution_id),
        )
        conn.commit()
        return cursor.lastrowid


def record_timing_end(
    timing_id: int,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Record the completion of a stage transition.

    Args:
        timing_id: ID from record_timing_start
        success: Whether the transition succeeded
        error_message: Optional error message if failed
    """
    with db_connection.get_connection() as conn:
        # Get started_at to calculate duration
        cursor = conn.execute(
            "SELECT started_at FROM cascade_stage_timings WHERE id = ?",
            (timing_id,),
        )
        row = cursor.fetchone()
        if not row:
            return

        started_at = row[0]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        now = datetime.now()
        duration = (now - started_at).total_seconds()

        conn.execute(
            """
            UPDATE cascade_stage_timings
            SET completed_at = CURRENT_TIMESTAMP,
                duration_seconds = ?,
                success = ?,
                error_message = ?
            WHERE id = ?
            """,
            (duration, success, error_message, timing_id),
        )
        conn.commit()


def get_average_timing(from_stage: str, to_stage: str) -> Optional[float]:
    """Get the average timing for a stage transition.

    Args:
        from_stage: Starting stage
        to_stage: Target stage

    Returns:
        Average duration in seconds, or None if no data
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT AVG(duration_seconds)
            FROM cascade_stage_timings
            WHERE from_stage = ? AND to_stage = ?
                AND success = TRUE
                AND duration_seconds IS NOT NULL
            """,
            (from_stage, to_stage),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None


def get_timing_percentile(
    from_stage: str,
    to_stage: str,
    percentile: int = 95,
) -> Optional[float]:
    """Get a percentile timing for a stage transition.

    Args:
        from_stage: Starting stage
        to_stage: Target stage
        percentile: Percentile to calculate (e.g., 95)

    Returns:
        Duration in seconds at the given percentile, or None if no data
    """
    with db_connection.get_connection() as conn:
        # SQLite doesn't have PERCENTILE, so we calculate manually
        cursor = conn.execute(
            """
            SELECT duration_seconds
            FROM cascade_stage_timings
            WHERE from_stage = ? AND to_stage = ?
                AND success = TRUE
                AND duration_seconds IS NOT NULL
            ORDER BY duration_seconds
            """,
            (from_stage, to_stage),
        )
        rows = cursor.fetchall()

        if not rows:
            return None

        durations = [row[0] for row in rows]
        n = len(durations)
        idx = int(n * percentile / 100)
        idx = min(idx, n - 1)  # Clamp to valid index
        return durations[idx]


def get_expected_timing(from_stage: str, to_stage: str) -> float:
    """Get expected timing for a stage transition.

    Uses historical 95th percentile if available, falls back to defaults.

    Args:
        from_stage: Starting stage
        to_stage: Target stage

    Returns:
        Expected duration in seconds
    """
    # Try historical data first
    p95 = get_timing_percentile(from_stage, to_stage, percentile=95)
    if p95 is not None:
        return p95

    # Fall back to defaults
    return DEFAULT_TIMINGS.get((from_stage, to_stage), 120)


def get_all_stage_timing_stats() -> Dict[str, Dict[str, Any]]:
    """Get timing statistics for all stage transitions.

    Returns:
        Dict mapping "from→to" to stats dict with:
        - avg: average duration
        - p95: 95th percentile
        - count: number of successful transitions
        - expected: expected timing (with fallback)
    """
    stats = {}

    for from_stage, to_stage in DEFAULT_TIMINGS.keys():
        key = f"{from_stage}→{to_stage}"

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    AVG(duration_seconds) as avg,
                    COUNT(*) as count
                FROM cascade_stage_timings
                WHERE from_stage = ? AND to_stage = ?
                    AND success = TRUE
                    AND duration_seconds IS NOT NULL
                """,
                (from_stage, to_stage),
            )
            row = cursor.fetchone()
            avg = row[0] if row and row[0] is not None else None
            count = row[1] if row else 0

        p95 = get_timing_percentile(from_stage, to_stage, 95)
        expected = get_expected_timing(from_stage, to_stage)

        stats[key] = {
            "from_stage": from_stage,
            "to_stage": to_stage,
            "avg": avg,
            "p95": p95,
            "count": count,
            "expected": expected,
        }

    return stats


def get_recent_timings(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent timing records.

    Args:
        limit: Max records to return

    Returns:
        List of timing records with all fields
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                id, doc_id, from_stage, to_stage,
                started_at, completed_at, duration_seconds,
                success, error_message, execution_id
            FROM cascade_stage_timings
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "doc_id": row[1],
                "from_stage": row[2],
                "to_stage": row[3],
                "started_at": row[4],
                "completed_at": row[5],
                "duration_seconds": row[6],
                "success": bool(row[7]),
                "error_message": row[8],
                "execution_id": row[9],
            }
            for row in rows
        ]


def get_in_progress_timing(doc_id: int) -> Optional[Dict[str, Any]]:
    """Get any in-progress timing record for a document.

    Args:
        doc_id: Document ID to check

    Returns:
        Timing record dict if in progress, None otherwise
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                id, doc_id, from_stage, to_stage,
                started_at, execution_id
            FROM cascade_stage_timings
            WHERE doc_id = ?
                AND completed_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (doc_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "doc_id": row[1],
            "from_stage": row[2],
            "to_stage": row[3],
            "started_at": row[4],
            "execution_id": row[5],
        }


def get_stuck_documents(stage: str, threshold_multiplier: float = 2.0) -> List[Dict[str, Any]]:
    """Find documents that appear stuck at a stage.

    A document is considered stuck if it's been at a stage longer than
    threshold_multiplier × expected_time for that transition.

    Args:
        stage: Stage to check (e.g., "idea")
        threshold_multiplier: How many times expected time before "stuck"

    Returns:
        List of stuck document info dicts with:
        - doc_id, title, time_at_stage, expected_time, is_stuck
    """
    if stage == "done" or stage not in NEXT_STAGE:
        return []  # Terminal stage, can't be stuck

    next_stage = NEXT_STAGE[stage]
    expected_time = get_expected_timing(stage, next_stage)
    threshold = expected_time * threshold_multiplier

    stuck_docs = []

    with db_connection.get_connection() as conn:
        # Find documents at this stage
        cursor = conn.execute(
            """
            SELECT d.id, d.title, d.created_at, d.updated_at
            FROM documents d
            WHERE d.stage = ?
                AND d.is_deleted = FALSE
            """,
            (stage,),
        )
        rows = cursor.fetchall()

        now = datetime.now()
        for row in rows:
            doc_id = row[0]
            title = row[1]
            created_at = row[2]
            updated_at = row[3]

            # Use updated_at if available, else created_at
            reference_time = updated_at or created_at
            if isinstance(reference_time, str):
                reference_time = datetime.fromisoformat(reference_time)

            time_at_stage = (now - reference_time).total_seconds()
            is_stuck = time_at_stage > threshold

            # Check for failed execution
            exec_cursor = conn.execute(
                """
                SELECT status, error_message
                FROM executions
                WHERE doc_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (doc_id,),
            )
            exec_row = exec_cursor.fetchone()
            has_failed_execution = exec_row and exec_row[0] == "failed"
            error_message = exec_row[1] if exec_row else None

            if is_stuck or has_failed_execution:
                stuck_docs.append({
                    "doc_id": doc_id,
                    "title": title,
                    "stage": stage,
                    "time_at_stage": time_at_stage,
                    "expected_time": expected_time,
                    "threshold": threshold,
                    "is_stuck": is_stuck,
                    "has_failed_execution": has_failed_execution,
                    "error_message": error_message,
                })

    return stuck_docs


def get_processing_status(doc_id: int) -> Optional[Dict[str, Any]]:
    """Get the current processing status for a document.

    Checks both in-progress timings and recent executions.

    Args:
        doc_id: Document ID to check

    Returns:
        Status dict with:
        - is_processing: bool
        - started_at: when processing started
        - elapsed_seconds: how long it's been running
        - from_stage, to_stage: transition info
        - execution_id: linked execution if any
        - execution_status: 'running', 'completed', or 'failed'
    """
    # Check for in-progress timing
    timing = get_in_progress_timing(doc_id)
    if not timing:
        return None

    started_at = timing["started_at"]
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)

    elapsed = (datetime.now() - started_at).total_seconds()

    result = {
        "is_processing": True,
        "started_at": timing["started_at"],
        "elapsed_seconds": elapsed,
        "from_stage": timing["from_stage"],
        "to_stage": timing["to_stage"],
        "timing_id": timing["id"],
        "execution_id": timing.get("execution_id"),
        "execution_status": None,
    }

    # Check execution status if linked
    if timing.get("execution_id"):
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM executions WHERE id = ?",
                (timing["execution_id"],),
            )
            row = cursor.fetchone()
            if row:
                result["execution_status"] = row[0]

    return result
