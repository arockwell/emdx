"""Delegate tasks to Claude agents with inline results.

The single command for all one-shot AI execution in EMDX. Results print to
stdout (so Claude can read them inline) AND persist to emdx (so they're
searchable later).

Single task:
    emdx delegate "analyze the auth module"

Parallel tasks:
    emdx delegate "check auth" "review tests" "scan for XSS"

With synthesis:
    emdx delegate --synthesize "task1" "task2" "task3"

With document context:
    emdx delegate --doc 42 "implement this plan"

With PR creation:
    emdx delegate --pr "fix the auth bug"

Push branch only (no PR):
    emdx delegate --branch "add logging to auth module"

With worktree isolation:
    emdx delegate --worktree "fix X"
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import click
import typer

from ..config.cli_config import (
    CliTool,
    get_model_display_name,
    resolve_model_alias,
    resolve_model_version,
)
from ..config.constants import DELEGATE_EXECUTION_TIMEOUT
from ..database.documents import get_document
from ..utils.git import generate_delegate_branch_name, validate_pr_preconditions

app = typer.Typer(
    name="delegate",
    context_settings={"allow_interspersed_args": False},
)


def _safe_create_task(
    title: str,
    prompt: str | None = None,
    task_type: str = "single",
    status: str = "open",
    source_doc_id: int | None = None,
    parent_task_id: int | None = None,
    seq: int | None = None,
    tags: str | None = None,
    epic_key: str | None = None,
) -> int | None:
    """Create task, never fail delegate.

    Args:
        title: Task title
        prompt: The prompt used for delegate execution
        task_type: Type of task (single, group, epic)
        status: Initial status (open, active, etc.)
        source_doc_id: Source document ID if derived from a doc
        parent_task_id: Parent task ID for subtasks
        seq: Sequence number within parent
        tags: Comma-separated tags
        epic_key: Epic category key for auto-numbering

    Returns:
        Created task ID or None on failure
    """
    try:
        from ..models.tasks import create_task

        return create_task(
            title=title,
            prompt=prompt,
            task_type=task_type,
            status=status,
            source_doc_id=source_doc_id,
            parent_task_id=parent_task_id,
            seq=seq,
            tags=tags,
            epic_key=epic_key,
        )
    except Exception as e:
        sys.stderr.write(f"delegate: task tracking failed: {e}\n")
        return None


def _safe_update_task(
    task_id: int | None,
    *,
    status: str | None = None,
    error: str | None = None,
    execution_id: int | None = None,
    output_doc_id: int | None = None,
) -> None:
    """Update task, never fail delegate.

    Args:
        task_id: Task ID to update (no-op if None)
        status: New status (open, active, done, failed, partial)
        error: Error message (for failed status)
        execution_id: Link to execution record
        output_doc_id: Output document ID
    """
    if task_id is None:
        return
    try:
        from typing import Any

        from ..models.tasks import update_task

        kwargs: dict[str, Any] = {}
        if status is not None:
            kwargs["status"] = status
        if error is not None:
            kwargs["error"] = error
        if execution_id is not None:
            kwargs["execution_id"] = execution_id
        if output_doc_id is not None:
            kwargs["output_doc_id"] = output_doc_id

        if kwargs:
            update_task(task_id, **kwargs)
    except Exception as e:
        sys.stderr.write(f"delegate: failed to update task {task_id}: {e}\n")


def _safe_create_execution(
    doc_title: str,
    working_dir: str | None,
    task_id: int | None,
) -> int | None:
    """Create execution record, never fail delegate."""
    try:
        from ..models.executions import create_execution

        exec_id = create_execution(
            doc_id=None,
            doc_title=doc_title,
            log_file="",
            working_dir=working_dir,
        )
        if task_id is not None:
            from ..models.executions import update_execution

            update_execution(exec_id, task_id=task_id)
        return exec_id
    except Exception as e:
        sys.stderr.write(f"delegate: execution tracking failed: {e}\n")
        return None


def _safe_update_execution_status(
    exec_id: int | None,
    status: str,
    exit_code: int | None = None,
) -> None:
    """Update execution status, never fail delegate."""
    if exec_id is None:
        return
    try:
        from ..models.executions import update_execution_status

        update_execution_status(exec_id, status, exit_code)
    except Exception as e:
        sys.stderr.write(f"delegate: failed to update execution {exec_id}: {e}\n")


def _read_batch_doc_id(batch_path: str) -> int | None:
    """Read the first doc ID from a batch file written by save-output.sh hook."""
    try:
        content = Path(batch_path).read_text().strip()
        if content:
            first_line = content.split("\n")[0].strip()
            if first_line:
                return int(first_line)
    except (ValueError, FileNotFoundError, OSError):
        pass
    return None


def _cleanup_batch_file(batch_path: str) -> None:
    """Remove the batch temp file, never fail."""
    try:
        os.unlink(batch_path)
    except OSError:
        pass


PR_INSTRUCTION_GENERIC = (
    "\n\nAfter saving your output, if you made any code changes, create a pull request:\n"
    "1. Create a new branch with a descriptive name\n"
    "2. Commit your changes with a clear message\n"
    '3. Push and create a PR using: gh pr create --title "..." --body "..."\n'
    "4. Report the PR URL that was created."
)

# Regex to find PR URLs in agent output
_PR_URL_RE = re.compile(r"https://github\.com/[^/]+/[^/]+/pull/\d+")

# Regex to find pushed branch references in agent output
_BRANCH_PUSH_RE = re.compile(r'(?:origin/|pushed to |branch [\'"`])([a-zA-Z0-9_./-]+)')


def _make_pr_instruction(branch_name: str | None = None, draft: bool = False) -> str:
    """Build a structured PR instruction for the agent.

    When branch_name is provided, the instruction tells the agent exactly
    which branch to use. Otherwise falls back to the generic instruction.

    Args:
        branch_name: The branch name to use (if pre-created).
        draft: Whether to create the PR as a draft (default True).
    """
    draft_flag = " --draft" if draft else ""
    if not branch_name:
        # Return modified generic instruction based on draft flag
        return (
            "\n\nAfter saving your output, if you made any code changes, create a pull request:\n"
            "1. Create a new branch with a descriptive name\n"
            "2. Commit your changes with a clear message\n"
            f'3. Push and create a PR using: gh pr create{draft_flag} --title "..." '
            '--body "..."\n'
            "4. Report the PR URL that was created."
        )
    return (
        "\n\nAfter saving your output, if you made any code changes, create a pull request:\n"
        f"1. You are already on branch `{branch_name}` — commit your changes there\n"
        "2. Write a clear commit message summarizing the changes\n"
        f"3. Push: git push -u origin {branch_name}\n"
        f'4. Create the PR: gh pr create{draft_flag} --title "<short title>" '
        '--body "<description of changes>"\n'
        "5. Report the PR URL in your output (e.g. https://github.com/.../pull/123)"
    )


def _make_branch_instruction(branch_name: str | None = None) -> str:
    """Build a push-only instruction for the agent (no PR creation).

    Tells the agent to commit and push to origin, but not open a PR.

    Args:
        branch_name: The branch name to use (if pre-created).
    """
    if not branch_name:
        return (
            "\n\nAfter saving your output, if you made any code changes,"
            " commit and push them:\n"
            "1. Create a new branch with a descriptive name\n"
            "2. Commit your changes with a clear message\n"
            "3. Push: git push -u origin <branch-name>\n"
            "4. Report the branch name that was pushed."
        )
    return (
        "\n\nAfter saving your output, if you made any code changes,"
        " commit and push them:\n"
        f"1. You are already on branch `{branch_name}`"
        " — commit your changes there\n"
        "2. Write a clear commit message summarizing the changes\n"
        f"3. Push: git push -u origin {branch_name}\n"
        f"4. Report the branch name `{branch_name}` in your output."
    )


def _extract_pr_url(text: str | None) -> str | None:
    """Extract a GitHub PR URL from text, if present."""
    if not text:
        return None
    match = _PR_URL_RE.search(text)
    return match.group(0) if match else None


def _validate_pr_and_warn(
    working_dir: str | None,
    base_branch: str = "main",
    quiet: bool = False,
) -> bool:
    """Run PR precondition checks and log warnings. Returns True if OK."""
    info = validate_pr_preconditions(working_dir, base_branch)
    if info.get("error"):
        sys.stderr.write(f"delegate: PR validation error: {info['error']}\n")
        return False

    ok = True
    branch = info["branch_name"]
    if not info["has_commits"]:
        sys.stderr.write(
            f"delegate: WARNING - No commits on branch '{branch}' "
            f"relative to {base_branch}. PR will likely fail.\n"
        )
        ok = False
    if not info["is_pushed"]:
        sys.stderr.write(f"delegate: WARNING - Branch '{branch}' not pushed to origin.\n")
    if info["files_changed"] == 0:
        sys.stderr.write("delegate: WARNING - 0 file changes in PR.\n")
    if ok and not quiet:
        sys.stderr.write(
            f"delegate: PR validation passed: {info['commit_count']} commit(s), "
            f"{info['files_changed']} file(s) changed\n"
        )
    return ok


def _resolve_task(task: str, pr: bool = False) -> str:
    """Resolve a task argument — if it's a numeric doc ID, load the document content.

    When pr=True and the task is a doc ID, adds implementation and PR instructions
    with a branch name derived from the document title.
    """
    try:
        doc_id = int(task)
    except ValueError:
        return task

    doc = get_document(doc_id)
    if not doc:
        sys.stderr.write(f"delegate: document #{doc_id} not found, treating as text\n")
        return task

    title = doc.get("title", f"Document #{doc_id}")
    content = doc.get("content", "")

    if pr:
        branch = generate_delegate_branch_name(title)
        return (
            f"Read and implement the following gameplan:\n\n# {title}\n\n{content}\n\n"
            f"---\n\n"
            f"Implementation instructions:\n"
            f"1. Implement the feature exactly as described in the gameplan above\n"
            f"2. Create a branch named `{branch}`\n"
            f"3. Commit your changes with a clear message\n"
            f'4. Push and create a PR via: gh pr create --title "feat: {title}" --body "..."\n'
            f"5. Use `poetry run emdx` to test your changes\n"
        )

    return f"Execute the following document:\n\n# {title}\n\n{content}"


def _load_doc_context(doc_id: int, prompt: str | None) -> str:
    """Load a document and combine it with an optional prompt.

    If prompt provided: "Document #id (title):\n\n{content}\n\n---\n\nTask: {prompt}"
    If no prompt: "Execute the following document:\n\n# {title}\n\n{content}"
    """
    doc = get_document(doc_id)
    if not doc:
        sys.stderr.write(f"delegate: document #{doc_id} not found\n")
        raise typer.Exit(1) from None

    title = doc.get("title", f"Document #{doc_id}")
    content = doc.get("content", "")

    if prompt:
        return f"Document #{doc_id} ({title}):\n\n{content}\n\n---\n\nTask: {prompt}"
    else:
        return f"Execute the following document:\n\n# {title}\n\n{content}"


def _print_doc_content(doc_id: int) -> None:
    """Print a document's content to stdout."""
    doc = get_document(doc_id)
    if doc:
        sys.stdout.write(doc.get("content", ""))
        sys.stdout.write("\n")


