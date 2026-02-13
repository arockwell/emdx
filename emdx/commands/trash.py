"""
Trash management commands for emdx.

Consolidates trash, restore, and purge into a subcommand group:
    emdx trash           → list trash
    emdx trash list      → list trash (explicit)
    emdx trash restore   → restore documents
    emdx trash purge     → permanently delete trash
"""

from typing import Optional

import typer
from rich.table import Table

from emdx.database import db
from emdx.models.documents import (
    list_deleted_documents,
    purge_deleted_documents,
    restore_document,
)
from emdx.utils.output import console

app = typer.Typer()


@app.callback(invoke_without_command=True)
def trash_callback(
    ctx: typer.Context,
    days: Optional[int] = typer.Option(
        None, "--days", "-d", help="Show items deleted in last N days"
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum results to return"),
) -> None:
    """Manage deleted documents (trash)."""
    # If a subcommand was invoked, don't run the default list behavior
    if ctx.invoked_subcommand is not None:
        return
    _list_trash(days=days, limit=limit)


@app.command("list")
def list_cmd(
    days: Optional[int] = typer.Option(
        None, "--days", "-d", help="Show items deleted in last N days"
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum results to return"),
) -> None:
    """List all soft-deleted documents."""
    _list_trash(days=days, limit=limit)


def _list_trash(days: Optional[int] = None, limit: int = 50) -> None:
    """Shared implementation for listing trash."""
    try:
        db.ensure_schema()

        deleted_docs = list_deleted_documents(days=days, limit=limit)

        if not deleted_docs:
            if days:
                console.print(f"[yellow]No documents deleted in the last {days} days[/yellow]")
            else:
                console.print("[yellow]No documents in trash[/yellow]")
            return

        if days:
            console.print(f"\n[bold]🗑️  Documents deleted in the last {days} days:[/bold]\n")
        else:
            console.print(f"\n[bold]🗑️  Documents in trash ({len(deleted_docs)} items):[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="green")
        table.add_column("Deleted", style="red")
        table.add_column("Views", style="yellow", justify="right")

        for doc in deleted_docs:
            table.add_row(
                str(doc["id"]),
                doc["title"][:50] + "..." if len(doc["title"]) > 50 else doc["title"],
                doc["project"] or "[dim]None[/dim]",
                doc["deleted_at"].strftime("%Y-%m-%d %H:%M"),
                str(doc["access_count"]),
            )

        console.print(table)
        console.print("\n[dim]💡 Use 'emdx trash restore <id>' to restore documents[/dim]")
        console.print("[dim]💡 Use 'emdx trash purge' to permanently delete all items[/dim]")

    except Exception as e:
        console.print(f"[red]Error listing deleted documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def restore(
    identifiers: Optional[list[str]] = typer.Argument(
        default=None, help="Document ID(s) or title(s) to restore"
    ),
    all: bool = typer.Option(False, "--all", help="Restore all deleted documents"),
) -> None:
    """Restore soft-deleted document(s)."""
    try:
        db.ensure_schema()

        if not identifiers and not all:
            console.print("[red]Error: Provide document ID(s) to restore or use --all[/red]")
            raise typer.Exit(1)

        if all:
            deleted_docs = list_deleted_documents()
            if not deleted_docs:
                console.print("[yellow]No documents to restore[/yellow]")
                return

            console.print(f"\n[bold]Will restore {len(deleted_docs)} document(s)[/bold]")
            typer.confirm("Continue?", abort=True)

            restored_count = 0
            for doc in deleted_docs:
                if restore_document(str(doc["id"])):
                    restored_count += 1

            console.print(f"\n[green]✅ Restored {restored_count} document(s)[/green]")
        else:
            restored = []
            not_found = []

            for identifier in identifiers:
                if restore_document(identifier):
                    restored.append(identifier)
                else:
                    not_found.append(identifier)

            if restored:
                console.print(f"\n[green]✅ Restored {len(restored)} document(s):[/green]")
                for r in restored:
                    console.print(f"  [dim]• {r}[/dim]")

            if not_found:
                console.print(f"\n[yellow]Could not restore {len(not_found)} document(s):[/yellow]")
                for nf in not_found:
                    console.print(f"  [dim]• {nf} (not found in trash)[/dim]")

    except typer.Abort:
        console.print("[yellow]Restore cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error restoring documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def purge(
    older_than: Optional[int] = typer.Option(
        None, "--older-than", help="Only purge items deleted more than N days ago"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Permanently delete all items in trash."""
    try:
        db.ensure_schema()

        if older_than:
            deleted_docs = list_deleted_documents()
            from datetime import datetime, timedelta

            cutoff = datetime.now() - timedelta(days=older_than)
            docs_to_purge = [d for d in deleted_docs if d["deleted_at"] < cutoff]
            count = len(docs_to_purge)
        else:
            deleted_docs = list_deleted_documents()
            count = len(deleted_docs)

        if count == 0:
            if older_than:
                console.print(
                    f"[yellow]No documents deleted more than {older_than} days ago[/yellow]"
                )
            else:
                console.print("[yellow]No documents in trash to purge[/yellow]")
            return

        console.print(
            f"\n[red bold]⚠️  WARNING: This will PERMANENTLY delete "
            f"{count} document(s) from trash![/red bold]"
        )
        console.print("[red]This action cannot be undone![/red]\n")

        if not force:
            typer.confirm("Are you absolutely sure?", abort=True)

        purged_count = purge_deleted_documents(older_than_days=older_than)

        console.print(
            f"\n[green]✅ Permanently deleted {purged_count} document(s) from trash[/green]"
        )

    except typer.Abort:
        console.print("[yellow]Purge cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error purging documents: {e}[/red]")
        raise typer.Exit(1) from e
