"""
Embedding index management commands for EMDX.

Build, inspect, and clear the semantic search index.
"""

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..utils.output import console

app = typer.Typer(help="Manage the semantic embedding index")


@app.command("build")
def build_index(
    force: bool = typer.Option(
        False, "--force", "-f", help="Reindex all documents"
    ),
    batch_size: int = typer.Option(
        50, "--batch-size", "-b", help="Documents per batch"
    ),
    chunks: bool = typer.Option(
        True,
        "--chunks/--no-chunks",
        help="Also build chunk-level index",
    ),
) -> None:
    """
    Build or update the semantic search index.

    This creates embeddings for all documents and chunks, enabling semantic search.
    Run this once initially, then periodically to index new documents.

    The chunk index enables more precise search results - returning the relevant
    paragraph instead of the entire document.

    Examples:
        emdx embed build          # Index new documents and chunks
        emdx embed build --force  # Reindex everything
        emdx embed build --no-chunks  # Only index documents, skip chunks
    """
    try:
        from ..services.embedding_service import EmbeddingService

        service = EmbeddingService()

        # Show current stats
        stats = service.stats()
        console.print(
            f"[dim]Current index: {stats.indexed_documents}/"
            f"{stats.total_documents} documents"
            f" ({stats.coverage_percent}%)[/dim]"
        )
        console.print(
            f"[dim]Chunk index: {stats.indexed_chunks} chunks[/dim]"
        )

        needs_doc_index = (
            stats.indexed_documents < stats.total_documents or force
        )
        needs_chunk_index = chunks and (stats.indexed_chunks == 0 or force)

        if not needs_doc_index and not needs_chunk_index:
            console.print("[green]Index is already up to date![/green]")
            return

        # Build document index
        if needs_doc_index:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Indexing documents...", total=None
                )
                doc_count = service.index_all(
                    force=force, batch_size=batch_size
                )
                progress.update(task, completed=True)
            console.print(f"[green]Indexed {doc_count} documents[/green]")

        # Build chunk index
        if needs_chunk_index:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Indexing chunks...", total=None
                )
                chunk_count = service.index_chunks(
                    force=force, batch_size=batch_size
                )
                progress.update(task, completed=True)
            console.print(f"[green]Indexed {chunk_count} chunks[/green]")

        # Show updated stats
        stats = service.stats()
        console.print(
            f"[dim]Index now: {stats.indexed_documents}/"
            f"{stats.total_documents} documents"
            f" ({stats.coverage_percent}%)[/dim]"
        )
        console.print(
            f"[dim]Chunk index: {stats.indexed_chunks} chunks[/dim]"
        )
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@app.command("stats")
def show_stats() -> None:
    """Show embedding index statistics."""
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    service = EmbeddingService()
    stats = service.stats()

    def format_bytes(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        else:
            return f"{b / (1024 * 1024):.1f} MB"

    total_size = stats.index_size_bytes + stats.chunk_index_size_bytes

    console.print(
        Panel(
            f"""[bold]Embedding Index Statistics[/bold]

Documents:    {stats.indexed_documents} / {stats.total_documents} indexed
Coverage:     {stats.coverage_percent}%
Chunks:       {stats.indexed_chunks} indexed
Model:        {stats.model_name}
Doc index:    {format_bytes(stats.index_size_bytes)}
Chunk index:  {format_bytes(stats.chunk_index_size_bytes)}
Total size:   {format_bytes(total_size)}
""",
            title="Embedding Index",
        )
    )


@app.command("clear")
def clear_index(
    confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation"
    ),
) -> None:
    """Clear the embedding index (requires reindexing)."""
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not confirm:
        confirm = typer.confirm(
            "This will delete all embeddings. Continue?"
        )
        if not confirm:
            raise typer.Abort()

    service = EmbeddingService()
    count = service.clear_index()

    console.print(f"[green]Cleared {count} embeddings[/green]")
