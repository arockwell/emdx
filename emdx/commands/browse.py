"""
Browse and analytics commands for emdx
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from emdx.database import db
from emdx.models.documents import list_documents, get_recent_documents, get_stats

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

        # Ensure database schema exists
        db.ensure_schema()

        # Query database
        docs = list_documents(project=project, limit=limit)

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
                    f"{doc['id']},{title},{doc['project'] or ''}"
                    f",{doc['created_at'].strftime('%Y-%m-%d')},{doc['access_count']}"
                )

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
                doc["title"][:50] + "..." if len(doc["title"]) > 50 else doc["title"],
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
        if stats_data.get('most_viewed'):
            most_viewed = stats_data['most_viewed']
            console.print(
                f"[blue]Most Viewed:[/blue] \"{most_viewed['title']}\" "
                f"({most_viewed['access_count']} views)"
            )
        else:
            console.print("[blue]Most Viewed:[/blue] N/A")

        # Most recent document
        if stats_data.get('newest_doc'):
            newest_date = stats_data['newest_doc']
            if isinstance(newest_date, str):
                from datetime import datetime
                newest_date = datetime.fromisoformat(newest_date)
            console.print(f"[blue]Most Recent:[/blue] {newest_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            console.print("[blue]Most Recent:[/blue] N/A")

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

                        if last_updated:
                            if isinstance(last_updated, str):
                                from datetime import datetime
                                last_updated = datetime.fromisoformat(last_updated)
                            last_updated_str = last_updated.strftime('%Y-%m-%d')
                        else:
                            last_updated_str = "N/A"

                        project_table.add_row(
                            project_name,
                            str(doc_count),
                            str(total_views),
                            last_updated_str
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
                    """ + (" AND project = ?" if project else "") + """
                    GROUP BY view_range
                    ORDER BY MIN(access_count)
                    """,
                    (project,) if project else ()
                )

                console.print("\n[bold]Access Patterns[/bold]")
                for row in cursor.fetchall():
                    console.print(f"[blue]{row[0]}:[/blue] {row[1]} documents")

    except Exception as e:
        console.print(f"[red]Error getting statistics: {e}[/red]")
        raise typer.Exit(1) from e


