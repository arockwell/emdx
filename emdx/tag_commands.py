"""Tag management commands for emdx."""

import typer
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from emdx.sqlite_database import db
from emdx.tags import (
    add_tags_to_document,
    remove_tags_from_document,
    get_document_tags,
    list_all_tags,
    search_by_tags,
    rename_tag,
    merge_tags,
)

app = typer.Typer()
console = Console()


@app.command()
def tag(
    doc_id: int = typer.Argument(..., help="Document ID to tag"),
    tags: List[str] = typer.Argument(None, help="Tags to add (space-separated)"),
):
    """Add tags to a document"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Check if document exists
        doc = db.get_document(str(doc_id))
        if not doc:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)
        
        # If no tags provided, show current tags
        if not tags:
            current_tags = get_document_tags(doc_id)
            if current_tags:
                console.print(f"\n[bold]Tags for #{doc_id}: {doc['title']}[/bold]")
                console.print(f"[cyan]{', '.join(current_tags)}[/cyan]")
            else:
                console.print(f"[yellow]No tags for #{doc_id}: {doc['title']}[/yellow]")
            return
        
        # Add tags
        added_tags = add_tags_to_document(doc_id, tags)
        
        if added_tags:
            console.print(f"[green]✅ Added tags to #{doc_id}:[/green] [cyan]{', '.join(added_tags)}[/cyan]")
        else:
            console.print("[yellow]No new tags added (may already exist)[/yellow]")
        
        # Show all tags for the document
        all_tags = get_document_tags(doc_id)
        console.print(f"[dim]All tags:[/dim] {', '.join(all_tags)}")
        
    except Exception as e:
        console.print(f"[red]Error adding tags: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def untag(
    doc_id: int = typer.Argument(..., help="Document ID to untag"),
    tags: List[str] = typer.Argument(..., help="Tags to remove (space-separated)"),
):
    """Remove tags from a document"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Check if document exists
        doc = db.get_document(str(doc_id))
        if not doc:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)
        
        # Remove tags
        removed_tags = remove_tags_from_document(doc_id, tags)
        
        if removed_tags:
            console.print(f"[green]✅ Removed tags from #{doc_id}:[/green] [cyan]{', '.join(removed_tags)}[/cyan]")
        else:
            console.print("[yellow]No tags removed (may not exist)[/yellow]")
        
        # Show remaining tags
        remaining_tags = get_document_tags(doc_id)
        if remaining_tags:
            console.print(f"[dim]Remaining tags:[/dim] {', '.join(remaining_tags)}")
        else:
            console.print("[dim]No tags remaining[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error removing tags: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def tags(
    sort: str = typer.Option("usage", "--sort", "-s", help="Sort by: usage, name, created"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum tags to show"),
):
    """List all tags with statistics"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get all tags
        all_tags = list_all_tags(sort_by=sort)
        
        if not all_tags:
            console.print("[yellow]No tags found[/yellow]")
            return
        
        # Display tags in a table
        console.print(f"\n[bold]📏 Tag Statistics (sorted by {sort}):[/bold]\n")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Tag", style="cyan")
        table.add_column("Count", style="yellow", justify="right")
        table.add_column("Created", style="green")
        table.add_column("Last Used", style="magenta")
        
        for i, tag in enumerate(all_tags[:limit]):
            created = tag['created_at'].strftime('%Y-%m-%d') if tag['created_at'] else 'Unknown'
            last_used = tag['last_used'].strftime('%Y-%m-%d') if tag['last_used'] else 'Never'
            
            table.add_row(
                tag['name'],
                str(tag['count']),
                created,
                last_used
            )
        
        console.print(table)
        
        if len(all_tags) > limit:
            console.print(f"\n[dim]Showing {limit} of {len(all_tags)} tags[/dim]")
        
        console.print(f"\n[dim]Total tags: {len(all_tags)}[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error listing tags: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="find-tags")
def find_by_tags(
    tags: List[str] = typer.Argument(..., help="Tags to search for"),
    mode: str = typer.Option("all", "--mode", "-m", help="Search mode: 'all' or 'any'"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results"),
):
    """Find documents by tags"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Validate mode
        if mode not in ['all', 'any']:
            console.print("[red]Error: mode must be 'all' or 'any'[/red]")
            raise typer.Exit(1)
        
        # Search by tags
        results = search_by_tags(tags, mode=mode, project=project, limit=limit)
        
        if not results:
            if mode == 'all':
                console.print(f"[yellow]No documents found with all tags: {', '.join(tags)}[/yellow]")
            else:
                console.print(f"[yellow]No documents found with any of these tags: {', '.join(tags)}[/yellow]")
            return
        
        # Display results
        mode_desc = "all of these" if mode == "all" else "any of these"
        console.print(f"\n[bold]🏷️  Found {len(results)} documents with {mode_desc} tags: [cyan]{', '.join(tags)}[/cyan][/bold]\n")
        
        for i, doc in enumerate(results, 1):
            console.print(f"[bold cyan]#{doc['id']}[/bold cyan] [bold]{doc['title']}[/bold]")
            
            metadata = []
            if doc['project']:
                metadata.append(f"[green]{doc['project']}[/green]")
            metadata.append(f"[yellow]{doc['created_at'].strftime('%Y-%m-%d')}[/yellow]")
            
            console.print(" • ".join(metadata))
            
            if doc.get('tags'):
                console.print(f"[dim]Tags: {doc['tags']}[/dim]")
            
            if i < len(results):
                console.print()
        
        console.print(f"\n[dim]💡 Use 'emdx view <id>' to view a document[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error searching by tags: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def retag(
    old_tag: str = typer.Argument(..., help="Old tag name"),
    new_tag: str = typer.Argument(..., help="New tag name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Rename a tag globally"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get current usage
        all_tags = list_all_tags()
        old_tag_info = next((t for t in all_tags if t['name'] == old_tag.lower()), None)
        
        if not old_tag_info:
            console.print(f"[red]Error: Tag '{old_tag}' not found[/red]")
            raise typer.Exit(1)
        
        # Confirm
        if not force:
            console.print(f"\n[yellow]This will rename tag '{old_tag}' to '{new_tag}' across {old_tag_info['count']} document(s)[/yellow]")
            confirm = typer.confirm("Continue?", abort=True)
        
        # Rename
        success = rename_tag(old_tag, new_tag)
        
        if success:
            console.print(f"[green]✅ Renamed tag '{old_tag}' to '{new_tag}'[/green]")
        else:
            console.print(f"[red]Error: Could not rename tag ('{new_tag}' may already exist)[/red]")
            raise typer.Exit(1)
        
    except typer.Abort:
        console.print("[yellow]Rename cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error renaming tag: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="merge-tags")
def merge_tags_cmd(
    source_tags: List[str] = typer.Argument(..., help="Source tags to merge"),
    target: str = typer.Option(..., "--into", "-i", help="Target tag to merge into"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Merge multiple tags into one"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get info about source tags
        all_tags = list_all_tags()
        source_infos = []
        total_docs = 0
        
        for tag in source_tags:
            tag_info = next((t for t in all_tags if t['name'] == tag.lower()), None)
            if tag_info:
                source_infos.append(tag_info)
                total_docs += tag_info['count']
        
        if not source_infos:
            console.print("[red]Error: No valid source tags found[/red]")
            raise typer.Exit(1)
        
        # Confirm
        if not force:
            console.print(f"\n[yellow]This will merge {len(source_infos)} tag(s) into '{target}':[/yellow]")
            for info in source_infos:
                console.print(f"  • {info['name']} ({info['count']} documents)")
            console.print(f"\n[yellow]Affecting up to {total_docs} document associations[/yellow]")
            confirm = typer.confirm("Continue?", abort=True)
        
        # Merge
        merged_count = merge_tags(source_tags, target)
        
        console.print(f"[green]✅ Merged {len(source_infos)} tag(s) into '{target}'[/green]")
        console.print(f"[dim]Updated {merged_count} document associations[/dim]")
        
    except typer.Abort:
        console.print("[yellow]Merge cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error merging tags: {e}[/red]")
        raise typer.Exit(1)