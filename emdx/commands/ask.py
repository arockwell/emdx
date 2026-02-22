"""
AI-powered Q&A and semantic search commands for EMDX.
"""

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..utils.output import console, is_non_interactive

app = typer.Typer(help="AI-powered knowledge base features")


@app.command("ask")
def ask_question(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to search"),
    project: str | None = typer.Option(None, "--project", "-p", help="Limit to project"),
    keyword: bool = typer.Option(
        False, "--keyword", "-k", help="Force keyword search (no embeddings)"
    ),  # noqa: E501
    show_sources: bool = typer.Option(True, "--sources/--no-sources", help="Show source documents"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug info"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    recent: int | None = typer.Option(
        None, "--recent", "-r", help="Limit to docs created in last N days"
    ),  # noqa: E501
) -> None:
    """
    Ask a question about your knowledge base.

    Uses semantic search if embeddings are indexed, otherwise falls back to keyword search.

    Examples:
        emdx ai ask "What's our caching strategy?"
        emdx ai ask "How did we solve the auth bug?" --project myapp
        emdx ai ask "What does AUTH-123 involve?"
        emdx ai ask "What are our security patterns?" --tags "security,active"
        emdx ai ask "What changed recently?" --recent 7
    """
    from ..services.ask_service import AskService

    service = AskService()

    try:
        with console.status("[bold blue]Thinking...", spinner="dots"):
            result = service.ask(
                question,
                limit=limit,
                project=project,
                force_keyword=keyword,
                tags=tags,
                recent_days=recent,
            )
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    # Display answer with confidence indicator
    confidence_colors = {"high": "green", "medium": "yellow", "low": "red"}
    confidence_color = confidence_colors.get(result.confidence, "dim")
    panel_title = f"Answer [{result.confidence.upper()} confidence]"

    console.print()
    console.print(Panel(result.text, title=panel_title, border_style=confidence_color))

    # Display metadata with source titles
    if show_sources and result.source_titles:
        console.print()
        source_strs = [f'#{doc_id} "{title}"' for doc_id, title in result.source_titles]
        console.print(f"[dim]Sources: {', '.join(source_strs)}[/dim]")

    if verbose:
        console.print(
            f"[dim]Method: {result.method} | Context: {result.context_size:,} chars[/dim]"
        )  # noqa: E501


@app.command("context")
def get_context(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to retrieve"),
    project: str | None = typer.Option(None, "--project", "-p", help="Limit to project"),
    keyword: bool = typer.Option(False, "--keyword", "-k", help="Force keyword search"),
    include_question: bool = typer.Option(
        True, "--question/--no-question", help="Include question in output"
    ),  # noqa: E501
    tags: str | None = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    recent: int | None = typer.Option(
        None, "--recent", "-r", help="Limit to docs created in last N days"
    ),  # noqa: E501
) -> None:
    """
    Retrieve context for a question (for piping to claude CLI).

    Outputs retrieved documents as plain text, suitable for piping to claude.

    Examples:
        emdx ai context "How does auth work?" | claude
        emdx ai context "What's the API design?" | claude "summarize this"
        emdx ai context "error handling" --no-question | claude "list the patterns"
        emdx ai context "security best practices" --tags "security" | claude
    """
    import sys

    from ..services.ask_service import AskService

    service = AskService()

    try:
        # Retrieve docs (reuse the retrieval logic)
        if keyword or not service._has_embeddings():
            docs, method = service._retrieve_keyword(
                question, limit, project, tags=tags, recent_days=recent
            )
        else:
            docs, method = service._retrieve_semantic(
                question, limit, project, tags=tags, recent_days=recent
            )
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
        emdx ai index          # Index new documents and chunks
        emdx ai index --force  # Reindex everything
        emdx ai index --no-chunks  # Only index documents, skip chunks
    """
    try:
        from ..services.embedding_service import EmbeddingService

        service = EmbeddingService()

        # Show current stats
        stats = service.stats()
        console.print(
            f"[dim]Current index: {stats.indexed_documents}/"
            f"{stats.total_documents} documents ({stats.coverage_percent}%)[/dim]"
        )
        console.print(f"[dim]Chunk index: {stats.indexed_chunks} chunks[/dim]")

        needs_doc_index = stats.indexed_documents < stats.total_documents or force
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
                task = progress.add_task("Indexing documents...", total=None)
                doc_count = service.index_all(force=force, batch_size=batch_size)
                progress.update(task, completed=True)
            console.print(f"[green]Indexed {doc_count} documents[/green]")

        # Build chunk index
        if needs_chunk_index:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Indexing chunks...", total=None)
                chunk_count = service.index_chunks(force=force, batch_size=batch_size)
                progress.update(task, completed=True)
            console.print(f"[green]Indexed {chunk_count} chunks[/green]")

        # Show updated stats
        stats = service.stats()
        console.print(
            f"[dim]Index now: {stats.indexed_documents}/"
            f"{stats.total_documents} documents ({stats.coverage_percent}%)[/dim]"
        )
        console.print(f"[dim]Chunk index: {stats.indexed_chunks} chunks[/dim]")
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@app.command("search")
def semantic_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Minimum similarity (0-1)"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
) -> None:
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
        console.print(
            f"[yellow]No documents found matching '{query}' (threshold: {threshold})[/yellow]"
        )  # noqa: E501
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
) -> None:
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
            title="AI Index",
        )
    )


@app.command("clear")
def clear_index(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clear the embedding index (requires reindexing)."""
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not confirm and not is_non_interactive():
        confirm = typer.confirm("This will delete all embeddings. Continue?")
        if not confirm:
            raise typer.Abort()

    service = EmbeddingService()
    count = service.clear_index()

    console.print(f"[green]Cleared {count} embeddings[/green]")


