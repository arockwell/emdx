"""Task resolution for workflow execution.

Tasks can be strings (used as-is) or document IDs (content loaded from DB).
"""

from dataclasses import dataclass
from typing import Union

from emdx.models.documents import get_document


@dataclass
class TaskContext:
    """Resolved task context for prompt substitution."""

    content: str
    title: str
    id: int | None


def resolve_task(task: Union[str, int]) -> TaskContext:
    """Resolve a task to its content.

    Args:
        task: Either a string (used directly) or doc ID (loads content)

    Returns:
        TaskContext with content, title, and optional ID
    """
    if isinstance(task, int):
        doc = get_document(task)
        if doc is None:
            raise ValueError(f"Document {task} not found")
        return TaskContext(
            content=doc.get("content", ""),
            title=doc.get("title", ""),
            id=task,
        )
    return TaskContext(content=str(task), title="", id=None)


def resolve_tasks(tasks: list[Union[str, int]]) -> list[TaskContext]:
    """Resolve a list of tasks.

    Args:
        tasks: List of strings or doc IDs

    Returns:
        List of resolved TaskContext objects
    """
    return [resolve_task(t) for t in tasks]
