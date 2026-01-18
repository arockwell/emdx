"""Streaming pipeline commands for emdx.

This module implements the minimal Gas Town-style streaming pipeline where
documents flow through stages: idea → prompt → analyzed → planned → done.

Key concepts:
- Status-as-queue: The stage column acts as a queue indicator
- Streaming: Items flow independently through stages (concurrency, not batch)
- Sessionless: Python owns the loop, Claude sessions are disposable compute
"""

import time
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..database.documents import (
    get_document,
    get_oldest_at_stage,
    get_pipeline_stats,
    list_documents_at_stage,
    save_document_to_pipeline,
    update_document_stage,
)
from ..services.claude_executor import execute_claude_detached
from ..database.connection import db_connection

console = Console()

app = typer.Typer(help="Streaming document pipeline")

# Stage configuration
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_PROMPTS = {
    "idea": "Convert this idea into a well-formed prompt that could be given to an AI assistant: {content}",
    "prompt": "Analyze this prompt and provide a thorough analysis: {content}",
    "analyzed": "Based on this analysis, create a detailed implementation gameplan: {content}",
    # planned stage uses a special implementation prompt - see process command
}
NEXT_STAGE = {
    "idea": "prompt",
    "prompt": "analyzed",
    "analyzed": "planned",
    "planned": "done",
}

# Special prompt for planned→done that actually implements and creates a PR
IMPLEMENTATION_PROMPT = """You are implementing a feature based on the gameplan below.

IMPORTANT INSTRUCTIONS:
1. Implement the gameplan by writing actual code
2. Create a new git branch for this work
3. Make commits as you go
4. When done, create a Pull Request using `gh pr create`
5. At the very end of your response, output the PR URL on its own line in this exact format:
   PR_URL: https://github.com/...

Here is the gameplan to implement:

{content}
"""


@app.command()
def add(
    content: str = typer.Argument(..., help="The idea content to add to the pipeline"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Document title"),
    stage: str = typer.Option("idea", "--stage", "-s", help="Starting stage"),
):
    """Add a new document to the pipeline.

    Examples:
        emdx pipeline add "Build a REST API for user management"
        emdx pipeline add "Add dark mode to the app" --title "Dark Mode Feature"
    """
    if stage not in STAGES:
        console.print(f"[red]Invalid stage: {stage}. Must be one of: {STAGES}[/red]")
        raise typer.Exit(1)

    doc_title = title or f"Pipeline: {content[:50]}..."
    doc_id = save_document_to_pipeline(
        title=doc_title,
        content=content,
        stage=stage,
    )
    console.print(f"[green]✓[/green] Added document #{doc_id} at stage '{stage}'")


@app.command()
def status():
    """Show pipeline status - documents at each stage."""
    stats = get_pipeline_stats()

    table = Table(title="Pipeline Status")
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
        console.print(f"\nTotal documents in pipeline: {total}")
    else:
        console.print("\n[dim]Pipeline is empty. Add ideas with: emdx pipeline add \"your idea\"[/dim]")


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
        emdx pipeline process idea
        emdx pipeline process prompt --doc 123
        emdx pipeline process analyzed --dry-run
    """
    if stage not in STAGE_PROMPTS:
        if stage == "done":
            console.print("[yellow]'done' is a terminal stage - nothing to process[/yellow]")
        else:
            console.print(f"[red]Invalid stage: {stage}. Processable stages: {list(STAGE_PROMPTS.keys())}[/red]")
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
    next_stage = NEXT_STAGE[stage]

    console.print(f"[cyan]Processing #{doc_id}: {doc['title'][:50]}[/cyan]")
    console.print(f"  Stage: {stage} → {next_stage}")

    if dry_run:
        console.print("[yellow]Dry run - skipping execution[/yellow]")
        return

    # Build the prompt - special handling for planned stage (implementation)
    if stage == "planned":
        prompt = IMPLEMENTATION_PROMPT.format(content=doc["content"])
        console.print("[bold yellow]⚡ Implementation mode - Claude will write code and create a PR[/bold yellow]")
    else:
        prompt = STAGE_PROMPTS[stage].format(content=doc["content"])

    # Create execution record
    from datetime import datetime
    from pathlib import Path

    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline_{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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

            result = execute_claude_sync(
                task=prompt,
                execution_id=execution_id,
                log_file=log_file,
                doc_id=str(doc_id),
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
            console.print(f"  Use 'emdx pipeline advance {doc_id}' after completion")

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
    """Run the streaming pipeline continuously.

    Watches all stages and processes documents as they become available.
    This is the minimal daemon - just a simple loop.

    Examples:
        emdx pipeline run --once
        emdx pipeline run --stages idea,prompt
        emdx pipeline run --interval 10
    """
    active_stages = stages.split(",") if stages else list(STAGE_PROMPTS.keys())

    # Validate stages
    for stage in active_stages:
        if stage not in STAGE_PROMPTS:
            console.print(f"[red]Invalid stage: {stage}[/red]")
            raise typer.Exit(1)

    console.print(f"[cyan]Starting pipeline for stages: {active_stages}[/cyan]")
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
                process(stage=stage, doc_id=None, dry_run=False)
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
        emdx pipeline advance 123
        emdx pipeline advance 123 --to done
    """
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    current_stage = doc.get("stage")
    if not current_stage:
        console.print(f"[red]Document #{doc_id} is not in the pipeline[/red]")
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

    update_document_stage(doc_id, new_stage)
    console.print(f"[green]✓[/green] Moved document #{doc_id}: {current_stage} → {new_stage}")


@app.command()
def remove(
    doc_id: int = typer.Argument(..., help="Document ID to remove from pipeline"),
):
    """Remove a document from the pipeline (keeps the document).

    Sets the stage to NULL, removing it from pipeline processing
    but keeping the document in the knowledge base.
    """
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    if not doc.get("stage"):
        console.print(f"[yellow]Document #{doc_id} is not in the pipeline[/yellow]")
        return

    update_document_stage(doc_id, None)
    console.print(f"[green]✓[/green] Removed document #{doc_id} from pipeline")


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
        emdx pipeline synthesize analyzed

        # Combine with custom title
        emdx pipeline synthesize analyzed --title "Combined Analysis"

        # Keep source docs (don't advance them to done)
        emdx pipeline synthesize analyzed --keep
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
    new_doc_id = save_document_to_pipeline(
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
