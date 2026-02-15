"""Review CLI commands for triaging agent output.

This module provides a lightweight review workflow for documents created
by delegate operations. Documents tagged 'needs-review' can be approved,
rejected, or listed for triage.

Commands:
    emdx review list                    List documents needing review
    emdx review approve ID [--note]     Approve a document
    emdx review reject ID --reason      Reject a document with reason
    emdx review stats                   Show review statistics
"""

import json
from typing import Any

import typer
from rich.table import Table

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.ui.formatting import format_tags
from emdx.utils.output import console

app = typer.Typer(help="Review and triage agent output")

# Tag constants for review workflow
TAG_NEEDS_REVIEW = "needs-review"
TAG_REVIEWED = "reviewed"
TAG_REJECTED = "rejected"


def _get_documents_needing_review(limit: int = 50) -> list[dict[str, Any]]:
    """Get all documents with 'needs-review' tag."""
    return search_by_tags([TAG_NEEDS_REVIEW], mode="any", limit=limit, prefix_match=False)


def _count_by_tag(tag_name: str) -> int:
    """Count documents with a specific tag."""
    docs = search_by_tags([tag_name], mode="any", limit=10000, prefix_match=False)
    return len(docs)


@app.command("list")
def list_cmd(
    limit: int = typer.Option(50, "-n", "--limit", help="Maximum documents to show"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List documents needing review.

    Shows all documents tagged 'needs-review' that haven't been approved or rejected.

    Examples:
        emdx review list
        emdx review list --limit 10
        emdx review list --json
    """
    try:
        db.ensure_schema()
        docs = _get_documents_needing_review(limit=limit)

        if as_json:
            output = {
                "count": len(docs),
                "documents": [
                    {
                        "id": doc["id"],
                        "title": doc["title"],
                        "project": doc.get("project"),
                        "created_at": str(doc.get("created_at")),
                        "tags": doc.get("tags", "").split(", ") if doc.get("tags") else [],
                    }
                    for doc in docs
                ],
            }
            console.print(json.dumps(output, indent=2))
            return

        if not docs:
            console.print("[green]✓ No documents pending review[/green]")
            return

        console.print(f"\n[bold]📋 Documents Pending Review ({len(docs)}):[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", min_width=30)
        table.add_column("Project", style="magenta", width=15)
        table.add_column("Tags", style="cyan")

        for doc in docs:
            tags = doc.get("tags", "")
            # Remove needs-review from display tags for cleaner output
            display_tags = ", ".join(
                t.strip() for t in tags.split(",")
                if t.strip() and t.strip() != TAG_NEEDS_REVIEW
            )
            table.add_row(
                str(doc["id"]),
                doc["title"][:50] + ("..." if len(doc["title"]) > 50 else ""),
                doc.get("project") or "",
                display_tags or "-",
            )

        console.print(table)
        console.print(
            "\n[dim]Use 'emdx review approve ID' or 'emdx review reject ID --reason ...'[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error listing reviews: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def approve(
    doc_id: int = typer.Argument(..., help="Document ID to approve"),
    note: str | None = typer.Option(None, "-n", "--note", help="Optional approval note"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Approve a document, marking it as reviewed.

    Removes 'needs-review' tag and adds 'reviewed' tag.

    Examples:
        emdx review approve 42
        emdx review approve 42 --note "Looks good, merged to main"
        emdx review approve 42 --json
    """
    try:
        db.ensure_schema()

        # Check if document exists
        doc = get_document(str(doc_id))
        if not doc:
            if as_json:
                console.print(json.dumps({"success": False, "error": "Document not found"}))
            else:
                console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        # Check if document has needs-review tag
        current_tags = get_document_tags(doc_id)
        if TAG_NEEDS_REVIEW not in current_tags:
            if as_json:
                console.print(json.dumps({
                    "success": False,
                    "error": "Document is not pending review",
                    "current_tags": current_tags,
                }))
            else:
                console.print(f"[yellow]Document #{doc_id} is not pending review[/yellow]")
                console.print(f"[dim]Current tags: {format_tags(current_tags)}[/dim]")
            raise typer.Exit(1)

        # Remove needs-review, add reviewed
        remove_tags_from_document(doc_id, [TAG_NEEDS_REVIEW])
        add_tags_to_document(doc_id, [TAG_REVIEWED])

        # If note provided, we could store it somewhere - for now just display it
        if as_json:
            console.print(json.dumps({
                "success": True,
                "doc_id": doc_id,
                "title": doc["title"],
                "status": "approved",
                "note": note,
                "tags": get_document_tags(doc_id),
            }))
        else:
            console.print(f"[green]✓ Approved #{doc_id}: {doc['title']}[/green]")
            if note:
                console.print(f"[dim]Note: {note}[/dim]")
            console.print(f"[dim]Tags: {format_tags(get_document_tags(doc_id))}[/dim]")

    except typer.Exit:
        raise
    except Exception as e:
        if as_json:
            console.print(json.dumps({"success": False, "error": str(e)}))
        else:
            console.print(f"[red]Error approving document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def reject(
    doc_id: int = typer.Argument(..., help="Document ID to reject"),
    reason: str = typer.Option(..., "-r", "--reason", help="Reason for rejection (required)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Reject a document with a reason.

    Removes 'needs-review' tag and adds 'rejected' tag.

    Examples:
        emdx review reject 42 --reason "Incomplete analysis, needs more detail"
        emdx review reject 42 -r "Wrong approach, see doc #45 for correct method"
        emdx review reject 42 --reason "Outdated" --json
    """
    try:
        db.ensure_schema()

        # Check if document exists
        doc = get_document(str(doc_id))
        if not doc:
            if as_json:
                console.print(json.dumps({"success": False, "error": "Document not found"}))
            else:
                console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        # Check if document has needs-review tag
        current_tags = get_document_tags(doc_id)
        if TAG_NEEDS_REVIEW not in current_tags:
            if as_json:
                console.print(json.dumps({
                    "success": False,
                    "error": "Document is not pending review",
                    "current_tags": current_tags,
                }))
            else:
                console.print(f"[yellow]Document #{doc_id} is not pending review[/yellow]")
                console.print(f"[dim]Current tags: {format_tags(current_tags)}[/dim]")
            raise typer.Exit(1)

        # Remove needs-review, add rejected
        remove_tags_from_document(doc_id, [TAG_NEEDS_REVIEW])
        add_tags_to_document(doc_id, [TAG_REJECTED])

        # Log the reason (could be stored in a notes field or separate table in the future)
        # For now, we just report it
        if as_json:
            console.print(json.dumps({
                "success": True,
                "doc_id": doc_id,
                "title": doc["title"],
                "status": "rejected",
                "reason": reason,
                "tags": get_document_tags(doc_id),
            }))
        else:
            console.print(f"[red]✗ Rejected #{doc_id}: {doc['title']}[/red]")
            console.print(f"[dim]Reason: {reason}[/dim]")
            console.print(f"[dim]Tags: {format_tags(get_document_tags(doc_id))}[/dim]")

    except typer.Exit:
        raise
    except Exception as e:
        if as_json:
            console.print(json.dumps({"success": False, "error": str(e)}))
        else:
            console.print(f"[red]Error rejecting document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def stats(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show review statistics.

    Displays counts of pending, approved, and rejected documents.

    Examples:
        emdx review stats
        emdx review stats --json
    """
    try:
        db.ensure_schema()

        pending = _count_by_tag(TAG_NEEDS_REVIEW)
        approved = _count_by_tag(TAG_REVIEWED)
        rejected = _count_by_tag(TAG_REJECTED)
        total = pending + approved + rejected

        if as_json:
            console.print(json.dumps({
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "total": total,
            }))
            return

        console.print("\n[bold]📊 Review Statistics:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")

        def pct(n: int) -> str:
            if total == 0:
                return "-"
            return f"{n / total * 100:.1f}%"

        table.add_row("⏳ Pending", str(pending), pct(pending))
        table.add_row("[green]✓ Approved[/green]", str(approved), pct(approved))
        table.add_row("[red]✗ Rejected[/red]", str(rejected), pct(rejected))
        table.add_row("[dim]─────────[/dim]", "[dim]─────[/dim]", "[dim]─────[/dim]")
        table.add_row("[bold]Total[/bold]", str(total), "100%")

        console.print(table)

        if pending > 0:
            console.print("\n[dim]Use 'emdx review list' to see pending documents[/dim]")

    except Exception as e:
        if as_json:
            console.print(json.dumps({"success": False, "error": str(e)}))
        else:
            console.print(f"[red]Error getting stats: {e}[/red]")
        raise typer.Exit(1) from e
