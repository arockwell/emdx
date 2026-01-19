"""Timeline database queries for Gantt chart visualization.

This module provides query functions for retrieving timeline data
from executions, run_groups, task_registry, and workflow tables.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from .connection import db_connection
from ..models.timeline import CriticalPath, RunGroup, TimelineData, TimelineTask
from ..utils.datetime_utils import parse_timestamp

logger = logging.getLogger(__name__)


def get_timeline_data(
    time_range: str = "24h",
    limit: int = 100,
    status_filter: Optional[List[str]] = None,
    group_id_filter: Optional[int] = None,
) -> TimelineData:
    """Get timeline data for visualization.

    Args:
        time_range: Time range to query ('1h', '24h', '7d', 'all')
        limit: Maximum number of tasks to return
        status_filter: Optional list of statuses to include
        group_id_filter: Optional run group ID to filter by

    Returns:
        TimelineData with groups and tasks
    """
    # Calculate time cutoff
    cutoff = _parse_time_range(time_range)

    # Get run groups (gracefully handle missing table)
    try:
        groups = _get_run_groups(cutoff, status_filter)
    except Exception as e:
        logger.debug(f"Could not get run_groups (table may not exist): {e}")
        groups = []

    # Get tasks for each group
    for group in groups:
        group.tasks = _get_tasks_for_group(group.id, status_filter)

    # Get ungrouped tasks (executions without a run_group_id)
    ungrouped = _get_ungrouped_tasks(cutoff, limit, status_filter)

    # Build timeline data
    all_tasks = ungrouped.copy()
    for group in groups:
        all_tasks.extend(group.tasks)

    # Calculate time bounds
    min_time = None
    max_time = None
    if all_tasks:
        start_times = [t.start_time for t in all_tasks if t.start_time]
        end_times = [t.end_time or datetime.now() for t in all_tasks if t.start_time]
        if start_times:
            min_time = min(start_times)
        if end_times:
            max_time = max(end_times)

    # Count statuses
    running = sum(1 for t in all_tasks if t.status == "running")
    completed = sum(1 for t in all_tasks if t.status == "completed")
    failed = sum(1 for t in all_tasks if t.status == "failed")

    return TimelineData(
        groups=groups,
        ungrouped_tasks=ungrouped,
        min_time=min_time,
        max_time=max_time,
        total_tasks=len(all_tasks),
        running_count=running,
        completed_count=completed,
        failed_count=failed,
    )


def get_run_group_with_tasks(group_id: int) -> Optional[RunGroup]:
    """Get a specific run group with all its tasks.

    Args:
        group_id: ID of the run group

    Returns:
        RunGroup with tasks, or None if not found
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, command_type, status, started_at, completed_at,
                   task_count, completed_count, failed_count
            FROM run_groups
            WHERE id = ?
            """,
            (group_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        group = RunGroup(
            id=row[0],
            name=row[1],
            command_type=row[2],
            status=row[3],
            started_at=parse_timestamp(row[4]),
            completed_at=parse_timestamp(row[5]) if row[5] else None,
            task_count=row[6] or 0,
            completed_count=row[7] or 0,
            failed_count=row[8] or 0,
        )

        group.tasks = _get_tasks_for_group(group_id, None)
        return group


def get_task_dependencies(task_id: int) -> List[int]:
    """Get IDs of tasks that a given task depends on.

    Args:
        task_id: ID of the task

    Returns:
        List of task IDs this task depends on
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT depends_on_task_id
            FROM task_dependencies
            WHERE task_id = ?
            """,
            (task_id,),
        )
        return [row[0] for row in cursor.fetchall()]


def compute_critical_path(group_id: int) -> CriticalPath:
    """Compute the critical path for a run group.

    Uses a topological sort and forward/backward pass to find
    the longest path through the task dependency graph.

    Args:
        group_id: ID of the run group

    Returns:
        CriticalPath with task IDs and total duration
    """
    group = get_run_group_with_tasks(group_id)
    if not group or not group.tasks:
        return CriticalPath()

    # Build adjacency list and get dependencies
    tasks_by_id = {t.id: t for t in group.tasks}
    dependencies = {}
    for task in group.tasks:
        dependencies[task.id] = get_task_dependencies(task.id)

    # Topological sort
    sorted_tasks = _topological_sort(group.tasks, dependencies)
    if not sorted_tasks:
        # No valid ordering (possibly has cycles)
        return CriticalPath()

    # Forward pass: calculate earliest start/finish times
    earliest_start = {}
    earliest_finish = {}
    for task_id in sorted_tasks:
        task = tasks_by_id.get(task_id)
        if not task:
            continue

        deps = dependencies.get(task_id, [])
        if deps:
            # Earliest start is max of all dependencies' earliest finish
            start = max(earliest_finish.get(d, 0) for d in deps)
        else:
            start = 0

        earliest_start[task_id] = start
        earliest_finish[task_id] = start + (task.duration or 0)

    # Find total project duration
    if earliest_finish:
        total_duration = max(earliest_finish.values())
    else:
        total_duration = 0

    # Backward pass: calculate latest start/finish times
    latest_finish = {}
    latest_start = {}
    for task_id in reversed(sorted_tasks):
        task = tasks_by_id.get(task_id)
        if not task:
            continue

        # Find tasks that depend on this one
        dependents = [
            t_id for t_id, deps in dependencies.items() if task_id in deps
        ]

        if dependents:
            finish = min(latest_start.get(d, total_duration) for d in dependents)
        else:
            finish = total_duration

        latest_finish[task_id] = finish
        latest_start[task_id] = finish - (task.duration or 0)

    # Critical path: tasks where slack = 0
    critical_path_ids = []
    bottleneck_id = None
    bottleneck_duration = 0

    for task_id in sorted_tasks:
        slack = latest_start.get(task_id, 0) - earliest_start.get(task_id, 0)
        if abs(slack) < 0.001:  # Essentially zero (floating point tolerance)
            critical_path_ids.append(task_id)
            task = tasks_by_id.get(task_id)
            if task and (task.duration or 0) > bottleneck_duration:
                bottleneck_duration = task.duration or 0
                bottleneck_id = task_id

    return CriticalPath(
        task_ids=critical_path_ids,
        total_duration=total_duration,
        bottleneck_task_id=bottleneck_id,
    )


def create_run_group(
    name: str,
    command_type: str,
    task_count: int = 0,
    working_dir: Optional[str] = None,
    base_branch: Optional[str] = None,
) -> int:
    """Create a new run group.

    Args:
        name: Display name for the group
        command_type: Type of command ('run', 'each', 'workflow', 'cascade')
        task_count: Initial task count
        working_dir: Working directory
        base_branch: Git base branch

    Returns:
        ID of the created run group
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO run_groups (name, command_type, task_count, working_dir, base_branch)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, command_type, task_count, working_dir, base_branch),
        )
        conn.commit()
        return cursor.lastrowid


