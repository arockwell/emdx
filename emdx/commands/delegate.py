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
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import typer

from ..database.documents import get_document
from ..services.unified_executor import ExecutionConfig, UnifiedExecutor
from ..workflows.executor import workflow_executor


app = typer.Typer(name="delegate", help="Delegate tasks to agents (stdout-friendly)")

PR_INSTRUCTION = (
    "\n\nAfter saving your output, if you made any code changes, create a pull request:\n"
    "1. Create a new branch with a descriptive name\n"
    "2. Commit your changes with a clear message\n"
    "3. Push and create a PR using: gh pr create --title \"...\" --body \"...\"\n"
    "4. Report the PR URL that was created."
)


def _load_doc_context(doc_id: int, prompt: Optional[str]) -> str:
    """Load a document and combine it with an optional prompt.

    If prompt provided: "Document #id (title):\n\n{content}\n\n---\n\nTask: {prompt}"
    If no prompt: "Execute the following document:\n\n# {title}\n\n{content}"
    """
    doc = get_document(doc_id)
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
    doc = get_document(doc_id)
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
) -> Optional[int]:
    """Run a single task via UnifiedExecutor. Returns doc_id or None."""
    doc_title = title or f"Delegate: {prompt[:60]}"

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
        timeout_seconds=300,
        model=model,
    )

    result = UnifiedExecutor().execute(config)

    if not result.success:
        sys.stderr.write(f"delegate: task failed: {result.error_message}\n")
        return None

    doc_id = result.output_doc_id
    if doc_id:
        _print_doc_content(doc_id)
        if not quiet:
            sys.stderr.write(
                f"doc_id:{doc_id} tokens:{result.tokens_used} "
                f"cost:${result.cost_usd:.4f} duration:{result.execution_time_ms / 1000:.1f}s\n"
            )
    else:
        # No doc saved — print whatever output we captured
        if result.output_content:
            sys.stdout.write(result.output_content)
            sys.stdout.write("\n")
        sys.stderr.write("delegate: agent completed but no document was saved\n")

    return doc_id


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
) -> List[int]:
    """Run multiple tasks in parallel via workflow executor. Returns doc_ids."""
    variables = {"tasks": tasks}
    if title:
        variables["task_title"] = title
    if jobs:
        variables["_max_concurrent_override"] = jobs
    if model:
        variables["_model"] = model

    # When --pr is set, append PR instruction to each task prompt
    if pr:
        variables["tasks"] = [t + PR_INSTRUCTION for t in tasks]

    result = asyncio.run(
        workflow_executor.execute_workflow(
            workflow_name_or_id="task_parallel",
            input_variables=variables,
        )
    )

    if result.status != "completed":
        sys.stderr.write(f"delegate: parallel run failed: {result.error_message}\n")
        raise typer.Exit(1)

    doc_ids = []
    if result.output_doc_ids:
        # output_doc_ids is a JSON string of IDs
        import json

        if isinstance(result.output_doc_ids, str):
            try:
                doc_ids = json.loads(result.output_doc_ids)
            except json.JSONDecodeError:
                doc_ids = [int(x.strip()) for x in result.output_doc_ids.split(",") if x.strip()]
        elif isinstance(result.output_doc_ids, list):
            doc_ids = result.output_doc_ids

    if not doc_ids:
        sys.stderr.write("delegate: parallel run completed but no output documents found\n")
        raise typer.Exit(1)

    if synthesize and len(doc_ids) > 1:
        # The last doc is the synthesis when task_parallel has synthesis enabled
        # Print just the synthesis
        _print_doc_content(doc_ids[-1])
        if not quiet:
            sys.stderr.write(
                f"doc_ids:{','.join(str(d) for d in doc_ids)} "
                f"synthesis_id:{doc_ids[-1]} "
                f"tokens:{result.total_tokens_used} "
                f"duration:{(result.total_execution_time_ms or 0) / 1000:.1f}s\n"
            )
    else:
        # Print each result separated
        for i, doc_id in enumerate(doc_ids):
            if len(doc_ids) > 1:
                sys.stdout.write(f"\n=== Task {i + 1}: {tasks[i] if i < len(tasks) else '?'} ===\n")
            _print_doc_content(doc_id)

        if not quiet:
            sys.stderr.write(
                f"doc_ids:{','.join(str(d) for d in doc_ids)} "
                f"tokens:{result.total_tokens_used} "
                f"duration:{(result.total_execution_time_ms or 0) / 1000:.1f}s\n"
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
) -> List[int]:
    """Run tasks sequentially, piping output from each step to the next.

    Returns list of doc_ids from all steps.
    """
    doc_ids = []
    previous_output = None

    for i, task in enumerate(tasks):
        step_num = i + 1
        total_steps = len(tasks)
        is_last_step = step_num == total_steps

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

        doc_id = _run_single(
            prompt=prompt,
            tags=tags,
            title=f"{step_title} [{step_num}/{total_steps}]",
            model=model,
            quiet=quiet,
            pr=step_pr,
            working_dir=working_dir,
        )

        if doc_id is None:
            sys.stderr.write(f"delegate: chain aborted at step {step_num}/{total_steps}\n")
            break

        doc_ids.append(doc_id)

        # Read output for next step
        doc = get_document(doc_id)
        if doc:
            previous_output = doc.get("content", "")

    if not quiet and doc_ids:
        ids_str = ",".join(str(d) for d in doc_ids)
        final_id = doc_ids[-1] if doc_ids else "none"
        sys.stderr.write(f"doc_ids:{ids_str} chain_final:{final_id}\n")

    return doc_ids


