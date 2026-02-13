"""
Browse and analytics commands for emdx
"""

from typing import Optional

import typer
from rich.table import Table

from emdx.database import db
from emdx.models.documents import get_recent_documents, get_stats, list_documents
from emdx.utils.datetime_utils import format_datetime as _format_datetime
from emdx.utils.text_formatting import truncate_title
from emdx.utils.output import console

app = typer.Typer()


@app.command()
def list(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum documents to show"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
    include_archived: bool = typer.Option(
        False, "--archived", "-a", help="Include archived documents"
    ),
):
    """List all documents in the knowledge base"""
    try:
        import json

        # Ensure database schema exists
        db.ensure_schema()

        # Query database
        docs = list_documents(project=project, limit=limit, include_archived=include_archived)

        if not docs:
            console.print("[yellow]No documents found[/yellow]")
            return

        if format == "table":
            # Create table with title
            title = "Knowledge Base Documents"
            if project:
                title += f" - Project: {project}"
            if include_archived:
                title += " (including archived)"

            table = Table(title=title)
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Title", style="magenta")
            table.add_column("Project", style="green")
            table.add_column("Created", style="yellow")
            table.add_column("Views", justify="right", style="blue")
            if include_archived:
                table.add_column("Status", style="dim")

            # Add rows from database
            for doc in docs:
                row = [
                    str(doc["id"]),
                    truncate_title(doc["title"]),
                    doc["project"] or "None",
                    doc["created_at"].strftime("%Y-%m-%d"),
                    str(doc["access_count"]),
                ]
                if include_archived:
                    status = "[dim]Archived[/dim]" if doc.get("archived_at") else ""
                    row.append(status)
                table.add_row(*row)

            console.print(table)
            console.print(f"\n[dim]Showing {len(docs)} of {len(docs)} documents[/dim]")

        elif format == "json":
            # Convert datetime objects to strings
            for doc in docs:
                doc["created_at"] = doc["created_at"].isoformat()
                if doc.get("archived_at"):
                    doc["archived_at"] = doc["archived_at"].isoformat()
                if doc.get("accessed_at"):
                    doc["accessed_at"] = doc["accessed_at"].isoformat()
            # Use plain print for machine-parseable output
            print(json.dumps(docs, indent=2))

        elif format == "csv":
            # Output CSV - include archived column when showing archived docs
            if include_archived:
                print("id,title,project,created,views,archived")
            else:
                print("id,title,project,created,views")
            for doc in docs:
                # Escape commas in title
                title = doc["title"].replace(",", "\\,")
                base_row = (
                    f"{doc['id']},{title},{doc['project'] or ''}"
                    f",{doc['created_at'].strftime('%Y-%m-%d')},{doc['access_count']}"
                )
                if include_archived:
                    archived = "yes" if doc.get("archived_at") else ""
                    print(f"{base_row},{archived}")
                else:
                    print(base_row)

    except Exception as e:
        console.print(f"[red]Error listing documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def recent(
    limit: int = typer.Argument(10, help="Number of recent documents to show"),
):
    """Show recently accessed documents"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Query database for recently accessed documents
        docs = get_recent_documents(limit=limit)

        if not docs:
            console.print("[yellow]No recently accessed documents found[/yellow]")
            return

        table = Table(title=f"Last {limit} Accessed Documents")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="magenta")
        table.add_column("Project", style="green")
        table.add_column("Last Accessed", style="yellow")
        table.add_column("Views", justify="right", style="blue")

        # Add rows from database
        for doc in docs:
            # Format accessed_at datetime
            accessed_str = "Never"
            if doc["accessed_at"]:
                accessed_str = doc["accessed_at"].strftime("%Y-%m-%d %H:%M")

            table.add_row(
                str(doc["id"]),
                truncate_title(doc["title"]),
                doc["project"] or "None",
                accessed_str,
                str(doc["access_count"]),
            )

        console.print(table)
        console.print(f"\n[dim]Showing {len(docs)} recently accessed documents[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting recent documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def stats(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Show stats for specific project"
    ),
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed statistics"),
):
    """Show knowledge base statistics"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Query database for statistics
        stats_data = get_stats(project=project)

        if project:
            console.print(f"[bold]Knowledge Base Statistics - Project: {project}[/bold]")
        else:
            console.print("[bold]Knowledge Base Statistics[/bold]")
        console.print("=" * 40)

        # Format and display basic stats
        console.print(f"[blue]Total Documents:[/blue] {stats_data.get('total_documents', 0)}")

        if not project:
            console.print(f"[blue]Total Projects:[/blue] {stats_data.get('total_projects', 0)}")

        console.print(f"[blue]Total Views:[/blue] {stats_data.get('total_views', 0)}")
        console.print(f"[blue]Average Views:[/blue] {stats_data.get('avg_views', 0):.1f}")
        console.print(f"[blue]Database Size:[/blue] {stats_data.get('table_size', '0 MB')}")

        # Most viewed document
        if stats_data.get("most_viewed"):
            most_viewed = stats_data["most_viewed"]
            console.print(
                f"[blue]Most Viewed:[/blue] \"{most_viewed['title']}\" "
                f"({most_viewed['access_count']} views)"
            )
        else:
            console.print("[blue]Most Viewed:[/blue] N/A")

        # Most recent document
        newest_date = stats_data.get("newest_doc")
        console.print(f"[blue]Most Recent:[/blue] {_format_datetime(newest_date)}")

        if detailed:
            console.print("\n[bold]Detailed Statistics[/bold]")
            console.print("-" * 40)

            # Show project breakdown if viewing overall stats
            if not project:
                with db.get_connection() as conn:
                    cursor = conn.execute(
                        """
                        SELECT
                            project,
                            COUNT(*) as doc_count,
                            SUM(access_count) as total_views,
                            MAX(created_at) as last_updated
                        FROM documents
                        WHERE is_deleted = FALSE
                        GROUP BY project
                        ORDER BY doc_count DESC
                        """
                    )

                    project_table = Table(title="Documents by Project")
                    project_table.add_column("Project", style="green")
                    project_table.add_column("Documents", justify="right", style="cyan")
                    project_table.add_column("Total Views", justify="right", style="blue")
                    project_table.add_column("Last Updated", style="yellow")

                    for row in cursor.fetchall():
                        project_name = row[0] or "None"
                        doc_count = row[1]
                        total_views = row[2] or 0
                        last_updated = row[3]

                        project_table.add_row(
                            project_name,
                            str(doc_count),
                            str(total_views),
                            _format_datetime(last_updated, "%Y-%m-%d"),
                        )

                    console.print(project_table)

            # Show access patterns
            with db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        CASE
                            WHEN access_count = 0 THEN 'Never accessed'
                            WHEN access_count <= 5 THEN '1-5 views'
                            WHEN access_count <= 10 THEN '6-10 views'
                            WHEN access_count <= 25 THEN '11-25 views'
                            ELSE '25+ views'
                        END as view_range,
                        COUNT(*) as document_count
                    FROM documents
                    WHERE is_deleted = FALSE
                    """
                    + (" AND project = ?" if project else "")
                    + """
                    GROUP BY view_range
                    ORDER BY MIN(access_count)
                    """,
                    (project,) if project else (),
                )

                console.print("\n[bold]Access Patterns[/bold]")
                for row in cursor.fetchall():
                    console.print(f"[blue]{row[0]}:[/blue] {row[1]} documents")

    except Exception as e:
        console.print(f"[red]Error getting statistics: {e}[/red]")
        raise typer.Exit(1) from e


