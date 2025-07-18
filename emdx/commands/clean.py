"""
Cleanup commands for EMDX knowledge base maintenance.
Provides tools to remove duplicates, empty documents, and maintain quality.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import hashlib

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich import box

from ..config.settings import get_db_path
from ..services.duplicate_detector import DuplicateDetector

app = typer.Typer()
console = Console()


@app.command()
def empty(
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute cleanup (default: dry run only)"),
    threshold: int = typer.Option(10, "--threshold", "-t", help="Maximum character count to consider empty"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information")
):
    """Remove empty or near-empty documents from the knowledge base."""
    
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    with console.status("[bold green]Finding empty documents..."):
        # Find empty documents
        cursor.execute("""
            SELECT id, title, LENGTH(content) as length, project, access_count
            FROM documents
            WHERE is_deleted = 0
            AND LENGTH(content) < ?
            ORDER BY length, id
        """, (threshold,))
        
        empty_docs = cursor.fetchall()
    
    if not empty_docs:
        console.print("✨ [green]No empty documents found![/green]")
        return
    
    # Display findings
    console.print(f"\n[yellow]Found {len(empty_docs)} empty documents (< {threshold} characters)[/yellow]\n")
    
    if verbose or len(empty_docs) <= 20:
        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", no_wrap=False)
        table.add_column("Length", justify="right")
        table.add_column("Views", justify="right")
        table.add_column("Project", style="cyan")
        
        for doc in empty_docs[:20]:
            table.add_row(
                str(doc['id']),
                doc['title'][:50] + "..." if len(doc['title']) > 50 else doc['title'],
                str(doc['length']),
                str(doc['access_count']),
                doc['project'] or "[No Project]"
            )
        
        if len(empty_docs) > 20:
            table.add_row("...", f"and {len(empty_docs) - 20} more", "...", "...", "...")
        
        console.print(table)
    else:
        console.print(f"[dim]Use --verbose to see document details[/dim]")
    
    if dry_run:
        console.print("\n[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]")
        console.print(f"Would delete {len(empty_docs)} documents")
        console.print("\n[dim]Run with --execute to perform cleanup[/dim]")
    else:
        # Confirm deletion
        if not Confirm.ask(f"\n🗑️  Delete {len(empty_docs)} empty documents?"):
            console.print("[red]Cleanup cancelled[/red]")
            return
        
        # Perform deletion
        deleted_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Deleting empty documents...", total=len(empty_docs))
            
            for doc in empty_docs:
                cursor.execute("""
                    UPDATE documents 
                    SET is_deleted = 1, deleted_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), doc['id']))
                deleted_count += 1
                progress.update(task, advance=1)
        
        conn.commit()
        console.print(f"\n✅ [green]Successfully deleted {deleted_count} empty documents![/green]")
    
    conn.close()