def update_run_group_status(
    group_id: int,
    status: str,
    completed_count: Optional[int] = None,
    failed_count: Optional[int] = None,
) -> None:
    """Update a run group's status and counts.

    Args:
        group_id: ID of the run group
        status: New status
        completed_count: Updated completed count
        failed_count: Updated failed count
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        updates = ["status = ?"]
        params = [status]

        if status in ("completed", "failed"):
            updates.append("completed_at = CURRENT_TIMESTAMP")

        if completed_count is not None:
            updates.append("completed_count = ?")
            params.append(completed_count)

        if failed_count is not None:
            updates.append("failed_count = ?")
            params.append(failed_count)

        params.append(group_id)

        cursor.execute(
            f"UPDATE run_groups SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()


def link_execution_to_group(execution_id: int, group_id: int) -> None:
    """Link an execution to a run group.

    Args:
        execution_id: ID of the execution
        group_id: ID of the run group
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE executions SET run_group_id = ? WHERE id = ?",
            (group_id, execution_id),
        )
        conn.commit()


# Private helper functions


def _parse_time_range(time_range: str) -> Optional[datetime]:
    """Parse time range string to cutoff datetime."""
    if time_range == "all":
        return None

    now = datetime.now()
    if time_range.endswith("h"):
        hours = int(time_range[:-1])
        return now - timedelta(hours=hours)
    elif time_range.endswith("d"):
        days = int(time_range[:-1])
        return now - timedelta(days=days)
    elif time_range.endswith("m"):
        minutes = int(time_range[:-1])
        return now - timedelta(minutes=minutes)

    # Default to 24 hours
    return now - timedelta(hours=24)