def _cleanup_stale_worktrees(quiet: bool = False) -> None:
    """Remove delegate worktrees older than 1 hour."""
    import time

    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return

    now = time.time()
    one_hour = 3600
    removed = 0

    for line in result.stdout.split("\n"):
        if not line.startswith("worktree "):
            continue
        path = line.removeprefix("worktree ").strip()
        # Only clean up delegate worktrees
        if "emdx-worktree-" not in Path(path).name:
            continue
        # Check age via directory mtime
        try:
            mtime = Path(path).stat().st_mtime
            age = now - mtime
            if age < one_hour:
                continue
            from ..utils.git import cleanup_worktree

            cleanup_worktree(path)
            removed += 1
            if not quiet:
                age_h = age / 3600
                sys.stderr.write(f"delegate: removed stale worktree ({age_h:.1f}h old): {path}\n")
        except (OSError, Exception) as e:
            sys.stderr.write(f"delegate: failed to clean {path}: {e}\n")

    if not quiet:
        sys.stderr.write(f"delegate: cleaned up {removed} stale worktree(s)\n")


def _format_duration(seconds: float | None) -> str:
    """Format seconds into a human-readable duration string like '3m12s'."""
    if seconds is None:
        return "?"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s"


def _format_summary_line(result: "SingleResult") -> str:
    """Format a clean summary line for a completed delegate.

    Example: 'delegate: done task_id:1 doc_id:42 exit:0 duration:3m12s'
    """
    parts = ["delegate:"]

    if result.success:
        parts.append("done")
    else:
        parts.append("FAILED")

    if result.task_id is not None:
        parts.append(f"task_id:{result.task_id}")
    if result.doc_id is not None:
        parts.append(f"doc_id:{result.doc_id}")
    if result.output_doc_id is not None and result.output_doc_id != result.doc_id:
        parts.append(f"output_doc_id:{result.output_doc_id}")
    if result.execution_id is not None:
        parts.append(f"exec_id:{result.execution_id}")
    if result.exit_code is not None:
        parts.append(f"exit:{result.exit_code}")
    if result.duration_seconds is not None:
        parts.append(f"duration:{_format_duration(result.duration_seconds)}")
    if result.pr_url:
        parts.append(f"pr:{result.pr_url}")
    elif result.branch_name:
        parts.append(f"branch:{result.branch_name}")
    if result.error_message:
        parts.append(f"error:{result.error_message[:100]}")

    return " ".join(parts)


