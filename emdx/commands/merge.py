"""
Document merging commands for EMDX.
Intelligently merge related or duplicate documents.
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.columns import Columns
from rich import box
from typing import Optional, List
import difflib

from ..services.document_merger import DocumentMerger, MergeStrategy
from ..models.documents import get_document
from ..models.tags import get_document_tags
from ..ui.formatting import format_tags

app = typer.Typer()
console = Console()


def _display_merge_candidate(candidate):
    """Display a merge candidate nicely."""
    console.print(f"\n[yellow]Similarity: {candidate.similarity_score:.0%}[/yellow]")
    console.print(f"[cyan]Reason:[/cyan] {candidate.merge_reason}")
    console.print(f"[dim]Recommendation:[/dim] {candidate.recommended_action}")
    
    # Show both documents
    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column(f"Document #{candidate.doc1_id}", style="cyan", width=40)
    table.add_column(f"Document #{candidate.doc2_id}", style="cyan", width=40)
    
    table.add_row(candidate.doc1_title, candidate.doc2_title)
    console.print(table)


def _display_merge_preview(strategy: MergeStrategy):
    """Display a preview of what the merge will do."""
    keep_doc = get_document(str(strategy.keep_doc_id))
    merge_doc = get_document(str(strategy.merge_doc_id))
    
    console.print("\n[bold cyan]📋 Merge Preview[/bold cyan]\n")
    
    # Action summary
    console.print(f"[green]✓ Keep:[/green] #{strategy.keep_doc_id}: {keep_doc['title']}")
    console.print(f"[red]✗ Delete:[/red] #{strategy.merge_doc_id}: {merge_doc['title']}")
    
    # Title change
    if keep_doc['title'] != strategy.merged_title:
        console.print(f"\n[yellow]Title will change to:[/yellow] {strategy.merged_title}")
    
    # Tags
    keep_tags = set(get_document_tags(strategy.keep_doc_id))
    merge_tags = set(get_document_tags(strategy.merge_doc_id))
    new_tags = merge_tags - keep_tags
    
    if new_tags:
        console.print(f"\n[yellow]New tags will be added:[/yellow] {format_tags(list(new_tags))}")
    
    # Content preview
    if keep_doc['content'] != strategy.merged_content:
        console.print("\n[yellow]Content will be merged[/yellow]")
        
        # Show a diff preview (first 500 chars)
        diff = difflib.unified_diff(
            (keep_doc['content'] or '')[:500].splitlines(keepends=True),
            strategy.merged_content[:500].splitlines(keepends=True),
            fromfile=f"Current #{strategy.keep_doc_id}",
            tofile="After merge",
            n=3
        )
        
        diff_text = ''.join(diff)
        if diff_text:
            console.print(Panel(diff_text, title="Content Changes Preview", box=box.ROUNDED))


@app.command()
def find(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    threshold: float = typer.Option(0.7, "--threshold", "-t", help="Similarity threshold (0-1)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum candidates to show"),
):
    """Find documents that are candidates for merging."""
    
    merger = DocumentMerger()
    
    with console.status("[bold green]Analyzing documents for merge candidates..."):
        candidates = merger.find_merge_candidates(
            project=project,
            similarity_threshold=threshold
        )
    
    if not candidates:
        console.print("[green]✨ No merge candidates found![/green]")
        console.print(f"[dim]No documents with >{threshold:.0%} similarity[/dim]")
        return
    
    # Display results
    console.print(f"\n[bold cyan]🔀 Found {len(candidates)} merge candidates[/bold cyan]")
    
    for i, candidate in enumerate(candidates[:limit], 1):
        console.print(f"\n[bold]Candidate #{i}[/bold]")
        _display_merge_candidate(candidate)
    
    if len(candidates) > limit:
        console.print(f"\n[dim]... and {len(candidates) - limit} more candidates[/dim]")
    
    # Suggest next action
    console.print("\n[dim]To merge documents, use:[/dim]")
    console.print(f"[dim]emdx merge docs DOC1_ID DOC2_ID[/dim]")


@app.command()
def docs(
    doc1_id: int = typer.Argument(..., help="First document ID"),
    doc2_id: int = typer.Argument(..., help="Second document ID"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Execute the merge"),
    strategy: str = typer.Option("auto", "--strategy", "-s", help="Merge strategy: auto, keep-first, keep-second"),
):
    """Merge two specific documents."""
    
    merger = DocumentMerger()
    
    # Get merge strategy
    with console.status("[bold green]Analyzing documents..."):
        try:
            merge_strategy = merger.suggest_merge_strategy(doc1_id, doc2_id)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
    
    # Apply strategy preference
    if strategy == "keep-first" and merge_strategy.keep_doc_id != doc1_id:
        # Swap the strategy
        merge_strategy.keep_doc_id, merge_strategy.merge_doc_id = merge_strategy.merge_doc_id, merge_strategy.keep_doc_id
    elif strategy == "keep-second" and merge_strategy.keep_doc_id != doc2_id:
        # Swap the strategy
        merge_strategy.keep_doc_id, merge_strategy.merge_doc_id = merge_strategy.merge_doc_id, merge_strategy.keep_doc_id
    
    # Display preview
    _display_merge_preview(merge_strategy)
    
    if not execute:
        console.print("\n[yellow]🔍 DRY RUN MODE - No changes made[/yellow]")
        console.print("[dim]Run with --execute to perform the merge[/dim]")
        return
    
    # Confirm merge
    if not Confirm.ask("\n🔀 Proceed with merge?"):
        console.print("[red]Merge cancelled[/red]")
        return
    
    # Execute merge
    with console.status("[bold green]Merging documents..."):
        success = merger.execute_merge(merge_strategy)
    
    if success:
        console.print(f"\n[green]✅ Successfully merged documents![/green]")
        console.print(f"[dim]Document #{merge_strategy.merge_doc_id} has been merged into #{merge_strategy.keep_doc_id}[/dim]")
    else:
        console.print("[red]❌ Merge failed! Check logs for details.[/red]")


@app.command()
def related(
    doc_id: int = typer.Argument(..., help="Document ID to find related documents for"),
    limit: int = typer.Option(5, "--limit", "-n", help="Maximum related documents to show"),
):
    """Find documents related to a specific document."""
    
    merger = DocumentMerger()
    
    # Get the document
    doc = get_document(str(doc_id))
    if not doc:
        console.print(f"[red]Error: Document #{doc_id} not found[/red]")
        raise typer.Exit(1)
    
    with console.status("[bold green]Finding related documents..."):
        related = merger.find_related_documents(doc_id, limit=limit)
    
    if not related:
        console.print(f"[yellow]No related documents found for #{doc_id}[/yellow]")
        return
    
    # Display results
    console.print(f"\n[bold cyan]📎 Documents related to #{doc_id}: {doc['title']}[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Title", style="cyan")
    table.add_column("Similarity", justify="center")
    table.add_column("Action", style="dim")
    
    for rel_id, rel_title, score in related:
        table.add_row(
            str(rel_id),
            rel_title[:50] + "..." if len(rel_title) > 50 else rel_title,
            f"{score:.0%}",
            f"merge docs {doc_id} {rel_id}"
        )
    
    console.print(table)


@app.command()
def batch(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    threshold: float = typer.Option(0.8, "--threshold", "-t", help="Similarity threshold (0-1)"),
    auto_approve: bool = typer.Option(False, "--auto", "-a", help="Auto-approve merges (dangerous!)"),
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute merges (default: dry run)"),
):
    """Batch merge highly similar documents."""
    
    merger = DocumentMerger()
    
    with console.status("[bold green]Finding merge candidates..."):
        candidates = merger.find_merge_candidates(
            project=project,
            similarity_threshold=threshold
        )
    
    if not candidates:
        console.print("[green]✨ No documents to merge![/green]")
        return
    
    # Filter to only very high confidence merges
    high_confidence = [c for c in candidates if c.similarity_score >= threshold]
    
    console.print(f"\n[bold cyan]🔀 Batch Merge Report[/bold cyan]")
    console.print(f"Found {len(high_confidence)} high-confidence merge candidates (>{threshold:.0%} similar)\n")
    
    if dry_run:
        # Show what would be merged
        for i, candidate in enumerate(high_confidence[:10], 1):
            console.print(f"[yellow]Would merge:[/yellow]")
            console.print(f"  • #{candidate.doc1_id}: {candidate.doc1_title[:40]}...")
            console.print(f"  • #{candidate.doc2_id}: {candidate.doc2_title[:40]}...")
            console.print(f"  [dim]Similarity: {candidate.similarity_score:.0%}[/dim]\n")
        
        if len(high_confidence) > 10:
            console.print(f"[dim]... and {len(high_confidence) - 10} more[/dim]\n")
        
        console.print("[yellow]🔍 DRY RUN MODE - No changes made[/yellow]")
        console.print("[dim]Run with --execute to perform merges[/dim]")
        return
    
    # Confirm batch merge
    if not auto_approve:
        if not Confirm.ask(f"\n🔀 Merge {len(high_confidence)} document pairs?"):
            console.print("[red]Batch merge cancelled[/red]")
            return
    
    # Execute merges
    success_count = 0
    failed_count = 0
    
    with console.status("[bold green]Executing merges...") as status:
        for i, candidate in enumerate(high_confidence, 1):
            status.update(f"[bold green]Merging {i}/{len(high_confidence)}...")
            
            try:
                # Get merge strategy
                strategy = merger.suggest_merge_strategy(candidate.doc1_id, candidate.doc2_id)
                
                # Execute
                if merger.execute_merge(strategy):
                    success_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                console.print(f"[red]Failed to merge #{candidate.doc1_id} and #{candidate.doc2_id}: {e}[/red]")
    
    # Report results
    console.print(f"\n[bold]Batch Merge Complete![/bold]")
    console.print(f"[green]✅ Successfully merged: {success_count} pairs[/green]")
    if failed_count > 0:
        console.print(f"[red]❌ Failed: {failed_count} pairs[/red]")


if __name__ == "__main__":
    app()