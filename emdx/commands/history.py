"""History and diff commands for emdx document versioning."""

from __future__ import annotations

import difflib
import json
from datetime import datetime

import typer
from rich.table import Table

from emdx.database.connection import db_connection
from emdx.models.documents import get_document
from emdx.utils.output import console


def history(
    doc_id: int = typer.Argument(..., help="Document ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show version history for a document.

    Lists all saved versions with version number, date, character
    delta, and change source.

    Examples:
        emdx history 42
        emdx history 42 --json
    """
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Error: Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    with db_connection.get_connection() as conn:
        rows = conn.execute(
            "SELECT version_number, title, content_hash, "
            "char_delta, change_source, created_at "
            "FROM document_versions "
            "WHERE document_id = ? ORDER BY version_number",
            (doc_id,),
        ).fetchall()

    if not rows:
        print(f"No version history for document #{doc_id}")
        return

    if json_output:
        versions = []
        for row in rows:
            versions.append(
                {
                    "version": row[0],
                    "title": row[1],
                    "content_hash": row[2],
                    "char_delta": row[3],
                    "change_source": row[4],
                    "created_at": str(row[5] or ""),
                }
            )
        print(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "title": doc["title"],
                    "versions": versions,
                },
                indent=2,
            )
        )
        return

    table = Table(title=f"Version history for #{doc_id}: {doc['title']}")
    table.add_column("Ver", justify="right", style="cyan")
    table.add_column("Date", style="dim")
    table.add_column("Delta", justify="right")
    table.add_column("Source")

    for row in rows:
        ver_num: int = row[0]
        created_at = row[5]
        char_delta: int | None = row[3]
        change_source: str = row[4] or "manual"

        # Format date
        if isinstance(created_at, datetime):
            date_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = str(created_at or "")[:16]

        # Format char delta with +/- prefix
        if char_delta is not None:
            if char_delta > 0:
                delta_str = f"+{char_delta}"
            elif char_delta < 0:
                delta_str = str(char_delta)
            else:
                delta_str = "0"
        else:
            delta_str = "-"

        table.add_row(
            str(ver_num),
            date_str,
            delta_str,
            change_source,
        )

    console.print(table)


def diff(
    doc_id: int = typer.Argument(..., help="Document ID"),
    version: int | None = typer.Argument(
        default=None,
        help=("Version to compare against (default: previous version)"),
    ),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output"),
) -> None:
    """Show diff between current content and a previous version.

    Compares the current document content against the specified
    version number.  Defaults to the most recent (previous) version
    if no version number is given.

    Examples:
        emdx diff 42         # diff against previous version
        emdx diff 42 1       # diff against version 1
    """
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Error: Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Normalise version: Typer passes ArgumentInfo when called
    # directly (not via CLI) if the argument was omitted.
    resolved_version: int | None = version if isinstance(version, int) else None

    with db_connection.get_connection() as conn:
        if resolved_version is not None:
            row = conn.execute(
                "SELECT version_number, title, content "
                "FROM document_versions "
                "WHERE document_id = ? AND version_number = ?",
                (doc_id, resolved_version),
            ).fetchone()
            if not row:
                console.print(
                    f"[red]Error: Version {resolved_version} not found for document #{doc_id}[/red]"
                )
                raise typer.Exit(1)
        else:
            # Default to most recent version
            row = conn.execute(
                "SELECT version_number, title, content "
                "FROM document_versions "
                "WHERE document_id = ? "
                "ORDER BY version_number DESC LIMIT 1",
                (doc_id,),
            ).fetchone()
            if not row:
                print(f"No version history for document #{doc_id}")
                return

    old_version: int = row[0]
    old_content: str = row[2]
    current_content: str = doc["content"]

    old_lines = old_content.splitlines(keepends=True)
    new_lines = current_content.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"#{doc_id} v{old_version}",
            tofile=f"#{doc_id} (current)",
        )
    )

    if not diff_lines:
        print("No differences found.")
        return

    if no_color:
        for line in diff_lines:
            print(line, end="")
    else:
        for line in diff_lines:
            stripped = line.rstrip("\n")
            if line.startswith("+++") or line.startswith("---"):
                console.print(f"[bold]{stripped}[/bold]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{stripped}[/cyan]")
            elif line.startswith("+"):
                console.print(f"[green]{stripped}[/green]")
            elif line.startswith("-"):
                console.print(f"[red]{stripped}[/red]")
            else:
                print(stripped)