@app.command(name="project-stats")
def project_stats(
    project: Optional[str] = typer.Argument(None, help="Project name (show all if omitted)"),
):
    """Show detailed project statistics"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        if project:
            console.print(f"[bold]Statistics for project: {project}[/bold]")
            console.print("=" * 50)

            # Get project-specific stats
            stats_data = get_stats(project=project)

            # Display basic project stats
            console.print(f"[blue]Documents:[/blue] {stats_data.get('total_documents', 0)}")
            console.print(f"[blue]Total Views:[/blue] {stats_data.get('total_views', 0)}")
            console.print(f"[blue]Average Views:[/blue] {stats_data.get('avg_views', 0):.1f}")

            if stats_data.get('most_viewed'):
                most_viewed = stats_data['most_viewed']
                console.print(
                    f"[blue]Most Viewed Document:[/blue] \"{most_viewed['title']}\" "
                    f"({most_viewed['access_count']} views)"
                )

            if stats_data.get('newest_doc'):
                newest_date = stats_data['newest_doc']
                if isinstance(newest_date, str):
                    from datetime import datetime
                    newest_date = datetime.fromisoformat(newest_date)
                console.print(
                    f"[blue]Newest Document:[/blue] {newest_date.strftime('%Y-%m-%d %H:%M')}"
                )

            if stats_data.get('last_accessed'):
                last_accessed = stats_data['last_accessed']
                if isinstance(last_accessed, str):
                    from datetime import datetime
                    last_accessed = datetime.fromisoformat(last_accessed)
                console.print(
                    f"[blue]Last Accessed:[/blue] {last_accessed.strftime('%Y-%m-%d %H:%M')}"
                )

            # Show recent documents for this project
            console.print(f"\n[bold]Recent Documents in {project}[/bold]")
            with db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, title, accessed_at, access_count
                    FROM documents
                    WHERE project = ? AND is_deleted = FALSE
                    ORDER BY accessed_at DESC
                    LIMIT 10
                    """,
                    (project,)
                )

                doc_table = Table()
                doc_table.add_column("ID", style="cyan", no_wrap=True)
                doc_table.add_column("Title", style="magenta")
                doc_table.add_column("Last Accessed", style="yellow")
                doc_table.add_column("Views", justify="right", style="blue")

                for row in cursor.fetchall():
                    doc_id, title, accessed_at, access_count = row

                    # Format accessed_at
                    if accessed_at:
                        if isinstance(accessed_at, str):
                            from datetime import datetime
                            accessed_at = datetime.fromisoformat(accessed_at)
                        accessed_str = accessed_at.strftime('%Y-%m-%d %H:%M')
                    else:
                        accessed_str = "Never"

                    doc_table.add_row(
                        str(doc_id),
                        title[:40] + "..." if len(title) > 40 else title,
                        accessed_str,
                        str(access_count)
                    )

                console.print(doc_table)

        else:
            console.print("[bold]Statistics by Project[/bold]")
            console.print("=" * 50)

            # Query database for project-specific stats
            with db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        project,
                        COUNT(*) as doc_count,
                        SUM(access_count) as total_views,
                        AVG(access_count) as avg_views,
                        MAX(created_at) as last_updated,
                        SUM(LENGTH(content)) as total_content_size
                    FROM documents
                    WHERE is_deleted = FALSE
                    GROUP BY project
                    ORDER BY doc_count DESC
                    """
                )

                table = Table()
                table.add_column("Project", style="green")
                table.add_column("Documents", justify="right", style="cyan")
                table.add_column("Total Views", justify="right", style="blue")
                table.add_column("Avg Views", justify="right", style="blue")
                table.add_column("Last Updated", style="yellow")
                table.add_column("Content Size", justify="right")

                # Add rows from database
                for row in cursor.fetchall():
                    project_name = row[0] or "None"
                    doc_count = row[1]
                    total_views = row[2] or 0
                    avg_views = row[3] or 0
                    last_updated = row[4]
                    content_size = row[5] or 0

                    # Format last_updated
                    if last_updated:
                        if isinstance(last_updated, str):
                            from datetime import datetime
                            last_updated = datetime.fromisoformat(last_updated)
                        last_updated_str = last_updated.strftime('%Y-%m-%d')
                    else:
                        last_updated_str = "N/A"

                    # Format content size
                    size_mb = content_size / (1024 * 1024)
                    if size_mb >= 1:
                        size_str = f"{size_mb:.1f} MB"
                    elif content_size >= 1024:
                        size_str = f"{content_size / 1024:.1f} KB"
                    else:
                        size_str = f"{content_size} B"

                    table.add_row(
                        project_name,
                        str(doc_count),
                        str(total_views),
                        f"{avg_views:.1f}",
                        last_updated_str,
                        size_str
                    )

                console.print(table)

                # Show summary
                total_docs = sum(row[1] for row in cursor.fetchall())
                if total_docs == 0:
                    console.print("\n[yellow]No documents found in the knowledge base[/yellow]")

    except Exception as e:
        console.print(f"[red]Error getting project statistics: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def projects():
    """List all projects with document counts"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    project,
                    COUNT(*) as count
                FROM documents
                WHERE is_deleted = FALSE
                GROUP BY project
                ORDER BY count DESC, project
                """
            )

            projects = []
            for row in cursor.fetchall():
                projects.append({
                    "project": row[0],
                    "count": row[1]
                })

            if not projects:
                console.print("[yellow]No projects found[/yellow]")
                return

            table = Table(title="Projects")
            table.add_column("Project", style="green")
            table.add_column("Documents", justify="right", style="cyan")

            for project_data in projects:
                project_name = project_data["project"] or "None"
                count = project_data["count"]
                table.add_row(project_name, str(count))

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing projects: {e}[/red]")
        raise typer.Exit(1) from e
