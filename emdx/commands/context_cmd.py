"""
Top-level context command for EMDX.

Retrieve KB documents as plain text context for piping to claude CLI.
"""

import typer

from ..utils.output import console

app = typer.Typer(help="Retrieve context for piping to claude CLI")


@app.callback(invoke_without_command=True)
def context(
    question: str = typer.Argument(..., help="Your question"),
    limit: int = typer.Option(
        10, "--limit", "-n", help="Max documents to retrieve"
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Limit to project"
    ),
    keyword: bool = typer.Option(
        False, "--keyword", "-k", help="Force keyword search"
    ),
    include_question: bool = typer.Option(
        True, "--question/--no-question", help="Include question in output"
    ),
    tags: str | None = typer.Option(
        None, "--tags", "-t", help="Filter by tags (comma-separated)"
    ),
    recent: int | None = typer.Option(
        None, "--recent", "-r", help="Limit to docs created in last N days"
    ),
) -> None:
    """
    Retrieve context for a question (for piping to claude CLI).

    Outputs retrieved documents as plain text, suitable for piping to claude.

    Examples:
        emdx context "How does auth work?" | claude
        emdx context "What's the API design?" | claude "summarize this"
        emdx context "error handling" --no-question | claude "list the patterns"
        emdx context "security best practices" --tags "security" | claude
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
