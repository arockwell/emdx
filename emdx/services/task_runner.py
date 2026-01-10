"""Task runner - spawns Claude for tasks.

Supports two execution modes:
- Direct: Simple one-shot Claude execution
- Workflow: Multi-stage execution via workflow system
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from emdx.models import tasks
from emdx.models.documents import get_document
from emdx.models.executions import create_execution
from emdx.models.task_executions import create_task_execution, complete_task_execution
from emdx.services.claude_executor import execute_with_claude_detached


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
    workflow_name: Optional[str] = None,
    variables: Optional[dict] = None,
    background: bool = True,
) -> int:
    """Run task with Claude or workflow. Returns task_execution ID.

    Args:
        task_id: Task to execute
        workflow_name: If provided, run via workflow system instead of direct execution
        variables: Additional variables to pass to workflow (merged with task info)
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

    if workflow_name:
        # Execute via workflow system
        return _run_task_with_workflow(task_id, task, workflow_name, variables)
    else:
        # Direct execution
        return _run_task_direct(task_id, task)


def _run_task_direct(task_id: int, task: dict) -> int:
    """Run task via direct Claude execution."""
    # Setup log file
    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"task-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"

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
    execute_with_claude_detached(
        task=prompt,
        execution_id=exec_id,
        log_file=log_file,
        allowed_tools=None,
        working_dir=str(Path.cwd()),
        doc_id=str(task['gameplan_id']) if task['gameplan_id'] else None,
        context=None,
    )

    return task_exec_id


def _create_task_worktree(task_id: int, task: dict) -> tuple[str, str]:
    """Create an isolated worktree for task execution.

    Returns:
        Tuple of (worktree_path, branch_name)
    """
    from emdx.utils.git_ops import create_worktree, get_repository_root

    # Generate branch name from task
    fix_type = task.get('title', '').lower()
    # Sanitize for git branch name
    fix_type = fix_type.replace(' ', '-').replace('/', '-')[:30]
    branch_name = f"task-{task_id}-{fix_type}"

    # Create worktree in ~/dev/worktrees/
    repo_root = get_repository_root()
    if not repo_root:
        raise ValueError("Not in a git repository")

    repo_name = Path(repo_root).name
    worktree_base = Path.home() / "dev" / "worktrees"
    worktree_path = worktree_base / f"{repo_name}-{branch_name}"

    success, path, error = create_worktree(
        branch_name=branch_name,
        path=str(worktree_path),
        base_branch="main",  # Always branch from main for clean slate
        repo_path=repo_root,
    )

    if not success:
        raise ValueError(f"Failed to create worktree: {error}")

    return path, branch_name


def _run_task_with_workflow(task_id: int, task: dict, workflow_name: str, variables: Optional[dict] = None) -> int:
    """Run task via workflow system in an isolated worktree using a subprocess."""
    import json
    import subprocess

    # Create isolated worktree for this task
    try:
        worktree_path, branch_name = _create_task_worktree(task_id, task)
        tasks.log_progress(task_id, f"Created worktree: {worktree_path} (branch: {branch_name})")
    except ValueError as e:
        # Fall back to current directory if worktree creation fails
        worktree_path = str(Path.cwd())
        branch_name = None
        tasks.log_progress(task_id, f"Warning: Could not create worktree ({e}), using current directory")

    # Create task_execution record first (will be linked to workflow_run)
    task_exec_id = create_task_execution(
        task_id=task_id,
        execution_type='workflow',
        notes=f"Workflow: {workflow_name}, worktree: {worktree_path}",
    )

    tasks.log_progress(task_id, f"Starting workflow '{workflow_name}' (task_exec #{task_exec_id})")

    # Merge task info with user-provided variables
    merged_variables = {
        'task_id': task_id,
        'task_title': task['title'],
        'task_description': task.get('description', ''),
    }
    if variables:
        merged_variables.update(variables)

    # Build the workflow runner script
    runner_script = f'''
import asyncio
import json

from emdx.workflows.executor import workflow_executor
from emdx.models import tasks
from emdx.models.task_executions import complete_task_execution, update_task_execution

async def run():
    try:
        workflow_run = await workflow_executor.execute_workflow(
            workflow_name_or_id="{workflow_name}",
            input_doc_id={task['gameplan_id'] or 'None'},
            task_id={task_id},
            input_variables={json.dumps(merged_variables)},
            working_dir="{worktree_path}",
        )

        update_task_execution(
            {task_exec_id},
            notes=f"Workflow: {workflow_name}, run #{{workflow_run.id}}",
        )

        if workflow_run.status == "completed":
            complete_task_execution({task_exec_id}, success=True)
            tasks.update_task({task_id}, status="done")
            tasks.log_progress({task_id}, "Workflow completed successfully")
        else:
            complete_task_execution({task_exec_id}, success=False)
            tasks.update_task({task_id}, status="blocked")
            tasks.log_progress({task_id}, f"Workflow failed: {{workflow_run.error_message}}")

    except Exception as e:
        complete_task_execution({task_exec_id}, success=False)
        tasks.update_task({task_id}, status="blocked")
        tasks.log_progress({task_id}, f"Workflow error: {{e}}")
        raise

asyncio.run(run())
'''

    # Setup log file
    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"task-workflow-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"

    # Launch as detached subprocess using poetry to ensure correct environment
    # Use the emdx project directory (where pyproject.toml lives)
    emdx_project_dir = Path(__file__).parent.parent.parent

    with open(log_file, 'w') as f:
        subprocess.Popen(
            ['poetry', 'run', 'python', '-c', runner_script],
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # Detach from parent process
            cwd=str(emdx_project_dir),  # Run from project dir for poetry
            env={**dict(__import__('os').environ), 'PYTHONUNBUFFERED': '1'},
        )

    tasks.log_progress(task_id, f"Workflow subprocess started, log: {log_file}")

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
