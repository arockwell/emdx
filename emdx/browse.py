"""
Browse and analytics commands for emdx
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def list(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum documents to show"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
):
    """List all documents in the knowledge base"""
    try:
        import json

        from emdx.database import db

        # Ensure database schema exists
        db.ensure_schema()

        # Query database
        docs = db.list_documents(project=project, limit=limit)

        if not docs:
            console.print("[yellow]No documents found[/yellow]")
            return

        if format == "table":
            # Create table with title
            title = "Knowledge Base Documents"
            if project:
                title += f" - Project: {project}"

            table = Table(title=title)
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Title", style="magenta")
            table.add_column("Project", style="green")
            table.add_column("Created", style="yellow")
            table.add_column("Views", justify="right", style="blue")

            # Add rows from database
            for doc in docs:
                table.add_row(
                    str(doc["id"]),
                    doc["title"][:50] + "..." if len(doc["title"]) > 50 else doc["title"],
                    doc["project"] or "None",
                    doc["created_at"].strftime("%Y-%m-%d"),
                    str(doc["access_count"]),
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(docs)} of {len(docs)} documents[/dim]")

        elif format == "json":
            # Convert datetime objects to strings
            for doc in docs:
                doc["created_at"] = doc["created_at"].isoformat()
            console.print(json.dumps(docs, indent=2))

        elif format == "csv":
            # Output CSV
            console.print("id,title,project,created,views")
            for doc in docs:
                # Escape commas in title
                title = doc["title"].replace(",", "\\,")
                console.print(
                    f"{doc['id']},{title},{doc['project'] or ''},{doc['created_at'].strftime('%Y-%m-%d')},{doc['access_count']}"
                )

    except Exception as e:
        console.print(f"[red]Error listing documents: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def recent(
    limit: int = typer.Argument(10, help="Number of recent documents to show"),
):
    """Show recently accessed documents"""
    # TODO: Query database for recently accessed documents
    # TODO: Order by accessed_at DESC

    table = Table(title=f"Last {limit} Accessed Documents")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Last Accessed", style="yellow")
    table.add_column("Views", justify="right", style="blue")

    # TODO: Add rows from database

    console.print(table)


@app.command()
def stats(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Show stats for specific project"
    ),
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed statistics"),
):
    """Show knowledge base statistics"""
    # TODO: Query database for statistics

    console.print("[bold]Knowledge Base Statistics[/bold]")
    console.print("=" * 40)

    # Basic stats
    stats_data = {
        "Total Documents": "0",
        "Total Projects": "0",
        "Total Views": "0",
        "Database Size": "0 MB",
        "Most Viewed": "N/A",
        "Most Recent": "N/A",
    }

    if project:
        console.print(f"\n[green]Project: {project}[/green]")
        # TODO: Add project-specific stats

    for key, value in stats_data.items():
        console.print(f"[blue]{key}:[/blue] {value}")

    if detailed:
        console.print("\n[bold]Detailed Statistics[/bold]")
        console.print("-" * 40)

        # TODO: Add detailed stats
        # - Documents by project
        # - Access patterns
        # - Growth over time
        # - Search performance metrics


@app.command(name="project-stats")
def project_stats(
    project: Optional[str] = typer.Argument(None, help="Project name (show all if omitted)"),
):
    """Show detailed project statistics"""
    # TODO: Query database for project-specific stats

    if project:
        console.print(f"[bold]Statistics for project: {project}[/bold]")
    else:
        console.print("[bold]Statistics by Project[/bold]")

    console.print("=" * 40)

    table = Table()
    table.add_column("Project", style="green")
    table.add_column("Documents", justify="right", style="cyan")
    table.add_column("Total Views", justify="right", style="blue")
    table.add_column("Last Updated", style="yellow")
    table.add_column("Size (MB)", justify="right")

    # TODO: Add rows from database

    console.print(table)
