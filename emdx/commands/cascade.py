"""Cascade - autonomous document transformation pipeline.

Cascade transforms raw ideas into working code through a series of stages:
idea → prompt → analyzed → planned → done

Each stage refines the document using Claude, with the final stage
actually implementing the code and creating a pull request.

Key concepts:
- Inevitable flow: Once an idea enters, it cascades through to completion
- Stage transformation: Each stage adds structure and refinement
- Autonomous execution: Claude handles the heavy lifting at each stage
"""

import re
import time
from datetime import datetime
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ..config.constants import EMDX_LOG_DIR
from ..database import cascade as cascade_db
from ..database.connection import db_connection
from ..database.documents import get_document, save_document
from ..services.claude_executor import execute_claude_detached, execute_cli_sync

console = Console()

app = typer.Typer(help="Cascade ideas through stages to working code")

# Stage configuration
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_PROMPTS = {
    "idea": """Convert this idea into a well-formed prompt that could be given to an AI
assistant.

IMPORTANT: Do NOT create any files. Just output the prompt text directly - your output
will be captured automatically.

Idea to convert:
{content}""",
    "prompt": """Analyze this prompt thoroughly. Consider:
- What is being asked?
- What are the requirements (explicit and implicit)?
- What are potential challenges or edge cases?
- What context or information is needed?

IMPORTANT: Do NOT create any files. Just output your analysis directly - your output
will be captured automatically.

Prompt to analyze:
{content}""",
    "analyzed": """Based on this analysis, create a detailed implementation gameplan.
Include:
- Step-by-step implementation plan
- Files that need to be modified
- Key design decisions
- Testing approach
- Potential risks

IMPORTANT: Do NOT create any files (no GAMEPLAN.md, no markdown files). Just output
the gameplan directly as text - your output will be captured automatically and saved
to the knowledge base.

Analysis to plan from:
{content}""",
    "planned": """You are implementing a feature based on the gameplan below.

IMPORTANT INSTRUCTIONS:
1. Implement the gameplan by writing actual code
2. Create a new git branch for this work
3. Make commits as you go
4. When done, create a Pull Request using `gh pr create`
5. At the very end of your response, output the PR URL on its own line in this exact format:
   PR_URL: https://github.com/...

Here is the gameplan to implement:

{content}""",
}
NEXT_STAGE = {
    "idea": "prompt",
    "prompt": "analyzed",
    "analyzed": "planned",
    "planned": "done",
}


def _get_stages_between(start: str, stop: str) -> list[str]:
    """Get list of stages to process between start and stop (inclusive of start, exclusive of stop)."""  # noqa: E501
    start_idx = STAGES.index(start)
    stop_idx = STAGES.index(stop)
    # Return stages from start up to (but not including) stop
    return STAGES[start_idx:stop_idx]


