"""
Distill command for EMDX.

Surface and synthesize the best knowledge base content for sharing.
Supports audience-aware output: personal, documentation, or team briefings.
"""

from __future__ import annotations

from typing import Any

import typer

from ..utils.output import console

app = typer.Typer(help="Distill knowledge base content into summaries")


@app.callback(invoke_without_command=True)
def distill(
    ctx: typer.Context,
    topic: str = typer.Argument(
        None,
        help="Topic or query to search for (e.g., 'authentication', 'API design')",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Filter by tags (comma-separated, e.g., 'security,active')",
    ),
    audience: str = typer.Option(
        "me",
        "--for",
        "-f",
        help="Target audience: 'me' (personal), 'docs' (technical), 'coworkers' (team)",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Maximum number of documents to include",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        "-s",
        help="Save the synthesis to the knowledge base",
    ),
    save_tags: str | None = typer.Option(
        None,
        "--save-tags",
        help="Tags to apply when saving (comma-separated)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Output only the synthesis (no metadata)",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Claude model to use (default: opus)",
    ),
) -> None:
    """
    Distill knowledge base content into a coherent summary.

    Finds documents matching a topic or tags, then uses AI to synthesize
    them into a well-organized summary tailored for your audience.

    Examples:
        emdx distill "authentication"
        emdx distill --tags "security,active"
        emdx distill "API design" --for docs
        emdx distill "sprint progress" --for coworkers
        emdx distill "auth" --save --save-tags "synthesis,auth"
    """
    # Validate inputs
    if not topic and not tags:
        console.print("[red]Error: Provide either a topic or --tags filter[/red]")
        raise typer.Exit(1)

    # Validate audience
    valid_audiences = {"me", "docs", "coworkers"}
    if audience not in valid_audiences:
        console.print(
            f"[red]Error: Invalid audience '{audience}'. "
            f"Use one of: {', '.join(valid_audiences)}[/red]"
        )
        raise typer.Exit(1)

    # Find relevant documents
    documents = _find_documents(topic, tags, limit)

    if not documents:
        if topic:
            console.print(f"[yellow]No documents found for topic: {topic}[/yellow]")
        else:
            console.print(f"[yellow]No documents found with tags: {tags}[/yellow]")
        raise typer.Exit(1)

    if not quiet:
        console.print(f"[dim]Found {len(documents)} documents to synthesize...[/dim]")

    # Perform synthesis
    try:
        from ..services.synthesis_service import SynthesisService

        service = SynthesisService(model=model)

        if not quiet:
            with console.status("[bold blue]Synthesizing...", spinner="dots"):
                result = service.synthesize_documents(
                    documents=documents,
                    audience=audience,
                    topic=topic,
                )
        else:
            result = service.synthesize_documents(
                documents=documents,
                audience=audience,
                topic=topic,
            )

    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    # Output the synthesis
    if quiet:
        print(result.content)
    else:
        console.print()
        console.print(result.content)
        console.print()
        console.print(
            f"[dim]Sources: {', '.join(f'#{id}' for id in result.source_ids)} | "
            f"Tokens: {result.token_count:,}[/dim]"
        )

    # Save if requested
    if save:
        _save_synthesis(result, topic, tags, audience, save_tags, quiet)


def _find_documents(
    topic: str | None, tags: str | None, limit: int
) -> list[dict[str, Any]]:
    """
    Find documents matching topic and/or tags.

    Uses hybrid search for topic queries, tag search for tag filters.
    """
    from ..database import db
    from ..models.tags import search_by_tags
    from ..utils.emoji_aliases import expand_alias_string

    db.ensure_schema()

    documents: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    # Search by topic using hybrid search
    if topic:
        try:
            from ..services.hybrid_search import HybridSearchService

            hybrid_service = HybridSearchService()
            results = hybrid_service.search(
                query=topic,
                limit=limit * 2,  # Get extra for tag filtering
                mode=None,  # Auto-detect best mode
            )

            for r in results:
                if r.doc_id not in seen_ids:
                    doc = _fetch_document(r.doc_id)
                    if doc:
                        documents.append(doc)
                        seen_ids.add(r.doc_id)
        except ImportError:
            # Fall back to keyword search if hybrid not available
            from ..models.documents import search_documents

            results = search_documents(topic, limit=limit * 2)
            for r in results:
                if r["id"] not in seen_ids:
                    doc = _fetch_document(r["id"])
                    if doc:
                        documents.append(doc)
                        seen_ids.add(r["id"])

    # Filter by tags if specified
    if tags:
        expanded_tags = expand_alias_string(tags)
        tag_list = [t.strip() for t in expanded_tags.split(",") if t.strip()]

        if tag_list:
            tag_results = search_by_tags(
                tag_names=tag_list,
                mode="all",
                limit=limit * 2,
            )
            tag_doc_ids = {r["id"] for r in tag_results}

            if topic:
                # Filter existing documents to only those matching tags
                documents = [d for d in documents if d["id"] in tag_doc_ids]
            else:
                # No topic, just use tag results
                for r in tag_results:
                    if r["id"] not in seen_ids:
                        doc = _fetch_document(r["id"])
                        if doc:
                            documents.append(doc)
                            seen_ids.add(r["id"])

    # Apply limit
    return documents[:limit]


def _fetch_document(doc_id: int) -> dict[str, Any] | None:
    """Fetch a document by ID."""
    from ..database import db

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, content, project
            FROM documents
            WHERE id = ? AND is_deleted = 0
            """,
            (doc_id,),
        )
        row = cursor.fetchone()

        if row:
            return {
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "project": row[3],
            }
        return None


def _save_synthesis(
    result: Any,
    topic: str | None,
    tags: str | None,
    audience: str,
    save_tags: str | None,
    quiet: bool,
) -> None:
    """Save the synthesis to the knowledge base."""
    from ..models.documents import save_document
    from ..models.tags import add_tags_to_document
    from ..utils.emoji_aliases import expand_alias_string

    # Generate title
    if topic:
        title = f"Synthesis: {topic}"
    elif tags:
        title = f"Synthesis: {tags}"
    else:
        title = "Synthesis"

    # Add audience suffix
    audience_labels = {
        "me": "",
        "docs": " (docs)",
        "coworkers": " (team briefing)",
    }
    title += audience_labels.get(audience, "")

    # Build content with metadata
    content = result.content
    content += f"\n\n---\n\n_Sources: {', '.join(f'#{id}' for id in result.source_ids)}_"

    # Save document
    doc_id = save_document(title=title, content=content, project=None)

    # Apply tags
    tag_list = ["synthesis"]
    if save_tags:
        expanded = expand_alias_string(save_tags)
        tag_list.extend(t.strip() for t in expanded.split(",") if t.strip())

    add_tags_to_document(doc_id, tag_list)

    if not quiet:
        console.print(f"\n[green]✅ Saved as #{doc_id}:[/green] [cyan]{title}[/cyan]")
        console.print(f"   [dim]Tags: {', '.join(tag_list)}[/dim]")
