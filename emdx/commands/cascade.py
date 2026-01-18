"""Cascade - autonomous document transformation pipeline.

Cascade transforms raw ideas into working code through a series of stages:
idea → prompt → analyzed → planned → done

Each stage refines the document using Claude, with the final stage
actually implementing the code and creating a pull request.

Key concepts:
- Inevitable flow: Once an idea enters, it cascades through to completion
- Stage transformation: Each stage adds structure and refinement
- Autonomous execution: Claude handles the heavy lifting at each stage
- Auto mode: End-to-end processing with `--auto` flag
"""

import time
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..database.documents import (
    get_document,
    get_oldest_at_stage,
    get_cascade_stats,
    list_documents_at_stage,
    save_document_to_cascade,
    update_document_stage,
)
from ..database import cascade as cascade_db
from ..services.claude_executor import execute_claude_detached
from ..database.connection import db_connection

console = Console()

app = typer.Typer(help="Cascade ideas through stages to working code")

# Fixed cascade stages
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_PROMPTS = {
    "idea": """Convert this idea into a well-formed prompt that could be given to an AI assistant.

IMPORTANT: Do NOT create any files. Just output the prompt text directly - your output will be captured automatically.

Idea to convert:
{content}""",
    "prompt": """Analyze this prompt thoroughly. Consider:
- What is being asked?
- What are the requirements (explicit and implicit)?
- What are potential challenges or edge cases?
- What context or information is needed?

IMPORTANT: Do NOT create any files. Just output your analysis directly - your output will be captured automatically.

Prompt to analyze:
{content}""",
    "analyzed": """Based on this analysis, create a detailed implementation gameplan. Include:
- Step-by-step implementation plan
- Files that need to be modified
- Key design decisions
- Testing approach
- Potential risks

IMPORTANT: Do NOT create any files (no GAMEPLAN.md, no markdown files). Just output the gameplan directly as text - your output will be captured automatically and saved to the knowledge base.

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


@app.command()
def add(
    content: str = typer.Argument(..., help="The idea content to add to the cascade"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Document title"),
    stage: str = typer.Option("idea", "--stage", "-s", help="Starting stage"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically process through all stages"),
    sync: bool = typer.Option(False, "--sync", help="Wait for each stage completion (implies --auto)"),
):
    """Add a new document to the cascade.

    Examples:
        emdx cascade add "Build a REST API for user management"
        emdx cascade add "Add dark mode to the app" --title "Dark Mode Feature"
        emdx cascade add "Quick fix" --auto
        emdx cascade add "Complex feature" --auto --sync
    """
    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    # Sync implies auto
    if sync:
        auto = True

    doc_title = title or f"Cascade: {content[:50]}..."
    doc_id = save_document_to_cascade(
        title=doc_title,
        content=content,
        stage=stage,
    )
    console.print(f"[green]✓[/green] Added document #{doc_id} at stage '{stage}'")

    # If auto mode, process through all stages
    if auto:
        console.print("[cyan]Auto mode enabled - processing through all stages[/cyan]")
        _run_auto(doc_id, sync)


@app.command()
def status():
    """Show cascade status - documents at each stage."""
    stats = get_cascade_stats()

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
        console.print("\n[dim]Cascade is empty. Add ideas with: emdx cascade add \"your idea\"[/dim]")


@app.command()
def show(
    stage: str = typer.Argument(..., help="Stage to show documents from"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to show"),
):
    """Show documents at a specific stage."""
    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    docs = list_documents_at_stage(stage, limit=limit)

    if not docs:
        console.print(f"[dim]No documents at stage '{stage}'[/dim]")
        return

    table = Table(title=f"Documents at '{stage}'")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Created")

    for doc in docs:
        created = doc["created_at"].strftime("%Y-%m-%d %H:%M") if doc.get("created_at") else ""
        table.add_row(str(doc["id"]), doc["title"][:60], created)

    console.print(table)


@app.command()
def process(
    stage: str = typer.Argument(..., help="Stage to process"),
    doc_id: Optional[int] = typer.Option(None, "--doc", "-d", help="Specific document ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
    sync: bool = typer.Option(False, "--sync", "-s", help="Wait for completion before advancing"),
):
    """Process one document at a stage.

    Picks up the oldest document at the given stage, runs it through Claude,
    and advances it to the next stage.

    Examples:
        emdx cascade process idea
        emdx cascade process prompt --doc 123
        emdx cascade process analyzed --dry-run
    """
    # Validate stage
    if stage == "done":
        console.print("[yellow]'done' is a terminal stage - nothing to process[/yellow]")
        raise typer.Exit(1)

    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    # Check if this stage has a prompt (terminal stages don't)
    stage_prompt = STAGE_PROMPTS.get(stage)
    if not stage_prompt:
        console.print(f"[yellow]Stage '{stage}' has no processing prompt[/yellow]")
        raise typer.Exit(1)

    # Get document to process
    if doc_id:
        doc = get_document(str(doc_id))
        if not doc:
            console.print(f"[red]Document #{doc_id} not found[/red]")
            raise typer.Exit(1)
        if doc.get("stage") != stage:
            console.print(f"[red]Document #{doc_id} is at stage '{doc.get('stage')}', not '{stage}'[/red]")
            raise typer.Exit(1)
    else:
        doc = get_oldest_at_stage(stage)
        if not doc:
            console.print(f"[dim]No documents waiting at stage '{stage}'[/dim]")
            return

    doc_id = doc["id"]
    next_stage = NEXT_STAGE.get(stage)

    console.print(f"[cyan]Processing #{doc_id}: {doc['title'][:50]}[/cyan]")
    console.print(f"  Stage: {stage} → {next_stage}")

    if dry_run:
        console.print("[yellow]Dry run - skipping execution[/yellow]")
        return

    # Build the prompt
    prompt = stage_prompt.format(content=doc["content"])

    # Special messaging for implementation stages
    if next_stage == "done" or stage == "planned":
        console.print("[bold yellow]⚡ Implementation mode - Claude will write code and create a PR[/bold yellow]")
        console.print("[dim]Note: This may take up to 30 minutes[/dim]")

    # Create execution record
    from datetime import datetime
    from pathlib import Path

    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"cascade_{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Record execution in database
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO executions (doc_id, doc_title, status, started_at, log_file)
            VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?)
            """,
            (doc_id, doc["title"], str(log_file)),
        )
        conn.commit()
        execution_id = cursor.lastrowid

    try:
        if sync:
            # Synchronous execution - wait for completion
            from ..services.claude_executor import execute_claude_sync
            console.print("[cyan]Running synchronously (waiting for completion)...[/cyan]")

            # Implementation stage (next is done) needs much longer timeout (30 min vs 5 min default)
            timeout = 1800 if next_stage == "done" or stage == "planned" else 300

            result = execute_claude_sync(
                task=prompt,
                execution_id=execution_id,
                log_file=log_file,
                doc_id=str(doc_id),
                timeout=timeout,
            )

            if result.get("success"):
                # Create a new child document with Claude's output
                output = result.get("output", "")
                if output:
                    from ..database.documents import save_document, update_document_pr_url
                    import re

                    # For planned stage, extract PR URL from output
                    pr_url = None
                    if stage == "planned":
                        # Look for PR_URL: pattern in the output
                        pr_match = re.search(r'PR_URL:\s*(https://github\.com/[^\s]+)', output)
                        if pr_match:
                            pr_url = pr_match.group(1)
                            console.print(f"[bold green]🔗 PR Created: {pr_url}[/bold green]")

                    # Create child doc with stage info in title
                    child_title = f"{doc['title']} [{stage}→{next_stage}]"
                    child_id = save_document(
                        title=child_title,
                        content=output,
                        project=doc.get("project"),
                        parent_id=doc_id,
                    )
                    # Set the child's stage to the next stage
                    update_document_stage(child_id, next_stage)
                    console.print(f"[green]✓[/green] Created child document #{child_id} ({len(output)} chars)")

                    # If we have a PR URL, store it on both the child and original doc
                    if pr_url:
                        update_document_pr_url(child_id, pr_url)
                        update_document_pr_url(doc_id, pr_url)
                        console.print(f"[green]✓[/green] Linked PR URL to documents")

                    # Mark original as done (it spawned a child)
                    update_document_stage(doc_id, "done")
                    console.print(f"[green]✓[/green] Completed processing")
                    console.print(f"  Original #{doc_id} → done")
                    console.print(f"  Child #{child_id} → {next_stage}")
                else:
                    # No output - just advance the original
                    update_document_stage(doc_id, next_stage)
                    console.print(f"[green]✓[/green] Completed (no output)")
                    console.print(f"  Document #{doc_id} → {next_stage}")

                # Mark execution as completed
                with db_connection.get_connection() as conn:
                    conn.execute(
                        "UPDATE executions SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (execution_id,),
                    )
                    conn.commit()
            else:
                console.print(f"[red]Processing failed - document stays at '{stage}'[/red]")
                with db_connection.get_connection() as conn:
                    conn.execute(
                        "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (execution_id,),
                    )
                    conn.commit()
        else:
            # Async execution - start and return immediately
            # Document stays at current stage until manually advanced
            pid = execute_claude_detached(
                task=prompt,
                execution_id=execution_id,
                log_file=log_file,
                doc_id=str(doc_id),
            )

            console.print(f"[green]✓[/green] Started processing (PID: {pid})")
            console.print(f"  Execution #{execution_id}")
            console.print(f"  [yellow]Document stays at '{stage}' until manually advanced[/yellow]")
            console.print(f"  Use 'emdx cascade advance {doc_id}' after completion")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        # Mark execution as failed
        with db_connection.get_connection() as conn:
            conn.execute(
                "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (execution_id,),
            )
            conn.commit()
        raise typer.Exit(1)


