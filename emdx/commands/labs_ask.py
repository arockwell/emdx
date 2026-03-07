"""Labs ask, wander, and watch commands.

Moved from find flags to standalone commands under `emdx labs`.
"""

from __future__ import annotations

import contextlib
import json
import sys
from typing import TYPE_CHECKING

import typer

from emdx.utils.output import console

if TYPE_CHECKING:
    from emdx.services.ask_service import AskMode


# =============================================================================
# Ask command
# =============================================================================

ask_app = typer.Typer(
    name="ask",
    help="AI-powered question answering over your knowledge base",
    invoke_without_command=True,
)


@ask_app.callback(invoke_without_command=True)
def ask(
    ctx: typer.Context,
    question: list[str] | None = typer.Argument(default=None, help="Question to ask"),
    think: bool = typer.Option(
        False,
        "--think",
        help="Deliberative: build a position paper with arguments for/against",
    ),
    challenge: bool = typer.Option(
        False,
        "--challenge",
        help="Devil's advocate: find evidence AGAINST the position (requires --think)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Socratic debugger: diagnostic questions from your bug history",
    ),
    cite: bool = typer.Option(
        False,
        "--cite",
        help="Add inline [#ID] citations using chunk-level retrieval",
    ),
    machine: bool = typer.Option(
        False,
        "--machine",
        help="Machine-readable output (answer on stdout, metadata on stderr)",
    ),
    recent_days: int | None = typer.Option(
        None,
        "--recent-days",
        help="Filter to docs created in the last N days",
    ),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to retrieve"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """Answer a question using RAG (retrieves context + LLM).

    Examples:
        emdx labs ask "What's our caching strategy?"
        emdx labs ask --think "Should we rewrite in Rust?"
        emdx labs ask --think --challenge "Should we rewrite in Rust?"
        emdx labs ask --debug "TUI freezes on click"
        emdx labs ask --cite "How does auth work?"
        emdx labs ask --machine "Summarize auth"
        emdx labs ask --recent-days 7 "What changed?"
        emdx labs ask --tags "gameplan" "What's the strategy?"
    """
    if ctx.invoked_subcommand is not None:
        return

    search_query = " ".join(question) if question else ""

    ask_mode = _resolve_ask_mode(ask=True, think=think, challenge=challenge, debug=debug, cite=cite)

    if not search_query:
        from emdx.services.ask_service import AskMode as AM

        flag = "ask" if ask_mode == AM.ANSWER else ask_mode.value
        console.print(f"[red]Error: --{flag} requires a question[/red]")
        raise typer.Exit(1)

    _run_ask(
        search_query,
        limit,
        project,
        tags,
        recent_days=recent_days,
        mode=ask_mode,
        cite=cite,
        json_output=json_output,
        machine=machine,
    )


# =============================================================================
# Wander command
# =============================================================================


def wander(
    query: list[str] | None = typer.Argument(default=None, help="Optional topic to wander from"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """Serendipity mode: surface surprising but related documents.

    Finds documents in the 'Goldilocks' similarity band (0.2-0.4) --
    related enough to be interesting, different enough to surprise.

    Examples:
        emdx labs wander                         # random serendipity
        emdx labs wander "machine learning"       # wander from a topic
    """
    search_query = " ".join(query) if query else ""
    _run_wander(search_query, limit, project, json_output)


# =============================================================================
# Watch command group
# =============================================================================

watch_app = typer.Typer(
    name="watch",
    help="Standing queries that alert on new matches",
)


@watch_app.command("add")
def watch_add(
    query: list[str] | None = typer.Argument(default=None, help="Search terms to watch for"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """Save a standing query that alerts when new matches appear.

    Examples:
        emdx labs watch add "deployment"
        emdx labs watch add --tags "security"
    """
    from emdx.commands._watch import create_standing_query

    search_query = " ".join(query) if query else ""

    if not search_query and not tags:
        console.print("[red]Error: watch add requires a query or --tags[/red]")
        raise typer.Exit(1)

    sq_id = create_standing_query(query=search_query, tags=tags, project=project)

    if json_output:
        print(
            json.dumps(
                {
                    "id": sq_id,
                    "query": search_query,
                    "tags": tags,
                    "project": project,
                }
            )
        )
    else:
        print(f"Saved standing query #{sq_id}: {search_query or tags}")


@watch_app.command("list")
def watch_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """List all standing queries.

    Examples:
        emdx labs watch list
        emdx labs watch list --json
    """
    from emdx.commands._watch import display_standing_queries_list

    display_standing_queries_list(json_output=json_output)


@watch_app.command("check")
def watch_check(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """Check all standing queries for new matches.

    Examples:
        emdx labs watch check
        emdx labs watch check --json
    """
    from emdx.commands._watch import (
        check_standing_queries,
        display_check_results,
    )

    matches = check_standing_queries()
    display_check_results(matches, json_output=json_output)


@watch_app.command("remove")
def watch_remove(
    query_id: int = typer.Argument(help="Standing query ID to remove"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
) -> None:
    """Remove a standing query by ID.

    Examples:
        emdx labs watch remove 3
    """
    from emdx.commands._watch import remove_standing_query

    removed = remove_standing_query(query_id)
    if removed:
        if json_output:
            print(json.dumps({"removed": query_id}))
        else:
            print(f"Removed standing query #{query_id}")
    else:
        if json_output:
            print(json.dumps({"error": f"No standing query #{query_id}"}))
        else:
            console.print(f"[red]Error: No standing query #{query_id}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Internal helpers (moved from core.py)
# =============================================================================


def _resolve_ask_mode(
    ask: bool,
    think: bool,
    challenge: bool,
    debug: bool,
    cite: bool,
) -> AskMode:
    """Resolve CLI flags to an AskMode.

    Validates mutual exclusivity of --think, --debug.
    --challenge is only valid with --think.
    --cite without --think/--debug uses default ANSWER mode.
    """
    from emdx.services.ask_service import AskMode

    active_modes = sum([think, debug])
    if active_modes > 1:
        console.print("[red]Error: --think and --debug are mutually exclusive[/red]")
        raise typer.Exit(1)

    if challenge and not think:
        console.print("[red]Error: --challenge requires --think[/red]")
        raise typer.Exit(1)

    if think and challenge:
        return AskMode.CHALLENGE
    if think:
        return AskMode.THINK
    if debug:
        return AskMode.DEBUG
    return AskMode.ANSWER


def _run_ask(
    question: str,
    limit: int,
    project: str | None,
    tags: str | None,
    recent_days: int | None = None,
    mode: AskMode | None = None,
    cite: bool = False,
    json_output: bool = False,
    machine: bool = False,
) -> None:
    """Answer a question using RAG (retrieves context + LLM)."""
    from emdx.services.ask_service import AskMode, AskService

    if mode is None:
        mode = AskMode.ANSWER

    mode_labels = {
        AskMode.ANSWER: "Thinking",
        AskMode.THINK: "Building position paper",
        AskMode.CHALLENGE: "Finding counterarguments",
        AskMode.DEBUG: "Analyzing error patterns",
    }
    spinner_label = mode_labels.get(mode, "Thinking")

    service = AskService()
    try:
        status_ctx = (
            contextlib.nullcontext()
            if (json_output or machine)
            else console.status(f"[bold blue]{spinner_label}...", spinner="dots")
        )
        with status_ctx:
            result = service.ask(
                question,
                limit=limit,
                project=project,
                tags=tags,
                recent_days=recent_days,
                mode=mode,
                cite=cite,
            )
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    # Machine-readable output mode (--machine)
    if machine:
        print(f"ANSWER: {result.text}")
        print()
        print("SOURCES:")
        if result.source_titles:
            for doc_id, title in result.source_titles:
                print(f'#{doc_id} "{title}"')
        else:
            print("(none)")
        print()
        print(f"CONFIDENCE: {result.confidence}")

        print(
            f"method={result.method} "
            f"context_size={result.context_size} "
            f"sources={len(result.sources)}",
            file=sys.stderr,
        )
        return

    # JSON output mode
    if json_output:
        output: dict[str, object] = {
            "mode": mode.value,
            "query": question,
            "answer": result.text,
            "confidence": result.confidence,
            "method": result.method,
            "context_size": result.context_size,
            "sources": [{"id": doc_id, "title": title} for doc_id, title in result.source_titles],
        }
        if result.confidence_signals:
            signals = result.confidence_signals
            output["confidence_score"] = round(signals.composite_score, 3)
            output["confidence_signals"] = {
                "retrieval_score_mean": round(signals.retrieval_score_mean, 3),
                "retrieval_score_spread": round(signals.retrieval_score_spread, 3),
                "source_count": signals.source_count,
                "query_term_coverage": round(signals.query_term_coverage, 3),
                "topic_coherence": round(signals.topic_coherence, 3),
                "recency_score": round(signals.recency_score, 3),
            }
        if cite and result.cited_ids:
            output["cited_ids"] = result.cited_ids
        print(json.dumps(output, indent=2))
        return

    # Rich output mode
    from rich.panel import Panel

    confidence_colors = {
        "high": "green",
        "medium": "yellow",
        "low": "red",
        "insufficient": "red",
    }
    confidence_color = confidence_colors.get(result.confidence, "dim")

    mode_title = {
        AskMode.ANSWER: "Answer",
        AskMode.THINK: "Position Paper",
        AskMode.CHALLENGE: "Devil's Advocate",
        AskMode.DEBUG: "Debugging Analysis",
    }.get(mode, "Answer")
    panel_title = f"{mode_title} [{result.confidence.upper()} confidence]"

    console.print()
    console.print(
        Panel(
            result.text,
            title=panel_title,
            border_style=confidence_color,
        )
    )

    if result.confidence_signals:
        signals = result.confidence_signals
        console.print()
        console.print(
            f"[dim]Confidence: {signals.composite_score:.0%} "
            f"({signals.source_count} sources, "
            f"coverage: {signals.query_term_coverage:.0%}, "
            f"coherence: {signals.topic_coherence:.0%})[/dim]"
        )

    if cite and result.cited_ids:
        console.print()
        cited_strs = [f"#{cid}" for cid in result.cited_ids]
        console.print(f"[dim]Cited: {', '.join(cited_strs)}[/dim]")

    if result.source_titles:
        console.print()
        source_strs = [f'#{doc_id} "{title}"' for doc_id, title in result.source_titles]
        console.print(f"[dim]Sources: {', '.join(source_strs)}[/dim]")


def _run_wander(
    search_query: str,
    limit: int,
    project: str | None,
    json_output: bool,
) -> None:
    """Serendipity search using the Goldilocks similarity band."""
    import random

    try:
        from emdx.services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    from emdx.database import db

    service = EmbeddingService()

    stats = service.stats()
    if stats.indexed_documents < 10:
        msg = (
            f"Serendipity works better with 50+ documents. "
            f"You have {stats.indexed_documents}. "
            f"Try `emdx maintain index` first."
        )
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            console.print(f"[yellow]{msg}[/yellow]")
        return

    seed_doc_id: int | None = None
    if search_query:
        seed_embedding = service.embed_text(search_query)
    else:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            query_sql = (
                "SELECT d.id FROM documents d "
                "JOIN document_embeddings e "
                "ON d.id = e.document_id "
                "WHERE d.is_deleted = 0 AND e.model_name = ? "
                "ORDER BY d.accessed_at DESC NULLS LAST "
                "LIMIT 20"
            )
            params: list[str | int] = [service.MODEL_NAME]
            cursor.execute(query_sql, params)
            recent_ids = [row[0] for row in cursor.fetchall()]

        if not recent_ids:
            msg = "No documents with embeddings found."
            if json_output:
                print(json.dumps({"error": msg}))
            else:
                console.print(f"[yellow]{msg}[/yellow]")
            return

        chosen_id: int = random.choice(recent_ids)
        seed_doc_id = chosen_id
        seed_embedding = service.embed_document(chosen_id)

    try:
        import numpy as np
    except ImportError:
        console.print(
            "[red]numpy is required for wander. Install with: pip install 'emdx[ai]'[/red]"
        )
        raise typer.Exit(1) from None

    with db.get_connection() as conn:
        cursor = conn.cursor()
        base_sql = (
            "SELECT e.document_id, e.embedding, d.title, "
            "d.project, SUBSTR(d.content, 1, 200) as snippet "
            "FROM document_embeddings e "
            "JOIN documents d ON e.document_id = d.id "
            "WHERE e.model_name = ? AND d.is_deleted = 0"
        )
        sql_params: list[str | int] = [service.MODEL_NAME]

        if project:
            base_sql += " AND d.project = ?"
            sql_params.append(project)

        cursor.execute(base_sql, sql_params)
        rows = cursor.fetchall()

    goldilocks_min = 0.2
    goldilocks_max = 0.4
    candidates = []
    for doc_id, emb_bytes, title, doc_project, snippet in rows:
        if doc_id == seed_doc_id:
            continue

        doc_embedding = np.frombuffer(emb_bytes, dtype=np.float32)
        similarity = float(np.dot(seed_embedding, doc_embedding))

        if goldilocks_min <= similarity <= goldilocks_max:
            clean_snippet = ""
            if snippet:
                clean_snippet = snippet.replace("\n", " ")[:100]
            candidates.append(
                {
                    "id": doc_id,
                    "title": title,
                    "project": doc_project,
                    "similarity": round(similarity, 3),
                    "snippet": clean_snippet,
                }
            )

    if not candidates:
        msg = (
            "No surprising connections found. "
            "Your KB might be too focused -- "
            "try saving docs on different topics!"
        )
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            console.print(f"[yellow]{msg}[/yellow]")
        return

    candidates.sort(key=lambda x: x["similarity"], reverse=True)

    effective_limit = min(limit, 5)
    results = candidates[:effective_limit]

    if json_output:
        output = {
            "seed": search_query if search_query else f"doc #{seed_doc_id}",
            "results": results,
        }
        print(json.dumps(output, indent=2))
        return

    seed_desc = f"'{search_query}'" if search_query else f"doc #{seed_doc_id}"
    console.print(
        f"\n[bold]Wandering from {seed_desc} ({len(results)} surprising connections):[/bold]\n"
    )
    for i, r in enumerate(results, 1):
        console.print(f"[bold cyan]#{r['id']}[/bold cyan] [bold]{r['title']}[/bold]")
        meta = []
        if r["project"]:
            meta.append(f"[green]{r['project']}[/green]")
        meta.append(f"[dim]similarity: {r['similarity']:.3f}[/dim]")
        console.print(" | ".join(meta))
        if r["snippet"]:
            console.print(f"[dim]{r['snippet']}[/dim]")
        if i < len(results):
            console.print()

    console.print("\n[dim]Use 'emdx view <id>' to explore a document[/dim]")
