"""Delegate tasks to parallel Claude agents with inline results.

Designed for Claude Code to call via Bash instead of the Task tool.
Results print to stdout (so Claude can read them inline) AND persist
to emdx (so they're searchable later).

Single task:
    emdx delegate "analyze the auth module"

Parallel tasks:
    emdx delegate "check auth" "review tests" "scan for XSS"

With synthesis:
    emdx delegate --synthesize "task1" "task2" "task3"
"""

import asyncio
import sys
from typing import List, Optional

import typer

from ..database.documents import get_document
from ..services.unified_executor import ExecutionConfig, UnifiedExecutor
from ..workflows.executor import workflow_executor


app = typer.Typer(name="delegate", help="Delegate tasks to parallel agents (stdout-friendly)")


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

    from pathlib import Path

    config = ExecutionConfig(
        prompt=prompt,
        title=doc_title,
        output_instruction=output_instruction,
        working_dir=str(Path.cwd()),
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
) -> List[int]:
    """Run multiple tasks in parallel via workflow executor. Returns doc_ids."""
    variables = {"tasks": tasks}
    if title:
        variables["task_title"] = title
    if jobs:
        variables["_max_concurrent_override"] = jobs
    if model:
        variables["_model"] = model

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
):
    """Delegate tasks to Claude agents with results on stdout.

    Designed for machine callers (Claude Code via Bash). Results print to
    stdout so the caller can read them inline. Documents are also saved to
    emdx for persistence. Metadata prints to stderr.

    Single task:
        emdx delegate "analyze the auth module for security issues"

    Parallel tasks (up to 10):
        emdx delegate "check auth" "review tests" "scan for XSS"

    Parallel with synthesis:
        emdx delegate --synthesize "task1" "task2" "task3"

    Quiet mode (just content, no metadata):
        emdx delegate -q "do something"
    """
    task_list = list(tasks) if tasks else []

    if not task_list:
        typer.echo("Error: No tasks provided", err=True)
        typer.echo('Usage: emdx delegate "task description"', err=True)
        raise typer.Exit(1)

    # Flatten tags
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(","))

    if len(task_list) == 1:
        doc_id = _run_single(
            prompt=task_list[0],
            tags=flat_tags,
            title=title,
            model=model,
            quiet=quiet,
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
        )
