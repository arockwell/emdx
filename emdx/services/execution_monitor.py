"""Monitor and manage execution lifecycle."""

import logging
from datetime import datetime, timezone
from typing import Any

import psutil

from ..database.connection import db_connection
from ..models.executions import (
    Execution,
    get_running_executions,
    get_stale_executions,
    update_execution_status,
)

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

    def check_process_health(self, execution: Execution) -> dict[str, Any]:
        """Check if an execution's process is still healthy.

        Args:
            execution: Execution to check

        Returns:
            Dictionary with health status
        """
        health: dict[str, Any] = {
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

    def cleanup_stuck_executions(self, dry_run: bool = True) -> list[dict[str, Any]]:
        """Find and clean up stuck executions.

        Args:
            dry_run: If True, only report what would be done

        Returns:
            List of actions taken/would be taken
        """
        actions = []

        # Get all running executions
        running = get_running_executions()

        for execution in running:
            health = self.check_process_health(execution)

            # Determine if execution should be marked as failed
            should_fail = False
            fail_reason = None

            if health["is_zombie"]:
                should_fail = True
                fail_reason = "zombie_process"
            elif not health["process_exists"] and execution.pid:
                should_fail = True
                fail_reason = "process_died"
            elif health["is_stale"] and not health["is_running"]:
                should_fail = True
                fail_reason = "stale_execution"

            if should_fail:
                action = {
                    "execution_id": execution.id,
                    "doc_title": execution.doc_title,
                    "action": "mark_failed",
                    "reason": fail_reason,
                    "details": health["reason"],
                }

                if not dry_run:
                    # Mark as failed with appropriate exit code
                    exit_code = {
                        "zombie_process": -2,
                        "process_died": -3,
                        "stale_execution": -4,
                    }.get(fail_reason or "", -1)

                    update_execution_status(execution.id, "failed", exit_code)
                    action["completed"] = True
                else:
                    action["completed"] = False

                actions.append(action)

        # Also check for stale executions using heartbeat
        stale = get_stale_executions(self.stale_timeout)

        for execution in stale:
            # Skip if already processed
            if any(a["execution_id"] == execution.id for a in actions):
                continue

            action = {
                "execution_id": execution.id,
                "doc_title": execution.doc_title,
                "action": "mark_failed",
                "reason": "no_heartbeat",
                "details": f"No heartbeat for {self.stale_timeout / 60} minutes",
            }

            if not dry_run:
                update_execution_status(execution.id, "failed", -5)  # -5 for heartbeat timeout
                action["completed"] = True
            else:
                action["completed"] = False

            actions.append(action)

        return actions

    def get_execution_metrics(self) -> dict[str, Any]:
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

    def kill_zombie_processes(self, dry_run: bool = True) -> list[dict[str, Any]]:
        """Kill zombie execution processes.

        Args:
            dry_run: If True, only report what would be done

        Returns:
            List of actions taken/would be taken
        """
        actions = []
        running = get_running_executions()

        for execution in running:
            if not execution.pid:
                continue

            try:
                proc = psutil.Process(execution.pid)

                # Check if it's a zombie
                if proc.status() == psutil.STATUS_ZOMBIE:
                    action = {
                        "execution_id": execution.id,
                        "pid": execution.pid,
                        "action": "kill_zombie",
                        "doc_title": execution.doc_title,
                    }

                    if not dry_run:
                        try:
                            proc.kill()
                            action["completed"] = True
                        except Exception as e:
                            action["completed"] = False
                            action["error"] = str(e)
                    else:
                        action["completed"] = False

                    actions.append(action)

            except psutil.NoSuchProcess:
                # Process already gone - expected during cleanup
                logger.debug("Process %s already terminated during cleanup", execution.pid)
            except psutil.AccessDenied:
                # Can't access process
                logger.debug("Access denied to process %s during cleanup", execution.pid)

        return actions