def _create_cascade_run(doc_id: int, start_stage: str, stop_stage: str) -> int:
    """Create a new cascade run record."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO cascade_runs
                (start_doc_id, current_doc_id, start_stage,
                 stop_stage, current_stage, status)
            VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (doc_id, doc_id, start_stage, stop_stage, start_stage),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def _update_cascade_run(
    run_id: int,
    current_doc_id: int | None = None,
    current_stage: str | None = None,
    status: str | None = None,
    pr_url: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update a cascade run record."""
    updates: list[str] = []
    params: list[int | str] = []

    if current_doc_id is not None:
        updates.append("current_doc_id = ?")
        params.append(current_doc_id)
    if current_stage is not None:
        updates.append("current_stage = ?")
        params.append(current_stage)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status in ('completed', 'failed'):
            updates.append("completed_at = CURRENT_TIMESTAMP")
    if pr_url is not None:
        updates.append("pr_url = ?")
        params.append(pr_url)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)

    if updates:
        params.append(run_id)
        with db_connection.get_connection() as conn:
            conn.execute(f"UPDATE cascade_runs SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()


def _process_stage(
    doc: dict[str, Any], stage: str, cascade_run_id: int | None = None,
) -> tuple[bool, int, str | None]:
    """Process a single stage for a document.

    Returns: (success, new_doc_id, pr_url or None)
    """
    doc_id = doc["id"]
    next_stage = NEXT_STAGE[stage]

    console.print(f"[cyan]Processing #{doc_id}: {doc['title'][:50]}[/cyan]")
    console.print(f"  Stage: {stage} → {next_stage}")

    # Build the prompt
    prompt = STAGE_PROMPTS[stage].format(content=doc["content"])

    if stage == "planned":
        console.print("[bold yellow]⚡ Implementation mode - Claude will write code and create a PR[/bold yellow]")  # noqa: E501

    # Set up logging
    EMDX_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = EMDX_LOG_DIR / f"cascade_{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"  # noqa: E501

    # Create execution record
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO executions (doc_id, doc_title, status, started_at, log_file, cascade_run_id)
            VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?, ?)
            """,
            (doc_id, doc["title"], str(log_file), cascade_run_id),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        execution_id = cursor.lastrowid

    # Implementation stage needs longer timeout
    timeout = 1800 if stage == "planned" else 300

    try:
        result = execute_cli_sync(
            task=prompt,
            execution_id=execution_id,
            log_file=log_file,
            cli_tool="claude",
            doc_id=str(doc_id),
            timeout=timeout,
        )

        if result.get("success"):
            output = result.get("output", "")
            pr_url = None
            new_doc_id = doc_id

            if output:
                # For planned stage, extract PR URL
                if stage == "planned":
                    pr_match = re.search(r'PR_URL:\s*(https://github\.com/[^\s]+)', output)
                    if pr_match:
                        pr_url = pr_match.group(1)
                        console.print(f"[bold green]🔗 PR Created: {pr_url}[/bold green]")

                # Create child document
                child_title = f"{doc['title']} [{stage}→{next_stage}]"
                new_doc_id = save_document(
                    title=child_title,
                    content=output,
                    project=doc.get("project"),
                    parent_id=doc_id,
                )
                cascade_db.update_cascade_stage(new_doc_id, next_stage)
                console.print(f"[green]✓[/green] Created document #{new_doc_id}")

                if pr_url:
                    cascade_db.update_cascade_pr_url(new_doc_id, pr_url)
                    cascade_db.update_cascade_pr_url(doc_id, pr_url)

                # Mark original as done
                cascade_db.update_cascade_stage(doc_id, "done")
            else:
                # No output - just advance
                cascade_db.update_cascade_stage(doc_id, next_stage)
                console.print(f"[green]✓[/green] Advanced to {next_stage}")

            # Mark execution complete
            with db_connection.get_connection() as conn:
                conn.execute(
                    "UPDATE executions SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: E501
                    (execution_id,),
                )
                conn.commit()

            return True, new_doc_id, pr_url
        else:
            console.print("[red]✗ Processing failed[/red]")
            with db_connection.get_connection() as conn:
                conn.execute(
                    "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: E501
                    (execution_id,),
                )
                conn.commit()
            return False, doc_id, None

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        with db_connection.get_connection() as conn:
            conn.execute(
                "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: E501
                (execution_id,),
            )
            conn.commit()
        return False, doc_id, None


@app.command()
def add(
    content: str = typer.Argument(..., help="The idea content to add to the cascade"),
    title: str | None = typer.Option(None, "--title", "-t", help="Document title"),
    stage: str = typer.Option("idea", "--stage", "-s", help="Starting stage"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically run through stages"),
    stop: str = typer.Option("done", "--stop", help="Stage to stop at (default: done)"),
    analyze: bool = typer.Option(False, "--analyze", help="Shortcut for --auto --stop analyzed"),
    plan: bool = typer.Option(False, "--plan", help="Shortcut for --auto --stop planned"),
) -> None:
    """Add a new document to the cascade and optionally run it.

    Examples:
        emdx cascade add "Build a REST API for user management"
        emdx cascade add "Add dark mode" --auto
        emdx cascade add "Add dark mode" --auto --stop planned
        emdx cascade add "Add dark mode" --analyze    # idea → analyzed
        emdx cascade add "Add dark mode" --plan       # idea → planned
        emdx cascade add "My gameplan" --stage planned --auto
    """
    # Handle shortcuts
    if analyze:
        auto = True
        stop = "analyzed"
    elif plan:
        auto = True
        stop = "planned"
    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    if stop not in STAGES:
        console.print(f"[red]Invalid stop stage: {stop}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    if STAGES.index(stop) <= STAGES.index(stage):
        console.print(f"[red]Stop stage '{stop}' must be after start stage '{stage}'[/red]")
        raise typer.Exit(1)

    doc_title = title or f"Cascade: {content[:50]}..."
    doc_id = cascade_db.save_document_to_cascade(
        title=doc_title,
        content=content,
        stage=stage,
    )
    console.print(f"[green]✓[/green] Added document #{doc_id} at stage '{stage}'")

    if auto:
        # Run automatically through stages
        _run_auto(doc_id, stage, stop)


def _run_auto(doc_id: int, start_stage: str, stop_stage: str) -> None:
    """Run a document through stages automatically."""
    stages_to_process = _get_stages_between(start_stage, stop_stage)

    if not stages_to_process:
        console.print(f"[yellow]No stages to process between {start_stage} and {stop_stage}[/yellow]")  # noqa: E501
        return

    console.print(f"\n[bold cyan]Auto-running: {start_stage} → {stop_stage}[/bold cyan]")
    console.print(f"[dim]Stages: {' → '.join(stages_to_process)} → {stop_stage}[/dim]\n")

    # Create cascade run record
    cascade_run_id = _create_cascade_run(doc_id, start_stage, stop_stage)
    console.print(f"[dim]Cascade run #{cascade_run_id}[/dim]\n")

    current_doc_id = doc_id
    pr_url = None

    for stage in stages_to_process:
        doc = get_document(str(current_doc_id))
        if not doc:
            console.print(f"[red]Document #{current_doc_id} not found[/red]")
            _update_cascade_run(cascade_run_id, status='failed', error_message=f"Document {current_doc_id} not found")  # noqa: E501
            raise typer.Exit(1)

        # Verify document is at expected stage
        if doc.get("stage") != stage:
            console.print(f"[red]Document #{current_doc_id} is at '{doc.get('stage')}', expected '{stage}'[/red]")  # noqa: E501
            _update_cascade_run(cascade_run_id, status='failed', error_message="Stage mismatch")
            raise typer.Exit(1)

        success, new_doc_id, stage_pr_url = _process_stage(dict(doc), stage, cascade_run_id)

        if not success:
            _update_cascade_run(cascade_run_id, status='failed', error_message=f"Failed at {stage}")
            console.print(f"\n[red]Cascade failed at stage '{stage}'[/red]")
            raise typer.Exit(1)

        current_doc_id = new_doc_id
        if stage_pr_url:
            pr_url = stage_pr_url

        # Update cascade run progress
        next_stage = NEXT_STAGE[stage]
        _update_cascade_run(cascade_run_id, current_doc_id=current_doc_id, current_stage=next_stage, pr_url=pr_url)  # noqa: E501

        console.print()  # Blank line between stages

    # Complete the cascade run
    _update_cascade_run(cascade_run_id, status='completed')

    console.print("[bold green]✓ Cascade complete![/bold green]")
    console.print(f"  Final document: #{current_doc_id}")
    console.print(f"  Final stage: {stop_stage}")
    if pr_url:
        console.print(f"  PR: {pr_url}")


@app.command()
def status() -> None:
    """Show cascade status - documents at each stage."""
    raw_stats = cascade_db.get_cascade_stats()
    # CascadeStats is a TypedDict with fixed stage keys; convert for dynamic access
    stats: dict[str, int] = {
        "idea": raw_stats["idea"], "prompt": raw_stats["prompt"],
        "analyzed": raw_stats["analyzed"], "planned": raw_stats["planned"],
        "done": raw_stats["done"],
    }

    table = Table(title="Cascade Status")
    table.add_column("Stage", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("→", justify="center")

    for i, stage in enumerate(STAGES):
        count = stats.get(stage, 0)
        arrow = "→" if i < len(STAGES) - 1 else ""
        style = "green" if count > 0 else "dim"
        table.add_row(stage, str(count), arrow, style=style)

    console.print(table)

    total = sum(stats.values())
    if total > 0:
        console.print(f"\nTotal documents in cascade: {total}")
    else:
        console.print("\n[dim]Cascade is empty. Add ideas with: emdx cascade add \"your idea\"[/dim]")  # noqa: E501

    # Show active cascade runs
    with db_connection.get_connection() as conn:
        runs = conn.execute(
            "SELECT id, start_stage, stop_stage, current_stage, status FROM cascade_runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 5"  # noqa: E501
        ).fetchall()

    if runs:
        console.print("\n[bold]Active Cascade Runs:[/bold]")
        for run in runs:
            console.print(f"  #{run[0]}: {run[1]} → {run[2]} (at {run[3]})")


@app.command()
def show(
    stage: str = typer.Argument(..., help="Stage to show documents from"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to show"),
) -> None:
    """Show documents at a specific stage."""
    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    docs = cascade_db.list_documents_at_stage(stage, limit=limit)

    if not docs:
        console.print(f"[dim]No documents at stage '{stage}'[/dim]")
        return

    table = Table(title=f"Documents at '{stage}'")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Created")

    for doc in docs:
        created = str(doc["created_at"] or "")[:16]
        table.add_row(str(doc["id"]), doc["title"][:60], created)

    console.print(table)


@app.command()
def process(
    stage: str = typer.Argument(..., help="Stage to process"),
    doc_id: int | None = typer.Option(None, "--doc", "-d", help="Specific document ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
    sync: bool = typer.Option(True, "--sync/--async", "-s", help="Wait for completion (default: sync)"),  # noqa: E501
) -> None:
    """Process one document at a stage.

    Picks up the oldest document at the given stage, runs it through Claude,
    and advances it to the next stage.

    Examples:
        emdx cascade process idea
        emdx cascade process prompt --doc 123
        emdx cascade process analyzed --dry-run
    """
    if stage == "done":
        console.print("[yellow]'done' is a terminal stage - nothing to process[/yellow]")
        raise typer.Exit(1)

    if stage not in STAGE_PROMPTS:
        console.print(f"[red]Invalid stage: {stage}. Processable stages: {list(STAGE_PROMPTS.keys())}[/red]")  # noqa: E501
        raise typer.Exit(1)

    # Get document to process
    doc: dict[str, Any] | None
    if doc_id:
        doc = dict(get_document(str(doc_id)) or {}) or None
        if not doc:
            console.print(f"[red]Document #{doc_id} not found[/red]")
            raise typer.Exit(1)
        if doc.get("stage") != stage:
            console.print(f"[red]Document #{doc_id} is at stage '{doc.get('stage')}', not '{stage}'[/red]")  # noqa: E501
            raise typer.Exit(1)
    else:
        oldest = cascade_db.get_oldest_at_stage(stage)
        doc = dict(oldest) if oldest else None
        if not doc:
            console.print(f"[dim]No documents waiting at stage '{stage}'[/dim]")
            return

    if dry_run:
        console.print(f"[yellow]Would process #{doc['id']}: {doc['title'][:50]}[/yellow]")
        return

    if sync:
        success, new_doc_id, pr_url = _process_stage(doc, stage)
        if not success:
            raise typer.Exit(1)
    else:
        # Async execution - start and return immediately
        doc_id = doc["id"]
        NEXT_STAGE[stage]
        prompt = STAGE_PROMPTS[stage].format(content=doc["content"])

        EMDX_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = EMDX_LOG_DIR / f"cascade_{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"  # noqa: E501

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO executions (doc_id, doc_title, status, started_at, log_file) VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?)",  # noqa: E501
                (doc_id, doc["title"], str(log_file)),
            )
            conn.commit()
            assert cursor.lastrowid is not None
            execution_id = cursor.lastrowid

        pid = execute_claude_detached(
            task=prompt,
            execution_id=execution_id,
            log_file=log_file,
            doc_id=str(doc_id),
        )

        console.print(f"[green]✓[/green] Started processing (PID: {pid})")
        console.print(f"  [yellow]Document stays at '{stage}' until manually advanced[/yellow]")
        console.print(f"  Use 'emdx cascade advance {doc_id}' after completion")


@app.command()
def run(
    auto: bool = typer.Option(False, "--auto", "-a", help="Process documents end-to-end automatically"),  # noqa: E501
    stop: str = typer.Option("done", "--stop", help="Stage to stop at (with --auto)"),
    once: bool = typer.Option(False, "--once", help="Run one iteration then exit"),
    interval: float = typer.Option(5.0, "--interval", "-i", help="Seconds between checks"),
) -> None:
    """Run the cascade continuously or in auto mode.

    Examples:
        emdx cascade run --auto                    # Process all ideas to done
        emdx cascade run --auto --stop planned     # Process all ideas to planned (no PRs)
        emdx cascade run --once                    # Process one document then exit
        emdx cascade run --interval 10             # Check every 10 seconds
    """
    if auto:
        # Auto mode: pick up ideas and run them through to stop stage
        console.print(f"[bold cyan]Auto mode: processing ideas → {stop}[/bold cyan]")
        if not once:
            console.print(f"[dim]Checking every {interval}s. Press Ctrl+C to stop.[/dim]")

        while True:
            doc = cascade_db.get_oldest_at_stage("idea")
            if doc:
                console.print(f"\n[cyan]Found idea: #{doc['id']}[/cyan]")
                try:
                    _run_auto(doc["id"], "idea", stop)
                except typer.Exit:
                    pass  # Continue to next document on failure
            elif once:
                console.print("[dim]No ideas to process[/dim]")
                break
            else:
                console.print(".", end="", style="dim")

            if once:
                break

            time.sleep(interval)
    else:
        # Legacy mode: process one stage at a time
        console.print("[cyan]Running cascade (one stage at a time)[/cyan]")
        if not once:
            console.print(f"[dim]Checking every {interval}s. Press Ctrl+C to stop.[/dim]")

        active_stages = [s for s in STAGES if s != "done"]

        while True:
            processed = False

            for stage in active_stages:
                stage_doc = cascade_db.get_oldest_at_stage(stage)
                if stage_doc:
                    console.print(f"\n[cyan]Found document at '{stage}'[/cyan]")
                    success, _, _ = _process_stage(dict(stage_doc), stage)
                    processed = True
                    break  # Process one at a time

            if once:
                if not processed:
                    console.print("[dim]No documents to process[/dim]")
                break

            if not processed:
                console.print(".", end="", style="dim")

            time.sleep(interval)


@app.command()
def advance(
    doc_id: int = typer.Argument(..., help="Document ID to advance"),
    to_stage: str | None = typer.Option(None, "--to", help="Target stage (default: next stage)"),
) -> None:
    """Manually advance a document to the next stage.

    Useful for testing or when you want to skip processing.

    Examples:
        emdx cascade advance 123
        emdx cascade advance 123 --to done
    """
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    current_stage = doc.get("stage")
    if not current_stage:
        console.print(f"[red]Document #{doc_id} is not in the cascade[/red]")
        raise typer.Exit(1)

    if to_stage:
        if to_stage not in STAGES:
            console.print(f"[red]Invalid stage: {to_stage}. Must be one of: {STAGES}[/red]")
            raise typer.Exit(1)
        new_stage = to_stage
    else:
        if current_stage == "done":
            console.print("[yellow]Document is already at 'done' stage[/yellow]")
            return
        new_stage = NEXT_STAGE.get(current_stage, "done")

    cascade_db.update_cascade_stage(doc_id, new_stage)
    console.print(f"[green]✓[/green] Moved document #{doc_id}: {current_stage} → {new_stage}")


@app.command()
def remove(
    doc_id: int = typer.Argument(..., help="Document ID to remove from cascade"),
) -> None:
    """Remove a document from the cascade (keeps the document).

    Sets the stage to NULL, removing it from cascade processing
    but keeping the document in the knowledge base.
    """
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    if not doc.get("stage"):
        console.print(f"[yellow]Document #{doc_id} is not in the cascade[/yellow]")
        return

    cascade_db.remove_from_cascade(doc_id)
    console.print(f"[green]✓[/green] Removed document #{doc_id} from cascade")


@app.command()
def synthesize(
    stage: str = typer.Argument(..., help="Stage to synthesize from (e.g., 'analyzed')"),
    title: str | None = typer.Option(None, "--title", "-t", help="Title for synthesized document"),
    next_stage: str = typer.Option("planned", "--next", "-n", help="Stage for the synthesized doc"),
    keep: bool = typer.Option(False, "--keep", "-k", help="Keep source docs in current stage"),
) -> None:
    """Combine multiple documents at a stage into one synthesized document.

    This is useful when you want to analyze multiple ideas separately,
    then combine them into a single plan.

    Examples:
        # Combine all analyzed docs into one planned doc
        emdx cascade synthesize analyzed

        # Combine with custom title
        emdx cascade synthesize analyzed --title "Combined Analysis"

        # Keep source docs (don't advance them to done)
        emdx cascade synthesize analyzed --keep
    """
    docs = cascade_db.list_documents_at_stage(stage)

    if not docs:
        console.print(f"[yellow]No documents at stage '{stage}' to synthesize[/yellow]")
        return

    if len(docs) == 1:
        console.print(f"[yellow]Only 1 document at '{stage}' - nothing to synthesize[/yellow]")
        console.print("Use 'advance' to move it forward, or add more documents first.")
        return

    console.print(f"[cyan]Synthesizing {len(docs)} documents from '{stage}':[/cyan]")
    for doc in docs:
        console.print(f"  #{doc['id']}: {doc['title'][:50]}")

    # Build combined content
    combined_content = f"# Synthesized from {len(docs)} documents\n\n"
    for doc in docs:
        full_doc = get_document(str(doc["id"]))
        if not full_doc:
            continue
        combined_content += f"## From: {full_doc['title']}\n\n"
        combined_content += full_doc["content"]
        combined_content += "\n\n---\n\n"

    # Create the synthesized document
    doc_title = title or f"Synthesis: {len(docs)} {stage} documents"
    new_doc_id = cascade_db.save_document_to_cascade(
        title=doc_title,
        content=combined_content,
        stage=next_stage,
    )

    console.print(f"\n[green]✓[/green] Created synthesized document #{new_doc_id} at '{next_stage}'")  # noqa: E501

    # Optionally advance source docs to done
    if not keep:
        for doc in docs:
            cascade_db.update_cascade_stage(doc["id"], "done")
        console.print(f"[dim]Moved {len(docs)} source documents to 'done'[/dim]")
    else:
        console.print(f"[dim]Kept {len(docs)} source documents at '{stage}'[/dim]")


@app.command()
def runs(
    limit: int = typer.Option(10, "--limit", "-n", help="Max runs to show"),
    status_filter: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """Show cascade run history."""
    query = "SELECT id, start_doc_id, start_stage, stop_stage, current_stage, status, pr_url, started_at, completed_at FROM cascade_runs"  # noqa: E501
    params: list[str | int] = []

    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    with db_connection.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        console.print("[dim]No cascade runs found[/dim]")
        return

    table = Table(title="Cascade Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Doc", style="dim")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("PR")
    table.add_column("Started")

    for row in rows:
        run_id, start_doc, start_stage, stop_stage, current_stage, status, pr_url, started, completed = row  # noqa: E501

        path = f"{start_stage}→{stop_stage}"
        if status == "running":
            path += f" (at {current_stage})"

        status_style = {
            "running": "yellow",
            "completed": "green",
            "failed": "red",
            "paused": "dim",
        }.get(status, "white")

        pr_display = "🔗" if pr_url else ""
        if started:
            started_str = started.strftime("%Y-%m-%d %H:%M") if hasattr(started, 'strftime') else str(started)[:16]  # noqa: E501
        else:
            started_str = ""

        table.add_row(
            str(run_id),
            str(start_doc),
            path,
            f"[{status_style}]{status}[/{status_style}]",
            pr_display,
            started_str,
        )

    console.print(table)
