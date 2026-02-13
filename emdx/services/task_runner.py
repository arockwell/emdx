"""Task runner - spawns Claude for tasks via direct execution."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from emdx.config.constants import EMDX_LOG_DIR
from emdx.models import tasks
from emdx.models.documents import get_document
from emdx.models.executions import create_execution
from emdx.models.task_executions import create_task_execution, complete_task_execution
from emdx.services.claude_executor import execute_claude_detached
from emdx.utils.environment import get_subprocess_env


def build_task_prompt(task_id: int) -> str:
    """Build prompt for task execution."""
    task = tasks.get_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    lines = [f"# Task #{task['id']}: {task['title']}", ""]

    # Gameplan context
    if task['gameplan_id']:
        doc = get_document(str(task['gameplan_id']))
        if doc:
            content = doc['content']
            if len(content) > 2000:
                content = content[:2000] + "\n\n[... truncated ...]"
            lines.extend(["## Context from Gameplan", content, ""])

    if task['description']:
        lines.extend(["## Description", task['description'], ""])

    if task['current_step']:
        lines.extend(["## Resume from", f"> {task['current_step']}", ""])

    # Dependencies
    deps = tasks.get_dependencies(task_id)
    if deps:
        lines.append("## Dependencies")
        for d in deps:
            icon = '✓' if d['status'] == 'done' else '○'
            lines.append(f"- {icon} #{d['id']} {d['title']}")
        lines.append("")

    # Instructions
    lines.extend([
        "## Instructions",
        "1. Complete the task described above",
        f"2. Log progress: emdx task log {task_id} \"message\"",
        f"3. When done: emdx task update {task_id} -s done -n \"summary\"",
        f"4. If blocked: emdx task update {task_id} -s blocked -n \"reason\"",
    ])

    return "\n".join(lines)


def run_task(
    task_id: int,
    background: bool = True,
) -> int:
    """Run task with Claude. Returns task_execution ID.

    Args:
        task_id: Task to execute
        background: Run in background (always True for now)

    Returns:
        task_execution_id: ID in task_executions table
    """
    task = tasks.get_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if task['status'] not in ('open', 'blocked'):
        raise ValueError(f"Task status is '{task['status']}', expected 'open' or 'blocked'")

    # Check deps
    deps = tasks.get_dependencies(task_id)
    unsatisfied = [d for d in deps if d['status'] != 'done']
    if unsatisfied:
        raise ValueError(f"Unsatisfied deps: {[d['id'] for d in unsatisfied]}")

    # Update task status
    tasks.update_task(task_id, status='active')

    return _run_task_direct(task_id, task)


def _run_task_direct(task_id: int, task: dict) -> int:
    """Run task via direct Claude execution."""
    # Setup log file
    EMDX_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = EMDX_LOG_DIR / f"task-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"

    prompt = build_task_prompt(task_id)

    # Create execution record
    exec_id = create_execution(
        doc_id=task['gameplan_id'] or 0,
        doc_title=f"Task #{task_id}: {task['title']}",
        log_file=str(log_file),
        working_dir=str(Path.cwd()),
    )

    # Create task_execution record (the join)
    task_exec_id = create_task_execution(
        task_id=task_id,
        execution_type='direct',
        execution_id=exec_id,
        notes=f"Direct execution via Claude",
    )

    tasks.log_progress(task_id, f"Started direct execution #{exec_id} (task_exec #{task_exec_id})")

    # Run Claude
    execute_claude_detached(
        task=prompt,
        execution_id=exec_id,
        log_file=log_file,
        allowed_tools=None,
        working_dir=str(Path.cwd()),
        doc_id=str(task['gameplan_id']) if task['gameplan_id'] else None,
    )

    return task_exec_id


def mark_task_manual(task_id: int, notes: Optional[str] = None) -> int:
    """Mark a task as manually completed. Returns task_execution ID."""
    task = tasks.get_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    # Create task_execution record for manual completion
    task_exec_id = create_task_execution(
        task_id=task_id,
        execution_type='manual',
        notes=notes or "Manually completed",
    )

    # Mark as completed immediately
    complete_task_execution(task_exec_id, success=True)
    tasks.update_task(task_id, status='done')
    tasks.log_progress(task_id, f"Marked as manually completed")

    return task_exec_id
