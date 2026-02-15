"""
AI-powered Q&A and semantic search commands for EMDX.
"""


import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.output import console

app = typer.Typer(help="AI-powered knowledge base features")


@app.command("ask")
def ask_question(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to search"),
    project: str | None = typer.Option(None, "--project", "-p", help="Limit to project"),
    keyword: bool = typer.Option(False, "--keyword", "-k", help="Force keyword search (no embeddings)"),
    show_sources: bool = typer.Option(True, "--sources/--no-sources", help="Show source documents"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug info"),
):
    """
    Ask a question about your knowledge base.

    Uses semantic search if embeddings are indexed, otherwise falls back to keyword search.

    Examples:
        emdx ai ask "What's our caching strategy?"
        emdx ai ask "How did we solve the auth bug?" --project myapp
        emdx ai ask "What does AUTH-123 involve?"
    """
    from ..services.ask_service import AskService

    service = AskService()

    try:
        with console.status("[bold blue]Thinking...", spinner="dots"):
            result = service.ask(question, limit=limit, project=project, force_keyword=keyword)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    # Display answer
    console.print()
    console.print(Panel(result.text, title="Answer", border_style="green"))

    # Display metadata
    if show_sources and result.sources:
        console.print()
        console.print(f"[dim]Sources: {', '.join(f'#{id}' for id in result.sources)}[/dim]")

    if verbose:
        console.print(f"[dim]Method: {result.method} | Context: {result.context_size:,} chars[/dim]")


@app.command("context")
def get_context(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to retrieve"),
    project: str | None = typer.Option(None, "--project", "-p", help="Limit to project"),
    keyword: bool = typer.Option(False, "--keyword", "-k", help="Force keyword search"),
    include_question: bool = typer.Option(True, "--question/--no-question", help="Include question in output"),
):
    """
    Retrieve context for a question (for piping to claude CLI).

    Outputs retrieved documents as plain text, suitable for piping to claude.

    Examples:
        emdx ai context "How does auth work?" | claude
        emdx ai context "What's the API design?" | claude "summarize this"
        emdx ai context "error handling" --no-question | claude "list the patterns"
    """
    import sys

    from ..services.ask_service import AskService

    service = AskService()

    try:
        # Retrieve docs (reuse the retrieval logic)
        if keyword or not service._has_embeddings():
            docs, method = service._retrieve_keyword(question, limit, project)
        else:
            docs, method = service._retrieve_semantic(question, limit, project)
    except ImportError as e:
        console.print(f"[red]{e}[/red]", highlight=False)
        raise typer.Exit(1) from None

    if not docs:
        print("No relevant documents found.", file=sys.stderr)
        raise typer.Exit(1) from None

    # Build context output
    output_parts = []

    if include_question:
        output_parts.append(f"Question: {question}\n")
        output_parts.append("=" * 60 + "\n")

    for doc_id, title, content in docs:
        # Truncate very long documents
        truncated = content[:4000] if len(content) > 4000 else content
        output_parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}\n")
        output_parts.append("-" * 60 + "\n")

    # Print to stdout (for piping)
    print("\n".join(output_parts))

    # Print metadata to stderr (so it doesn't pollute the pipe)
    print(f"Retrieved {len(docs)} docs via {method} search", file=sys.stderr)


@app.command("index")
def build_index(
    force: bool = typer.Option(False, "--force", "-f", help="Reindex all documents"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Documents per batch"),
):
    """
    Build or update the semantic search index.

    This creates embeddings for all documents, enabling semantic search.
    Run this once initially, then periodically to index new documents.

    Examples:
        emdx ai index          # Index new documents only
        emdx ai index --force  # Reindex everything
    """
    try:
        from ..services.embedding_service import EmbeddingService

        service = EmbeddingService()

        # Show current stats
        stats = service.stats()
        console.print(f"[dim]Current index: {stats.indexed_documents}/{stats.total_documents} documents ({stats.coverage_percent}%)[/dim]")

        if stats.indexed_documents == stats.total_documents and not force:
            console.print("[green]Index is already up to date![/green]")
            return

        # Build index
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing documents...", total=None)
            count = service.index_all(force=force, batch_size=batch_size)
            progress.update(task, completed=True)

        console.print(f"[green]Indexed {count} documents[/green]")

        # Show updated stats
        stats = service.stats()
        console.print(f"[dim]Index now: {stats.indexed_documents}/{stats.total_documents} documents ({stats.coverage_percent}%)[/dim]")
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@app.command("search")
def semantic_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Minimum similarity (0-1)"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
):
    """
    Semantic search across your documents.

    Finds conceptually similar documents, not just keyword matches.

    Examples:
        emdx ai search "authentication flow"
        emdx ai search "performance optimization" --limit 5
    """
    try:
        from ..services.embedding_service import EmbeddingService

        service = EmbeddingService()
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    # Check if we have embeddings
    stats = service.stats()
    if stats.indexed_documents == 0:
        console.print("[yellow]No documents indexed. Run 'emdx ai index' first.[/yellow]")
        raise typer.Exit(1) from None

    try:
        with console.status("[bold blue]Searching...", spinner="dots"):
            results = service.search(query, limit=limit, threshold=threshold)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not results:
        console.print(f"[yellow]No documents found matching '{query}' (threshold: {threshold})[/yellow]")
        return

    # Filter by project if specified
    if project:
        results = [r for r in results if r.project == project]

    table = Table(title=f"Semantic search: '{query}'")
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Score", style="green", width=6)
    table.add_column("Title", width=40)
    table.add_column("Snippet", style="dim")

    for r in results:
        score = f"{r.similarity:.0%}"
        title = r.title[:38] + "..." if len(r.title) > 40 else r.title
        snippet = r.snippet[:50] + "..." if len(r.snippet) > 50 else r.snippet

        table.add_row(str(r.doc_id), score, title, snippet)

    console.print(table)


@app.command("similar")
def find_similar(
    doc_id: int = typer.Argument(..., help="Document ID to find similar docs for"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
):
    """
    Find documents similar to a given document.

    Examples:
        emdx ai similar 42
        emdx ai similar 42 --limit 10
    """
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    from ..database import db

    service = EmbeddingService()

    # Get the source document title
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            console.print(f"[red]Document {doc_id} not found[/red]")
            raise typer.Exit(1) from None
        source_title = row[0]

    try:
        with console.status("[bold blue]Finding similar...", spinner="dots"):
            results = service.find_similar(doc_id, limit=limit)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not results:
        console.print("[yellow]No similar documents found[/yellow]")
        return

    console.print(f"[bold]Documents similar to #{doc_id} '{source_title}':[/bold]\n")

    table = Table()
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Score", style="green", width=6)
    table.add_column("Title", width=50)

    for r in results:
        score = f"{r.similarity:.0%}"
        table.add_row(str(r.doc_id), score, r.title)

    console.print(table)


@app.command("stats")
def show_stats():
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

    console.print(Panel(f"""[bold]Embedding Index Statistics[/bold]

Documents:  {stats.indexed_documents} / {stats.total_documents} indexed
Coverage:   {stats.coverage_percent}%
Model:      {stats.model_name}
Index size: {format_bytes(stats.index_size_bytes)}
""", title="AI Index"))


@app.command("clear")
def clear_index(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear the embedding index (requires reindexing)."""
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not confirm:
        confirm = typer.confirm("This will delete all embeddings. Continue?")
        if not confirm:
            raise typer.Abort()

    service = EmbeddingService()
    count = service.clear_index()

    console.print(f"[green]Cleared {count} embeddings[/green]")
