"""Monitor and manage execution lifecycle."""

import logging
from datetime import datetime, timezone

import psutil

from ..database.connection import db_connection
from ..models.executions import (
    Execution,
    get_running_executions,
)
from ..services.types import ExecutionMetrics, ProcessHealthStatus

logger = logging.getLogger(__name__)


class ExecutionMonitor:
    """Monitor and manage execution lifecycle."""

    def __init__(self, stale_timeout_seconds: int = 1800):
        """Initialize execution monitor.

        Args:
            stale_timeout_seconds: Seconds after which execution is considered
                stale (default 30 min)
        """
        self.stale_timeout = stale_timeout_seconds

    def check_process_health(self, execution: Execution) -> ProcessHealthStatus:
        """Check if an execution's process is still healthy.

        Args:
            execution: Execution to check

        Returns:
            Dictionary with health status
        """
        health: ProcessHealthStatus = {
            "execution_id": execution.id,
            "is_zombie": False,
            "is_running": False,
            "process_exists": False,
            "is_stale": False,
            "reason": None,
        }

        # Check if process exists
        if execution.pid:
            try:
                proc = psutil.Process(execution.pid)
                health["process_exists"] = True
                health["is_running"] = proc.is_running()

                # Check if zombie
                if proc.status() == psutil.STATUS_ZOMBIE:
                    health["is_zombie"] = True
                    health["reason"] = "Process is zombie"

            except psutil.NoSuchProcess:
                logger.debug("Process %s not found for execution %s", execution.pid, execution.id)
                health["process_exists"] = False
                health["reason"] = "Process not found"
            except psutil.AccessDenied:
                logger.debug(
                    "Access denied to process %s for execution %s", execution.pid, execution.id
                )  # noqa: E501
                health["process_exists"] = True  # Assume it exists if we can't access
                health["reason"] = "Access denied to process"
        else:
            health["reason"] = "No PID recorded"

        # Check staleness
        age = (datetime.now(timezone.utc) - execution.started_at).total_seconds()
        if age > self.stale_timeout:
            health["is_stale"] = True
            if not health["reason"]:
                health["reason"] = f"Running for {int(age / 60)} minutes"

        return health

    def get_execution_metrics(self) -> ExecutionMetrics:
        """Get metrics about executions.

        Returns:
            Dictionary with execution metrics
        """
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()

            # Total executions by status
            cursor.execute("""
                SELECT status, COUNT(*)
                FROM executions
                GROUP BY status
            """)
            status_counts = dict(cursor.fetchall())

            # Recent executions (last 24h)
            cursor.execute("""
                SELECT status, COUNT(*)
                FROM executions
                WHERE started_at > datetime('now', '-1 day')
                GROUP BY status
            """)
            recent_counts = dict(cursor.fetchall())

            # Average execution time
            cursor.execute("""
                SELECT AVG(
                    CAST((julianday(completed_at) - julianday(started_at)) * 24 * 60 AS REAL)
                )
                FROM executions
                WHERE status = 'completed'
                AND completed_at IS NOT NULL
            """)
            avg_duration = cursor.fetchone()[0] or 0

            # Failure rate
            total = sum(status_counts.values())
            failed = status_counts.get("failed", 0)
            failure_rate = (failed / total * 100) if total > 0 else 0

            # Check current health
            running = get_running_executions()
            health_checks = [self.check_process_health(e) for e in running]
            unhealthy = sum(1 for h in health_checks if h["is_zombie"] or not h["process_exists"])

            return {
                "total_executions": total,
                "status_breakdown": status_counts,
                "recent_24h": recent_counts,
                "currently_running": len(running),
                "unhealthy_running": unhealthy,
                "average_duration_minutes": round(avg_duration, 2),
                "failure_rate_percent": round(failure_rate, 2),
                "metrics_timestamp": datetime.now(timezone.utc).isoformat(),
            }
