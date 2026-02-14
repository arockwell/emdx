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

Sequential pipeline:
    emdx delegate --chain "analyze" "plan" "implement"

With PR creation:
    emdx delegate --pr "fix the auth bug"

With worktree isolation:
    emdx delegate --worktree "fix X"

Dynamic discovery:
    emdx delegate --each "fd -e py src/" --do "Review {{item}}"
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

import typer

from ..database.documents import get_document
from ..services.unified_executor import ExecutionConfig, UnifiedExecutor


app = typer.Typer(name="delegate", help="Delegate tasks to agents (stdout-friendly)")


def _safe_create_task(**kwargs) -> Optional[int]:
    """Create task, never fail delegate."""
    try:
        from ..models.tasks import create_task
        return create_task(**kwargs)
    except Exception as e:
        sys.stderr.write(f"delegate: task tracking failed: {e}\n")
        return None


def _safe_update_task(task_id: Optional[int], **kwargs) -> None:
    """Update task, never fail delegate."""
    if task_id is None:
        return
    try:
        from ..models.tasks import update_task
        update_task(task_id, **kwargs)
    except Exception:
        pass


def _safe_update_execution(exec_id: Optional[int], **kwargs) -> None:
    """Update execution record, never fail delegate."""
    if exec_id is None:
        return
    try:
        from ..models.executions import update_execution
        update_execution(exec_id, **kwargs)
    except Exception:
        pass


PR_INSTRUCTION = (
    "\n\nAfter saving your output, if you made any code changes, create a pull request:\n"
    "1. Create a new branch with a descriptive name\n"
    "2. Commit your changes with a clear message\n"
    "3. Push and create a PR using: gh pr create --title \"...\" --body \"...\"\n"
    "4. Report the PR URL that was created."
)


def _slugify_title(title: str) -> str:
    """Convert a document title to a git branch slug.

    Examples:
        "Gameplan #1: Contextual Save" -> "contextual-save"
        "Smart Priming (context-aware)" -> "smart-priming-context-aware"
    """
    import re
    # Remove common prefixes like "Gameplan #1:", "Feature:", etc.
    slug = re.sub(r'^(?:gameplan|feature|plan|doc(?:ument)?)\s*#?\d*[:\s—-]*', '', title, flags=re.IGNORECASE).strip()
    # Keep only alphanumeric and spaces/hyphens
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', slug)
    # Collapse whitespace to hyphens, lowercase
    slug = re.sub(r'\s+', '-', slug).strip('-').lower()
    # Truncate to reasonable branch name length
    return slug[:50].rstrip('-') or 'feature'


def _resolve_task(task: str, pr: bool = False) -> str:
    """Resolve a task argument — if it's a numeric doc ID, load the document content.

    When pr=True and the task is a doc ID, adds implementation and PR instructions
    with a branch name derived from the document title.
    """
    try:
        doc_id = int(task)
    except ValueError:
        return task

    doc = get_document(doc_id, track_access=False)
    if not doc:
        sys.stderr.write(f"delegate: document #{doc_id} not found, treating as text\n")
        return task

    title = doc.get("title", f"Document #{doc_id}")
    content = doc.get("content", "")

    if pr:
        branch = f"feat/{_slugify_title(title)}"
        return (
            f"Read and implement the following gameplan:\n\n# {title}\n\n{content}\n\n"
            f"---\n\n"
            f"Implementation instructions:\n"
            f"1. Implement the feature exactly as described in the gameplan above\n"
            f"2. Create a branch named `{branch}`\n"
            f"3. Commit your changes with a clear message\n"
            f"4. Push and create a PR via: gh pr create --title \"feat: {title}\" --body \"...\"\n"
            f"5. Use `poetry run emdx` to test your changes\n"
        )

    return f"Execute the following document:\n\n# {title}\n\n{content}"


