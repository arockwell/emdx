"""Tag management commands for emdx.

All tag-related commands live under `emdx tag <subcommand>`.
The `add` subcommand is also the default callback, so `emdx tag 42 gameplan`
works as a shorthand for `emdx tag add 42 gameplan`.
"""


from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    list_all_tags,
    merge_tags,
    remove_tags_from_document,
    rename_tag,
)
from emdx.services.auto_tagger import AutoTagger
from emdx.ui.formatting import format_tags
from emdx.utils.output import console
from emdx.utils.text_formatting import truncate_title

app = typer.Typer(help="Manage document tags")


def _add_tags_impl(
    doc_id: int,
    tags: Optional[list[str]],
    auto: bool,
    suggest: bool,
):
    """Shared implementation for adding tags (used by both callback and add subcommand)."""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Check if document exists
        doc = get_document(str(doc_id))
        if not doc:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        # Handle auto-tagging
        if auto:
            tagger = AutoTagger()
            applied = tagger.auto_tag_document(doc_id, confidence_threshold=0.7)
            if applied:
                console.print(
                    f"[green]Auto-tagged #{doc_id} with:[/green] [cyan]{format_tags(applied)}[/cyan]"
                )
            else:
                console.print("[yellow]No tags met confidence threshold for auto-tagging[/yellow]")

            # Show all tags
            all_tags = get_document_tags(doc_id)
            console.print(f"[dim]All tags:[/dim] {format_tags(all_tags)}")
            return

        # Handle suggestions
        if suggest:
            tagger = AutoTagger()
            suggestions = tagger.suggest_tags(doc_id)

            if suggestions:
                console.print(f"\n[bold]Tag suggestions for #{doc_id}: {doc['title']}[/bold]\n")

                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Tag", style="cyan")
                table.add_column("Confidence", justify="right")
                table.add_column("Apply?", style="dim")

                for tag_name, confidence in suggestions:
                    conf_percent = f"{confidence:.0%}"
                    apply_hint = "High" if confidence >= 0.8 else "Medium" if confidence >= 0.7 else "Low"
                    table.add_row(tag_name, conf_percent, apply_hint)

                console.print(table)
                console.print("\n[dim]Use 'emdx tag add ID TAG...' to apply tags[/dim]")
            else:
                console.print("[yellow]No tag suggestions found[/yellow]")

            # Show current tags
            current_tags = get_document_tags(doc_id)
            if current_tags:
                console.print(f"\n[dim]Current tags:[/dim] {format_tags(current_tags)}")
            return

        # If no tags provided and no auto/suggest, show current tags
        if not tags:
            current_tags = get_document_tags(doc_id)
            if current_tags:
                console.print(f"\n[bold]Tags for #{doc_id}: {doc['title']}[/bold]")
                console.print(f"[cyan]{format_tags(current_tags)}[/cyan]")
            else:
                console.print(f"[yellow]No tags for #{doc_id}: {doc['title']}[/yellow]")
            return

        # Add tags manually
        added_tags = add_tags_to_document(doc_id, tags)

        if added_tags:
            console.print(
                f"[green]Added tags to #{doc_id}:[/green] [cyan]{format_tags(added_tags)}[/cyan]"
            )
        else:
            console.print("[yellow]No new tags added (may already exist)[/yellow]")

        # Show all tags for the document
        all_tags = get_document_tags(doc_id)
        console.print(f"[dim]All tags:[/dim] {format_tags(all_tags)}")

    except Exception as e:
        console.print(f"[red]Error adding tags: {e}[/red]")
        raise typer.Exit(1) from e


@app.callback()
def tag_callback():
    """Manage document tags.

    Subcommands: add, remove, list, rename, merge, batch.

    Shorthand: `emdx tag 42 gameplan active` is equivalent to `emdx tag add 42 gameplan active`.
    """


