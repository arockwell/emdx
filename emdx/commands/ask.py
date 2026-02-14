"""
AI-powered Q&A and semantic search commands for EMDX.
"""

from typing import Optional

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
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Limit to project"),
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
        raise typer.Exit(1)

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
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Limit to project"),
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
    from ..services.ask_service import AskService
    import sys

    service = AskService()

    try:
        # Retrieve docs (reuse the retrieval logic)
        if keyword or not service._has_embeddings():
            docs, method = service._retrieve_keyword(question, limit, project)
        else:
            docs, method = service._retrieve_semantic(question, limit, project)
    except ImportError as e:
        console.print(f"[red]{e}[/red]", highlight=False)
        raise typer.Exit(1)

    if not docs:
        print("No relevant documents found.", file=sys.stderr)
        raise typer.Exit(1)

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
        raise typer.Exit(1)


@app.command("search")
def semantic_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Minimum similarity (0-1)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
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
        raise typer.Exit(1)

    # Check if we have embeddings
    stats = service.stats()
    if stats.indexed_documents == 0:
        console.print("[yellow]No documents indexed. Run 'emdx ai index' first.[/yellow]")
        raise typer.Exit(1)

    try:
        with console.status("[bold blue]Searching...", spinner="dots"):
            results = service.search(query, limit=limit, threshold=threshold)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

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
        raise typer.Exit(1)
    from ..database import db

    service = EmbeddingService()

    # Get the source document title
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            console.print(f"[red]Document {doc_id} not found[/red]")
            raise typer.Exit(1)
        source_title = row[0]

    try:
        with console.status("[bold blue]Finding similar...", spinner="dots"):
            results = service.find_similar(doc_id, limit=limit)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print(f"[yellow]No similar documents found[/yellow]")
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
        raise typer.Exit(1)

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
        raise typer.Exit(1)

    if not confirm:
        confirm = typer.confirm("This will delete all embeddings. Continue?")
        if not confirm:
            raise typer.Abort()

    service = EmbeddingService()
    count = service.clear_index()

    console.print(f"[green]Cleared {count} embeddings[/green]")


@app.command("links")
def show_links(
    doc_id: int = typer.Argument(..., help="Document ID to show links for"),
    depth: int = typer.Option(1, "--depth", "-d", help="How many levels deep to traverse (1-3)"),
):
    """
    Show documents linked to a given document.

    Displays the link graph for a document, showing related documents
    and optionally their related documents (nested).

    Examples:
        emdx ai links 42              # Show links for doc #42
        emdx ai links 42 --depth 2    # Show 2 levels deep
    """
    from ..services.linking_service import LinkingService
    from ..database import db

    linker = LinkingService()

    # Clamp depth to reasonable range
    depth = max(1, min(depth, 3))

    # Get the source document title
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            console.print(f"[red]Document {doc_id} not found[/red]")
            raise typer.Exit(1)
        source_title = row[0]

    # Get links
    links = linker.get_links(doc_id)

    if not links:
        console.print(f"[yellow]No links found for #{doc_id} '{source_title}'[/yellow]")
        console.print("[dim]Run 'emdx ai link <id>' or 'emdx ai link --all' to create links[/dim]")
        return

    console.print(f"[bold]#{doc_id}[/bold] \"{source_title}\"")

    def print_tree(links, prefix="", current_level=1, visited=None):
        if visited is None:
            visited = {doc_id}  # Start with root doc as visited

        for i, link in enumerate(links):
            is_last = i == len(links) - 1

            # Build the tree branch characters
            if prefix:
                branch = "└── " if is_last else "├── "
            else:
                branch = "├── " if not is_last else "└── "

            score = f"{link.similarity_score:.0%}"
            console.print(f"{prefix}{branch}#{link.doc_id} \"{link.title}\" ({score})")

            # Get child links if we haven't reached max depth
            if current_level < depth:
                child_prefix = prefix + ("    " if is_last else "│   ")
                child_links = linker.get_links(link.doc_id, limit=3)
                # Filter out all visited ancestors to prevent cycles
                child_links = [l for l in child_links if l.doc_id not in visited]
                if child_links:
                    new_visited = visited | {link.doc_id}
                    print_tree(child_links[:3], child_prefix, current_level + 1, new_visited)

    print_tree(links)


@app.command("link")
def link_document(
    doc_id: Optional[int] = typer.Argument(None, help="Document ID to link (or use --all)"),
    all_docs: bool = typer.Option(False, "--all", "-a", help="Link all documents"),
    force: bool = typer.Option(False, "--force", "-f", help="Recompute links even if they exist"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Documents per batch (for --all)"),
):
    """
    Create semantic links for a document or all documents.

    This analyzes document content using embeddings and creates bidirectional
    links to similar documents. Requires embeddings to be built first.

    Examples:
        emdx ai link 42           # Link document #42 to similar docs
        emdx ai link --all        # Link all documents (backfill)
        emdx ai link --all -f     # Recompute all links
    """
    from ..services.linking_service import LinkingService

    linker = LinkingService()

    if all_docs:
        # Backfill all documents
        console.print("[bold]Linking all documents...[/bold]")

        # Show current stats
        stats = linker.get_stats()
        console.print(f"[dim]Current links: {stats.total_links} across {stats.documents_with_links} documents[/dim]")

        def progress_callback(current, total):
            console.print(f"[dim]Progress: {current}/{total} documents[/dim]", end="\r")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Linking documents...", total=None)
            count = linker.link_all(force=force, batch_size=batch_size)
            progress.update(task, completed=True)

        console.print(f"\n[green]Linked {count} documents[/green]")

        # Show updated stats
        stats = linker.get_stats()
        console.print(f"[dim]Total links: {stats.total_links} (avg {stats.avg_links_per_doc:.1f}/doc, avg similarity {stats.avg_similarity:.0%})[/dim]")

    elif doc_id is not None:
        # Link a single document
        from ..database import db

        # Get document title
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            if not row:
                console.print(f"[red]Document {doc_id} not found[/red]")
                raise typer.Exit(1)
            title = row[0]

        console.print(f"[bold]Linking #{doc_id} '{title}'...[/bold]")

        with console.status("[bold blue]Finding similar documents..."):
            links = linker.link_document(doc_id, force=force)

        if links:
            console.print(f"[green]Created {len(links)} links:[/green]")
            for link in links:
                score = f"{link.similarity_score:.0%}"
                console.print(f"  #{link.doc_id} \"{link.title}\" ({score})")
        else:
            console.print("[yellow]No similar documents found[/yellow]")
            console.print("[dim]Make sure embeddings are built: emdx ai index[/dim]")

    else:
        console.print("[red]Error: Provide a document ID or use --all[/red]")
        raise typer.Exit(1)


@app.command("link-stats")
def link_stats():
    """Show document linking statistics."""
    from ..services.linking_service import LinkingService

    linker = LinkingService()
    stats = linker.get_stats()

    console.print(Panel(f"""[bold]Document Link Statistics[/bold]

Total links:        {stats.total_links}
Documents linked:   {stats.documents_with_links}
Avg links/doc:      {stats.avg_links_per_doc:.1f}
Avg similarity:     {stats.avg_similarity:.0%}
""", title="Auto-Linking"))
