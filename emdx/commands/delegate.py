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

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import typer

from ..config.cli_config import resolve_model_for_tag
from ..config.constants import DELEGATE_EXECUTION_TIMEOUT
from ..database.documents import get_document, save_document
from ..services.unified_executor import ExecutionConfig, UnifiedExecutor
from ..utils.git import generate_delegate_branch_name, validate_pr_preconditions

app = typer.Typer(
    name="delegate",
    help="Delegate tasks to agents (stdout-friendly)",
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


def _safe_update_execution(
    exec_id: int | None,
    *,
    doc_id: int | None = None,
) -> None:
    """Update execution record, never fail delegate.

    Args:
        exec_id: Execution ID to update (no-op if None)
        doc_id: Output document ID to link
    """
    if exec_id is None:
        return
    try:
        from typing import Any

        from ..models.executions import update_execution

        kwargs: dict[str, Any] = {}
        if doc_id is not None:
            kwargs["doc_id"] = doc_id

        if kwargs:
            update_execution(exec_id, **kwargs)
    except Exception as e:
        sys.stderr.write(f"delegate: failed to update execution {exec_id}: {e}\n")


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


def _make_output_file_id(working_dir: str | None, seq: int | None) -> str:
    """Generate a traceable ID for the agent's output file.

    Uses the worktree basename when available (so the file can be traced
    back to its worktree), otherwise falls back to pid-seq-timestamp.
    """
    if working_dir:
        basename = Path(working_dir).name
        if "emdx-worktree-" in basename:
            return basename
    return f"{os.getpid()}-{seq or 0}-{int(time.time())}"


def _make_output_file_path(file_id: str) -> Path:
    """Build the /tmp path for a delegate output file."""
    return Path(f"/tmp/emdx-delegate-{file_id}.md")


def _save_output_fallback(
    output_file: Path,
    output_content: str | None,
    title: str,
    tags: list[str],
) -> int | None:
    """Try to save agent output via fallback methods.

    Priority:
    1. Read the output file the agent was asked to write
    2. Save captured stdout/result content
    Returns doc_id or None.
    """
    content = None

    # Fallback 1: agent wrote the file
    if output_file.exists() and output_file.stat().st_size > 0:
        try:
            content = output_file.read_text(encoding="utf-8")
        except Exception as e:
            sys.stderr.write(f"delegate: failed to read {output_file}: {e}\n")

    # Fallback 2: captured output from executor
    if not content and output_content and output_content.strip():
        content = output_content

    if not content:
        return None

    try:
        doc_id: int = save_document(title=title, content=content, tags=tags)
        return doc_id
    except Exception as e:
        sys.stderr.write(f"delegate: fallback save failed: {e}\n")
        return None


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


@dataclass
class SingleResult:
    """Result from a single delegate execution."""

    doc_id: int | None = None
    task_id: int | None = None
    pr_url: str | None = None
    branch_name: str | None = None
    success: bool = True
    error_message: str | None = None


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
) -> SingleResult:
    """Run a single task via UnifiedExecutor. Returns SingleResult."""
    doc_title = title or f"Delegate: {prompt[:60]}"

    # Resolve model and add tag with alias + version (e.g. model:opus/claude-opus-4-6)
    model_tag = f"model:{resolve_model_for_tag(model)}"
    if model_tag not in tags:
        tags = [*tags, model_tag]

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

    # Build save instruction so the sub-agent persists output
    # Always include 'needs-review' tag for triage workflow
    all_tags = list(tags) if tags else []
    if "needs-review" not in all_tags:
        all_tags.append("needs-review")

    # Generate a traceable output file path for the agent
    file_id = _make_output_file_id(working_dir, seq)
    output_file = _make_output_file_path(file_id)
    tags_str = ",".join(all_tags)

    output_instruction = (
        "\n\nIMPORTANT — SAVE YOUR OUTPUT:\n"
        f"1. Write your complete findings/analysis to: {output_file}\n"
        f'2. Save it: emdx save {output_file} --title "{doc_title}" '
        f'--tags "{tags_str}"\n'
        "3. Report the document ID shown after saving."
    )

    if pr:
        output_instruction += _make_pr_instruction(pr_branch, draft=draft)
    elif branch:
        output_instruction += _make_branch_instruction(pr_branch)

    config = ExecutionConfig(
        prompt=prompt,
        title=doc_title,
        output_instruction=output_instruction,
        working_dir=working_dir or str(Path.cwd()),
        timeout_seconds=timeout if timeout is not None else DELEGATE_EXECUTION_TIMEOUT,
        model=model,
    )

    result = UnifiedExecutor().execute(config)

    # Link execution to task
    _safe_update_task(task_id, execution_id=result.execution_id)

    if not result.success:
        sys.stderr.write(f"delegate: task failed: {result.error_message}\n")
        _safe_update_task(task_id, status="failed", error=result.error_message)
        return SingleResult(task_id=task_id, success=False, error_message=result.error_message)

    # Validate PR preconditions if --pr was requested
    if pr and working_dir:
        _validate_pr_and_warn(working_dir, quiet=quiet)

    # Extract PR URL from output content
    pr_url = _extract_pr_url(result.output_content)
    # Track branch name (known from pr_branch, or extracted from output)
    pushed_branch = pr_branch

    doc_id = result.output_doc_id

    # Fallback: if agent didn't save, try output file then captured output
    if not doc_id:
        doc_id = _save_output_fallback(
            output_file,
            result.output_content,
            doc_title,
            all_tags,
        )
        if doc_id:
            sys.stderr.write(f"delegate: auto-saved from fallback → #{doc_id}\n")

    if doc_id:
        _safe_update_task(task_id, status="done", output_doc_id=doc_id)
        _safe_update_execution(result.execution_id, doc_id=doc_id)
        # Try to extract PR URL from saved doc content
        if not pr_url:
            doc = get_document(doc_id)
            if doc:
                pr_url = _extract_pr_url(doc.get("content", ""))
        _print_doc_content(doc_id)
        if not quiet:
            pr_info = f" pr:{pr_url}" if pr_url else ""
            branch_info = f" branch:{pushed_branch}" if pushed_branch and not pr_url else ""
            sys.stderr.write(
                f"task_id:{task_id} doc_id:{doc_id} "
                f"tokens:{result.tokens_used} "
                f"cost:${result.cost_usd:.4f} "
                f"duration:{result.execution_time_ms / 1000:.1f}s"
                f"{pr_info}{branch_info}\n"
            )
    else:
        _safe_update_task(task_id, status="done")
        # Last resort: print whatever we have to stdout
        if result.output_content:
            sys.stdout.write(result.output_content)
            sys.stdout.write("\n")
        sys.stderr.write("delegate: agent completed with no output\n")

    return SingleResult(
        doc_id=doc_id,
        task_id=task_id,
        pr_url=pr_url,
        branch_name=pushed_branch,
    )


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
) -> list[int]:
    """Run multiple tasks in parallel via ThreadPoolExecutor. Returns doc_ids."""
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

    if not doc_ids:
        sys.stderr.write(
            f"delegate: parallel run completed but all {failed_count} task(s) failed\n"
        )
        _safe_update_task(
            parent_task_id,
            status="failed",
            error="all tasks failed",
        )
        raise typer.Exit(1) from None

    # Log partial failures
    if failed_count > 0:
        sys.stderr.write(
            f"delegate: {succeeded_count}/{len(tasks)} task(s) succeeded, {failed_count} failed\n"
        )

    # Print PR/branch summary if any were created
    if pr:
        _print_pr_summary(tasks, results)
    elif branch:
        _print_branch_summary(tasks, results)

    # Update parent task
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
        synthesis_result = _run_single(
            prompt=synthesis_prompt,
            tags=tags,
            title=f"{synthesis_title} [synthesis]",
            model=model,
            quiet=True,
            parent_task_id=parent_task_id,
        )
        if synthesis_result.doc_id:
            doc_ids.append(synthesis_result.doc_id)
            # _run_single already printed the synthesis content to stdout

        # Set status based on partial failures
        final_status = "partial" if failed_count > 0 else "done"
        error_msg = f"{failed_count}/{len(tasks)} tasks failed" if failed_count > 0 else None
        _safe_update_task(
            parent_task_id,
            status=final_status,
            output_doc_id=synthesis_result.doc_id,
            error=error_msg,
        )
        if not quiet:
            status_suffix = f" ({failed_count} failed)" if failed_count > 0 else ""
            sys.stderr.write(
                f"task_id:{parent_task_id} "
                f"doc_ids:{','.join(str(d) for d in doc_ids)} "
                f"synthesis_id:{synthesis_result.doc_id or 'none'}{status_suffix}\n"
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

        if not quiet:
            status_suffix = f" ({failed_count} failed)" if failed_count > 0 else ""
            sys.stderr.write(
                f"task_id:{parent_task_id} "
                f"doc_ids:{','.join(str(d) for d in doc_ids)}{status_suffix}\n"
            )

    return doc_ids


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
    """
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

    try:
        # 4. Route
        if len(task_list) == 1:
            single_result = _run_single(
                prompt=task_list[0],
                tags=flat_tags,
                title=title,
                model=model,
                quiet=quiet,
                pr=pr,
                branch=branch,
                pr_branch=worktree_branch,
                draft=draft,
                working_dir=worktree_path,
                source_doc_id=doc,
                parent_task_id=epic_parent_id,
                epic_key=epic_key,
            )
            if single_result.pr_url and not quiet:
                sys.stderr.write(f"delegate: PR created: {single_result.pr_url}\n")
            elif single_result.branch_name and not quiet:
                sys.stderr.write(f"delegate: branch pushed: {single_result.branch_name}\n")
            if single_result.doc_id is None:
                raise typer.Exit(1) from None
        else:
            _run_parallel(
                tasks=task_list,
                tags=flat_tags,
                title=title,
                jobs=jobs,
                synthesize=synthesize,
                model=model,
                quiet=quiet,
                pr=pr,
                branch=branch,
                draft=draft,
                base_branch=base_branch,
                source_doc_id=doc,
                worktree=use_worktree,
                epic_key=epic_key,
                epic_parent_id=epic_parent_id,
            )
    finally:
        # Clean up worktree unless --branch (needs local branch)
        # For --pr: branch is already pushed, worktree no longer needed
        if worktree_path and not branch:
            from ..utils.git import cleanup_worktree

            if not quiet:
                sys.stderr.write(f"delegate: cleaning up worktree {worktree_path}\n")
            cleanup_worktree(worktree_path)