@dataclass
class SingleResult:
    """Result from a single delegate execution."""

    doc_id: int | None = None
    task_id: int | None = None
    pr_url: str | None = None
    branch_name: str | None = None
    success: bool = True
    error_message: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    execution_id: int | None = None
    output_doc_id: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-serializable dict."""
        d: dict[str, object] = {
            "task_id": self.task_id,
            "doc_id": self.doc_id,
            "output_doc_id": self.output_doc_id,
            "execution_id": self.execution_id,
            "exit_code": self.exit_code,
            "success": self.success,
            "duration_seconds": (
                round(self.duration_seconds, 2) if self.duration_seconds else None
            ),
            "duration": (
                _format_duration(self.duration_seconds) if self.duration_seconds else None
            ),
        }
        if self.pr_url:
            d["pr_url"] = self.pr_url
        if self.branch_name:
            d["branch_name"] = self.branch_name
        if self.error_message:
            d["error"] = self.error_message
        return d


def _run_single(
    prompt: str,
    tags: list[str],
    title: str | None,
    model: str | None,
    quiet: bool,
    pr: bool = False,
    branch: bool = False,
    pr_branch: str | None = None,
    draft: bool = False,
    working_dir: str | None = None,
    source_doc_id: int | None = None,
    parent_task_id: int | None = None,
    seq: int | None = None,
    epic_key: str | None = None,
    timeout: int | None = None,
    limit: float | None = None,
) -> SingleResult:
    """Run a single task via Claude CLI subprocess. Hooks handle save/tracking."""
    doc_title = title or f"Delegate: {prompt[:60]}"

    # Add model tags: model:opus for filtering, model-ver:claude-opus-4-6 for version
    alias_tag = f"model:{get_model_display_name(model)}"
    ver_tag = f"model-ver:{resolve_model_version(model)}"
    new_tags = list(tags)
    if alias_tag not in new_tags:
        new_tags.append(alias_tag)
    if ver_tag not in new_tags:
        new_tags.append(ver_tag)
    tags = new_tags

    # Create task before execution
    task_id = _safe_create_task(
        title=doc_title,
        prompt=prompt[:500],
        task_type="single",
        status="active",
        source_doc_id=source_doc_id,
        parent_task_id=parent_task_id,
        seq=seq,
        tags=",".join(tags) if tags else None,
        epic_key=epic_key,
    )

    # Always include 'needs-review' tag for triage workflow
    all_tags = list(tags) if tags else []
    if "needs-review" not in all_tags:
        all_tags.append("needs-review")

    # Create execution record
    execution_id = _safe_create_execution(doc_title, working_dir, task_id)

    # Build the full prompt with PR/branch instructions appended
    full_prompt = prompt
    if pr:
        full_prompt += _make_pr_instruction(pr_branch, draft=draft)
    elif branch:
        full_prompt += _make_branch_instruction(pr_branch)

    # Set up batch file for doc ID collection (written by save-output.sh hook)
    batch_fd, batch_path = tempfile.mkstemp(suffix=".ids", prefix="emdx-batch-")
    os.close(batch_fd)

    # Build environment for hooks (strip CLAUDECODE to allow nested sessions)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.update(
        {
            "EMDX_AUTO_SAVE": "1",
            "EMDX_TITLE": doc_title,
            "EMDX_TAGS": ",".join(all_tags),
            "EMDX_BATCH_FILE": batch_path,
        }
    )
    if task_id is not None:
        env["EMDX_TASK_ID"] = str(task_id)
    if execution_id is not None:
        env["EMDX_EXECUTION_ID"] = str(execution_id)
    if source_doc_id is not None:
        env["EMDX_DOC_ID"] = str(source_doc_id)

    # Build claude command: claude --print --model <model>
    resolved_model = resolve_model_alias(model or "opus", CliTool.CLAUDE)
    cmd = ["claude", "--print", "--model", resolved_model]

    # Apply budget limit if specified
    if limit is not None:
        cmd += ["--max-budget-usd", str(limit)]

    # Grant tool permissions so delegates can operate without interactive approval.
    # --print mode can't prompt for permission, so we must pre-authorize tools.
    # Use comma separator — space separator breaks patterns containing spaces
    # like "Bash(gh pr:*)" which gets split into "Bash(gh" + "pr:*)".
    allowed = [
        "Bash(git:*)",
        "Bash(poetry:*)",
        "Bash(ruff:*)",
        "Bash(mypy:*)",
        "Bash(pytest:*)",
        "Bash(emdx:*)",
    ]
    if pr or branch:
        allowed.append("Bash(gh:*)")
    cmd += ["--allowedTools", ",".join(allowed)]

    # Run the subprocess — hooks handle priming, saving, and task tracking
    effective_timeout = timeout if timeout is not None else DELEGATE_EXECUTION_TIMEOUT
    start_time = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=working_dir,
            env=env,
        )
        elapsed = time.monotonic() - start_time
        output = result.stdout
        success = result.returncode == 0
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start_time
        sys.stderr.write(
            f"delegate: FAILED task_id:{task_id} exit:-1 "
            f"duration:{_format_duration(elapsed)} error:timeout\n"
        )
        _safe_update_task(task_id, status="failed", error="timeout")
        _safe_update_execution_status(execution_id, "failed", exit_code=-1)
        _cleanup_batch_file(batch_path)
        return SingleResult(
            task_id=task_id,
            success=False,
            error_message="timeout",
            exit_code=-1,
            duration_seconds=elapsed,
            execution_id=execution_id,
        )
    except Exception as e:
        elapsed = time.monotonic() - start_time
        sys.stderr.write(
            f"delegate: FAILED task_id:{task_id} "
            f"duration:{_format_duration(elapsed)} error:{str(e)[:100]}\n"
        )
        _safe_update_task(task_id, status="failed", error=str(e)[:200])
        _safe_update_execution_status(execution_id, "failed")
        _cleanup_batch_file(batch_path)
        return SingleResult(
            task_id=task_id,
            success=False,
            error_message=str(e),
            duration_seconds=elapsed,
            execution_id=execution_id,
        )

    # Update execution with exit code
    status = "completed" if success else "failed"
    _safe_update_execution_status(execution_id, status, exit_code=result.returncode)

    if not success:
        error_msg = (result.stderr or "")[:200] or f"exit code {result.returncode}"
        sys.stderr.write(
            f"delegate: FAILED task_id:{task_id} exit:{result.returncode} "
            f"duration:{_format_duration(elapsed)} error:{error_msg[:100]}\n"
        )
        _safe_update_task(task_id, status="failed", error=error_msg)
        _cleanup_batch_file(batch_path)
        return SingleResult(
            task_id=task_id,
            success=False,
            error_message=error_msg,
            exit_code=result.returncode,
            duration_seconds=elapsed,
            execution_id=execution_id,
        )

    # Validate PR preconditions if --pr was requested
    if pr and working_dir:
        _validate_pr_and_warn(working_dir, quiet=quiet)

    # Read doc ID from batch file (written by save-output.sh hook)
    doc_id = _read_batch_doc_id(batch_path)
    _cleanup_batch_file(batch_path)

    # Extract PR URL from output
    pr_url = _extract_pr_url(output)
    pushed_branch = pr_branch

    if doc_id:
        _safe_update_task(task_id, status="done", output_doc_id=doc_id)
        # Try to extract PR URL from saved doc content
        if not pr_url:
            doc = get_document(doc_id)
            if doc:
                pr_url = _extract_pr_url(doc.get("content", ""))
        _print_doc_content(doc_id)
    else:
        _safe_update_task(task_id, status="done")
        # Hook didn't save — print captured output directly
        if output:
            sys.stdout.write(output)
            if not output.endswith("\n"):
                sys.stdout.write("\n")

    single_result = SingleResult(
        doc_id=doc_id,
        task_id=task_id,
        pr_url=pr_url,
        branch_name=pushed_branch,
        exit_code=result.returncode,
        duration_seconds=elapsed,
        execution_id=execution_id,
        output_doc_id=doc_id,
    )

    # Print summary line (unless suppressed by quiet or caller)
    if not quiet:
        sys.stderr.write(_format_summary_line(single_result) + "\n")

    return single_result


def _print_pr_summary(
    tasks: list[str],
    results: dict[int, SingleResult],
) -> None:
    """Print a summary table of PRs created by parallel tasks."""
    pr_results = [(i, results[i]) for i in sorted(results) if results[i].pr_url]
    if not pr_results:
        return

    sys.stderr.write(f"\ndelegate: {len(pr_results)} PR(s) created:\n")
    for i, sr in pr_results:
        label = tasks[i][:60] if i < len(tasks) else "?"
        sys.stderr.write(f"  [{i + 1}] {sr.pr_url}  {label}\n")
    sys.stderr.write("\n")


def _print_branch_summary(
    tasks: list[str],
    results: dict[int, SingleResult],
) -> None:
    """Print a summary table of branches pushed by parallel tasks."""
    branch_results = [
        (i, results[i]) for i in sorted(results) if results[i].branch_name and not results[i].pr_url
    ]
    if not branch_results:
        return

    sys.stderr.write(f"\ndelegate: {len(branch_results)} branch(es) pushed:\n")
    for i, sr in branch_results:
        label = tasks[i][:60] if i < len(tasks) else "?"
        sys.stderr.write(f"  [{i + 1}] {sr.branch_name}  {label}\n")
    sys.stderr.write("\n")


@dataclass
class ParallelResult:
    """Result from a parallel delegate execution."""

    parent_task_id: int | None = None
    results: dict[int, SingleResult] = field(default_factory=dict)
    doc_ids: list[int] = field(default_factory=list)
    synthesis_result: SingleResult | None = None
    total_duration_seconds: float | None = None
    succeeded: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-serializable dict."""
        task_results: list[dict[str, object]] = []
        for i in sorted(self.results):
            r = self.results[i]
            rd = r.to_dict()
            rd["index"] = i
            task_results.append(rd)

        d: dict[str, object] = {
            "parent_task_id": self.parent_task_id,
            "task_count": len(self.results),
            "succeeded": self.succeeded,
            "failed": self.failed,
            "doc_ids": self.doc_ids,
            "tasks": task_results,
            "total_duration_seconds": (
                round(self.total_duration_seconds, 2) if self.total_duration_seconds else None
            ),
            "total_duration": (
                _format_duration(self.total_duration_seconds)
                if self.total_duration_seconds
                else None
            ),
        }
        if self.synthesis_result:
            d["synthesis"] = self.synthesis_result.to_dict()
        return d