def _get_run_groups(
    cutoff: Optional[datetime],
    status_filter: Optional[List[str]],
) -> List[RunGroup]:
    """Get run groups from database."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT id, name, command_type, status, started_at, completed_at,
                   task_count, completed_count, failed_count
            FROM run_groups
            WHERE 1=1
        """
        params = []

        if cutoff:
            query += " AND started_at >= ?"
            params.append(cutoff.isoformat())

        if status_filter:
            placeholders = ", ".join("?" * len(status_filter))
            query += f" AND status IN ({placeholders})"
            params.extend(status_filter)

        query += " ORDER BY started_at DESC LIMIT 50"

        cursor.execute(query, params)
        groups = []
        for row in cursor.fetchall():
            groups.append(
                RunGroup(
                    id=row[0],
                    name=row[1],
                    command_type=row[2],
                    status=row[3],
                    started_at=parse_timestamp(row[4]),
                    completed_at=parse_timestamp(row[5]) if row[5] else None,
                    task_count=row[6] or 0,
                    completed_count=row[7] or 0,
                    failed_count=row[8] or 0,
                )
            )
        return groups


def _get_tasks_for_group(
    group_id: int,
    status_filter: Optional[List[str]],
) -> List[TimelineTask]:
    """Get tasks belonging to a run group."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT id, doc_title, status, started_at, completed_at, pid
            FROM executions
            WHERE run_group_id = ?
        """
        params = [group_id]

        if status_filter:
            placeholders = ", ".join("?" * len(status_filter))
            query += f" AND status IN ({placeholders})"
            params.extend(status_filter)

        query += " ORDER BY started_at"

        cursor.execute(query, params)
        tasks = []
        for row in cursor.fetchall():
            started = parse_timestamp(row[3]) if row[3] else datetime.now()
            ended = parse_timestamp(row[4]) if row[4] else None

            task = TimelineTask(
                id=row[0],
                name=row[1] or f"Task #{row[0]}",
                status=row[2],
                start_time=started,
                end_time=ended,
                run_group_id=group_id,
                task_type="run",
            )

            # Get dependencies
            task.dependencies = get_task_dependencies(row[0])

            tasks.append(task)

        return tasks


def _get_ungrouped_tasks(
    cutoff: Optional[datetime],
    limit: int,
    status_filter: Optional[List[str]],
) -> List[TimelineTask]:
    """Get tasks not belonging to any group (or all tasks if run_group_id doesn't exist)."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Check if run_group_id column exists
        cursor.execute("PRAGMA table_info(executions)")
        columns = {row[1] for row in cursor.fetchall()}
        has_run_group_id = "run_group_id" in columns

        if has_run_group_id:
            query = """
                SELECT id, doc_title, status, started_at, completed_at, pid
                FROM executions
                WHERE run_group_id IS NULL
            """
        else:
            # Fall back to getting all executions if column doesn't exist
            query = """
                SELECT id, doc_title, status, started_at, completed_at, pid
                FROM executions
                WHERE 1=1
            """
        params = []

        if cutoff:
            query += " AND started_at >= ?"
            params.append(cutoff.isoformat())

        if status_filter:
            placeholders = ", ".join("?" * len(status_filter))
            query += f" AND status IN ({placeholders})"
            params.extend(status_filter)

        query += f" ORDER BY started_at DESC LIMIT {int(limit)}"

        cursor.execute(query, params)
        tasks = []
        for row in cursor.fetchall():
            started = parse_timestamp(row[3]) if row[3] else datetime.now()
            ended = parse_timestamp(row[4]) if row[4] else None

            task = TimelineTask(
                id=row[0],
                name=row[1] or f"Task #{row[0]}",
                status=row[2],
                start_time=started,
                end_time=ended,
                task_type="agent",
            )
            tasks.append(task)

        return tasks


def _topological_sort(
    tasks: List[TimelineTask],
    dependencies: dict,
) -> List[int]:
    """Topological sort of tasks based on dependencies.

    Returns task IDs in order such that dependencies come before
    their dependents. Uses Kahn's algorithm.
    """
    # Calculate in-degree for each task
    in_degree = {t.id: 0 for t in tasks}
    for task_id, deps in dependencies.items():
        if task_id in in_degree:
            in_degree[task_id] = len([d for d in deps if d in in_degree])

    # Start with tasks that have no dependencies
    queue = [t_id for t_id, degree in in_degree.items() if degree == 0]
    result = []

    while queue:
        task_id = queue.pop(0)
        result.append(task_id)

        # Reduce in-degree of tasks that depend on this one
        for other_id, deps in dependencies.items():
            if task_id in deps and other_id in in_degree:
                in_degree[other_id] -= 1
                if in_degree[other_id] == 0:
                    queue.append(other_id)

    # Check for cycles
    if len(result) != len(tasks):
        logger.warning("Dependency graph contains cycles")
        # Return all tasks in original order as fallback
        return [t.id for t in tasks]

    return result