@app.command()
def run(
    once: bool = typer.Option(False, "--once", help="Run one iteration then exit"),
    stages: Optional[str] = typer.Option(None, "--stages", help="Comma-separated stages to process"),
    interval: float = typer.Option(5.0, "--interval", "-i", help="Seconds between checks"),
):
    """Run the cascade continuously.

    Watches all stages and processes documents as they become available.
    This is the minimal daemon - just a simple loop.

    Examples:
        emdx cascade run --once
        emdx cascade run --stages idea,prompt
        emdx cascade run --interval 10
    """
    # Filter to processable stages (those with prompts, excluding terminal stage)
    processable = [s for s in STAGES if STAGE_PROMPTS.get(s)]

    active_stages = stages.split(",") if stages else processable

    # Validate stages
    for stage in active_stages:
        if stage not in STAGES:
            console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
            raise typer.Exit(1)

    console.print(f"[cyan]Starting cascade for stages: {active_stages}[/cyan]")
    if not once:
        console.print(f"[dim]Checking every {interval}s. Press Ctrl+C to stop.[/dim]")

    iteration = 0
    while True:
        iteration += 1
        processed = False

        for stage in active_stages:
            doc = get_oldest_at_stage(stage)
            if doc:
                console.print(f"\n[cyan]Found document at '{stage}'[/cyan]")
                # Use invoke to call the process command
                ctx = typer.Context(app)
                process(stage=stage, doc_id=None, dry_run=False, sync=False)
                processed = True

        if once:
            if not processed:
                console.print("[dim]No documents to process[/dim]")
            break

        if not processed:
            # Show a dot to indicate we're alive but idle
            console.print(".", end="", style="dim")

        time.sleep(interval)