def _run_discovery(command: str) -> List[str]:
    """Run a shell command and return output lines as items."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            sys.stderr.write(f"delegate: discovery failed: {result.stderr.strip()}\n")
            raise typer.Exit(1)

        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        if not lines:
            sys.stderr.write("delegate: discovery returned no items\n")
            raise typer.Exit(1)

        sys.stderr.write(f"delegate: discovered {len(lines)} item(s)\n")
        return lines

    except subprocess.TimeoutExpired:
        sys.stderr.write("delegate: discovery command timed out after 30s\n")
        raise typer.Exit(1)


def _load_doc_context(doc_id: int, prompt: Optional[str]) -> str:
    """Load a document and combine it with an optional prompt.

    If prompt provided: "Document #id (title):\n\n{content}\n\n---\n\nTask: {prompt}"
    If no prompt: "Execute the following document:\n\n# {title}\n\n{content}"
    """
    doc = get_document(doc_id, track_access=False)
    if not doc:
        sys.stderr.write(f"delegate: document #{doc_id} not found\n")
        raise typer.Exit(1)

    title = doc.get("title", f"Document #{doc_id}")
    content = doc.get("content", "")

    if prompt:
        return f"Document #{doc_id} ({title}):\n\n{content}\n\n---\n\nTask: {prompt}"
    else:
        return f"Execute the following document:\n\n# {title}\n\n{content}"


def _print_doc_content(doc_id: int) -> None:
    """Print a document's content to stdout."""
    doc = get_document(doc_id, track_access=False)
    if doc:
        sys.stdout.write(doc.get("content", ""))
        sys.stdout.write("\n")


def _run_single(
    prompt: str,
    tags: List[str],
    title: Optional[str],
    model: Optional[str],
    quiet: bool,
    pr: bool = False,
    working_dir: Optional[str] = None,
    source_doc_id: Optional[int] = None,
    parent_task_id: Optional[int] = None,
    seq: Optional[int] = None,
) -> tuple[Optional[int], Optional[int]]:
    """Run a single task via UnifiedExecutor. Returns (doc_id, task_id)."""
    doc_title = title or f"Delegate: {prompt[:60]}"

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
    )

    # Build save instruction so the sub-agent persists output
    cmd_parts = [f'emdx save --title "{doc_title}"']
    if tags:
        cmd_parts.append(f'--tags "{",".join(tags)}"')
    save_cmd = " ".join(cmd_parts)

    output_instruction = (
        "\n\nIMPORTANT: When you complete this task, save your final output using:\n"
        f'echo "YOUR OUTPUT HERE" | {save_cmd}\n'
        "Report the document ID that was created."
    )

    if pr:
        output_instruction += PR_INSTRUCTION

    config = ExecutionConfig(
        prompt=prompt,
        title=doc_title,
        output_instruction=output_instruction,
        working_dir=working_dir or str(Path.cwd()),
        timeout_seconds=600,
        model=model,
    )

    result = UnifiedExecutor().execute(config)

    # Link execution to task
    _safe_update_task(task_id, execution_id=result.execution_id)

    if not result.success:
        sys.stderr.write(f"delegate: task failed: {result.error_message}\n")
        _safe_update_task(task_id, status="failed", error=result.error_message)
        return None, task_id

    doc_id = result.output_doc_id
    if doc_id:
        _safe_update_task(task_id, status="done", output_doc_id=doc_id)
        # Write doc_id back to execution so activity browser can show the output
        _safe_update_execution(result.execution_id, doc_id=doc_id)
        _print_doc_content(doc_id)
        if not quiet:
            sys.stderr.write(
                f"task_id:{task_id} doc_id:{doc_id} tokens:{result.tokens_used} "
                f"cost:${result.cost_usd:.4f} duration:{result.execution_time_ms / 1000:.1f}s\n"
            )
    else:
        _safe_update_task(task_id, status="done")
        # No doc saved — print whatever output we captured
        if result.output_content:
            sys.stdout.write(result.output_content)
            sys.stdout.write("\n")
        sys.stderr.write("delegate: agent completed but no document was saved\n")

    return doc_id, task_id