@app.command("links")
def show_links(
    doc_id: int = typer.Argument(..., help="Document ID to show links for"),
    depth: int = typer.Option(1, "--depth", "-d", help="Traversal depth (1=direct, 2=two hops)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Show document links (auto-detected and manual).

    Displays all documents linked to the given document, with
    similarity scores and link method.

    Examples:
        emdx ai links 42
        emdx ai links 42 --depth 2
        emdx ai links 42 --json
    """
    import json

    from ..database import document_links

    links = document_links.get_links_for_document(doc_id)

    if json_output:
        items = []
        for link in links:
            if link["source_doc_id"] == doc_id:
                other_id = link["target_doc_id"]
                other_title = link["target_title"]
            else:
                other_id = link["source_doc_id"]
                other_title = link["source_title"]
            items.append(
                {
                    "doc_id": other_id,
                    "title": other_title,
                    "similarity": link["similarity_score"],
                    "method": link["method"],
                }
            )
        print(json.dumps({"doc_id": doc_id, "links": items}, indent=2))
        return

    if not links:
        console.print(f"[yellow]No links found for document #{doc_id}[/yellow]")
        return

    # Get source document title
    from ..database import db

    with db.get_connection() as conn:
        cursor = conn.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        source_title = row[0] if row else f"Document #{doc_id}"

    console.print(f"[bold]Links for #{doc_id} '{source_title}':[/bold]\n")

    table = Table()
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Score", style="green", width=6)
    table.add_column("Title", width=50)
    table.add_column("Method", style="dim", width=8)

    for link in links:
        if link["source_doc_id"] == doc_id:
            other_id = link["target_doc_id"]
            other_title = link["target_title"]
        else:
            other_id = link["source_doc_id"]
            other_title = link["source_title"]
        score = f"{link['similarity_score']:.0%}"
        table.add_row(str(other_id), score, other_title, link["method"])

    console.print(table)

    # Depth 2: show links of linked documents
    if depth >= 2:
        seen = {doc_id}
        for link in links:
            if link["source_doc_id"] == doc_id:
                neighbor_id = link["target_doc_id"]
            else:
                neighbor_id = link["source_doc_id"]
            seen.add(neighbor_id)

        for link in links:
            if link["source_doc_id"] == doc_id:
                neighbor_id = link["target_doc_id"]
                neighbor_title = link["target_title"]
            else:
                neighbor_id = link["source_doc_id"]
                neighbor_title = link["source_title"]

            hop2_links = document_links.get_links_for_document(neighbor_id)
            hop2_new = []
            for h in hop2_links:
                if h["source_doc_id"] == neighbor_id:
                    h_other = h["target_doc_id"]
                else:
                    h_other = h["source_doc_id"]
                if h_other not in seen:
                    hop2_new.append(h)
                    seen.add(h_other)

            if hop2_new:
                console.print(f"\n[dim]  via #{neighbor_id} '{neighbor_title}':[/dim]")
                for h in hop2_new:
                    if h["source_doc_id"] == neighbor_id:
                        h_id = h["target_doc_id"]
                        h_title = h["target_title"]
                    else:
                        h_id = h["source_doc_id"]
                        h_title = h["source_title"]
                    console.print(
                        f"    [cyan]#{h_id}[/cyan] {h_title} "
                        f"[dim]({h['similarity_score']:.0%})[/dim]"
                    )


@app.command("link")
def create_link(
    doc_id: int = typer.Argument(..., help="Document ID to create links for"),
    all_docs: bool = typer.Option(False, "--all", help="Backfill links for all indexed documents"),
    threshold: float = typer.Option(0.5, "--threshold", "-t", help="Minimum similarity (0-1)"),
    max_links: int = typer.Option(5, "--max", "-m", help="Maximum links per document"),
) -> None:
    """
    Create semantic links for a document (or all documents).

    Uses the embedding index to find similar documents and create
    links. Requires ``emdx ai index`` to be run first.

    Examples:
        emdx ai link 42
        emdx ai link 0 --all
        emdx ai link 42 --threshold 0.6 --max 3
    """
    try:
        from ..services.link_service import auto_link_all, auto_link_document
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if all_docs:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Linking all documents...", total=None)
            total = auto_link_all(threshold=threshold, max_links=max_links)
            progress.update(task, completed=True)
        console.print(f"[green]Created {total} links across all documents[/green]")
    else:
        result = auto_link_document(doc_id, threshold=threshold, max_links=max_links)
        if result.links_created > 0:
            console.print(
                f"[green]Created {result.links_created} link(s) for document #{doc_id}[/green]"
            )
            for lid, score in zip(result.linked_doc_ids, result.scores, strict=False):
                console.print(f"  [cyan]#{lid}[/cyan] ({score:.0%})")
        else:
            console.print(
                f"[yellow]No similar documents found above {threshold:.0%} threshold[/yellow]"
            )


@app.command("unlink")
def remove_link(
    source_id: int = typer.Argument(..., help="First document ID"),
    target_id: int = typer.Argument(..., help="Second document ID"),
) -> None:
    """
    Remove a link between two documents.

    Removes the link in either direction between the two documents.

    Examples:
        emdx ai unlink 42 57
    """
    from ..database import document_links

    deleted = document_links.delete_link(source_id, target_id)
    if deleted:
        console.print(f"[green]Removed link between #{source_id} and #{target_id}[/green]")
    else:
        console.print(f"[yellow]No link found between #{source_id} and #{target_id}[/yellow]")