def _run_parallel(
    tasks: list[str],
    tags: list[str],
    title: str | None,
    jobs: int | None,
    synthesize: bool,
    model: str | None,
    quiet: bool,
    pr: bool = False,
    branch: bool = False,
    draft: bool = False,
    base_branch: str = "main",
    source_doc_id: int | None = None,
    worktree: bool = False,
    epic_key: str | None = None,
    epic_parent_id: int | None = None,
    limit: float | None = None,
) -> ParallelResult:
    """Run multiple tasks in parallel via ThreadPoolExecutor."""
    max_workers = min(jobs or len(tasks), len(tasks), 10)

    # Create parent group task (does NOT get epic numbering)
    flat_tags = ",".join(tags) if tags else None
    parent_task_id = epic_parent_id or _safe_create_task(
        title=title or f"Parallel: {len(tasks)} tasks",
        prompt=" | ".join(t[:60] for t in tasks),
        task_type="group",
        status="active",
        source_doc_id=source_doc_id,
        tags=flat_tags,
    )

    # Pre-generate branch names for --pr/--branch tasks (unified naming)
    branch_names: list[str | None] = [None] * len(tasks)
    if pr or branch:
        for i, task in enumerate(tasks):
            branch_names[i] = generate_delegate_branch_name(task)

    # Results indexed by task position to preserve order
    results: dict[int, SingleResult] = {}

    def run_task(idx: int, task: str) -> tuple[int, SingleResult]:
        task_title = title or f"Delegate: {task[:60]}"
        if len(tasks) > 1:
            task_title = f"{task_title} [{idx + 1}/{len(tasks)}]"

        # Create per-task worktree if requested
        task_worktree_path = None
        if worktree:
            from ..utils.git import create_worktree

            try:
                task_worktree_path, _ = create_worktree(base_branch, task_title=task)
                if not quiet:
                    sys.stderr.write(
                        f"delegate: worktree [{idx + 1}/{len(tasks)}] "
                        f"created at {task_worktree_path}\n"
                    )
            except Exception as e:
                sys.stderr.write(f"delegate: failed to create worktree for task {idx + 1}: {e}\n")
                return idx, SingleResult()

        try:
            result = (
                idx,
                _run_single(
                    prompt=task,
                    tags=tags,
                    title=task_title,
                    model=model,
                    quiet=True,  # suppress per-task metadata in parallel mode
                    pr=pr,
                    branch=branch,
                    pr_branch=branch_names[idx],
                    draft=draft,
                    working_dir=task_worktree_path,
                    parent_task_id=parent_task_id,
                    seq=idx + 1,
                    epic_key=epic_key,
                    limit=limit,
                ),
            )
            return result
        finally:
            # Clean up worktree unless --branch (needs local branch)
            # For --pr: branch is already pushed, worktree no longer needed
            if task_worktree_path and not branch:
                from ..utils.git import cleanup_worktree

                cleanup_worktree(task_worktree_path)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_task, i, task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx, single_result = future.result()
            results[idx] = single_result

    # Collect doc_ids in original task order (filter out None values)
    doc_ids: list[int] = [
        r.doc_id for i in range(len(tasks)) if (r := results.get(i)) and r.doc_id is not None
    ]

    # Collect failed tasks for synthesis context
    failed_tasks: list[tuple[int, str, str | None]] = [
        (i, tasks[i], results[i].error_message)
        for i in range(len(tasks))
        if (r := results.get(i)) and not r.success
    ]

    # Track success/failure counts
    succeeded_count = len(doc_ids)
    failed_count = len(failed_tasks)

    # Calculate total wall-clock duration from individual tasks
    total_duration = (
        sum(r.duration_seconds for r in results.values() if r.duration_seconds is not None) or None
    )

    if not doc_ids:
        # Build result even for all-failures case
        parallel_result = ParallelResult(
            parent_task_id=parent_task_id,
            results=results,
            doc_ids=[],
            total_duration_seconds=total_duration,
            succeeded=0,
            failed=failed_count,
        )
        if not quiet:
            sys.stderr.write(
                f"delegate: FAILED group task_id:{parent_task_id} "
                f"0/{len(tasks)} succeeded "
                f"duration:{_format_duration(total_duration)}\n"
            )
            for i in range(len(tasks)):
                r = results.get(i)
                if r and not r.success:
                    sys.stderr.write(f"  [{i + 1}] FAILED: {r.error_message or 'unknown'}\n")
        _safe_update_task(
            parent_task_id,
            status="failed",
            error="all tasks failed",
        )
        raise typer.Exit(1) from None

    # Print PR/branch summary if any were created
    if pr:
        _print_pr_summary(tasks, results)
    elif branch:
        _print_branch_summary(tasks, results)

    # Update parent task
    synthesis_result_obj: SingleResult | None = None
    if synthesize and (len(doc_ids) > 1 or (len(doc_ids) >= 1 and failed_count > 0)):
        # Run a synthesis task that combines all outputs
        # Include both successful results and note about failed tasks
        combined = []

        # Add successful task results
        for i in range(len(tasks)):
            r = results.get(i)
            if r and r.doc_id is not None:
                doc = get_document(r.doc_id)
                if doc:
                    combined.append(
                        f"## Task {i + 1} (SUCCESS): {tasks[i][:80]}\n\n{doc.get('content', '')}"
                    )

        # Add failed task summaries
        if failed_tasks:
            failed_section = "## Failed Tasks\n\nThe following tasks failed:\n\n"
            for idx, task_prompt, error_msg in failed_tasks:
                error_info = f": {error_msg}" if error_msg else ""
                failed_section += f"- **Task {idx + 1}**: {task_prompt[:80]}{error_info}\n"
            combined.append(failed_section)

        # Build synthesis prompt with failure context
        if failed_tasks:
            synthesis_intro = (
                f"Synthesize the following task results into a unified summary. "
                f"Note: {succeeded_count} of {len(tasks)} tasks succeeded. "
                f"{failed_count} task(s) failed and are noted below. "
                f"Highlight key findings, common themes, and actionable items. "
                f"Also note the impact of the failed tasks on the overall analysis.\n\n"
            )
        else:
            synthesis_intro = (
                "Synthesize the following task results into a unified summary. "
                "Highlight key findings, common themes, and actionable items.\n\n"
            )

        synthesis_prompt = synthesis_intro + "\n\n---\n\n".join(combined)
        synthesis_title = title or "Delegate synthesis"
        synthesis_result_obj = _run_single(
            prompt=synthesis_prompt,
            tags=tags,
            title=f"{synthesis_title} [synthesis]",
            model=model,
            quiet=True,
            parent_task_id=parent_task_id,
        )
        if synthesis_result_obj.doc_id:
            doc_ids.append(synthesis_result_obj.doc_id)
            # _run_single already printed the synthesis content to stdout

        # Set status based on partial failures
        final_status = "partial" if failed_count > 0 else "done"
        error_msg = f"{failed_count}/{len(tasks)} tasks failed" if failed_count > 0 else None
        _safe_update_task(
            parent_task_id,
            status=final_status,
            output_doc_id=synthesis_result_obj.doc_id,
            error=error_msg,
        )
    else:
        # Set status based on partial failures
        final_status = "partial" if failed_count > 0 else "done"
        error_msg = f"{failed_count}/{len(tasks)} tasks failed" if failed_count > 0 else None
        _safe_update_task(parent_task_id, status=final_status, error=error_msg)

        # Print each result separated
        for i, doc_id in enumerate(doc_ids):
            if len(doc_ids) > 1:
                sys.stdout.write(f"\n=== Task {i + 1}: {tasks[i] if i < len(tasks) else '?'} ===\n")
            _print_doc_content(doc_id)

    parallel_result = ParallelResult(
        parent_task_id=parent_task_id,
        results=results,
        doc_ids=doc_ids,
        synthesis_result=synthesis_result_obj,
        total_duration_seconds=total_duration,
        succeeded=succeeded_count,
        failed=failed_count,
    )

    # Print group summary line
    if not quiet:
        fail_info = f" ({failed_count} failed)" if failed_count > 0 else ""
        sys.stderr.write(
            f"delegate: done group task_id:{parent_task_id} "
            f"{succeeded_count}/{len(tasks)} succeeded{fail_info} "
            f"doc_ids:{','.join(str(d) for d in doc_ids)} "
            f"duration:{_format_duration(total_duration)}\n"
        )

    return parallel_result


