"""
Touch command - Reset document staleness without incrementing view count.

Useful for marking a document as "reviewed" without opening it in the viewer.
This resets the staleness timer in the Knowledge Decay system.
"""

from typing import Optional

import typer
from rich.console import Console

from ..database import db

console = Console()


def get_document_info(doc_id: int) -> Optional[dict]:
    """Get basic document info without incrementing view count.

    Args:
        doc_id: Document ID to look up

    Returns:
        Dict with id and title, or None if not found
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title FROM documents
            WHERE id = ? AND is_deleted = FALSE
            """,
            (doc_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def touch_document(doc_id: int) -> Optional[str]:
    """Update a document's accessed_at timestamp without incrementing view count.

    Args:
        doc_id: Document ID to touch

    Returns:
        Document title if successful, None if document not found
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET accessed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE
            RETURNING title
            """,
            (doc_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        return row["title"] if row else None


def touch(
    doc_ids: list[str] = typer.Argument(
        ..., help="Document ID(s) to mark as reviewed"
    ),
):
    """
    Mark document(s) as reviewed without opening them.

    Resets the staleness timer for the Knowledge Decay system without
    incrementing the view count. Useful when you've reviewed a document
    externally or want to confirm it's still accurate.

    Examples:
        emdx touch 123
        emdx touch 123 456 789
    """
    success_count = 0
    failed = []

    for doc_id_str in doc_ids:
        # Validate it's a number
        if not doc_id_str.isdigit():
            console.print(f"[red]Error: '{doc_id_str}' is not a valid document ID[/red]")
            failed.append(doc_id_str)
            continue

        doc_id = int(doc_id_str)

        # Touch the document and get title in one operation
        title = touch_document(doc_id)
        if title:
            console.print(f"[green]✅ Touched #{doc_id}:[/green] [cyan]{title}[/cyan]")
            console.print(f"   [dim]Staleness timer reset[/dim]")
            success_count += 1
        else:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
            failed.append(doc_id_str)

    # Summary for multiple docs
    if len(doc_ids) > 1:
        console.print()
        if success_count > 0:
            console.print(f"[green]Touched {success_count} document(s)[/green]")
        if failed:
            console.print(f"[red]Failed: {len(failed)} document(s)[/red]")


# Create typer app for the command
app = typer.Typer()
app.command(name="touch")(touch)