@app.command()
def advance(
    doc_id: int = typer.Argument(..., help="Document ID to advance"),
    to_stage: Optional[str] = typer.Option(None, "--to", help="Target stage (default: next stage)"),
):
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
        new_stage = NEXT_STAGE.get(current_stage) or "done"

    update_document_stage(doc_id, new_stage)
    console.print(f"[green]✓[/green] Moved document #{doc_id}: {current_stage} → {new_stage}")


@app.command()
def remove(
    doc_id: int = typer.Argument(..., help="Document ID to remove from cascade"),
):
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

    update_document_stage(doc_id, None)
    console.print(f"[green]✓[/green] Removed document #{doc_id} from cascade")


@app.command()
def synthesize(
    stage: str = typer.Argument(..., help="Stage to synthesize from (e.g., 'analyzed')"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Title for synthesized document"),
    next_stage: str = typer.Option("planned", "--next", "-n", help="Stage for the synthesized doc"),
    keep: bool = typer.Option(False, "--keep", "-k", help="Keep source docs in current stage"),
):
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
    docs = list_documents_at_stage(stage)

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
        combined_content += f"## From: {full_doc['title']}\n\n"
        combined_content += full_doc["content"]
        combined_content += "\n\n---\n\n"

    # Create the synthesized document
    doc_title = title or f"Synthesis: {len(docs)} {stage} documents"
    new_doc_id = save_document_to_cascade(
        title=doc_title,
        content=combined_content,
        stage=next_stage,
    )

    console.print(f"\n[green]✓[/green] Created synthesized document #{new_doc_id} at '{next_stage}'")

    # Optionally advance source docs to done
    if not keep:
        for doc in docs:
            update_document_stage(doc["id"], "done")
        console.print(f"[dim]Moved {len(docs)} source documents to 'done'[/dim]")
    else:
        console.print(f"[dim]Kept {len(docs)} source documents at '{stage}'[/dim]")


def _run_auto(doc_id: int, sync: bool):
    """Run automatic processing through all stages.

    This is the core auto-mode logic that processes a document
    through the cascade until it reaches the terminal stage.

    Args:
        doc_id: Document ID to process
        sync: Whether to run synchronously (wait for each stage)
    """
    from ..database.documents import save_document, update_document_pr_url
    from ..services.claude_executor import execute_claude_sync
    from datetime import datetime
    from pathlib import Path
    import re

    # Create cascade run record for activity grouping
    try:
        run_id = cascade_db.create_cascade_run(doc_id)
        console.print(f"[dim]Created cascade run #{run_id}[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not create cascade run: {e}[/yellow]")
        run_id = None

    # Get current document
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        return

    current_stage = doc.get("stage", "idea")
    current_doc_id = doc_id
    current_content = doc["content"]
    current_title = doc["title"]

    # Process through stages
    while True:
        # Check if we have a prompt for this stage
        stage_prompt = STAGE_PROMPTS.get(current_stage)
        next_stage = NEXT_STAGE.get(current_stage)

        # If no next stage, we're done
        if not next_stage:
            console.print(f"[green]✓ Cascade complete - document at '{current_stage}'[/green]")
            break

        # If no prompt, skip to next stage
        if not stage_prompt:
            console.print(f"[yellow]Stage '{current_stage}' has no prompt, advancing...[/yellow]")
            update_document_stage(current_doc_id, next_stage)
            current_stage = next_stage
            continue

        console.print(f"\n[cyan]Processing stage: {current_stage} → {next_stage}[/cyan]")

        # Update cascade run stage
        if run_id:
            try:
                cascade_db.update_cascade_run_stage(run_id, current_stage)
            except Exception:
                pass

        # Build prompt
        prompt = stage_prompt.format(content=current_content)

        # Special messaging for implementation stage
        if next_stage == "done":
            console.print("[bold yellow]⚡ Implementation mode - Claude will write code and create a PR[/bold yellow]")

        # Create log file
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"cascade_{current_doc_id}_{current_stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Create execution record
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO executions (doc_id, doc_title, status, started_at, log_file, cascade_run_id)
                VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?, ?)
                """,
                (current_doc_id, current_title, str(log_file), run_id),
            )
            conn.commit()
            execution_id = cursor.lastrowid

        # Link execution to run
        if run_id:
            try:
                cascade_db.link_execution_to_run(execution_id, run_id)
            except Exception:
                pass

        try:
            if sync:
                # Implementation stage needs longer timeout
                timeout = 1800 if next_stage == "done" else 300

                result = execute_claude_sync(
                    task=prompt,
                    execution_id=execution_id,
                    log_file=log_file,
                    doc_id=str(current_doc_id),
                    timeout=timeout,
                )

                if result.get("success"):
                    output = result.get("output", "")

                    # Mark execution completed
                    with db_connection.get_connection() as conn:
                        conn.execute(
                            "UPDATE executions SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (execution_id,),
                        )
                        conn.commit()

                    if output:
                        # Extract PR URL if present
                        pr_url = None
                        if next_stage == "done":
                            pr_match = re.search(r'PR_URL:\s*(https://github\.com/[^\s]+)', output)
                            if pr_match:
                                pr_url = pr_match.group(1)
                                console.print(f"[bold green]🔗 PR Created: {pr_url}[/bold green]")

                        # Create child document with output
                        child_title = f"{current_title} [{current_stage}→{next_stage}]"
                        child_id = save_document(
                            title=child_title,
                            content=output,
                            project=doc.get("project"),
                            parent_id=current_doc_id,
                        )
                        update_document_stage(child_id, next_stage)

                        if pr_url:
                            update_document_pr_url(child_id, pr_url)
                            update_document_pr_url(current_doc_id, pr_url)

                        # Mark original as done
                        update_document_stage(current_doc_id, "done")
                        console.print(f"[green]✓[/green] Created #{child_id}, advancing to '{next_stage}'")

                        # Continue with child document
                        current_doc_id = child_id
                        current_content = output
                        current_title = child_title
                        current_stage = next_stage
                    else:
                        # No output - advance original
                        update_document_stage(current_doc_id, next_stage)
                        current_stage = next_stage
                        console.print(f"[green]✓[/green] Advanced to '{next_stage}'")
                else:
                    console.print(f"[red]Processing failed at '{current_stage}'[/red]")
                    with db_connection.get_connection() as conn:
                        conn.execute(
                            "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (execution_id,),
                        )
                        conn.commit()
                    # Mark run as failed
                    if run_id:
                        try:
                            cascade_db.complete_cascade_run(run_id, success=False, error_msg=f"Failed at stage {current_stage}")
                        except Exception:
                            pass
                    break
            else:
                # Async mode - just start the first stage and exit
                pid = execute_claude_detached(
                    task=prompt,
                    execution_id=execution_id,
                    log_file=log_file,
                    doc_id=str(current_doc_id),
                )
                console.print(f"[green]✓[/green] Started processing (PID: {pid})")
                console.print("[yellow]Auto mode without --sync only starts the first stage[/yellow]")
                console.print("Use --sync for end-to-end processing, or manually advance stages")
                break

        except Exception as e:
            console.print(f"[red]Error at '{current_stage}': {e}[/red]")
            with db_connection.get_connection() as conn:
                conn.execute(
                    "UPDATE executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (execution_id,),
                )
                conn.commit()
            if run_id:
                try:
                    cascade_db.complete_cascade_run(run_id, success=False, error_msg=str(e))
                except Exception:
                    pass
            break

    # Mark run as completed if we finished successfully
    if run_id and current_stage == "done":
        try:
            cascade_db.complete_cascade_run(run_id, success=True)
        except Exception:
            pass