@app.command()
def add(
    doc_id: int = typer.Argument(..., help="Document ID to tag"),
    tags: Optional[list[str]] = typer.Argument(None, help="Tags to add (space-separated)"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Apply high-confidence auto-tags"),
    suggest: bool = typer.Option(False, "--suggest", "-s", help="Show tag suggestions"),
):
    """Add tags to a document with optional auto-tagging."""
    _add_tags_impl(doc_id, tags, auto, suggest)


@app.command()
def remove(
    doc_id: int = typer.Argument(..., help="Document ID to untag"),
    tags: list[str] = typer.Argument(..., help="Tags to remove (space-separated)"),
):
    """Remove tags from a document."""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Check if document exists
        doc = get_document(str(doc_id))
        if not doc:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        # Remove tags
        removed_tags = remove_tags_from_document(doc_id, tags)

        if removed_tags:
            console.print(
                f"[green]✅ Removed tags from #{doc_id}:[/green] "
                f"[cyan]{format_tags(removed_tags)}[/cyan]"
            )
        else:
            console.print("[yellow]No tags removed (may not exist)[/yellow]")

        # Show remaining tags
        remaining_tags = get_document_tags(doc_id)
        if remaining_tags:
            console.print(f"[dim]Remaining tags:[/dim] {format_tags(remaining_tags)}")
        else:
            console.print("[dim]No tags remaining[/dim]")

    except Exception as e:
        console.print(f"[red]Error removing tags: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("list")
def list_tags(
    sort: str = typer.Option("usage", "--sort", "-s", help="Sort by: usage, name, created"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum tags to show"),
):
    """List all tags with statistics."""
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

        for tag_entry in all_tags[:limit]:
            created = tag_entry["created_at"].strftime("%Y-%m-%d") if tag_entry["created_at"] else "Unknown"
            last_used = tag_entry["last_used"].strftime("%Y-%m-%d") if tag_entry["last_used"] else "Never"

            table.add_row(tag_entry["name"], str(tag_entry["count"]), created, last_used)

        console.print(table)

        if len(all_tags) > limit:
            console.print(f"\n[dim]Showing {limit} of {len(all_tags)} tags[/dim]")

        console.print(f"\n[dim]Total tags: {len(all_tags)}[/dim]")

    except Exception as e:
        console.print(f"[red]Error listing tags: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def rename(
    old_tag: str = typer.Argument(..., help="Old tag name"),
    new_tag: str = typer.Argument(..., help="New tag name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Rename a tag globally."""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Get current usage
        all_tags = list_all_tags()
        old_tag_info = next((t for t in all_tags if t["name"] == old_tag.lower()), None)

        if not old_tag_info:
            console.print(f"[red]Error: Tag '{old_tag}' not found[/red]")
            raise typer.Exit(1)

        # Confirm
        if not force:
            console.print(
                f"\n[yellow]This will rename tag '{old_tag}' to '{new_tag}' across "
                f"{old_tag_info['count']} document(s)[/yellow]"
            )
            typer.confirm("Continue?", abort=True)

        # Rename
        success = rename_tag(old_tag, new_tag)

        if success:
            console.print(f"[green]✅ Renamed tag '{old_tag}' to '{new_tag}'[/green]")
        else:
            console.print(f"[red]Error: Could not rename tag ('{new_tag}' may already exist)[/red]")
            raise typer.Exit(1)

    except typer.Abort:
        console.print("[yellow]Rename cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error renaming tag: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def merge(
    source_tags: list[str] = typer.Argument(..., help="Source tags to merge"),
    target: str = typer.Option(..., "--into", "-i", help="Target tag to merge into"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Merge multiple tags into one."""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Get info about source tags
        all_tags = list_all_tags()
        source_infos = []
        total_docs = 0

        for tag_name in source_tags:
            tag_info = next((t for t in all_tags if t["name"] == tag_name.lower()), None)
            if tag_info:
                source_infos.append(tag_info)
                total_docs += tag_info["count"]

        if not source_infos:
            console.print("[red]Error: No valid source tags found[/red]")
            raise typer.Exit(1)

        # Confirm
        if not force:
            console.print(
                f"\n[yellow]This will merge {len(source_infos)} tag(s) into '{target}':[/yellow]"
            )
            for info in source_infos:
                console.print(f"  • {info['name']} ({info['count']} documents)")
            console.print(f"\n[yellow]Affecting up to {total_docs} document associations[/yellow]")
            typer.confirm("Continue?", abort=True)

        # Merge
        merged_count = merge_tags(source_tags, target)

        console.print(f"[green]✅ Merged {len(source_infos)} tag(s) into '{target}'[/green]")
        console.print(f"[dim]Updated {merged_count} document associations[/dim]")

    except typer.Abort:
        console.print("[yellow]Merge cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error merging tags: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def batch(
    untagged_only: bool = typer.Option(True, "--untagged/--all", help="Only process untagged documents"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    confidence: float = typer.Option(0.7, "--confidence", "-c", help="Minimum confidence threshold"),
    max_tags: int = typer.Option(3, "--max-tags", "-m", help="Maximum tags per document"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Execute tagging (default: dry run only)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum documents to process"),
):
    """Batch auto-tag multiple documents."""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        tagger = AutoTagger()

        # Get suggestions first
        with console.status("[bold green]Analyzing documents..."):
            suggestions = tagger.batch_suggest(
                untagged_only=untagged_only,
                project=project,
                limit=limit
            )

        if not suggestions:
            console.print("[yellow]No documents found matching criteria[/yellow]")
            return

        # Filter by confidence
        eligible_docs = []
        total_tags_to_apply = 0

        for doc_id, doc_suggestions in suggestions.items():
            eligible_tags = [
                (tag_name, conf) for tag_name, conf in doc_suggestions[:max_tags]
                if conf >= confidence
            ]
            if eligible_tags:
                eligible_docs.append((doc_id, eligible_tags))
                total_tags_to_apply += len(eligible_tags)

        if not eligible_docs:
            console.print(f"[yellow]No tags found with confidence >= {confidence:.0%}[/yellow]")
            return

        # Display what will be done
        console.print("\n[bold cyan]🏷️  Batch Auto-Tagging Report[/bold cyan]")
        console.print(f"\n[yellow]Found {len(eligible_docs)} documents to tag[/yellow]")
        console.print(f"[yellow]Total tags to apply: {total_tags_to_apply}[/yellow]\n")

        # Show sample of what will be done
        sample_size = min(10, len(eligible_docs))
        if sample_size > 0:
            console.print("[bold]Sample of documents to be tagged:[/bold]\n")

            for doc_id, tag_list in eligible_docs[:sample_size]:
                # Get document title
                doc = get_document(str(doc_id))
                title = truncate_title(doc['title'])

                console.print(f"  [dim]#{doc_id}[/dim] {title}")
                for tag_name, conf in tag_list:
                    console.print(f"    → {tag_name} [dim]({conf:.0%})[/dim]")
                console.print()

            if len(eligible_docs) > sample_size:
                console.print(f"[dim]... and {len(eligible_docs) - sample_size} more documents[/dim]\n")

        if dry_run:
            console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]")
            console.print(f"Would apply {total_tags_to_apply} tags to {len(eligible_docs)} documents")
            console.print("\n[dim]Run with --execute to apply tags[/dim]")
        else:
            # Confirm
            if not typer.confirm(f"\n🏷️  Apply {total_tags_to_apply} tags to {len(eligible_docs)} documents?"):
                console.print("[red]Batch tagging cancelled[/red]")
                return

            # Execute batch tagging
            applied_count = 0
            tagged_docs = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Applying tags...", total=len(eligible_docs))

                for doc_id, _tag_list in eligible_docs:
                    applied = tagger.auto_tag_document(
                        doc_id,
                        confidence_threshold=confidence,
                        max_tags=max_tags
                    )
                    if applied:
                        applied_count += len(applied)
                        tagged_docs += 1
                    progress.update(task, advance=1)

            console.print(f"\n✅ [green]Successfully tagged {tagged_docs} documents![/green]")
            console.print(f"[dim]Total tags applied: {applied_count}[/dim]")

    except Exception as e:
        console.print(f"[red]Error batch tagging: {e}[/red]")
        raise typer.Exit(1) from e
