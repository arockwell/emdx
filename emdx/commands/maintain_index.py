"""
Index and linking commands for EMDX maintain.

Embedding index management, semantic/title-match linking, and
entity extraction commands.
"""

from __future__ import annotations

import json
import logging

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..utils.output import console, is_non_interactive

logger = logging.getLogger(__name__)


def index_embeddings(
    force: bool = typer.Option(False, "--force", "-f", help="Reindex all documents"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Documents per batch"),
    chunks: bool = typer.Option(True, "--chunks/--no-chunks", help="Also build chunk-level index"),
    stats_only: bool = typer.Option(False, "--stats", help="Show index stats only"),
    clear: bool = typer.Option(False, "--clear", help="Clear the embedding index"),
) -> None:
    """Build, update, or manage the semantic search index.

    Examples:
        emdx maintain index              # Index new documents
        emdx maintain index --force      # Reindex everything
        emdx maintain index --stats      # Show index statistics
        emdx maintain index --clear      # Clear all embeddings
    """
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        from ..services.embedding_service import EmbeddingService

        service = EmbeddingService()
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if clear:
        if not is_non_interactive():
            confirm = typer.confirm("This will delete all embeddings. Continue?")
            if not confirm:
                raise typer.Abort()
        count = service.clear_index()
        console.print(f"[green]Cleared {count} embeddings[/green]")
        return

    idx_stats = service.stats()

    if stats_only:

        def format_bytes(b: int) -> str:
            if b < 1024:
                return f"{b} B"
            elif b < 1024 * 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b / (1024 * 1024):.1f} MB"

        total_size = idx_stats.index_size_bytes + idx_stats.chunk_index_size_bytes
        console.print(
            Panel(
                f"[bold]Embedding Index Statistics[/bold]\n\n"
                f"Documents:    {idx_stats.indexed_documents} / "
                f"{idx_stats.total_documents} indexed\n"
                f"Coverage:     {idx_stats.coverage_percent}%\n"
                f"Chunks:       {idx_stats.indexed_chunks} indexed\n"
                f"Model:        {idx_stats.model_name}\n"
                f"Doc index:    {format_bytes(idx_stats.index_size_bytes)}\n"
                f"Chunk index:  {format_bytes(idx_stats.chunk_index_size_bytes)}\n"
                f"Total size:   {format_bytes(total_size)}",
                title="AI Index",
            )
        )
        return

    console.print(
        f"[dim]Current index: {idx_stats.indexed_documents}/"
        f"{idx_stats.total_documents} documents ({idx_stats.coverage_percent}%)[/dim]"
    )
    console.print(f"[dim]Chunk index: {idx_stats.indexed_chunks} chunks[/dim]")

    needs_doc_index = idx_stats.indexed_documents < idx_stats.total_documents or force
    needs_chunk_index = chunks and (idx_stats.indexed_chunks == 0 or force)

    if not needs_doc_index and not needs_chunk_index:
        console.print("[green]Index is already up to date![/green]")
        return

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


