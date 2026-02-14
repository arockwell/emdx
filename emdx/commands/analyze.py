"""
Unified analyze command for EMDX.
Consolidates all read-only analysis and inspection operations.
"""

import json

# Removed CommandDefinition import - using standard typer pattern
from datetime import datetime
from typing import Any, Dict, Optional

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from ..database.connection import db_connection
from ..services.document_merger import DocumentMerger
from ..services.duplicate_detector import DuplicateDetector
from ..services.health_monitor import HealthMonitor
from ..utils.datetime_utils import parse_datetime
from ..utils.output import console


def analyze(
    health: bool = typer.Option(False, "--health", "-h", help="Show detailed health metrics"),
    duplicates: bool = typer.Option(False, "--duplicates", "-d", help="Find duplicate documents"),
    similar: bool = typer.Option(False, "--similar", "-s", help="Find similar documents for merging"),
    empty: bool = typer.Option(False, "--empty", "-e", help="Find empty documents"),
    tags: bool = typer.Option(False, "--tags", "-t", help="Analyze tag coverage and patterns"),
    projects: bool = typer.Option(False, "--projects", "-p", help="Show project-level analysis"),
    all_analyses: bool = typer.Option(False, "--all", "-a", help="Run all analyses"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter by specific project"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
):
    """
    Analyze your knowledge base to discover patterns, issues, and insights.

    This command provides comprehensive read-only analysis without making any changes.
    Use it to understand the current state of your knowledge base and identify
    opportunities for improvement.

    Examples:
        emdx maintain analyze              # Show health overview with recommendations
        emdx maintain analyze --health     # Detailed health metrics
        emdx maintain analyze --duplicates # Find duplicate documents
        emdx maintain analyze --all        # Run all analyses
    """

    # If no specific analysis requested, show health overview
    if not any([health, duplicates, similar, empty, tags, projects, all_analyses]):
        health = True

    # If --all is specified, enable everything
    if all_analyses:
        health = duplicates = similar = empty = tags = projects = True

    # Collect results if JSON output is requested
    if json_output:
        results = {}

        if health:
            results["health"] = _collect_health_data()

        if duplicates:
            results["duplicates"] = _collect_duplicates_data()

        if similar:
            results["similar"] = _collect_similar_data()

        if empty:
            results["empty"] = _collect_empty_data()

        if tags:
            results["tags"] = _collect_tags_data(project)

        if projects:
            results["projects"] = _collect_projects_data()

        # Output as JSON
        print(json.dumps(results, indent=2))
        return

    # Header for human-readable output
    console.print(Panel(
        "[bold cyan]📊 Knowledge Base Analysis[/bold cyan]",
        box=box.DOUBLE
    ))

    # Health Analysis
    if health:
        _analyze_health()
        if any([duplicates, similar, empty, tags, projects]):
            console.print()  # Add spacing between sections

    # Duplicate Analysis
    if duplicates:
        _analyze_duplicates()
        if any([similar, empty, tags, projects]):
            console.print()

    # Similar Documents Analysis
    if similar:
        _analyze_similar()
        if any([empty, tags, projects]):
            console.print()

    # Empty Documents Analysis
    if empty:
        _analyze_empty()
        if any([tags, projects]):
            console.print()

    # Tag Analysis
    if tags:
        _analyze_tags(project)
        if projects:
            console.print()

    # Project Analysis
    if projects:
        _analyze_projects()


def _analyze_health():
    """Show detailed health metrics."""
    monitor = HealthMonitor()

    try:
        with console.status("[bold green]Analyzing knowledge base health..."):
            metrics = monitor.calculate_overall_health()
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return

    # Overall health score
    overall_score = metrics["overall_score"] * 100  # Convert to percentage
    health_color = (
        "green" if overall_score >= 80 else
        "yellow" if overall_score >= 60 else
        "red"
    )

    console.print(f"\n[bold]Overall Health Score: [{health_color}]{overall_score:.0f}%[/{health_color}][/bold]")

    # Detailed metrics
    console.print("\n[bold]Health Metrics:[/bold]")

    metrics_table = Table(show_header=False, box=box.SIMPLE)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Score", justify="right")
    metrics_table.add_column("Status")
    metrics_table.add_column("Details")

    # Tag Coverage
    tag_metric = metrics["metrics"]["tag_coverage"]
    tag_score = tag_metric.value * 100  # Convert to percentage
    tag_color = "green" if tag_score >= 80 else "yellow" if tag_score >= 60 else "red"
    metrics_table.add_row(
        "Tag Coverage",
        f"[{tag_color}]{tag_score:.0f}%[/{tag_color}]",
        _get_status_emoji(tag_score),
        tag_metric.details
    )

    # Duplicate Ratio
    dup_metric = metrics["metrics"]["duplicate_ratio"]
    dup_score = dup_metric.value * 100
    dup_color = "green" if dup_score >= 80 else "yellow" if dup_score >= 60 else "red"
    metrics_table.add_row(
        "Duplicate Ratio",
        f"[{dup_color}]{dup_score:.0f}%[/{dup_color}]",
        _get_status_emoji(dup_score),
        dup_metric.details
    )

    # Organization
    org_metric = metrics["metrics"]["organization"]
    org_score = org_metric.value * 100
    org_color = "green" if org_score >= 80 else "yellow" if org_score >= 60 else "red"
    metrics_table.add_row(
        "Organization",
        f"[{org_color}]{org_score:.0f}%[/{org_color}]",
        _get_status_emoji(org_score),
        org_metric.details
    )

    # Activity
    act_metric = metrics["metrics"]["activity"]
    act_score = act_metric.value * 100
    act_color = "green" if act_score >= 80 else "yellow" if act_score >= 60 else "red"
    metrics_table.add_row(
        "Activity",
        f"[{act_color}]{act_score:.0f}%[/{act_color}]",
        _get_status_emoji(act_score),
        act_metric.details
    )

    console.print(metrics_table)

    # Collect all recommendations
    all_recommendations = []
    for metric in metrics["metrics"].values():
        all_recommendations.extend(metric.recommendations)

    if all_recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in all_recommendations:
            console.print(f"  • {rec}")
        console.print("\n[dim]Run 'emdx maintain' to fix these issues[/dim]")


def _analyze_duplicates():
    """Find duplicate documents."""
    detector = DuplicateDetector()

    try:
        with console.status("[bold green]Detecting duplicates..."):
            exact_dupes = detector.find_duplicates()
            near_dupes = detector.find_near_duplicates(threshold=0.85)
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return

    console.print("[bold]Duplicate Analysis:[/bold]")

    if not exact_dupes and not near_dupes:
        console.print("  ✨ [green]No duplicate documents found![/green]")
        return

    # Exact duplicates
    if exact_dupes:
        total_exact = sum(len(group) - 1 for group in exact_dupes)
        console.print(f"\n  [yellow]Exact Duplicates:[/yellow] {len(exact_dupes)} groups ({total_exact} documents)")

        # Show a few examples
        for i, group in enumerate(exact_dupes[:3], 1):
            console.print(f"    • Group {i}: '{group[0]['title']}' ({len(group)} copies)")

    # Near duplicates
    if near_dupes:
        console.print(f"\n  [yellow]Near Duplicates:[/yellow] {len(near_dupes)} pairs (85%+ similar)")

        # Show a few examples
        for _i, (doc1, doc2, similarity) in enumerate(near_dupes[:3], 1):
            console.print(f"    • '{doc1['title']}' ↔ '{doc2['title']}' ({similarity:.0%} similar)")

    console.print("\n[dim]Run 'emdx maintain --clean' to remove duplicates[/dim]")


def _analyze_similar():
    """Find similar documents for merging."""
    merger = DocumentMerger()

    try:
        with console.status("[bold green]Finding similar documents..."):
            candidates = merger.find_merge_candidates(similarity_threshold=0.7)
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return

    console.print("[bold]Similar Documents (Merge Candidates):[/bold]")

    if not candidates:
        console.print("  ✨ [green]No similar documents found![/green]")
        return

    console.print(f"\n  Found {len(candidates)} merge candidates:")

    # Show top candidates
    for i, candidate in enumerate(candidates[:5], 1):
        console.print(f"\n  [{i}] [cyan]{candidate.doc1['title']}[/cyan]")
        console.print(f"      ↔ [cyan]{candidate.doc2['title']}[/cyan]")
        console.print(f"      [dim]Similarity: {candidate.similarity:.0%} | "
                     f"Combined length: {candidate.combined_length:,} chars[/dim]")

    if len(candidates) > 5:
        console.print(f"\n  [dim]... and {len(candidates) - 5} more[/dim]")

    console.print("\n[dim]Run 'emdx maintain --merge' to merge similar documents[/dim]")


def _analyze_empty():
    """Find empty documents."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title, LENGTH(content) as length, project, access_count
            FROM documents
            WHERE is_deleted = 0
            AND LENGTH(content) < 10
            ORDER BY length, id
        """)

        empty_docs = cursor.fetchall()

    console.print("[bold]Empty Documents Analysis:[/bold]")

    if not empty_docs:
        console.print("  ✨ [green]No empty documents found![/green]")
        return

    console.print(f"\n  [yellow]Found {len(empty_docs)} empty documents[/yellow]")

    # Show examples
    console.print("\n  Examples:")
    for doc in empty_docs[:5]:
        console.print(f"    • #{doc['id']}: '{doc['title']}' ({doc['length']} chars, {doc['access_count']} views)")

    if len(empty_docs) > 5:
        console.print(f"    [dim]... and {len(empty_docs) - 5} more[/dim]")

    console.print("\n[dim]Run 'emdx maintain --clean' to remove empty documents[/dim]")


