"""Task runner - spawns Claude for tasks."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from emdx.models import tasks
from emdx.models.documents import get_document
from emdx.models.executions import create_execution
from emdx.commands.claude_execute import execute_with_claude_detached


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


def run_task(task_id: int, background: bool = True) -> int:
    """Run task with Claude. Returns execution ID."""
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

    # Setup log file
    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"task-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"

    prompt = build_task_prompt(task_id)

    # Create execution record
    # create_execution(doc_id: int, doc_title: str, log_file: str, working_dir, pid)
    exec_id = create_execution(
        doc_id=task['gameplan_id'] or 0,
        doc_title=f"Task #{task_id}: {task['title']}",
        log_file=str(log_file),
        working_dir=str(Path.cwd()),
    )

    # Update task
    tasks.update_task(task_id, status='active')
    tasks.log_progress(task_id, f"Started execution #{exec_id}")

    # Run Claude
    # execute_with_claude_detached(task, execution_id, log_file: Path, ...)
    execute_with_claude_detached(
        task=prompt,
        execution_id=exec_id,
        log_file=log_file,  # Path object
        allowed_tools=None,
        working_dir=str(Path.cwd()),
        doc_id=str(task['gameplan_id']) if task['gameplan_id'] else None,
        context=None,
    )

    return exec_id