@app.command()
def duplicates(
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute cleanup (default: dry run only)"),
    strategy: str = typer.Option("highest-views", "--strategy", "-s", 
                                help="Keep strategy: highest-views, newest, oldest"),
    show_diff: bool = typer.Option(False, "--diff", help="Show content differences"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Include near-duplicates (85%+ similar)"),
    threshold: float = typer.Option(0.85, "--threshold", "-t", help="Similarity threshold for fuzzy matching")
):
    """Find and remove duplicate documents based on content."""
    
    detector = DuplicateDetector()
    
    if fuzzy:
        # Find near-duplicates
        with console.status("[bold green]Detecting near-duplicates..."):
            near_dupes = detector.find_near_duplicates(threshold=threshold)
        
        if not near_dupes:
            console.print(f"✨ [green]No near-duplicate documents found (>{threshold:.0%} similar)![/green]")
            return
        
        # Convert to format similar to exact duplicates
        duplicates = []
        seen_pairs = set()
        
        for doc1, doc2, similarity in near_dupes:
            # Create a pair identifier to avoid duplicates
            pair_id = tuple(sorted([doc1['id'], doc2['id']]))
            if pair_id not in seen_pairs:
                seen_pairs.add(pair_id)
                # Create a group of 2 documents
                group = [doc1, doc2]
                # Add similarity info
                for doc in group:
                    doc['similarity'] = similarity
                duplicates.append(group)
    else:
        # Find exact duplicates
        with console.status("[bold green]Detecting duplicates..."):
            duplicates = detector.find_duplicates()
        
        if not duplicates:
            console.print("✨ [green]No duplicate documents found![/green]")
            return
    
    # Calculate stats
    total_dupes = sum(len(group) - 1 for group in duplicates)  # -1 to keep one
    space_saved = sum(
        sum(doc['content_length'] for doc in group[1:])  # Skip the one we'll keep
        for group in duplicates
    )
    
    # Display findings
    console.print(f"\n[yellow]Found {len(duplicates)} duplicate groups ({total_dupes} documents)[/yellow]")
    console.print(f"[dim]Space to be saved: {space_saved:,} characters[/dim]\n")
    
    # Show duplicate groups
    if verbose or len(duplicates) <= 10:
        for i, group in enumerate(duplicates[:10], 1):
            console.print(f"[bold]Group {i}[/bold] ({len(group)} copies):")
            
            # Sort by strategy
            sorted_group = detector.sort_by_strategy(group, strategy)
            
            # Create table for this group
            table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
            table.add_column("Action", style="bold")
            table.add_column("ID", style="dim")
            table.add_column("Title")
            table.add_column("Views", justify="right")
            table.add_column("Created")
            
            for j, doc in enumerate(sorted_group):
                action = "[green]KEEP[/green]" if j == 0 else "[red]DELETE[/red]"
                table.add_row(
                    action,
                    str(doc['id']),
                    doc['title'][:40] + "..." if len(doc['title']) > 40 else doc['title'],
                    str(doc['access_count']),
                    doc['created_at'][:10]
                )
            
            console.print(table)
            
            if show_diff and len(group) == 2:
                # Show content preview
                content = sorted_group[0]['content'][:100].replace('\n', ' ')
                console.print(f"[dim]Content: {content}...[/dim]\n")
            else:
                console.print()
    
    if len(duplicates) > 10:
        console.print(f"[dim]... and {len(duplicates) - 10} more groups[/dim]\n")
    
    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]")
        console.print(f"Would delete {total_dupes} duplicate documents")
        console.print(f"Would save {space_saved:,} characters")
        console.print("\n[dim]Run with --execute to perform cleanup[/dim]")
    else:
        # Get documents to delete
        docs_to_delete = detector.get_documents_to_delete(duplicates, strategy)
        
        # Confirm deletion
        if not Confirm.ask(f"\n🗑️  Delete {len(docs_to_delete)} duplicate documents?"):
            console.print("[red]Cleanup cancelled[/red]")
            return
        
        # Perform deletion
        deleted_count = detector.delete_documents(docs_to_delete)
        
        console.print(f"\n✅ [green]Successfully deleted {deleted_count} duplicate documents![/green]")
        console.print(f"[dim]Saved {space_saved:,} characters[/dim]")


