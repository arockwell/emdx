"""Timeline data models for Gantt chart visualization.

This module provides dataclasses for representing timeline data
used in the Timeline Browser TUI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TimelineTask:
    """Represents a single task in the timeline.

    Attributes:
        id: Unique task/execution ID
        name: Display name
        status: Current status (running, completed, failed, pending)
        start_time: When the task started
        end_time: When the task ended (None if still running)
        run_group_id: ID of parent run group (if any)
        task_type: Type of task (run, agent, workflow, cascade, each)
        dependencies: List of task IDs this task depends on
    """

    id: int
    name: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    run_group_id: Optional[int] = None
    task_type: str = "agent"
    dependencies: List[int] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        """Calculate duration in seconds."""
        if not self.start_time:
            return None
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.status == "running"

    @property
    def is_completed(self) -> bool:
        """Check if task completed successfully."""
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        """Check if task failed."""
        return self.status == "failed"

    @property
    def status_icon(self) -> str:
        """Get status icon for display."""
        return {
            "running": "⟳",
            "completed": "✓",
            "failed": "✗",
            "pending": "○",
            "queued": "◷",
        }.get(self.status, "?")


@dataclass
class RunGroup:
    """Represents a group of related tasks (from emdx run, each, workflow, etc.).

    Attributes:
        id: Unique group ID
        name: Display name
        command_type: Type of command that created this group
        status: Overall status
        started_at: When the group started
        completed_at: When the group completed
        task_count: Total number of tasks
        completed_count: Number of completed tasks
        failed_count: Number of failed tasks
        tasks: List of tasks in this group
    """

    id: int
    name: str
    command_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    task_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    tasks: List[TimelineTask] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        """Calculate total duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    @property
    def progress(self) -> float:
        """Calculate progress as a percentage."""
        if self.task_count == 0:
            return 0.0
        return (self.completed_count + self.failed_count) / self.task_count * 100


@dataclass
class CriticalPath:
    """Represents the critical path through a task dependency graph.

    The critical path is the longest sequence of dependent tasks,
    which determines the minimum time to complete all tasks.

    Attributes:
        task_ids: List of task IDs on the critical path
        total_duration: Total duration of the critical path in seconds
        bottleneck_task_id: ID of the task that is the biggest bottleneck
    """

    task_ids: List[int] = field(default_factory=list)
    total_duration: float = 0.0
    bottleneck_task_id: Optional[int] = None


@dataclass
class TimelineData:
    """Container for all timeline visualization data.

    Attributes:
        groups: List of run groups with their tasks
        ungrouped_tasks: Tasks not belonging to any group
        min_time: Earliest start time across all tasks
        max_time: Latest end time across all tasks
        total_tasks: Total number of tasks
        running_count: Number of currently running tasks
        completed_count: Number of completed tasks
        failed_count: Number of failed tasks
    """

    groups: List[RunGroup] = field(default_factory=list)
    ungrouped_tasks: List[TimelineTask] = field(default_factory=list)
    min_time: Optional[datetime] = None
    max_time: Optional[datetime] = None
    total_tasks: int = 0
    running_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    @property
    def all_tasks(self) -> List[TimelineTask]:
        """Get all tasks (grouped and ungrouped)."""
        tasks = list(self.ungrouped_tasks)
        for group in self.groups:
            tasks.extend(group.tasks)
        return tasks

    @property
    def time_span(self) -> Optional[float]:
        """Calculate total time span in seconds."""
        if not self.min_time or not self.max_time:
            return None
        return (self.max_time - self.min_time).total_seconds()