def create_links(
    doc_id: int = typer.Argument(..., help="Document ID to create links for"),
    all_docs: bool = typer.Option(False, "--all", help="Backfill links for all documents"),
    threshold: float = typer.Option(0.5, "--threshold", "-t", help="Minimum similarity (0-1)"),
    max_links: int = typer.Option(5, "--max", "-m", help="Maximum links per document"),
    cross_project: bool = typer.Option(
        False, "--cross-project", help="Match across all projects (default: same project only)"
    ),
) -> None:
    """Create semantic links for a document (or all documents).

    By default, only matches documents within the same project.
    Use --cross-project to match across all projects.

    Examples:
        emdx maintain link 42
        emdx maintain link 0 --all
        emdx maintain link 42 --threshold 0.6 --max 3
        emdx maintain link 42 --cross-project
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
            total = auto_link_all(
                threshold=threshold,
                max_links=max_links,
                cross_project=cross_project,
            )
            progress.update(task, completed=True)
        console.print(f"[green]Created {total} links across all documents[/green]")
    else:
        # Look up the document's project for scoping
        doc_project: str | None = None
        if not cross_project:
            from ..database import db

            with db.get_connection() as conn:
                row = conn.execute(
                    "SELECT project FROM documents WHERE id = ?", (doc_id,)
                ).fetchone()
                if row:
                    doc_project = row[0]

        result = auto_link_document(
            doc_id, threshold=threshold, max_links=max_links, project=doc_project
        )
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


def remove_link(
    source_id: int = typer.Argument(..., help="First document ID"),
    target_id: int = typer.Argument(..., help="Second document ID"),
) -> None:
    """Remove a link between two documents.

    Examples:
        emdx maintain unlink 42 57
    """
    from ..database import document_links

    deleted = document_links.delete_link(source_id, target_id)
    if deleted:
        console.print(f"[green]Removed link between #{source_id} and #{target_id}[/green]")
    else:
        console.print(f"[yellow]No link found between #{source_id} and #{target_id}[/yellow]")


def wikify_command(
    doc_id: int | None = typer.Argument(None, help="Document ID to wikify"),
    all_docs: bool = typer.Option(False, "--all", help="Wikify all documents"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show matches without creating links"),
    cross_project: bool = typer.Option(
        False,
        "--cross-project",
        help="Match across all projects (default: same project only)",
    ),
) -> None:
    """Create title-match links between documents (auto-wikification).

    Scans document content for mentions of other documents' titles
    and creates links. No AI or embeddings required.

    Examples:
        emdx maintain wikify 42                # Wikify a single document
        emdx maintain wikify --all             # Backfill all documents
        emdx maintain wikify 42 --dry-run      # Preview matches
        emdx maintain wikify --all --cross-project  # Cross-project
    """
    from ..services.wikify_service import title_match_wikify, wikify_all

    if all_docs:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Wikifying all documents...", total=None)
            total_created, docs_processed = wikify_all(dry_run=dry_run, cross_project=cross_project)
            progress.update(task, completed=True)

        if dry_run:
            console.print(
                f"[yellow]Dry run: scanned {docs_processed} documents, "
                f"would create {total_created} links[/yellow]"
            )
        else:
            console.print(
                f"[green]Created {total_created} title-match links "
                f"across {docs_processed} documents[/green]"
            )
        return

    if doc_id is None:
        console.print("[red]Error: provide a document ID or use --all[/red]")
        raise typer.Exit(1)

    result = title_match_wikify(doc_id, dry_run=dry_run, cross_project=cross_project)

    if dry_run:
        if result.dry_run_matches:
            console.print(
                f"[bold]Dry run: {len(result.dry_run_matches)} title match(es) "
                f"found in document #{doc_id}:[/bold]"
            )
            for target_id, target_title in result.dry_run_matches:
                console.print(f"  [cyan]#{target_id}[/cyan] {target_title}")
            if result.skipped_existing > 0:
                console.print(f"  [dim]({result.skipped_existing} already linked)[/dim]")
        else:
            console.print(f"[yellow]No title matches found in document #{doc_id}[/yellow]")
        return

    if result.links_created > 0:
        console.print(
            f"[green]Created {result.links_created} title-match link(s) "
            f"for document #{doc_id}[/green]"
        )
        for lid in result.linked_doc_ids:
            console.print(f"  [cyan]#{lid}[/cyan]")
        if result.skipped_existing > 0:
            console.print(f"  [dim]({result.skipped_existing} already linked)[/dim]")
    else:
        msg = f"[yellow]No new title matches found for document #{doc_id}[/yellow]"
        if result.skipped_existing > 0:
            msg += f" [dim]({result.skipped_existing} already linked)[/dim]"
        console.print(msg)


def _entities_llm(
    *,
    doc_id: int | None,
    all_docs: bool,
    model: str,
    json_output: bool,
) -> None:
    """Handle LLM-powered entity extraction (--llm flag)."""
    from ..services.entity_service import extract_and_save_entities_llm

    if doc_id is None and not all_docs:
        if json_output:
            print(json.dumps({"error": "Provide a document ID or use --all"}))
        else:
            console.print("[red]Error: provide a document ID or use --all[/red]")
        raise typer.Exit(1)

    if all_docs:
        from ..database import db

        with db.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
            doc_ids_list = [row[0] for row in cursor.fetchall()]

        total_entities = 0
        total_relationships = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        docs_processed = 0
        used_model = ""

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task("Extracting entities with LLM...", total=None)
            for did in doc_ids_list:
                report = extract_and_save_entities_llm(did, model=model)
                if report is not None:
                    total_entities += report.entities_extracted
                    total_relationships += report.relationships_extracted
                    total_input_tokens += report.input_tokens
                    total_output_tokens += report.output_tokens
                    total_cost += report.cost_usd
                    used_model = report.model
                    docs_processed += 1
            progress.update(task, completed=True)

        if json_output:
            print(
                json.dumps(
                    {
                        "action": "llm_extract",
                        "entities_extracted": total_entities,
                        "relationships_extracted": total_relationships,
                        "docs_processed": docs_processed,
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "cost_usd": round(total_cost, 4),
                        "model": used_model,
                    }
                )
            )
        else:
            console.print(
                f"[green]Extracted {total_entities} entities, "
                f"{total_relationships} relationships "
                f"from {docs_processed} documents[/green]"
            )
            console.print(
                f"[dim]Tokens: {total_input_tokens:,} in / "
                f"{total_output_tokens:,} out | "
                f"Cost: ${total_cost:.4f} ({used_model})[/dim]"
            )
    else:
        assert doc_id is not None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task(
                f"Extracting entities from #{doc_id} with LLM...",
                total=None,
            )
            report = extract_and_save_entities_llm(doc_id, model=model)
            progress.update(task, completed=True)

        if report is None:
            if json_output:
                print(json.dumps({"error": f"Document {doc_id} not found"}))
            else:
                console.print(f"[red]Document #{doc_id} not found[/red]")
            raise typer.Exit(1)

        if json_output:
            print(
                json.dumps(
                    {
                        "action": "llm_extract",
                        "doc_id": doc_id,
                        "entities_extracted": report.entities_extracted,
                        "relationships_extracted": (report.relationships_extracted),
                        "input_tokens": report.input_tokens,
                        "output_tokens": report.output_tokens,
                        "cost_usd": round(report.cost_usd, 4),
                        "model": report.model,
                    }
                )
            )
        else:
            console.print(
                f"Extracted [cyan]{report.entities_extracted}[/cyan] entities, "
                f"[cyan]{report.relationships_extracted}[/cyan] relationships "
                f"from document #{doc_id}"
            )
            console.print(
                f"[dim]Tokens: {report.input_tokens:,} in / "
                f"{report.output_tokens:,} out | "
                f"Cost: ${report.cost_usd:.4f} ({report.model})[/dim]"
            )


def entities_command(
    doc_id: int | None = typer.Argument(None, help="Document ID to extract entities from"),
    all_docs: bool = typer.Option(False, "--all", help="Extract entities for all documents"),
    wikify: bool = typer.Option(
        True,
        "--wikify/--no-wikify",
        help="Also create entity-match links",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="Clear entity-match links before regenerating",
    ),
    cleanup: bool = typer.Option(
        False,
        "--cleanup",
        help="Remove noisy entities and re-extract with current filters",
    ),
    cross_project: bool = typer.Option(
        False,
        "--cross-project",
        help="Match across all projects (default: same project only)",
    ),
    llm: bool = typer.Option(
        False,
        "--llm",
        help="Use Claude LLM for richer entity extraction (costs tokens)",
    ),
    model: str = typer.Option(
        "haiku",
        "--model",
        help="Model for LLM extraction: haiku (default), sonnet, opus",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Extract entities from documents and create entity-match links.

    Extracts key concepts, technical terms, and proper nouns from
    markdown structure (headings, backtick terms, bold text, capitalized
    phrases). Then cross-references entities across documents to
    create links.

    Use --llm for Claude-powered extraction with richer entity types
    (person, organization, technology, etc.) and relationship discovery.

    Examples:
        emdx maintain entities 42              # Extract + link one doc
        emdx maintain entities --all           # Backfill all documents
        emdx maintain entities 42 --no-wikify  # Extract only, no linking
        emdx maintain entities --cleanup       # Clean + re-extract
        emdx maintain entities --all --json    # JSON output
        emdx maintain entities --all --cross-project  # Cross-project
    """
    from ..services.entity_service import (
        cleanup_noisy_entities,
        entity_match_wikify,
        entity_wikify_all,
        extract_and_save_entities,
    )

    if llm:
        _entities_llm(
            doc_id=doc_id,
            all_docs=all_docs,
            model=model,
            json_output=json_output,
        )
        return

    if cleanup:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task("Cleaning noisy entities & re-extracting...", total=None)
            deleted, re_extracted = cleanup_noisy_entities()
            progress.update(task, completed=True)

        total_links = 0
        docs = 0
        total_entities = 0
        if wikify:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                disable=json_output,
            ) as progress:
                task = progress.add_task("Rebuilding entity-match links...", total=None)
                total_entities, total_links, docs = entity_wikify_all(
                    rebuild=True, cross_project=cross_project
                )
                progress.update(task, completed=True)

        if json_output:
            print(
                json.dumps(
                    {
                        "action": "cleanup",
                        "entities_deleted": deleted,
                        "docs_re_extracted": re_extracted,
                        "entities_extracted": total_entities,
                        "links_created": total_links,
                        "docs_processed": docs,
                    }
                )
            )
        else:
            console.print(
                f"[green]Cleaned up entities, re-extracted for {re_extracted} documents[/green]"
            )
            if wikify:
                console.print(
                    f"[green]Created {total_links} entity-match links "
                    f"across {docs} documents[/green]"
                )
        return

    if all_docs:
        if wikify:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                disable=json_output,
            ) as progress:
                task = progress.add_task("Extracting entities & linking...", total=None)
                total_entities, total_links, docs = entity_wikify_all(
                    rebuild=rebuild,
                    cross_project=cross_project,
                )
                progress.update(task, completed=True)
            if json_output:
                print(
                    json.dumps(
                        {
                            "action": "extract_and_link",
                            "entities_extracted": total_entities,
                            "links_created": total_links,
                            "docs_processed": docs,
                        }
                    )
                )
            else:
                console.print(
                    f"[green]Extracted {total_entities} entities, "
                    f"created {total_links} links "
                    f"across {docs} documents[/green]"
                )
        else:
            from ..database import db

            with db.get_connection() as conn:
                cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
                doc_ids_list = [row[0] for row in cursor.fetchall()]

            total = 0
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                disable=json_output,
            ) as progress:
                task = progress.add_task("Extracting entities...", total=None)
                for did in doc_ids_list:
                    total += extract_and_save_entities(did)
                progress.update(task, completed=True)
            if json_output:
                print(
                    json.dumps(
                        {
                            "action": "extract_only",
                            "entities_extracted": total,
                            "docs_processed": len(doc_ids_list),
                        }
                    )
                )
            else:
                console.print(
                    f"[green]Extracted {total} entities from {len(doc_ids_list)} documents[/green]"
                )
        return

    if doc_id is None:
        if json_output:
            print(json.dumps({"error": "Provide a document ID or use --all"}))
        else:
            console.print("[red]Error: provide a document ID or use --all[/red]")
        raise typer.Exit(1)

    if wikify:
        result = entity_match_wikify(doc_id, cross_project=cross_project)
        if json_output:
            print(
                json.dumps(
                    {
                        "action": "extract_and_link",
                        "doc_id": doc_id,
                        "entities_extracted": result.entities_extracted,
                        "links_created": result.links_created,
                        "linked_doc_ids": result.linked_doc_ids,
                        "skipped_existing": result.skipped_existing,
                    }
                )
            )
        else:
            console.print(
                f"Extracted [cyan]{result.entities_extracted}[/cyan] "
                f"entities from document #{doc_id}"
            )
            if result.links_created > 0:
                console.print(f"[green]Created {result.links_created} entity-match link(s)[/green]")
                for lid in result.linked_doc_ids:
                    console.print(f"  [cyan]#{lid}[/cyan]")
            else:
                console.print("[dim]No new entity-match links created[/dim]")
    else:
        count = extract_and_save_entities(doc_id)
        if json_output:
            print(
                json.dumps(
                    {
                        "action": "extract_only",
                        "doc_id": doc_id,
                        "entities_extracted": count,
                    }
                )
            )
        else:
            console.print(f"Extracted [cyan]{count}[/cyan] entities from document #{doc_id}")