@app.command()
def all(
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute cleanup (default: dry run only)"),
    interactive: bool = typer.Option(True, "--interactive/--batch", help="Interactive mode")
):
    """Run all cleanup operations in sequence."""
    
    console.print("[bold cyan]🧹 EMDX Cleanup Wizard[/bold cyan]\n")
    
    # Check for issues
    issues = []
    
    # Check empty documents
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM documents 
        WHERE is_deleted = 0 AND LENGTH(content) < 10
    """)
    empty_count = cursor.fetchone()[0]
    if empty_count > 0:
        issues.append(('empty', f"{empty_count} empty documents"))
    
    # Check duplicates
    detector = DuplicateDetector()
    duplicates = detector.find_duplicates()
    if duplicates:
        dupe_count = sum(len(group) - 1 for group in duplicates)
        issues.append(('duplicates', f"{dupe_count} duplicate documents"))
    
    # Check untagged
    cursor.execute("""
        SELECT COUNT(*) FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
    """)
    untagged_count = cursor.fetchone()[0]
    if untagged_count > 10:  # Only if significant
        issues.append(('untagged', f"{untagged_count} untagged documents"))
    
    conn.close()
    
    if not issues:
        console.print("✨ [green]Your knowledge base is already clean![/green]")
        return
    
    # Display issues
    console.print("[yellow]Found the following issues:[/yellow]\n")
    for issue_type, description in issues:
        console.print(f"  • {description}")
    
    console.print()
    
    if interactive:
        # Let user choose what to clean
        actions = []
        
        if any(i[0] == 'empty' for i in issues):
            if Confirm.ask("Delete empty documents?"):
                actions.append('empty')
        
        if any(i[0] == 'duplicates' for i in issues):
            if Confirm.ask("Remove duplicate documents?"):
                actions.append('duplicates')
        
        if not actions:
            console.print("\n[yellow]No actions selected[/yellow]")
            return
    else:
        # Batch mode - do everything
        actions = [i[0] for i in issues if i[0] in ['empty', 'duplicates']]
    
    # Execute selected actions
    console.print(f"\n[bold]Executing cleanup actions...[/bold]\n")
    
    for action in actions:
        if action == 'empty':
            console.print("[cyan]Cleaning empty documents...[/cyan]")
            empty(dry_run=dry_run, verbose=False)
            console.print()
        
        elif action == 'duplicates':
            console.print("[cyan]Removing duplicates...[/cyan]")
            duplicates(dry_run=dry_run, verbose=False)
            console.print()
    
    console.print("[bold green]✅ Cleanup complete![/bold green]")


@app.command()
def stats():
    """Show cleanup statistics and potential improvements."""
    
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Gather statistics
    stats = {}
    
    # Document counts
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN is_deleted = 0 THEN 1 END) as active,
            COUNT(CASE WHEN is_deleted = 1 THEN 1 END) as deleted
        FROM documents
    """)
    counts = cursor.fetchone()
    stats['active_docs'] = counts[0]
    stats['deleted_docs'] = counts[1]
    
    # Empty documents
    cursor.execute("""
        SELECT COUNT(*), SUM(LENGTH(content))
        FROM documents 
        WHERE is_deleted = 0 AND LENGTH(content) < 10
    """)
    empty = cursor.fetchone()
    stats['empty_docs'] = empty[0] or 0
    stats['empty_space'] = empty[1] or 0
    
    # Potential duplicates
    detector = DuplicateDetector()
    duplicates = detector.find_duplicates()
    stats['duplicate_groups'] = len(duplicates)
    stats['duplicate_docs'] = sum(len(group) - 1 for group in duplicates)
    stats['duplicate_space'] = sum(
        sum(doc['content_length'] for doc in group[1:])
        for group in duplicates
    )
    
    # Untagged
    cursor.execute("""
        SELECT COUNT(*) FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
    """)
    stats['untagged_docs'] = cursor.fetchone()[0]
    
    conn.close()
    
    # Display statistics
    console.print("[bold cyan]📊 Cleanup Statistics[/bold cyan]\n")
    
    # Current state
    state_table = Table(show_header=False, box=box.ROUNDED)
    state_table.add_column("Metric", style="bold")
    state_table.add_column("Value", justify="right")
    
    state_table.add_row("Active Documents", f"{stats['active_docs']:,}")
    state_table.add_row("Deleted Documents", f"{stats['deleted_docs']:,}")
    state_table.add_row("Total Documents", f"{stats['active_docs'] + stats['deleted_docs']:,}")
    
    console.print(state_table)
    
    # Potential improvements
    if any([stats['empty_docs'], stats['duplicate_docs'], stats['untagged_docs'] > 10]):
        console.print("\n[bold yellow]🎯 Potential Improvements[/bold yellow]\n")
        
        improve_table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        improve_table.add_column("Issue", style="yellow")
        improve_table.add_column("Count", justify="right")
        improve_table.add_column("Impact", justify="right")
        improve_table.add_column("Command")
        
        if stats['empty_docs'] > 0:
            improve_table.add_row(
                "Empty Documents",
                str(stats['empty_docs']),
                f"{stats['empty_space']:,} chars",
                "emdx clean empty"
            )
        
        if stats['duplicate_docs'] > 0:
            improve_table.add_row(
                "Duplicate Documents",
                str(stats['duplicate_docs']),
                f"{stats['duplicate_space']:,} chars",
                "emdx clean duplicates"
            )
        
        if stats['untagged_docs'] > 10:
            improve_table.add_row(
                "Untagged Documents",
                str(stats['untagged_docs']),
                "Poor organization",
                "emdx tag --auto"
            )
        
        console.print(improve_table)
        
        # Summary
        total_savings = stats['empty_space'] + stats['duplicate_space']
        if total_savings > 0:
            console.print(f"\n💡 [green]Potential space savings: {total_savings:,} characters[/green]")
            console.print("[dim]Run 'emdx clean all' to optimize your knowledge base[/dim]")
    else:
        console.print("\n✨ [green]Your knowledge base is well maintained![/green]")


if __name__ == "__main__":
    app()