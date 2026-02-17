"""
Distill command - Surface and synthesize best KB content for sharing.

Provides audience-aware synthesis of documents matching a topic or tags.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

import typer

if TYPE_CHECKING:
    from ..services.synthesis_service import Audience
from rich.console import Console
from rich.panel import Panel

from ..database import db
from ..database.search import search_documents
from ..models.tags import search_by_tags

console = Console()

app = typer.Typer(help="Distill KB content into audience-aware summaries")


class DistillDocumentDict(TypedDict):
    """Document data used in distillation."""

    id: int
    title: str
    content: str


def _get_documents_by_query(
    query: str,
    limit: int = 20,
) -> list[DistillDocumentDict]:
    """Get documents matching a search query."""
    docs = search_documents(query=query, limit=limit)
    return _fetch_full_content(cast(list[DistillDocumentDict], docs))


def _get_documents_by_tags(
    tags: list[str],
    limit: int = 20,
) -> list[DistillDocumentDict]:
    """Get documents matching tags."""
    docs = search_by_tags(tag_names=tags, mode="any", limit=limit)
    return _fetch_full_content(cast(list[DistillDocumentDict], docs))


def _fetch_full_content(docs: list[DistillDocumentDict]) -> list[DistillDocumentDict]:
    """Fetch full content for a list of document summaries."""
    if not docs:
        return []

    doc_ids = [d["id"] for d in docs]

    with db.get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(doc_ids))
        cursor.execute(
            f"SELECT id, title, content FROM documents WHERE id IN ({placeholders})",
            doc_ids,
        )
        rows = cursor.fetchall()

    # Build map for ordering
    content_map = {
        row["id"]: {"id": row["id"], "title": row["title"], "content": row["content"]}
        for row in rows
    }

    # Return in original order
    return [content_map[d["id"]] for d in docs if d["id"] in content_map]  # type: ignore[misc]


def _parse_audience(audience_str: str) -> Audience:
    """Parse audience string to Audience enum."""
    # Import here to handle optional dependency
    try:
        from ..services.synthesis_service import Audience as AudienceEnum
    except ImportError:
        raise typer.Exit(1) from None

    audience_map = {
        "me": AudienceEnum.ME,
        "docs": AudienceEnum.DOCS,
        "coworkers": AudienceEnum.COWORKERS,
        "team": AudienceEnum.COWORKERS,  # alias
    }

    normalized = audience_str.lower().strip()
    if normalized not in audience_map:
        console.print(
            f"[red]Unknown audience: {audience_str}[/red]\n"
            f"Valid options: me, docs, coworkers (or team)"
        )
        raise typer.Exit(1)

    return audience_map[normalized]


@app.callback(invoke_without_command=True)
def distill(
    ctx: typer.Context,
    topic: str = typer.Argument(
        None,
        help="Topic or search query to find and distill documents",
    ),
    tags: str = typer.Option(
        None,
        "--tags",
        "-t",
        help="Comma-separated tags to filter documents",
    ),
    audience: str = typer.Option(
        "me",
        "--for",
        "-f",
        help="Target audience: me (personal), docs (documentation), coworkers (team briefing)",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum number of documents to include",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        "-s",
        help="Save the distilled output to the knowledge base",
    ),
    save_title: str = typer.Option(
        None,
        "--title",
        help="Title for saved document (defaults to 'Distilled: <topic>')",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Output only the distilled content (no headers/stats)",
    ),
) -> None:
    """
    Distill KB content into audience-aware summaries.

    Finds documents matching the topic or tags, then synthesizes them
    into a coherent summary tailored for the target audience.

    Examples:

        emdx distill 'authentication'
            Find all auth-related docs and synthesize

        emdx distill --tags 'security,active'
            Distill docs matching these tags

        emdx distill --for docs 'API design'
            Output suitable for documentation

        emdx distill 'auth' --save --title "Auth Summary"
            Save the distilled output to KB
    """
    # If subcommand invoked, don't run default
    if ctx.invoked_subcommand is not None:
        return

    db.ensure_schema()

    # Validate input
    if not topic and not tags:
        console.print(
            "[red]Please provide a topic to search or --tags to filter by[/red]\n"
            "Examples:\n"
            "  emdx distill 'authentication'\n"
            "  emdx distill --tags 'security,active'"
        )
        raise typer.Exit(1)

    # Parse audience
    target_audience = _parse_audience(audience)

    from ..services.synthesis_service import DistillService

    # Gather documents
    if not quiet:
        console.print("[dim]Searching for documents...[/dim]")

    documents: list[DistillDocumentDict] = []

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        documents = _get_documents_by_tags(tag_list, limit=limit)
        if not quiet:
            console.print(
                f"[dim]Found {len(documents)} docs matching tags: {', '.join(tag_list)}[/dim]"
            )  # noqa: E501

    if topic:
        topic_docs = _get_documents_by_query(topic, limit=limit)
        if not quiet:
            console.print(f"[dim]Found {len(topic_docs)} docs matching: {topic}[/dim]")

        # Merge results, preferring topic docs but including tag docs
        seen_ids = {d["id"] for d in documents}
        for doc in topic_docs:
            if doc["id"] not in seen_ids:
                documents.append(doc)
                seen_ids.add(doc["id"])

    if not documents:
        console.print("[yellow]No documents found matching your criteria.[/yellow]")
        raise typer.Exit(0)

    # Trim to limit
    documents = documents[:limit]

    # Perform synthesis
    try:
        service = DistillService()
        total_chars = sum(len(d.get("content", "")) for d in documents)
        status_msg = (
            f"Synthesizing {len(documents)} documents "
            f"({total_chars:,} chars) for audience: {audience}"
        )
        # Cast to list[dict[str, Any]] for DistillService interface
        docs_for_service = cast(list[dict[str, Any]], documents)
        if quiet:
            result = service.synthesize_documents(
                documents=docs_for_service,
                topic=topic,
                audience=target_audience,
            )
        else:
            with console.status(f"[bold]{status_msg}[/bold]"):
                result = service.synthesize_documents(
                    documents=docs_for_service,
                    topic=topic,
                    audience=target_audience,
                )
    except Exception as e:
        console.print(f"[red]Synthesis failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Output results
    if quiet:
        console.print(result.content)
    else:
        # Show header with stats
        source_ids_str = ", ".join(f"#{id}" for id in result.source_ids[:10])
        if len(result.source_ids) > 10:
            source_ids_str += f" ... (+{len(result.source_ids) - 10} more)"

        header = f"[bold]Distilled Summary[/bold] | Audience: {audience} | Sources: {result.source_count}"  # noqa: E501
        console.print(Panel(header, expand=False))
        console.print()
        console.print(result.content)
        console.print()
        console.print(f"[dim]Sources: {source_ids_str}[/dim]")
        console.print(f"[dim]Tokens: {result.input_tokens} in / {result.output_tokens} out[/dim]")

    # Save if requested
    if save:
        from ..database.documents import save_document as db_save_document
        from ..models.tags import add_tags_to_document

        title = save_title or f"Distilled: {topic or 'Tagged content'}"
        doc_id = db_save_document(title=title, content=result.content)

        # Tag with distilled and audience
        add_tags_to_document(doc_id, ["distilled", f"for-{audience}"])

        if not quiet:
            console.print(f"\n[green]Saved as document #{doc_id}[/green]")
        else:
            console.print(f"#{doc_id}")