@app.callback(invoke_without_command=True)
def delegate(
    ctx: typer.Context,
    tasks: list[str] = typer.Argument(
        None,
        help="Task prompt(s) or document IDs. Numeric args load doc content.",
    ),
    tags: list[str] | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Tags to apply to outputs (comma-separated)",
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        "-T",
        help="Title for output document(s)",
    ),
    synthesize: bool = typer.Option(
        False,
        "--synthesize",
        "-s",
        help="Combine parallel outputs with synthesis",
    ),
    jobs: int | None = typer.Option(
        None,
        "-j",
        "--jobs",
        help="Max parallel tasks (default: auto)",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model to use (overrides default)",
    ),
    sonnet: bool = typer.Option(
        False,
        "--sonnet",
        help="Use Sonnet model (shortcut for --model sonnet)",
    ),
    opus: bool = typer.Option(
        False,
        "--opus",
        help="Use Opus model (shortcut for --model opus)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress metadata on stderr (just content on stdout)",
    ),
    doc: int | None = typer.Option(
        None,
        "--doc",
        "-d",
        help="Document ID to use as input context",
    ),
    pr: bool = typer.Option(
        False,
        "--pr",
        help="Instruct agent to create a PR (implies --worktree)",
    ),
    branch: bool = typer.Option(
        False,
        "--branch",
        help="Commit and push to origin branch (implies --worktree, no PR)",
    ),
    draft: bool = typer.Option(
        False,
        "--draft/--no-draft",
        help="Create PR as draft (default: False, use --draft for draft PRs)",
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree",
        "-w",
        help="Run in isolated git worktree",
    ),
    base_branch: str = typer.Option(
        "main",
        "--base-branch",
        "-b",
        help="Base branch for worktree/branch (default: main)",
    ),
    epic: int | None = typer.Option(
        None,
        "--epic",
        "-e",
        help="Epic task ID to add tasks to",
    ),
    cat: str | None = typer.Option(
        None,
        "--cat",
        "-c",
        help="Category key for auto-numbered tasks",
    ),
    cleanup: bool = typer.Option(
        False,
        "--cleanup",
        help="Remove stale delegate worktrees (>1 hour old)",
    ),
    limit: float | None = typer.Option(
        None,
        "--limit",
        "-l",
        help="Max budget in USD per task (passed as --max-budget-usd to claude)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output structured JSON with task_id, doc_id, exit_code, duration",
    ),
) -> None:
    """Delegate tasks to Claude agents with results on stdout.

    The single command for all one-shot AI execution. Results print to stdout
    so the caller can read them inline. Documents are also saved to emdx for
    persistence. Metadata prints to stderr.

    Single task:
        emdx delegate "analyze the auth module for security issues"

    Execute documents by ID:
        emdx delegate 42 43 44

    Parallel tasks (up to 10):
        emdx delegate "check auth" "review tests" "scan for XSS"

    Parallel with synthesis:
        emdx delegate --synthesize "task1" "task2" "task3"

    With document context:
        emdx delegate --doc 42 "implement the plan"

    With PR creation:
        emdx delegate --pr "fix the auth bug"

    Push branch only (no PR):
        emdx delegate --branch "add logging to auth module"

    Push branch from a specific base:
        emdx delegate --branch -b develop "add feature X"

    Implement gameplans by doc ID (auto-branches + PRs):
        emdx delegate --worktree --pr -j 7 6097 6098 6099 6100 6101 6102 6103

    With worktree isolation:
        emdx delegate --worktree --pr "fix X"

    Quiet mode (just content, no metadata):
        emdx delegate -q "do something"

    Structured JSON output:
        emdx delegate --json "analyze code"
    """
    # Route subcommands: typer's invoke_without_command=True with a variadic
    # positional arg swallows subcommand names (e.g. "list") as task arguments.
    # Detect this and re-invoke through click's subcommand machinery.
    # Uses click.Group.get_command() which works on TyperGroup and LazyCommand.
    multi_cmd = ctx.command if isinstance(ctx.command, click.Group) else None
    if tasks and multi_cmd is not None:
        subcmd = multi_cmd.get_command(ctx, tasks[0])
        if subcmd:
            remaining = list(tasks[1:])
            sub_ctx = subcmd.make_context(tasks[0], remaining, parent=ctx)
            with sub_ctx:
                subcmd.invoke(sub_ctx)
            raise typer.Exit(0)

    # Handle --cleanup: remove stale delegate worktrees
    if cleanup is True:
        _cleanup_stale_worktrees(quiet)
        if not tasks:
            return

    # Validate mutually exclusive options
    if pr and branch:
        typer.echo("Error: --pr and --branch are mutually exclusive", err=True)
        raise typer.Exit(1) from None

    # Resolve model shortcut flags (use `is True` to avoid truthy typer.Option objects)
    if sonnet is True and opus is True:
        typer.echo("Error: --sonnet and --opus are mutually exclusive", err=True)
        raise typer.Exit(1) from None
    if sonnet is True:
        if model is not None:
            typer.echo("Error: --sonnet conflicts with --model", err=True)
            raise typer.Exit(1) from None
        model = "sonnet"
    elif opus is True:
        if model is not None:
            typer.echo("Error: --opus conflicts with --model", err=True)
            raise typer.Exit(1) from None
        model = "opus"

    task_list = list(tasks) if tasks else []

    # Guard: detect flags accidentally consumed as task arguments.
    # This can happen if allow_interspersed_args is misconfigured or bypassed.
    known_flags = {
        "--tags",
        "-t",
        "--title",
        "-T",
        "--synthesize",
        "-s",
        "--jobs",
        "-j",
        "--model",
        "-m",
        "--sonnet",
        "--opus",
        "--quiet",
        "-q",
        "--doc",
        "-d",
        "--pr",
        "--branch",
        "--draft",
        "--no-draft",
        "--worktree",
        "-w",
        "--base-branch",
        "-b",
        "--epic",
        "-e",
        "--cat",
        "-c",
        "--cleanup",
        "--json",
    }
    consumed_flags = [t for t in task_list if t in known_flags]
    if consumed_flags:
        sys.stderr.write(
            f"delegate: error: flags {consumed_flags} were parsed as task arguments.\n"
            f"Place all --flags BEFORE the task arguments.\n"
            f"Example: emdx delegate --tags 'x' --title 'y' \"task1\" \"task2\"\n"
        )
        raise typer.Exit(1)

    # 1. Resolve numeric args as doc IDs (e.g. `emdx delegate 42 43 44`)
    #    When --pr is set, doc IDs get implementation + PR instructions with branch names
    task_list = [_resolve_task(t, pr=pr) for t in task_list]

    # 2. Resolve --doc (applies doc context to all tasks)
    if doc:
        if task_list:
            task_list = [_load_doc_context(doc, t) for t in task_list]
        else:
            task_list = [_load_doc_context(doc, None)]

    if not task_list:
        typer.echo("Error: No tasks provided", err=True)
        typer.echo('Usage: emdx delegate "task description"', err=True)
        raise typer.Exit(1) from None

    # Flatten tags
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(","))

    # Resolve --epic and --cat to parent_task_id and epic_key
    epic_parent_id = None
    epic_key = cat.upper() if isinstance(cat, str) else None

    if isinstance(epic, int) and epic:
        from ..models.tasks import get_task as _get_task

        epic_task = _get_task(epic)
        if not epic_task:
            typer.echo(f"Error: Epic #{epic} not found", err=True)
            raise typer.Exit(1)
        epic_parent_id = epic
        if not epic_key and epic_task.get("epic_key"):
            epic_key = epic_task["epic_key"]

    # 3. Setup worktree for single task paths (parallel creates per-task worktrees)
    #    --pr/--branch always imply --worktree for a clean git environment
    use_worktree = worktree or pr or branch
    worktree_path = None
    worktree_branch = None
    if use_worktree and len(task_list) == 1:
        from ..utils.git import create_worktree

        try:
            task_title_for_branch = title or task_list[0][:80] if task_list else None
            worktree_path, worktree_branch = create_worktree(
                base_branch,
                task_title=task_title_for_branch,
            )
            if not quiet:
                sys.stderr.write(f"delegate: worktree created at {worktree_path}\n")
        except Exception as e:
            sys.stderr.write(f"delegate: failed to create worktree: {e}\n")
            raise typer.Exit(1) from None

    # --json implies --quiet for stderr (structured output goes to stdout)
    effective_quiet = quiet or json_output

    try:
        # 4. Route
        if len(task_list) == 1:
            single_result = _run_single(
                prompt=task_list[0],
                tags=flat_tags,
                title=title,
                model=model,
                quiet=effective_quiet,
                pr=pr,
                branch=branch,
                pr_branch=worktree_branch,
                draft=draft,
                working_dir=worktree_path,
                source_doc_id=doc,
                parent_task_id=epic_parent_id,
                epic_key=epic_key,
                limit=limit,
            )
            if json_output:
                sys.stdout.write(json.dumps(single_result.to_dict(), indent=2) + "\n")
            else:
                if single_result.pr_url and not quiet:
                    sys.stderr.write(f"delegate: PR created: {single_result.pr_url}\n")
                elif single_result.branch_name and not quiet:
                    sys.stderr.write(f"delegate: branch pushed: {single_result.branch_name}\n")
            if single_result.doc_id is None:
                raise typer.Exit(1) from None
        else:
            parallel_result = _run_parallel(
                tasks=task_list,
                tags=flat_tags,
                title=title,
                jobs=jobs,
                synthesize=synthesize,
                model=model,
                quiet=effective_quiet,
                pr=pr,
                branch=branch,
                draft=draft,
                base_branch=base_branch,
                source_doc_id=doc,
                worktree=use_worktree,
                epic_key=epic_key,
                epic_parent_id=epic_parent_id,
                limit=limit,
            )
            if json_output:
                sys.stdout.write(json.dumps(parallel_result.to_dict(), indent=2) + "\n")
    finally:
        # Clean up worktree unless --branch (needs local branch)
        # For --pr: branch is already pushed, worktree no longer needed
        if worktree_path and not branch:
            from ..utils.git import cleanup_worktree

            if not quiet:
                sys.stderr.write(f"delegate: cleaning up worktree {worktree_path}\n")
            cleanup_worktree(worktree_path)


# =============================================================================
# Execution management subcommands (formerly `emdx exec`)
# Registered as flat subcommands: `emdx delegate list`, `emdx delegate show`, etc.
# =============================================================================
from .executions import app as _executions_app  # noqa: E402

for _cmd in _executions_app.registered_commands:
    app.registered_commands.append(_cmd)