def _analyze_tags(project: Optional[str] = None):
    """Analyze tag coverage and patterns."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Overall tag statistics
        if project:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT d.id) as total_docs,
                    COUNT(DISTINCT CASE WHEN dt.document_id IS NOT NULL THEN d.id END) as tagged_docs,
                    COUNT(DISTINCT t.id) as unique_tags,
                    AVG(CASE WHEN dt.document_id IS NOT NULL THEN tag_count ELSE 0 END) as avg_tags
                FROM documents d
                LEFT JOIN (
                    SELECT document_id, COUNT(*) as tag_count
                    FROM document_tags
                    GROUP BY document_id
                ) dt ON d.id = dt.document_id
                LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
                LEFT JOIN tags t ON dt2.tag_id = t.id
                WHERE d.is_deleted = 0 AND d.project = ?
            """, (project,))
        else:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT d.id) as total_docs,
                    COUNT(DISTINCT CASE WHEN dt.document_id IS NOT NULL THEN d.id END) as tagged_docs,
                    COUNT(DISTINCT t.id) as unique_tags,
                    AVG(CASE WHEN dt.document_id IS NOT NULL THEN tag_count ELSE 0 END) as avg_tags
                FROM documents d
                LEFT JOIN (
                    SELECT document_id, COUNT(*) as tag_count
                    FROM document_tags
                    GROUP BY document_id
                ) dt ON d.id = dt.document_id
                LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
                LEFT JOIN tags t ON dt2.tag_id = t.id
                WHERE d.is_deleted = 0
            """)

        stats = cursor.fetchone()

        console.print("[bold]Tag Analysis:[/bold]")

        if project:
            console.print(f"  [dim]Project: {project}[/dim]")

        coverage = (stats['tagged_docs'] / stats['total_docs'] * 100) if stats['total_docs'] > 0 else 0

        console.print(f"\n  Tag Coverage: [{_get_coverage_color(coverage)}]{coverage:.1f}%[/{_get_coverage_color(coverage)}]")
        console.print(f"  Total Documents: {stats['total_docs']:,}")
        console.print(f"  Tagged Documents: {stats['tagged_docs']:,}")
        console.print(f"  Unique Tags: {stats['unique_tags']}")
        console.print(f"  Avg Tags per Doc: {stats['avg_tags']:.1f}")

        # Most used tags
        cursor.execute("""
            SELECT t.name, COUNT(dt.document_id) as usage_count
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = 0
            GROUP BY t.id, t.name
            ORDER BY usage_count DESC
            LIMIT 10
        """)

        top_tags = cursor.fetchall()
        if top_tags:
            console.print("\n  [bold]Most Used Tags:[/bold]")
            for tag in top_tags[:5]:
                console.print(f"    • {tag['name']} ({tag['usage_count']} docs)")

        # Untagged documents
        cursor.execute("""
            SELECT COUNT(*) as untagged
            FROM documents d
            WHERE d.is_deleted = 0
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """ + (" AND d.project = ?" if project else ""),
        (project,) if project else ())

        untagged = cursor.fetchone()['untagged']
        if untagged > 0:
            console.print(f"\n  [yellow]⚠️  {untagged} documents have no tags[/yellow]")
            console.print("  [dim]Run 'emdx maintain --tags' to auto-tag documents[/dim]")


def _analyze_projects():
    """Show project-level analysis."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                p.project,
                COUNT(*) as doc_count,
                AVG(LENGTH(p.content)) as avg_length,
                SUM(p.access_count) as total_views,
                COUNT(DISTINCT dt.tag_id) as unique_tags,
                MAX(p.updated_at) as last_updated
            FROM documents p
            LEFT JOIN document_tags dt ON p.id = dt.document_id
            WHERE p.is_deleted = 0
            GROUP BY p.project
            ORDER BY doc_count DESC
        """)

        projects = cursor.fetchall()

    console.print("[bold]Project Analysis:[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Project", style="cyan")
    table.add_column("Docs", justify="right")
    table.add_column("Avg Size", justify="right")
    table.add_column("Views", justify="right")
    table.add_column("Tags", justify="right")
    table.add_column("Last Updated")

    for proj in projects:
        last_updated = parse_datetime(proj['last_updated'])
        days_ago = (datetime.now() - last_updated).days if last_updated else 0

        table.add_row(
            proj['project'] or "[No Project]",
            str(proj['doc_count']),
            f"{proj['avg_length']:.0f}",
            f"{proj['total_views']:,}",
            str(proj['unique_tags']),
            f"{days_ago}d ago"
        )

    console.print(table)


def _get_status_emoji(score: float) -> str:
    """Get status emoji based on score."""
    if score >= 80:
        return "✅"
    elif score >= 60:
        return "⚠️"
    else:
        return "❌"


def _get_coverage_color(coverage: float) -> str:
    """Get color based on coverage percentage."""
    if coverage >= 80:
        return "green"
    elif coverage >= 60:
        return "yellow"
    else:
        return "red"


# JSON collection functions
def _collect_health_data() -> Dict[str, Any]:
    """Collect health metrics as structured data."""
    monitor = HealthMonitor()
    try:
        metrics = monitor.calculate_overall_health()
    except ImportError as e:
        return {"error": str(e)}

    # Convert HealthMetric objects to dictionaries
    result = {
        "overall_score": metrics["overall_score"],
        "overall_status": metrics["overall_status"],
        "metrics": {},
        "statistics": metrics.get("statistics", {}),
        "timestamp": metrics.get("timestamp", datetime.now().isoformat())
    }

    # Convert each metric
    for key, metric in metrics["metrics"].items():
        result["metrics"][key] = {
            "name": metric.name,
            "value": metric.value,
            "score": metric.value * 100,  # Convert to percentage
            "weight": metric.weight,
            "status": metric.status,
            "details": metric.details,
            "recommendations": metric.recommendations
        }

    return result


def _collect_duplicates_data() -> Dict[str, Any]:
    """Collect duplicate analysis data."""
    detector = DuplicateDetector()
    exact_dupes = detector.find_duplicates()
    try:
        near_dupes = detector.find_near_duplicates(threshold=0.85)
    except ImportError:
        near_dupes = []

    result = {
        "exact_duplicates": {
            "count": len(exact_dupes),
            "total_duplicates": sum(len(group) - 1 for group in exact_dupes),
            "groups": []
        },
        "near_duplicates": {
            "count": len(near_dupes),
            "pairs": []
        }
    }

    # Add exact duplicate groups
    for group in exact_dupes[:10]:  # Limit to 10 groups
        result["exact_duplicates"]["groups"].append({
            "title": group[0]['title'],
            "count": len(group),
            "ids": [doc['id'] for doc in group]
        })

    # Add near duplicate pairs
    for doc1, doc2, similarity in near_dupes[:10]:  # Limit to 10 pairs
        result["near_duplicates"]["pairs"].append({
            "doc1": {"id": doc1['id'], "title": doc1['title']},
            "doc2": {"id": doc2['id'], "title": doc2['title']},
            "similarity": similarity
        })

    return result


def _collect_similar_data() -> Dict[str, Any]:
    """Collect similar documents data."""
    merger = DocumentMerger()
    try:
        candidates = merger.find_merge_candidates(similarity_threshold=0.7)
    except ImportError as e:
        return {"error": str(e), "count": 0, "candidates": []}

    result = {
        "count": len(candidates),
        "candidates": []
    }

    for candidate in candidates[:20]:  # Limit to 20
        result["candidates"].append({
            "doc1": {"id": candidate.doc1['id'], "title": candidate.doc1['title']},
            "doc2": {"id": candidate.doc2['id'], "title": candidate.doc2['title']},
            "similarity": candidate.similarity,
            "combined_length": candidate.combined_length
        })

    return result


def _collect_empty_data() -> Dict[str, Any]:
    """Collect empty documents data."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title, LENGTH(content) as length, project, access_count
            FROM documents
            WHERE is_deleted = 0
            AND LENGTH(content) < 10
            ORDER BY length, id
        """)

        empty_docs = cursor.fetchall()

    result = {
        "count": len(empty_docs),
        "documents": []
    }

    for doc in empty_docs:
        result["documents"].append({
            "id": doc['id'],
            "title": doc['title'],
            "length": doc['length'],
            "project": doc['project'],
            "access_count": doc['access_count']
        })

    return result


def _collect_tags_data(project: Optional[str] = None) -> Dict[str, Any]:
    """Collect tag analysis data."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Overall tag statistics
        if project:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT d.id) as total_docs,
                    COUNT(DISTINCT CASE WHEN dt.document_id IS NOT NULL THEN d.id END) as tagged_docs,
                    COUNT(DISTINCT t.id) as unique_tags,
                    AVG(CASE WHEN dt.document_id IS NOT NULL THEN tag_count ELSE 0 END) as avg_tags
                FROM documents d
                LEFT JOIN (
                    SELECT document_id, COUNT(*) as tag_count
                    FROM document_tags
                    GROUP BY document_id
                ) dt ON d.id = dt.document_id
                LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
                LEFT JOIN tags t ON dt2.tag_id = t.id
                WHERE d.is_deleted = 0 AND d.project = ?
            """, (project,))
        else:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT d.id) as total_docs,
                    COUNT(DISTINCT CASE WHEN dt.document_id IS NOT NULL THEN d.id END) as tagged_docs,
                    COUNT(DISTINCT t.id) as unique_tags,
                    AVG(CASE WHEN dt.document_id IS NOT NULL THEN tag_count ELSE 0 END) as avg_tags
                FROM documents d
                LEFT JOIN (
                    SELECT document_id, COUNT(*) as tag_count
                    FROM document_tags
                    GROUP BY document_id
                ) dt ON d.id = dt.document_id
                LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
                LEFT JOIN tags t ON dt2.tag_id = t.id
                WHERE d.is_deleted = 0
            """)

        stats = cursor.fetchone()
        coverage = (stats['tagged_docs'] / stats['total_docs'] * 100) if stats['total_docs'] > 0 else 0

        result = {
            "project": project,
            "coverage": coverage,
            "total_documents": stats['total_docs'],
            "tagged_documents": stats['tagged_docs'],
            "unique_tags": stats['unique_tags'],
            "avg_tags_per_doc": float(stats['avg_tags'] or 0),
            "top_tags": []
        }

        # Most used tags
        cursor.execute("""
            SELECT t.name, COUNT(dt.document_id) as usage_count
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = 0
            GROUP BY t.id, t.name
            ORDER BY usage_count DESC
            LIMIT 20
        """)

        for tag in cursor.fetchall():
            result["top_tags"].append({
                "name": tag['name'],
                "count": tag['usage_count']
            })

        # Untagged count
        cursor.execute("""
            SELECT COUNT(*) as untagged
            FROM documents d
            WHERE d.is_deleted = 0
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """ + (" AND d.project = ?" if project else ""),
        (project,) if project else ())

        result["untagged_count"] = cursor.fetchone()['untagged']

    return result


def _collect_projects_data() -> Dict[str, Any]:
    """Collect project analysis data."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                p.project,
                COUNT(*) as doc_count,
                AVG(LENGTH(p.content)) as avg_length,
                SUM(p.access_count) as total_views,
                COUNT(DISTINCT dt.tag_id) as unique_tags,
                MAX(p.updated_at) as last_updated
            FROM documents p
            LEFT JOIN document_tags dt ON p.id = dt.document_id
            WHERE p.is_deleted = 0
            GROUP BY p.project
            ORDER BY doc_count DESC
        """)

        projects = cursor.fetchall()

    result = {
        "count": len(projects),
        "projects": []
    }

    for proj in projects:
        last_updated = parse_datetime(proj['last_updated'])
        days_ago = (datetime.now() - last_updated).days if last_updated else 0

        result["projects"].append({
            "name": proj['project'] or "[No Project]",
            "doc_count": proj['doc_count'],
            "avg_length": float(proj['avg_length'] or 0),
            "total_views": proj['total_views'],
            "unique_tags": proj['unique_tags'],
            "last_updated": proj['last_updated'],
            "days_since_update": days_ago
        })

    return result


# Create typer app for this module
app = typer.Typer()
app.command()(analyze)


if __name__ == "__main__":
    app()
