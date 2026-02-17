"""Review commands for triaging agent-produced documents.

Tag-based workflow for reviewing delegate outputs. Documents tagged 'needs-review'
are pending human review. After review they get 'reviewed' or 'rejected' tags.

Commands:
    emdx review list                    # List documents needing review
    emdx review approve 42              # Mark document as reviewed
    emdx review reject 42 --reason "..." # Mark document as rejected
    emdx review stats                   # Show review statistics
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
    list_all_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.ui.formatting import format_tags
from emdx.utils.datetime_utils import parse_datetime
from emdx.utils.output import console

app = typer.Typer(help="Triage agent-produced documents")


def _format_date(date_str: str | None) -> str:
    """Format a date string for display."""
    if not date_str:
        return "Unknown"
    dt = parse_datetime(date_str)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(date_str)[:16]


def _get_tag_count(tag_name: str) -> int:
    """Get the count of documents with a specific tag."""
    all_tags = list_all_tags()
    for tag in all_tags:
        if tag["name"] == tag_name.lower():
            return int(tag["count"])
    return 0


def _output_json(data: Any) -> None:
    """Output data as JSON."""
    console.print(json.dumps(data, indent=2, default=str))


@app.command("list")
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum documents to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List documents tagged 'needs-review'.

    Shows documents awaiting human review with their metadata.

    Examples:
        emdx review list
        emdx review list --limit 50
        emdx review list --json
    """
    try:
        db.ensure_schema()

        docs = search_by_tags(["needs-review"], limit=limit, prefix_match=False)

        if json_output:
            output = []
            for doc in docs:
                doc_tags = get_document_tags(doc["id"])
                output.append(
                    {
                        "id": doc["id"],
                        "title": doc["title"],
                        "project": doc.get("project"),
                        "created_at": doc.get("created_at"),
                        "tags": doc_tags,
                    }
                )
            _output_json({"documents": output, "count": len(output)})
            return

        if not docs:
            console.print("[yellow]No documents pending review[/yellow]")
            return

        console.print(f"\n[bold]📋 Documents Pending Review ({len(docs)}):[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", max_width=50)
        table.add_column("Created", width=16)
        table.add_column("Tags", max_width=30)

        for doc in docs:
            doc_tags = get_document_tags(doc["id"])
            # Filter out needs-review for display (it's implied)
            other_tags = [t for t in doc_tags if t != "needs-review"]

            table.add_row(
                str(doc["id"]),
                doc["title"][:50] if doc["title"] else "(untitled)",
                _format_date(doc.get("created_at")),
                format_tags(other_tags) if other_tags else "[dim]-[/dim]",
            )

        console.print(table)
        console.print(f"\n[dim]{len(docs)} document(s) pending review[/dim]")

    except Exception as e:
        console.print(f"[red]Error listing reviews: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def approve(
    doc_id: int = typer.Argument(..., help="Document ID to approve"),
    note: str | None = typer.Option(None, "--note", "-n", help="Optional review note"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Approve a document after review.

    Removes 'needs-review' tag and adds 'reviewed' tag.

    Examples:
        emdx review approve 42
        emdx review approve 42 --note "LGTM"
    """
    try:
        db.ensure_schema()

        doc = get_document(str(doc_id))
        if not doc:
            if json_output:
                _output_json({"success": False, "error": f"Document #{doc_id} not found"})
            else:
                console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        current_tags = get_document_tags(doc_id)

        if "needs-review" not in current_tags:
            if json_output:
                _output_json(
                    {
                        "success": False,
                        "error": f"Document #{doc_id} is not pending review",
                    }
                )
            else:
                console.print(f"[yellow]Document #{doc_id} is not pending review[/yellow]")
            raise typer.Exit(1)

        # Remove needs-review, add reviewed
        remove_tags_from_document(doc_id, ["needs-review"])
        add_tags_to_document(doc_id, ["reviewed"])

        if json_output:
            result = {
                "success": True,
                "doc_id": doc_id,
                "action": "approved",
                "tags_added": ["reviewed"],
                "tags_removed": ["needs-review"],
            }
            if note:
                result["note"] = note
            _output_json(result)
        else:
            console.print(f"[green]✅ Approved:[/green] #{doc_id} {doc['title']}")
            if note:
                console.print(f"[dim]Note: {note}[/dim]")

            # Show updated tags
            updated_tags = get_document_tags(doc_id)
            console.print(f"[dim]Tags:[/dim] {format_tags(updated_tags)}")

    except typer.Exit:
        raise
    except Exception as e:
        if json_output:
            _output_json({"success": False, "error": str(e)})
        else:
            console.print(f"[red]Error approving document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def reject(
    doc_id: int = typer.Argument(..., help="Document ID to reject"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for rejection"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Reject a document after review.

    Removes 'needs-review' tag and adds 'rejected' tag.

    Examples:
        emdx review reject 42 --reason "Incomplete analysis"
        emdx review reject 42 -r "Missing error handling"
    """
    try:
        db.ensure_schema()

        doc = get_document(str(doc_id))
        if not doc:
            if json_output:
                _output_json({"success": False, "error": f"Document #{doc_id} not found"})
            else:
                console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        current_tags = get_document_tags(doc_id)

        if "needs-review" not in current_tags:
            if json_output:
                _output_json(
                    {
                        "success": False,
                        "error": f"Document #{doc_id} is not pending review",
                    }
                )
            else:
                console.print(f"[yellow]Document #{doc_id} is not pending review[/yellow]")
            raise typer.Exit(1)

        # Remove needs-review, add rejected
        remove_tags_from_document(doc_id, ["needs-review"])
        add_tags_to_document(doc_id, ["rejected"])

        if json_output:
            _output_json(
                {
                    "success": True,
                    "doc_id": doc_id,
                    "action": "rejected",
                    "reason": reason,
                    "tags_added": ["rejected"],
                    "tags_removed": ["needs-review"],
                }
            )
        else:
            console.print(f"[red]❌ Rejected:[/red] #{doc_id} {doc['title']}")
            console.print(f"[dim]Reason: {reason}[/dim]")

            # Show updated tags
            updated_tags = get_document_tags(doc_id)
            console.print(f"[dim]Tags:[/dim] {format_tags(updated_tags)}")

    except typer.Exit:
        raise
    except Exception as e:
        if json_output:
            _output_json({"success": False, "error": str(e)})
        else:
            console.print(f"[red]Error rejecting document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def stats(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show review statistics.

    Displays counts of documents tagged 'needs-review', 'reviewed', and 'rejected'.

    Examples:
        emdx review stats
        emdx review stats --json
    """
    try:
        db.ensure_schema()

        needs_review = _get_tag_count("needs-review")
        reviewed = _get_tag_count("reviewed")
        rejected = _get_tag_count("rejected")

        total = needs_review + reviewed + rejected

        if json_output:
            _output_json(
                {
                    "needs_review": needs_review,
                    "reviewed": reviewed,
                    "rejected": rejected,
                    "total": total,
                }
            )
        else:
            console.print("\n[bold]📊 Review Statistics:[/bold]\n")

            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Status", width=20)
            table.add_column("Count", justify="right", width=10)

            table.add_row("⏳ Needs Review", str(needs_review))
            table.add_row("✅ Reviewed", str(reviewed))
            table.add_row("❌ Rejected", str(rejected))
            table.add_row("─" * 15, "─" * 5)
            table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

            console.print(table)

            if needs_review > 0:
                console.print("\n[yellow]Run 'emdx review list' to see pending documents[/yellow]")

    except Exception as e:
        if json_output:
            _output_json({"error": str(e)})
        else:
            console.print(f"[red]Error getting review stats: {e}[/red]")
        raise typer.Exit(1) from e