def _run_parallel(
    tasks: List[str],
    tags: List[str],
    title: Optional[str],
    jobs: Optional[int],
    synthesize: bool,
    model: Optional[str],
    quiet: bool,
    pr: bool = False,
    base_branch: str = "main",
    source_doc_id: Optional[int] = None,
    worktree: bool = False,
) -> List[int]:
    """Run multiple tasks in parallel via ThreadPoolExecutor. Returns doc_ids."""
    max_workers = min(jobs or len(tasks), len(tasks), 10)

    # Create parent group task
    flat_tags = ",".join(tags) if tags else None
    parent_task_id = _safe_create_task(
        title=title or f"Parallel: {len(tasks)} tasks",
        prompt=" | ".join(t[:60] for t in tasks),
        task_type="group",
        status="active",
        source_doc_id=source_doc_id,
        tags=flat_tags,
    )

    # Results indexed by task position to preserve order
    results: dict[int, tuple[Optional[int], Optional[int]]] = {}

    def run_task(idx: int, task: str) -> tuple[int, tuple[Optional[int], Optional[int]]]:
        task_title = title or f"Delegate: {task[:60]}"
        if len(tasks) > 1:
            task_title = f"{task_title} [{idx + 1}/{len(tasks)}]"

        # Create per-task worktree if requested
        task_worktree_path = None
        if worktree:
            from ..utils.git import create_worktree
            try:
                task_worktree_path, _ = create_worktree(base_branch)
                if not quiet:
                    sys.stderr.write(f"delegate: worktree [{idx + 1}/{len(tasks)}] created at {task_worktree_path}\n")
            except Exception as e:
                sys.stderr.write(f"delegate: failed to create worktree for task {idx + 1}: {e}\n")
                return idx, (None, None)

        try:
            return idx, _run_single(
                prompt=task,
                tags=tags,
                title=task_title,
                model=model,
                quiet=True,  # suppress per-task metadata in parallel mode
                pr=pr,
                working_dir=task_worktree_path,
                parent_task_id=parent_task_id,
                seq=idx + 1,
            )
        finally:
            # Clean up worktree unless --pr (keep for the PR branch)
            if task_worktree_path and not pr:
                from ..utils.git import cleanup_worktree
                cleanup_worktree(task_worktree_path)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_task, i, task): i
            for i, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            idx, result_pair = future.result()
            results[idx] = result_pair

    # Collect doc_ids in original task order
    doc_ids = [results[i][0] for i in range(len(tasks)) if results.get(i) and results[i][0] is not None]

    if not doc_ids:
        sys.stderr.write("delegate: parallel run completed but no output documents found\n")
        _safe_update_task(parent_task_id, status="failed", error="no output documents")
        raise typer.Exit(1)

    # Update parent task
    if synthesize and len(doc_ids) > 1:
        # Run a synthesis task that combines all outputs
        combined = []
        for i, doc_id in enumerate(doc_ids):
            doc = get_document(doc_id, track_access=False)
            if doc:
                combined.append(f"## Task {i + 1}: {tasks[i][:80]}\n\n{doc.get('content', '')}")

        synthesis_prompt = (
            "Synthesize the following task results into a unified summary. "
            "Highlight key findings, common themes, and actionable items.\n\n"
            + "\n\n---\n\n".join(combined)
        )
        synthesis_title = title or "Delegate synthesis"
        synthesis_doc_id, _ = _run_single(
            prompt=synthesis_prompt,
            tags=tags,
            title=f"{synthesis_title} [synthesis]",
            model=model,
            quiet=True,
            parent_task_id=parent_task_id,
        )
        if synthesis_doc_id:
            doc_ids.append(synthesis_doc_id)
            # Print just the synthesis
            _print_doc_content(synthesis_doc_id)
        _safe_update_task(parent_task_id, status="done", output_doc_id=synthesis_doc_id)
        if not quiet:
            sys.stderr.write(
                f"task_id:{parent_task_id} doc_ids:{','.join(str(d) for d in doc_ids)} "
                f"synthesis_id:{synthesis_doc_id or 'none'}\n"
            )
    else:
        _safe_update_task(parent_task_id, status="done")
        # Print each result separated
        for i, doc_id in enumerate(doc_ids):
            if len(doc_ids) > 1:
                sys.stdout.write(f"\n=== Task {i + 1}: {tasks[i] if i < len(tasks) else '?'} ===\n")
            _print_doc_content(doc_id)

        if not quiet:
            sys.stderr.write(
                f"task_id:{parent_task_id} doc_ids:{','.join(str(d) for d in doc_ids)}\n"
            )

    return doc_ids


def _run_chain(
    tasks: List[str],
    tags: List[str],
    title: Optional[str],
    model: Optional[str],
    quiet: bool,
    pr: bool = False,
    working_dir: Optional[str] = None,
    source_doc_id: Optional[int] = None,
) -> List[int]:
    """Run tasks sequentially, piping output from each step to the next.

    Returns list of doc_ids from all steps.
    """
    # Create parent task for the chain
    parent_task_id = _safe_create_task(
        title=title or f"Chain: {len(tasks)} steps",
        prompt=" → ".join(t[:40] for t in tasks),
        task_type="chain",
        status="active",
        source_doc_id=source_doc_id,
        tags=",".join(tags) if tags else None,
    )

    # Pre-create all step tasks
    step_task_ids = []
    prev_step_id = None
    for i, task in enumerate(tasks):
        step_id = _safe_create_task(
            title=f"Step {i+1}/{len(tasks)}: {task[:60]}",
            prompt=task[:500],
            task_type="single",
            status="open",
            parent_task_id=parent_task_id,
            seq=i + 1,
            depends_on=[prev_step_id] if prev_step_id else None,
        )
        step_task_ids.append(step_id)
        prev_step_id = step_id

    doc_ids = []
    previous_output = None

    for i, task in enumerate(tasks):
        step_num = i + 1
        total_steps = len(tasks)
        is_last_step = step_num == total_steps

        # Mark step as active
        _safe_update_task(step_task_ids[i], status="active")

        # Build prompt with previous context
        if previous_output:
            prompt = (
                f"Previous step output:\n\n{previous_output}\n\n---\n\n"
                f"Your task (step {step_num}/{total_steps}): {task}"
            )
        else:
            prompt = f"Your task (step {step_num}/{total_steps}): {task}"

        sys.stdout.write(f"\n=== Step {step_num}/{total_steps}: {task[:60]} ===\n")

        # Only last step gets --pr
        step_pr = pr and is_last_step

        step_title = title or f"Delegate chain step {step_num}/{total_steps}"

        doc_id, _ = _run_single(
            prompt=prompt,
            tags=tags,
            title=f"{step_title} [{step_num}/{total_steps}]",
            model=model,
            quiet=quiet,
            pr=step_pr,
            working_dir=working_dir,
            parent_task_id=parent_task_id,
            seq=step_num,
        )

        if doc_id is None:
            sys.stderr.write(f"delegate: chain aborted at step {step_num}/{total_steps}\n")
            # Mark current step as failed
            _safe_update_task(step_task_ids[i], status="failed", error="execution failed")
            # Mark remaining steps as failed
            for j in range(i + 1, len(step_task_ids)):
                _safe_update_task(step_task_ids[j], status="failed", error="chain aborted")
            _safe_update_task(parent_task_id, status="failed", error=f"aborted at step {step_num}")
            break

        # Update step task with output
        _safe_update_task(step_task_ids[i], status="done", output_doc_id=doc_id)
        doc_ids.append(doc_id)

        # Read output for next step
        doc = get_document(doc_id, track_access=False)
        if doc:
            previous_output = doc.get("content", "")

    # If all steps completed, mark parent as done
    if len(doc_ids) == len(tasks):
        _safe_update_task(parent_task_id, status="done", output_doc_id=doc_ids[-1])

    if not quiet and doc_ids:
        ids_str = ",".join(str(d) for d in doc_ids)
        final_id = doc_ids[-1] if doc_ids else "none"
        sys.stderr.write(f"task_id:{parent_task_id} doc_ids:{ids_str} chain_final:{final_id}\n")

    return doc_ids


@app.callback(invoke_without_command=True)
def delegate(
    ctx: typer.Context,
    tasks: List[str] = typer.Argument(
        None,
        help="Task prompt(s) or document IDs. Numeric args load doc content.",
    ),
    tags: Optional[List[str]] = typer.Option(
        None, "--tags", "-t",
        help="Tags to apply to outputs (comma-separated)",
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-T",
        help="Title for output document(s)",
    ),
    synthesize: bool = typer.Option(
        False, "--synthesize", "-s",
        help="Combine parallel outputs with synthesis",
    ),
    jobs: int = typer.Option(
        None, "-j", "--jobs",
        help="Max parallel tasks (default: auto)",
    ),
    model: str = typer.Option(
        None, "--model", "-m",
        help="Model to use (overrides default)",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Suppress metadata on stderr (just content on stdout)",
    ),
    doc: int = typer.Option(
        None, "--doc", "-d",
        help="Document ID to use as input context",
    ),
    pr: bool = typer.Option(
        False, "--pr",
        help="Instruct agent to create a PR (implies --worktree)",
    ),
    worktree: bool = typer.Option(
        False, "--worktree", "-w",
        help="Run in isolated git worktree",
    ),
    base_branch: str = typer.Option(
        "main", "--base-branch",
        help="Base branch for worktree (only with --worktree)",
    ),
    chain: bool = typer.Option(
        False, "--chain",
        help="Run tasks sequentially, piping output forward",
    ),
    each: str = typer.Option(
        None, "--each",
        help="Shell command to discover items (one per line)",
    ),
    do: str = typer.Option(
        None, "--do",
        help="Template for each discovered item (use {{item}})",
    ),
):
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

    Sequential pipeline:
        emdx delegate --chain "analyze code" "create plan" "implement changes"

    With PR creation:
        emdx delegate --pr "fix the auth bug"

    Implement gameplans by doc ID (auto-branches + PRs):
        emdx delegate --worktree --pr -j 7 6097 6098 6099 6100 6101 6102 6103

    Dynamic discovery (for each item, do action):
        emdx delegate --each "fd -e py src/" --do "Review {{item}} for issues"

    With worktree isolation:
        emdx delegate --worktree --pr "fix X"

    Quiet mode (just content, no metadata):
        emdx delegate -q "do something"
    """
    # Validate mutually exclusive options
    if chain and synthesize:
        typer.echo("Error: --chain and --synthesize are mutually exclusive", err=True)
        raise typer.Exit(1)

    if each and not do:
        typer.echo("Error: --each requires --do", err=True)
        raise typer.Exit(1)

    task_list = list(tasks) if tasks else []

    # 0. Dynamic discovery: --each "cmd" --do "template {{item}}"
    if each:
        items = _run_discovery(each)
        template = do or "{{item}}"
        discovered = [template.replace("{{item}}", item) for item in items]
        task_list = discovered + task_list  # discovered tasks + any explicit tasks

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
        raise typer.Exit(1)

    # Flatten tags
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(","))

    # 3. Setup worktree for single/chain paths (parallel creates per-task worktrees)
    #    --pr always implies --worktree so the sub-agent has a clean git environment
    use_worktree = worktree or pr
    worktree_path = None
    if use_worktree and (len(task_list) == 1 or chain):
        from ..utils.git import create_worktree
        try:
            worktree_path, _ = create_worktree(base_branch)
            if not quiet:
                sys.stderr.write(f"delegate: worktree created at {worktree_path}\n")
        except Exception as e:
            sys.stderr.write(f"delegate: failed to create worktree: {e}\n")
            raise typer.Exit(1)

    try:
        # 4. Route
        if chain and len(task_list) > 1:
            _run_chain(
                tasks=task_list,
                tags=flat_tags,
                title=title,
                model=model,
                quiet=quiet,
                pr=pr,
                working_dir=worktree_path,
                source_doc_id=doc,
            )
        elif len(task_list) == 1:
            doc_id, _ = _run_single(
                prompt=task_list[0],
                tags=flat_tags,
                title=title,
                model=model,
                quiet=quiet,
                pr=pr,
                working_dir=worktree_path,
                source_doc_id=doc,
            )
            if doc_id is None:
                raise typer.Exit(1)
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
                base_branch=base_branch,
                source_doc_id=doc,
                worktree=use_worktree,
            )
    finally:
        if worktree_path and not pr:
            from ..utils.git import cleanup_worktree
            if not quiet:
                sys.stderr.write(f"delegate: cleaning up worktree {worktree_path}\n")
            cleanup_worktree(worktree_path)
