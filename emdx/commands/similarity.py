"""
Similarity commands for EMDX.

Provides CLI commands for finding similar documents using TF-IDF similarity.
"""

import json
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from ..services.similarity import SimilarityService

console = Console()

# Create typer app for this module
app = typer.Typer(help="Document similarity commands")


@app.command(name="similar")
def similar(
    doc_id: int = typer.Argument(..., help="Document ID to find similar documents for"),
    limit: int = typer.Option(5, "--limit", "-l", help="Number of results to return"),
    threshold: float = typer.Option(
        0.1, "--threshold", "-t", help="Minimum similarity score (0-1)"
    ),
    content_only: bool = typer.Option(
        False, "--content-only", "-c", help="Only use content similarity (ignore tags)"
    ),
    tags_only: bool = typer.Option(
        False, "--tags-only", "-T", help="Only use tag similarity (ignore content)"
    ),
    same_project: bool = typer.Option(
        False, "--same-project", "-p", help="Only find similar docs in same project"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Find documents similar to the specified document.

    Uses TF-IDF content analysis and tag similarity for hybrid scoring.
    By default uses 60% content weight and 40% tag weight.

    Examples:
        emdx similar 42                    # Find top 5 similar to doc #42
        emdx similar 42 --limit 10         # Find top 10
        emdx similar 42 --content-only     # Ignore tags, pure TF-IDF
        emdx similar 42 --same-project     # Only within same project
    """
    if content_only and tags_only:
        console.print("[red]Error: Cannot use both --content-only and --tags-only[/red]")
        raise typer.Exit(1)

    service = SimilarityService()

    with console.status("[bold green]Finding similar documents..."):
        results = service.find_similar(
            doc_id=doc_id,
            limit=limit,
            min_similarity=threshold,
            content_only=content_only,
            tags_only=tags_only,
            same_project=same_project,
        )

    if json_output:
        output = {
            "query_doc_id": doc_id,
            "results": [
                {
                    "doc_id": r.doc_id,
                    "title": r.title,
                    "project": r.project,
                    "similarity_score": round(r.similarity_score, 4),
                    "content_similarity": round(r.content_similarity, 4),
                    "tag_similarity": round(r.tag_similarity, 4),
                    "common_tags": r.common_tags,
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
        return

    if not results:
        console.print(f"[yellow]No similar documents found for #{doc_id}[/yellow]")
        console.print("[dim]Try lowering the threshold with --threshold 0.05[/dim]")
        return

    console.print(f"\n[bold]Similar documents to #{doc_id}:[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("ID", justify="right")
    table.add_column("Title", max_width=40)
    table.add_column("Score", justify="right")
    table.add_column("Content", justify="right")
    table.add_column("Tags", justify="right")
    table.add_column("Common Tags", max_width=30)

    for i, result in enumerate(results, 1):
        # Color code the score
        score = result.similarity_score
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "dim"

        common_tags_str = ", ".join(result.common_tags[:3])
        if len(result.common_tags) > 3:
            common_tags_str += f" (+{len(result.common_tags) - 3})"

        table.add_row(
            str(i),
            str(result.doc_id),
            result.title[:40],
            f"[{score_color}]{score:.2%}[/{score_color}]",
            f"{result.content_similarity:.2%}",
            f"{result.tag_similarity:.2%}",
            common_tags_str or "-",
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(results)} results with threshold >= {threshold}[/dim]")


@app.command(name="similar-text")
def similar_text(
    text: str = typer.Argument(..., help="Text to find similar documents for"),
    limit: int = typer.Option(5, "--limit", "-l", help="Number of results to return"),
    threshold: float = typer.Option(
        0.1, "--threshold", "-t", help="Minimum similarity score (0-1)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Find documents similar to the provided text.

    Uses TF-IDF content analysis to find matching documents.

    Examples:
        emdx similar-text "kubernetes deployment"
        emdx similar-text "how to configure docker compose" --limit 10
    """
    service = SimilarityService()

    with console.status("[bold green]Finding similar documents..."):
        results = service.find_similar_by_text(
            text=text,
            limit=limit,
            min_similarity=threshold,
        )

    if json_output:
        output = {
            "query_text": text,
            "results": [
                {
                    "doc_id": r.doc_id,
                    "title": r.title,
                    "project": r.project,
                    "similarity_score": round(r.similarity_score, 4),
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
        return

    if not results:
        console.print(f"[yellow]No similar documents found for query[/yellow]")
        console.print("[dim]Try lowering the threshold with --threshold 0.05[/dim]")
        return

    console.print(f"\n[bold]Documents similar to: \"{text[:50]}{'...' if len(text) > 50 else ''}\"[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("ID", justify="right")
    table.add_column("Title", max_width=50)
    table.add_column("Project", max_width=20)
    table.add_column("Score", justify="right")

    for i, result in enumerate(results, 1):
        score = result.similarity_score
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "dim"

        table.add_row(
            str(i),
            str(result.doc_id),
            result.title[:50],
            result.project or "-",
            f"[{score_color}]{score:.2%}[/{score_color}]",
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(results)} results with threshold >= {threshold}[/dim]")


@app.command(name="build-index")
def build_index(
    force: bool = typer.Option(False, "--force", "-f", help="Force rebuild even if cache exists"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output except errors"),
):
    """
    Rebuild the TF-IDF similarity index.

    The index is automatically built when first needed, but you can use this
    command to force a rebuild after adding or modifying documents.

    Examples:
        emdx build-index         # Rebuild only if stale
        emdx build-index --force # Always rebuild
    """
    service = SimilarityService()

    if not quiet:
        console.print("[bold]Building TF-IDF similarity index...[/bold]")

    with console.status("[bold green]Building index...") if not quiet else nullcontext():
        stats = service.build_index(force=force)

    if not quiet:
        console.print(f"\n[green]✓[/green] Index built successfully!")
        console.print(f"  Documents indexed: {stats.document_count:,}")
        console.print(f"  Vocabulary size: {stats.vocabulary_size:,}")
        console.print(f"  Cache size: {stats.cache_size_bytes / 1024:.1f} KB")


@app.command(name="index-stats")
def index_stats(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Show statistics about the similarity index.

    Displays information about the current TF-IDF index including
    document count, vocabulary size, and cache age.

    Examples:
        emdx index-stats
        emdx index-stats --json
    """
    service = SimilarityService()

    # Try to load existing cache without rebuilding
    service._load_cache()
    stats = service.get_index_stats()

    if json_output:
        output = {
            "document_count": stats.document_count,
            "vocabulary_size": stats.vocabulary_size,
            "cache_size_bytes": stats.cache_size_bytes,
            "cache_age_seconds": round(stats.cache_age_seconds, 2),
            "last_built": stats.last_built.isoformat() if stats.last_built else None,
        }
        print(json.dumps(output, indent=2))
        return

    console.print("[bold]Similarity Index Statistics[/bold]\n")

    if stats.document_count == 0:
        console.print("[yellow]No index found. Run 'emdx build-index' to create one.[/yellow]")
        return

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Documents indexed", f"{stats.document_count:,}")
    table.add_row("Vocabulary size", f"{stats.vocabulary_size:,}")
    table.add_row("Cache size", f"{stats.cache_size_bytes / 1024:.1f} KB")

    if stats.last_built:
        age_hours = stats.cache_age_seconds / 3600
        if age_hours < 1:
            age_str = f"{stats.cache_age_seconds / 60:.0f} minutes ago"
        elif age_hours < 24:
            age_str = f"{age_hours:.1f} hours ago"
        else:
            age_str = f"{age_hours / 24:.1f} days ago"
        table.add_row("Last built", age_str)
    else:
        table.add_row("Last built", "Never")

    console.print(table)


# Context manager for quiet mode (when no console.status needed)
class nullcontext:
    def __enter__(self):
        return None
    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    app()