@app.callback(invoke_without_command=True)
def delegate(
    ctx: typer.Context,
    tasks: List[str] = typer.Argument(
        None,
        help="Task prompt(s) to delegate. Multiple tasks run in parallel.",
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
        help="Instruct agent to create a PR after code changes",
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
):
    """Delegate tasks to Claude agents with results on stdout.

    The single command for all one-shot AI execution. Results print to stdout
    so the caller can read them inline. Documents are also saved to emdx for
    persistence. Metadata prints to stderr.

    Single task:
        emdx delegate "analyze the auth module for security issues"

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

    With worktree isolation:
        emdx delegate --worktree --pr "fix X"

    Quiet mode (just content, no metadata):
        emdx delegate -q "do something"
    """
    # Validate mutually exclusive options
    if chain and synthesize:
        typer.echo("Error: --chain and --synthesize are mutually exclusive", err=True)
        raise typer.Exit(1)

    task_list = list(tasks) if tasks else []

    # 1. Resolve --doc
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

    # 2. Setup worktree for single/chain paths
    worktree_path = None
    if worktree and (len(task_list) == 1 or chain):
        from .workflows import create_worktree_for_workflow
        try:
            worktree_path, _ = create_worktree_for_workflow(base_branch)
            if not quiet:
                sys.stderr.write(f"delegate: worktree created at {worktree_path}\n")
        except Exception as e:
            sys.stderr.write(f"delegate: failed to create worktree: {e}\n")
            raise typer.Exit(1)

    try:
        # 3. Route
        if chain and len(task_list) > 1:
            _run_chain(
                tasks=task_list,
                tags=flat_tags,
                title=title,
                model=model,
                quiet=quiet,
                pr=pr,
                working_dir=worktree_path,
            )
        elif len(task_list) == 1:
            doc_id = _run_single(
                prompt=task_list[0],
                tags=flat_tags,
                title=title,
                model=model,
                quiet=quiet,
                pr=pr,
                working_dir=worktree_path,
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
            )
    finally:
        if worktree_path and not pr:
            from .workflows import cleanup_worktree
            if not quiet:
                sys.stderr.write(f"delegate: cleaning up worktree {worktree_path}\n")
            cleanup_worktree(worktree_path)
