"""Task Registry - Tracks running tasks across all execution systems.

This module provides a central registry for tracking running tasks
from emdx run, agent, each, workflow, and cascade commands.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RunningTask:
    """Represents a currently running task.

    Attributes:
        id: Unique task ID (usually execution_id)
        task_type: Type of task (agent, workflow, cascade, run, each)
        name: Display name/title
        status: Current status
        started_at: When the task started
        pid: Process ID (if available)
        tokens_used: Tokens consumed so far
        cost: Estimated cost so far
        doc_id: Associated document ID
        group_id: Run group ID (for grouped tasks)
        log_file: Path to log file
    """

    id: int
    task_type: str
    name: str
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    pid: Optional[int] = None
    tokens_used: int = 0
    cost: float = 0.0
    doc_id: Optional[int] = None
    group_id: Optional[int] = None
    log_file: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return (datetime.now() - self.started_at).total_seconds()


class TaskRegistry:
    """Thread-safe registry for tracking running tasks.

    Provides a central place to register, update, and query running tasks
    from all execution systems (agent, workflow, cascade, run, each).

    Usage:
        registry = get_task_registry()

        # Register a new task
        registry.register(RunningTask(
            id=123,
            task_type="agent",
            name="Analyze auth module"
        ))

        # Update task status
        registry.update(123, tokens_used=5000, cost=0.05)

        # Get all running tasks
        tasks = registry.get_all()

        # Unregister when done
        registry.unregister(123)
    """

    _instance: Optional["TaskRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._tasks: Dict[int, RunningTask] = {}
        self._task_lock = threading.Lock()
        self._initialized = True

    def register(self, task: RunningTask) -> None:
        """Register a new running task.

        Args:
            task: The task to register
        """
        with self._task_lock:
            self._tasks[task.id] = task
            logger.debug(f"Registered task {task.id}: {task.name}")

    def unregister(self, task_id: int) -> Optional[RunningTask]:
        """Unregister a task when it completes.

        Args:
            task_id: ID of the task to unregister

        Returns:
            The unregistered task, or None if not found
        """
        with self._task_lock:
            task = self._tasks.pop(task_id, None)
            if task:
                logger.debug(f"Unregistered task {task_id}: {task.name}")
            return task

    def update(self, task_id: int, **kwargs) -> None:
        """Update a task's attributes.

        Args:
            task_id: ID of the task to update
            **kwargs: Attributes to update (tokens_used, cost, status, etc.)
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                for key, value in kwargs.items():
                    if hasattr(task, key):
                        setattr(task, key, value)

    def get(self, task_id: int) -> Optional[RunningTask]:
        """Get a task by ID.

        Args:
            task_id: ID of the task

        Returns:
            The task, or None if not found
        """
        with self._task_lock:
            return self._tasks.get(task_id)

    def get_all(self) -> List[RunningTask]:
        """Get all running tasks.

        Returns:
            List of all running tasks, sorted by start time (newest first)
        """
        with self._task_lock:
            tasks = list(self._tasks.values())
        return sorted(tasks, key=lambda t: t.started_at, reverse=True)

    def get_by_type(self, task_type: str) -> List[RunningTask]:
        """Get all tasks of a specific type.

        Args:
            task_type: Type of tasks to get (agent, workflow, cascade, etc.)

        Returns:
            List of matching tasks
        """
        with self._task_lock:
            return [t for t in self._tasks.values() if t.task_type == task_type]

    def get_count(self) -> int:
        """Get the number of running tasks.

        Returns:
            Number of running tasks
        """
        with self._task_lock:
            return len(self._tasks)

    def get_total_tokens(self) -> int:
        """Get total tokens used across all running tasks.

        Returns:
            Total tokens used
        """
        with self._task_lock:
            return sum(t.tokens_used for t in self._tasks.values())

    def get_total_cost(self) -> float:
        """Get total cost across all running tasks.

        Returns:
            Total cost in dollars
        """
        with self._task_lock:
            return sum(t.cost for t in self._tasks.values())

    def clear(self) -> None:
        """Clear all tasks (for testing)."""
        with self._task_lock:
            self._tasks.clear()


# Module-level singleton accessor
_registry: Optional[TaskRegistry] = None


def get_task_registry() -> TaskRegistry:
    """Get the global task registry instance.

    Returns:
        The TaskRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry
