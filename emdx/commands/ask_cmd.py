"""
Top-level ask command for EMDX.

Ask questions about your knowledge base using semantic or keyword search.
"""

import typer
from rich.panel import Panel

from ..utils.output import console

app = typer.Typer(help="Ask a question about your knowledge base")


@app.callback(invoke_without_command=True)
def ask(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max documents to search"),
    project: str | None = typer.Option(None, "--project", "-p", help="Limit to project"),
    keyword: bool = typer.Option(
        False, "--keyword", "-k", help="Force keyword search (no embeddings)"
    ),
    show_sources: bool = typer.Option(
        True, "--sources/--no-sources", help="Show source documents"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug info"),
    tags: str | None = typer.Option(
        None, "--tags", "-t", help="Filter by tags (comma-separated)"
    ),
    recent: int | None = typer.Option(
        None, "--recent", "-r", help="Limit to docs created in last N days"
    ),
) -> None:
    """
    Ask a question about your knowledge base.

    Uses semantic search if embeddings are indexed, otherwise falls back to keyword search.

    Examples:
        emdx ask "What's our caching strategy?"
        emdx ask "How did we solve the auth bug?" --project myapp
        emdx ask "What does AUTH-123 involve?"
        emdx ask "What are our security patterns?" --tags "security,active"
        emdx ask "What changed recently?" --recent 7
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
        source_strs = [
            f'#{doc_id} "{title}"' for doc_id, title in result.source_titles
        ]
        console.print(f"[dim]Sources: {', '.join(source_strs)}[/dim]")

    if verbose:
        console.print(
            f"[dim]Method: {result.method} | "
            f"Context: {result.context_size:,} chars[/dim]"
        )
