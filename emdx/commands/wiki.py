"""
Wiki commands for EMDX.

Auto-wiki generation from the knowledge base: topic discovery, article
generation, entity pages, export, and editorial controls.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import cast

import typer
from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..utils.output import console

logger = logging.getLogger(__name__)


def slugify_label(label: str) -> str:
    """Convert a topic label to a URL-friendly slug.

    Shared helper used by wiki rename, retitle, merge, split, and
    the wiki synthesis service.
    """
    slug = label.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:80].strip("-")


def _format_ms(ms: float) -> str:
    """Format milliseconds into a human-readable string."""
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    if ms == 0:
        return "0ms"
    if ms < 1:
        return f"{ms:.2f}ms"
    return f"{ms:.0f}ms"


def _set_topic_status(topic_id: int, new_status: str) -> tuple[str, str]:
    """Set a wiki topic's status. Returns (topic_label, old_status).

    Raises typer.Exit(1) if topic not found.
    """
    from ..database import db as _db

    with _db.get_connection() as conn:
        row = conn.execute(
            "SELECT topic_label, status FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()

        if not row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)

        old_status = row[1]
        conn.execute(
            "UPDATE wiki_topics SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, topic_id),
        )
        conn.commit()

    return row[0], old_status


# ── Wiki typer app ────────────────────────────────────────────────────

wiki_app = typer.Typer(help="Auto-wiki generation from knowledge base")


@wiki_app.command(name="topics")
def wiki_topics(
    resolution: float = typer.Option(0.005, "--resolution", "-r", help="Clustering resolution"),
    save: bool = typer.Option(False, "--save", help="Save discovered topics to DB"),
    min_size: int = typer.Option(3, "--min-size", help="Minimum cluster size"),
    entity_types: list[str] = typer.Option(
        ["heading", "proper_noun"],
        "--entity-types",
        "-e",
        help="Entity types to use for clustering (default: heading, proper_noun)",
    ),
    min_df: int = typer.Option(
        2,
        "--min-df",
        help="Minimum document frequency for an entity to be included",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show extra columns (model override, editorial prompt)"
    ),
) -> None:
    """Discover topic clusters using Leiden community detection.

    Examples:
        emdx maintain wiki topics              # Preview topics
        emdx maintain wiki topics --save       # Save to DB
        emdx maintain wiki topics -r 0.01      # Finer resolution
        emdx maintain wiki topics --verbose    # Show model overrides and editorial prompts
        emdx maintain wiki topics -e heading -e proper_noun -e concept  # Custom entity types
        emdx maintain wiki topics --entity-types heading  # Only headings
    """
    from rich.table import Table

    if verbose:
        from ..services.wiki_clustering_service import get_topics

        topics = get_topics()
        if not topics:
            console.print("[dim]No saved topics found[/dim]")
            return

        # Fetch editorial prompts for all topics
        from ..database import db

        editorial_prompts: dict[int, str | None] = {}
        with db.get_connection() as conn:
            for t in topics:
                tid = t["id"]
                assert isinstance(tid, int)
                row = conn.execute(
                    "SELECT editorial_prompt FROM wiki_topics WHERE id = ?",
                    (tid,),
                ).fetchone()
                editorial_prompts[tid] = row[0] if row else None

        table = Table(title="Saved Topics", box=box.SIMPLE)
        table.add_column("ID", style="dim", width=4)
        table.add_column("Label", style="cyan")
        table.add_column("Docs", justify="right")
        table.add_column("Status")
        table.add_column("Editorial Prompt", style="yellow")

        for t in topics:
            tid = t["id"]
            assert isinstance(tid, int)
            prompt = editorial_prompts.get(tid)
            prompt_display = str(prompt)[:60] if prompt else "[dim]-[/dim]"
            table.add_row(
                str(tid),
                str(t["label"])[:50],
                str(t["member_count"]),
                str(t["status"]),
                prompt_display,
            )

        console.print(table)
        return

    from ..services.wiki_clustering_service import discover_topics, save_topics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Discovering topics...", total=None)
        result = discover_topics(
            resolution=resolution,
            min_cluster_size=min_size,
            entity_types=entity_types or None,
            min_df=min_df,
        )
        progress.update(task, completed=True)

    console.print(
        f"\n[bold]Found {len(result.clusters)} topics[/bold] "
        f"covering {result.docs_clustered}/{result.total_docs} docs "
        f"({result.docs_unclustered} unclustered)"
    )

    table = Table(title="Topic Clusters", box=box.SIMPLE)
    table.add_column("#", style="dim", width=4)
    table.add_column("Label", style="cyan")
    table.add_column("Docs", justify="right")
    table.add_column("Coherence", justify="right")
    table.add_column("Top Entities", style="dim")
    if verbose:
        table.add_column("Model Override", style="yellow")

    # If verbose, fetch saved topics with model_override from DB
    saved_overrides: dict[int, str | None] = {}
    if verbose:
        from ..services.wiki_clustering_service import get_topics as _get_saved

        for t in _get_saved():
            saved_overrides[cast(int, t["id"])] = cast("str | None", t.get("model_override"))

    for cluster in result.clusters[:30]:
        entities = ", ".join(e[0] for e in cluster.top_entities[:3])
        row_data = [
            str(cluster.cluster_id),
            cluster.label[:50],
            str(len(cluster.doc_ids)),
            f"{cluster.coherence_score:.3f}",
            entities[:60],
        ]
        if verbose:
            override = saved_overrides.get(cluster.cluster_id)
            row_data.append(override or "[dim]-[/dim]")
        table.add_row(*row_data)

    console.print(table)

    if save:
        count = save_topics(result)
        console.print(f"\n[green]Saved {count} topics to database[/green]")
    else:
        console.print("\n[dim]Use --save to persist topics to the database[/dim]")


@wiki_app.command(name="status")
def wiki_status() -> None:
    """Show wiki generation status and statistics.

    Examples:
        emdx maintain wiki status
    """
    from ..services.wiki_clustering_service import get_topics
    from ..services.wiki_entity_service import get_entity_index_stats
    from ..services.wiki_synthesis_service import get_wiki_status

    status = get_wiki_status()
    topics = get_topics()
    entity_stats = get_entity_index_stats()

    console.print(
        Panel(
            f"[bold]Wiki Status[/bold]\n\n"
            f"Topics:         {status['total_topics']}\n"
            f"Articles:       {status['total_articles']} "
            f"({status['fresh_articles']} fresh, {status['stale_articles']} stale)\n"
            f"Entity pages:   {entity_stats.tier_a_count} full + "
            f"{entity_stats.tier_b_count} stubs + "
            f"{entity_stats.tier_c_count} index\n"
            f"Total cost:     ${status['total_cost_usd']:.4f}\n"
            f"Input tokens:   {status['total_input_tokens']:,}\n"
            f"Output tokens:  {status['total_output_tokens']:,}",
            title="Auto-Wiki",
        )
    )

    if topics:
        from rich.table import Table

        # Check if any topic has a model override
        has_overrides = any(t.get("model_override") for t in topics[:20])

        table = Table(title="Topics (by size)", box=box.SIMPLE)
        table.add_column("ID", style="dim", width=4)
        table.add_column("Label", style="cyan")
        table.add_column("Docs", justify="right")
        table.add_column("Status")
        if has_overrides:
            table.add_column("Model", style="yellow")

        for t in topics[:20]:
            status_str = str(t["status"])
            status_styled = {
                "active": "[green]active[/green]",
                "skipped": "[red]skipped[/red]",
                "pinned": "[yellow]pinned[/yellow]",
            }.get(status_str, status_str)
            row_data = [
                str(t["id"]),
                str(t["label"])[:50],
                str(t["member_count"]),
                status_styled,
            ]
            if has_overrides:
                override = t.get("model_override")
                row_data.append(str(override) if override else "")
            table.add_row(*row_data)
        console.print(table)


@wiki_app.command(name="generate")
def wiki_generate(
    topic_id: int | None = typer.Argument(None, help="Specific topic ID to generate"),
    audience: str = typer.Option("team", "--audience", "-a", help="Privacy mode: me, team, public"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max articles to generate"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Estimate costs without calling LLM"),
    all_topics: bool = typer.Option(False, "--all", help="Generate for all topics"),
    concurrency: int = typer.Option(
        1, "--concurrency", "-c", help="Max concurrent generations (default: 1 = sequential)"
    ),
) -> None:
    """Generate wiki articles from topic clusters.

    By default processes topics sequentially (--concurrency 1) for
    memory-efficient streaming.  Use -c N to allow N concurrent
    generations.

    Examples:
        emdx maintain wiki generate --dry-run        # Estimate costs
        emdx maintain wiki generate 5                # Generate for topic 5
        emdx maintain wiki generate --all -l 50      # Generate up to 50
        emdx maintain wiki generate --all -c 3       # 3 concurrent
        emdx maintain wiki generate --audience me    # Personal wiki mode
    """
    import time as _time

    from ..services.wiki_clustering_service import get_topics as _get_topics
    from ..services.wiki_synthesis_service import (
        complete_wiki_run,
        create_wiki_run,
        generate_article,
    )

    if not all_topics and topic_id is None:
        console.print("[red]Provide a topic ID or use --all[/red]")
        raise typer.Exit(1)

    if concurrency < 1:
        console.print("[red]--concurrency must be >= 1[/red]")
        raise typer.Exit(1)

    # Build topic list
    topic_list: list[int]
    if topic_id is not None:
        topic_list = [topic_id]
    else:
        topics_data = _get_topics()
        topic_list = [cast(int, t["id"]) for t in topics_data]

    # Apply limit to topic list upfront to avoid over-fetching
    effective_topics = topic_list[:limit]

    # Create a run record
    run_model = model or "claude-sonnet-4-5-20250929"
    run_id = create_wiki_run(model=run_model, dry_run=dry_run)

    generated = 0
    skipped = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0
    topics_attempted = 0
    total_count = len(effective_topics)
    batch_start = _time.time()

    if concurrency == 1:
        # Sequential processing — memory-efficient, streaming progress
        for i, tid in enumerate(effective_topics):
            topics_attempted += 1
            start = _time.time()

            result = generate_article(
                topic_id=tid,
                audience=audience,
                model=model,
                dry_run=dry_run,
            )
            elapsed = _time.time() - start

            label = f"[{i + 1}/{total_count}]"
            if result.skipped and result.skip_reason != "dry run":
                skipped += 1
                console.print(
                    f"  {label} [dim]Skipped: {result.topic_label or f'topic {tid}'}"
                    f" — {result.skip_reason} ({elapsed:.1f}s)[/dim]"
                )
            else:
                generated += 1
                if dry_run:
                    console.print(
                        f"  {label} [cyan]Would generate:[/cyan] "
                        f"{result.topic_label[:50]} "
                        f"(~${result.cost_usd:.2f})"
                    )
                else:
                    console.print(
                        f"  {label} [green]Generated:[/green] "
                        f"{result.topic_label[:50]} "
                        f"({elapsed:.0f}s, ${result.cost_usd:.2f})"
                    )
                if result.warnings:
                    for w in result.warnings:
                        console.print(f"         [yellow]⚠ {w}[/yellow]")

            total_input += result.input_tokens
            total_output += result.output_tokens
            total_cost += result.cost_usd
    else:
        # Concurrent processing with ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ..services.wiki_synthesis_service import WikiArticleResult

        # Track order of completion for progress labeling
        completed_count = 0

        def _gen_one(tid: int) -> tuple[int, WikiArticleResult, float]:
            t0 = _time.time()
            res = generate_article(
                topic_id=tid,
                audience=audience,
                model=model,
                dry_run=dry_run,
            )
            return tid, res, _time.time() - t0

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_gen_one, tid): tid for tid in effective_topics}
            topics_attempted = len(futures)

            for future in as_completed(futures):
                _tid, result, elapsed = future.result()
                completed_count += 1
                label = f"[{completed_count}/{total_count}]"

                if result.skipped and result.skip_reason != "dry run":
                    skipped += 1
                    console.print(
                        f"  {label} [dim]Skipped: "
                        f"{result.topic_label or f'topic {_tid}'}"
                        f" — {result.skip_reason} ({elapsed:.1f}s)[/dim]"
                    )
                else:
                    generated += 1
                    if dry_run:
                        console.print(
                            f"  {label} [cyan]Would generate:[/cyan] "
                            f"{result.topic_label[:50]} "
                            f"(~${result.cost_usd:.2f})"
                        )
                    else:
                        console.print(
                            f"  {label} [green]Generated:[/green] "
                            f"{result.topic_label[:50]} "
                            f"({elapsed:.0f}s, ${result.cost_usd:.2f})"
                        )
                    if result.warnings:
                        for w in result.warnings:
                            console.print(f"         [yellow]⚠ {w}[/yellow]")

                total_input += result.input_tokens
                total_output += result.output_tokens
                total_cost += result.cost_usd

    # Update run record with results
    complete_wiki_run(
        run_id,
        topics_attempted=topics_attempted,
        articles_generated=generated,
        articles_skipped=skipped,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_usd=total_cost,
    )

    total_elapsed = _time.time() - batch_start
    action = "Estimated" if dry_run else "Generated"
    mode = f" (concurrency={concurrency})" if concurrency > 1 else ""
    console.print(
        f"\n[bold]{action} {generated} article(s)[/bold] "
        f"(skipped {skipped}) in {total_elapsed:.1f}s{mode}\n"
        f"  Total tokens: {total_input:,} in / {total_output:,} out\n"
        f"  Total cost:   ${total_cost:.4f}\n"
        f"  Run ID:       {run_id}"
    )

    if dry_run:
        console.print("\n[dim]Remove --dry-run to actually generate articles[/dim]")


@wiki_app.command(name="entities")
def wiki_entities(
    entity: str | None = typer.Argument(None, help="Entity name to look up"),
    tier: str | None = typer.Option(None, "--tier", "-t", help="Filter by tier: A, B, C"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max entities to show"),
    stats: bool = typer.Option(False, "--stats", help="Show entity index statistics"),
) -> None:
    """Browse entity index pages.

    Examples:
        emdx maintain wiki entities                   # List top entities
        emdx maintain wiki entities "SQLite"           # Entity detail page
        emdx maintain wiki entities --tier A           # Full pages only
        emdx maintain wiki entities --stats            # Index statistics
    """
    from ..services.wiki_entity_service import (
        get_entity_detail,
        get_entity_index_stats,
        get_entity_pages,
        render_entity_page,
    )

    if stats:
        idx_stats = get_entity_index_stats()
        console.print(
            Panel(
                f"[bold]Entity Index[/bold]\n\n"
                f"Tier A (full):  {idx_stats.tier_a_count}\n"
                f"Tier B (stub):  {idx_stats.tier_b_count}\n"
                f"Tier C (index): {idx_stats.tier_c_count}\n"
                f"Total:          {idx_stats.total_entities}\n"
                f"Filtered:       {idx_stats.filtered_noise}",
                title="Entity Index Stats",
            )
        )
        return

    if entity:
        page = get_entity_detail(entity)
        if page:
            from rich.markdown import Markdown

            md = render_entity_page(page)
            console.print(Markdown(md))
        else:
            console.print(f"[yellow]Entity '{entity}' not found[/yellow]")
        return

    pages = get_entity_pages(tier=tier, limit=limit)

    from rich.table import Table

    table = Table(title="Entity Index", box=box.SIMPLE)
    table.add_column("Entity", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Docs", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Tier")

    for p in pages:
        tier_style = {"A": "green", "B": "yellow", "C": "dim"}.get(p.tier, "")
        table.add_row(
            p.entity[:40],
            p.entity_type,
            str(p.doc_frequency),
            f"{p.page_score:.1f}",
            f"[{tier_style}]{p.tier}[/{tier_style}]",
        )

    console.print(table)


@wiki_app.command(name="list")
def wiki_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max articles to show"),
    stale: bool = typer.Option(False, "--stale", help="Show only stale articles"),
    timing: bool = typer.Option(False, "--timing", "-T", help="Show step-level timing"),
) -> None:
    """List generated wiki articles.

    Examples:
        emdx maintain wiki list                # All articles
        emdx maintain wiki list --stale        # Stale articles only
        emdx maintain wiki list --timing       # Show step-level timing
    """
    from rich.table import Table

    from ..database import db

    with db.get_connection() as conn:
        query = (
            "SELECT wa.id, wa.topic_id, d.id as doc_id, d.title, "
            "wa.model, wa.input_tokens, wa.output_tokens, wa.cost_usd, "
            "wa.is_stale, wa.version, wa.generated_at, "
            "wa.prepare_ms, wa.route_ms, wa.outline_ms, "
            "wa.write_ms, wa.validate_ms, wa.save_ms, wa.rating "
            "FROM wiki_articles wa "
            "JOIN documents d ON wa.document_id = d.id "
        )
        if stale:
            query += "WHERE wa.is_stale = 1 "
        query += "ORDER BY wa.generated_at DESC LIMIT ?"

        rows = conn.execute(query, (limit,)).fetchall()

    if not rows:
        msg = "stale " if stale else ""
        console.print(f"[dim]No {msg}wiki articles found[/dim]")
        return

    table = Table(title="Wiki Articles", box=box.SIMPLE)
    table.add_column("Doc", style="cyan", width=6)
    table.add_column("Title")
    table.add_column("Rating", justify="center", width=7)
    table.add_column("Ver", justify="right", width=4)
    table.add_column("Model", style="dim")
    table.add_column("Cost", justify="right")
    table.add_column("Status")
    table.add_column("Generated", style="dim")
    if timing:
        table.add_column("Prepare", justify="right", style="dim")
        table.add_column("Route", justify="right", style="dim")
        table.add_column("Outline", justify="right", style="dim")
        table.add_column("Write", justify="right", style="dim")
        table.add_column("Validate", justify="right", style="dim")
        table.add_column("Save", justify="right", style="dim")

    for row in rows:
        status = "[red]stale[/red]" if row[8] else "[green]fresh[/green]"
        r = row[17]
        rating_str = "\u2605" * r + "\u2606" * (5 - r) if r else "[dim]-[/dim]"
        base_cols = [
            f"#{row[2]}",
            str(row[3])[:50],
            rating_str,
            f"v{row[9]}",
            str(row[4]).split("-")[1] if "-" in str(row[4]) else str(row[4]),
            f"${row[7]:.4f}",
            status,
            str(row[10])[:10] if row[10] else "",
        ]
        if timing:
            base_cols.extend(
                [
                    _format_ms(row[11] or 0),
                    _format_ms(row[12] or 0),
                    _format_ms(row[13] or 0),
                    _format_ms(row[14] or 0),
                    _format_ms(row[15] or 0),
                    _format_ms(row[16] or 0),
                ]
            )
        table.add_row(*base_cols)

    console.print(table)


@wiki_app.command(name="runs")
def wiki_runs_command(
    limit: int = typer.Option(10, "--limit", "-l", help="Max runs to show"),
) -> None:
    """List recent wiki generation runs.

    Examples:
        emdx maintain wiki runs              # Recent runs
        emdx maintain wiki runs -l 20        # More history
    """
    from rich.table import Table

    from ..services.wiki_synthesis_service import list_wiki_runs

    runs = list_wiki_runs(limit=limit)

    if not runs:
        console.print("[dim]No wiki generation runs found[/dim]")
        return

    table = Table(title="Wiki Generation Runs", box=box.SIMPLE)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Date", style="cyan")
    table.add_column("Articles", justify="right")
    table.add_column("Skipped", justify="right", style="dim")
    table.add_column("Tokens (in/out)", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Model", style="dim")
    table.add_column("Type")

    for run in runs:
        started = str(run["started_at"])[:16] if run["started_at"] else ""
        run_type = "[yellow]dry-run[/yellow]" if run["dry_run"] else "[green]live[/green]"
        model_short = str(run["model"])
        if "-" in model_short:
            parts = model_short.split("-")
            model_short = "-".join(parts[1:3]) if len(parts) > 2 else parts[-1]
        tokens = f"{run['total_input_tokens']:,}/{run['total_output_tokens']:,}"
        table.add_row(
            str(run["id"]),
            started,
            str(run["articles_generated"]),
            str(run["articles_skipped"]),
            tokens,
            f"${run['total_cost_usd']:.4f}",
            model_short[:20],
            run_type,
        )

    console.print(table)


@wiki_app.command(name="coverage")
def wiki_coverage(
    limit: int = typer.Option(0, "--limit", "-l", help="Max uncovered docs to show (0=all)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show which documents are NOT covered by any wiki topic cluster.

    Cross-references all non-deleted user docs (doc_type='user') against
    the wiki_topic_members table and reports uncovered documents.

    Examples:
        emdx maintain wiki coverage              # Full coverage report
        emdx maintain wiki coverage --limit 10   # Show first 10 uncovered
        emdx maintain wiki coverage --json       # Machine-readable output
    """
    import json

    from ..database import db

    with db.get_connection() as conn:
        # Total non-deleted user docs
        total_row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE is_deleted = 0 AND doc_type = 'user'"
        ).fetchone()
        total_docs = total_row[0] if total_row else 0

        # Covered docs (in at least one topic)
        covered_row = conn.execute(
            "SELECT COUNT(DISTINCT m.document_id) "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE d.is_deleted = 0 AND d.doc_type = 'user'"
        ).fetchone()
        covered_docs = covered_row[0] if covered_row else 0

        uncovered_count = total_docs - covered_docs

        # Fetch uncovered documents
        query = (
            "SELECT d.id, d.title, d.created_at "
            "FROM documents d "
            "WHERE d.is_deleted = 0 AND d.doc_type = 'user' "
            "AND d.id NOT IN ("
            "  SELECT DISTINCT document_id FROM wiki_topic_members"
            ") "
            "ORDER BY d.id"
        )
        if limit > 0:
            query += f" LIMIT {limit}"

        uncovered_rows = conn.execute(query).fetchall()

    if json_output:
        data = {
            "total_docs": total_docs,
            "covered_docs": covered_docs,
            "uncovered_docs": uncovered_count,
            "coverage_percent": round(
                (covered_docs / total_docs * 100) if total_docs > 0 else 0, 1
            ),
            "uncovered": [
                {"id": row[0], "title": row[1], "created_at": row[2]} for row in uncovered_rows
            ],
        }
        print(json.dumps(data, indent=2, default=str))
        return

    # Rich output
    coverage_pct = (covered_docs / total_docs * 100) if total_docs > 0 else 0
    pct_color = "green" if coverage_pct >= 80 else "yellow" if coverage_pct >= 50 else "red"

    console.print(
        f"\n[bold]Wiki Topic Coverage[/bold]\n\n"
        f"  Total user docs:  {total_docs}\n"
        f"  Covered by topic: {covered_docs}\n"
        f"  Uncovered:        {uncovered_count}\n"
        f"  Coverage:         [{pct_color}]{coverage_pct:.1f}%[/{pct_color}]"
    )

    if uncovered_rows:
        from rich.table import Table

        table = Table(title="Uncovered Documents", box=box.SIMPLE)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title")
        table.add_column("Created", style="dim")

        for row in uncovered_rows:
            created = str(row[2])[:10] if row[2] else ""
            table.add_row(f"#{row[0]}", str(row[1])[:60], created)

        console.print()
        console.print(table)

        if limit > 0 and uncovered_count > limit:
            remaining = uncovered_count - limit
            console.print(f"\n[dim]...and {remaining} more. Use --limit 0 to see all.[/dim]")
    else:
        console.print("\n[green]All user documents are covered by wiki topics![/green]")


@wiki_app.command(name="progress")
def wiki_progress(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show wiki generation progress: topics generated vs pending.

    Displays total topics, how many have generated articles, how many are
    pending or skipped, total cost so far, and estimated remaining cost
    based on the average cost per article.

    Examples:
        emdx maintain wiki progress              # Rich progress report
        emdx maintain wiki progress --json       # Machine-readable output
    """
    from ..database import db
    from ..utils.output import print_json

    with db.get_connection() as conn:
        # Total topics by status
        total_row = conn.execute("SELECT COUNT(*) FROM wiki_topics").fetchone()
        total_topics = total_row[0] if total_row else 0

        skipped_row = conn.execute(
            "SELECT COUNT(*) FROM wiki_topics WHERE status = 'skipped'"
        ).fetchone()
        skipped = skipped_row[0] if skipped_row else 0

        # Topics that have a generated article (joined via wiki_articles)
        generated_row = conn.execute(
            "SELECT COUNT(DISTINCT a.topic_id) FROM wiki_articles a "
            "JOIN wiki_topics t ON a.topic_id = t.id"
        ).fetchone()
        generated = generated_row[0] if generated_row else 0

        # Pending = total - generated - skipped
        pending = total_topics - generated - skipped

        # Cost info from wiki_articles
        cost_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), "
            "COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0) "
            "FROM wiki_articles"
        ).fetchone()
        total_cost = cost_row[0] if cost_row else 0.0
        total_input_tokens = cost_row[1] if cost_row else 0
        total_output_tokens = cost_row[2] if cost_row else 0

        # Average cost per article for estimation
        avg_cost = total_cost / generated if generated > 0 else 0.0
        est_remaining = avg_cost * pending

    pct = (generated / total_topics * 100) if total_topics > 0 else 0.0

    if json_output:
        data = {
            "total_topics": total_topics,
            "generated": generated,
            "pending": pending,
            "skipped": skipped,
            "percent_complete": round(pct, 1),
            "cost_usd": round(total_cost, 4),
            "avg_cost_per_article": round(avg_cost, 4),
            "est_remaining_cost_usd": round(est_remaining, 2),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
        }
        print_json(data)
        return

    # Rich output
    pct_color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"

    # Build progress bar (30 chars wide)
    bar_width = 30
    filled = int(bar_width * pct / 100) if total_topics > 0 else 0
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

    summary = f"Topics: {generated}/{total_topics} generated ({pending} pending, {skipped} skipped)"

    cost_line = f"Cost so far: ${total_cost:.2f}"
    if generated > 0 and pending > 0:
        cost_line += f"  Est. remaining: ${est_remaining:.2f}"

    tokens_line = f"Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out"

    console.print(
        f"\n[bold]Wiki Generation Progress[/bold]\n\n"
        f"  {summary}\n"
        f"  [{pct_color}]{bar}[/{pct_color}]"
        f" [{pct_color}]{pct:.1f}%[/{pct_color}]\n\n"
        f"  {cost_line}\n"
        f"  {tokens_line}"
    )

    if generated > 0:
        console.print(f"  Avg cost/article: ${avg_cost:.4f}")

    console.print()


@wiki_app.command(name="diff")
def wiki_diff_command(
    topic_id: int = typer.Argument(..., help="Topic ID to show diff for"),
) -> None:
    """Show unified diff between previous and current article content.

    When wiki generate regenerates an existing article, the previous
    content is stashed. This command shows what changed.

    Examples:
        emdx maintain wiki diff 5              # Diff for topic 5
    """
    from ..services.wiki_synthesis_service import get_article_diff

    diff = get_article_diff(topic_id)

    if diff is None:
        console.print(
            f"[dim]No previous content for topic {topic_id} "
            f"(article not found or never regenerated)[/dim]"
        )
        raise typer.Exit(1)

    if not diff:
        console.print("[green]No changes — previous and current content are identical[/green]")
        return

    from rich.syntax import Syntax

    syntax = Syntax(diff, "diff", theme="monokai")
    console.print(syntax)


@wiki_app.command(name="rate")
def wiki_rate(
    topic_id: int = typer.Argument(..., help="Topic ID to rate"),
    rating: int | None = typer.Argument(None, help="Rating value (1-5)"),
    up: bool = typer.Option(False, "--up", help="Quick thumbs up (maps to 4)"),
    down: bool = typer.Option(False, "--down", help="Quick thumbs down (maps to 2)"),
) -> None:
    """Rate a wiki article's quality (1-5 scale).

    Examples:
        emdx maintain wiki rate 5 4            # Rate topic 5 as 4/5
        emdx maintain wiki rate 5 --up         # Quick thumbs up (4)
        emdx maintain wiki rate 5 --down       # Quick thumbs down (2)
    """
    from ..database import db

    if up and down:
        print("Error: Cannot use both --up and --down")
        raise typer.Exit(1)

    if up:
        resolved_rating = 4
    elif down:
        resolved_rating = 2
    elif rating is not None:
        resolved_rating = rating
    else:
        print("Error: Provide a rating (1-5) or use --up/--down")
        raise typer.Exit(1)

    if resolved_rating < 1 or resolved_rating > 5:
        print("Error: Rating must be between 1 and 5")
        raise typer.Exit(1)

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT wa.id, d.title FROM wiki_articles wa "
            "JOIN documents d ON wa.document_id = d.id "
            "WHERE wa.topic_id = ?",
            (topic_id,),
        ).fetchone()

        if not row:
            print(f"No wiki article found for topic {topic_id}")
            raise typer.Exit(1)

        conn.execute(
            "UPDATE wiki_articles SET rating = ?, rated_at = CURRENT_TIMESTAMP WHERE topic_id = ?",
            (resolved_rating, topic_id),
        )
        conn.commit()

    stars = "\u2605" * resolved_rating + "\u2606" * (5 - resolved_rating)
    print(f"Rated {row[1]} {stars} ({resolved_rating}/5)")


@wiki_app.command(name="rename")
def wiki_rename(
    topic_id: int = typer.Argument(..., help="Topic ID to rename"),
    new_label: str = typer.Argument(..., help="New topic label"),
) -> None:
    """Rename a wiki topic (label, slug, and associated document title).

    The slug is auto-generated from the new label (lowercase, hyphens).

    Examples:
        emdx maintain wiki rename 5 "Database Architecture"
        emdx maintain wiki rename 12 "Auth / OAuth / JWT"
    """
    from ..database import db

    new_slug = slugify_label(new_label)

    with db.get_connection() as conn:
        # Look up current topic
        topic_row = conn.execute(
            "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()

        if not topic_row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)

        old_label = topic_row[0]
        old_slug = topic_row[1]

        # Check slug uniqueness
        conflict = conn.execute(
            "SELECT id FROM wiki_topics WHERE topic_slug = ? AND id != ?",
            (new_slug, topic_id),
        ).fetchone()

        if conflict:
            print(f"Error: slug '{new_slug}' already in use by topic {conflict[0]}")
            raise typer.Exit(1)

        # Update topic
        conn.execute(
            "UPDATE wiki_topics SET topic_label = ?, topic_slug = ? WHERE id = ?",
            (new_label, new_slug, topic_id),
        )

        # Update associated wiki document title if article exists
        article_row = conn.execute(
            "SELECT document_id FROM wiki_articles WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()

        if article_row:
            doc_id = article_row[0]
            conn.execute(
                "UPDATE documents SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_label, doc_id),
            )

        conn.commit()

    print(f"Renamed topic {topic_id}:")
    print(f"  Label: {old_label} -> {new_label}")
    print(f"  Slug:  {old_slug} -> {new_slug}")
    if article_row:
        print(f"  Document #{doc_id} title updated")


@wiki_app.command(name="retitle")
def wiki_retitle(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without updating"),
) -> None:
    """Batch-update topic labels from article H1 headings.

    Scans all active topics that have a generated article, extracts the
    H1 heading from each article, and updates the topic label and slug
    if the H1 differs from the current label.

    Examples:
        emdx maintain wiki retitle --dry-run   # Preview changes
        emdx maintain wiki retitle             # Apply changes
    """
    from ..database import db

    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT t.id, t.topic_label, t.topic_slug, d.content, wa.document_id "
            "FROM wiki_topics t "
            "JOIN wiki_articles wa ON t.id = wa.topic_id "
            "JOIN documents d ON wa.document_id = d.id "
            "WHERE t.status != 'skipped' AND d.is_deleted = 0"
        ).fetchall()

    if not rows:
        print("No topics with articles found")
        return

    retitled = 0
    skipped = 0
    for row in rows:
        topic_id, old_label, old_slug, content, doc_id = row
        # Extract H1 heading
        match = re.search(r"^#\s+(.+)$", content or "", re.MULTILINE)
        if not match:
            continue
        h1 = match.group(1).strip()
        if h1 == old_label:
            skipped += 1
            continue

        new_slug = slugify_label(h1)

        if dry_run:
            print(f"  Topic {topic_id}: '{old_label}' -> '{h1}'")
            retitled += 1
            continue

        with db.get_connection() as conn:
            # Check slug uniqueness
            conflict = conn.execute(
                "SELECT id FROM wiki_topics WHERE topic_slug = ? AND id != ?",
                (new_slug, topic_id),
            ).fetchone()
            if conflict:
                print(
                    f"  Topic {topic_id}: skipped — slug '{new_slug}' "
                    f"conflicts with topic {conflict[0]}"
                )
                continue

            conn.execute(
                "UPDATE wiki_topics SET topic_label = ?, topic_slug = ? WHERE id = ?",
                (h1, new_slug, topic_id),
            )
            conn.execute(
                "UPDATE documents SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (h1, doc_id),
            )
            conn.commit()
            print(f"  Topic {topic_id}: '{old_label}' -> '{h1}'")
            retitled += 1

    action = "Would retitle" if dry_run else "Retitled"
    print(f"{action} {retitled}/{len(rows)} topics ({skipped} already matching)")


@wiki_app.command(name="skip")
def wiki_skip(
    topic_id: int = typer.Argument(..., help="Topic ID to skip"),
) -> None:
    """Skip a topic during wiki generation.

    Sets the topic status to 'skipped' so it is excluded from
    future wiki generate runs.

    Examples:
        emdx maintain wiki skip 5
    """
    label, old_status = _set_topic_status(topic_id, "skipped")
    print(f"Skipped topic {topic_id} ({label}) [was: {old_status}]")


@wiki_app.command(name="unskip")
def wiki_unskip(
    topic_id: int = typer.Argument(..., help="Topic ID to unskip"),
) -> None:
    """Reset a skipped topic back to active.

    Examples:
        emdx maintain wiki unskip 5
    """
    label, old_status = _set_topic_status(topic_id, "active")
    print(f"Unskipped topic {topic_id} ({label}) [was: {old_status}]")


@wiki_app.command(name="pin")
def wiki_pin(
    topic_id: int = typer.Argument(..., help="Topic ID to pin"),
) -> None:
    """Pin a topic so it always regenerates during wiki generation.

    Pinned topics bypass the staleness check and are always
    regenerated, even if their source hash is unchanged.

    Examples:
        emdx maintain wiki pin 5
    """
    label, old_status = _set_topic_status(topic_id, "pinned")
    print(f"Pinned topic {topic_id} ({label}) [was: {old_status}]")


@wiki_app.command(name="unpin")
def wiki_unpin(
    topic_id: int = typer.Argument(..., help="Topic ID to unpin"),
) -> None:
    """Reset a pinned topic back to active.

    Examples:
        emdx maintain wiki unpin 5
    """
    label, old_status = _set_topic_status(topic_id, "active")
    print(f"Unpinned topic {topic_id} ({label}) [was: {old_status}]")


@wiki_app.command(name="model")
def wiki_model(
    topic_id: int = typer.Argument(..., help="Topic ID to set model for"),
    model_name: str | None = typer.Argument(None, help="Model name to use for this topic"),
    clear: bool = typer.Option(False, "--clear", help="Remove model override"),
) -> None:
    """Set or clear a per-topic model override for wiki generation.

    Examples:
        emdx maintain wiki model 5 claude-opus-4-5-20250514     # Set override
        emdx maintain wiki model 5 --clear                       # Remove override
    """
    from ..database import db

    if clear and model_name is not None:
        print("Error: Cannot use both a model name and --clear")
        raise typer.Exit(1)

    if not clear and model_name is None:
        print("Error: Provide a model name or use --clear")
        raise typer.Exit(1)

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id, topic_label, model_override FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()

        if not row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)

        topic_label = row[1]

        if clear:
            conn.execute(
                "UPDATE wiki_topics SET model_override = NULL WHERE id = ?",
                (topic_id,),
            )
            conn.commit()
            print(f"Cleared model override for topic {topic_id} ({topic_label})")
        else:
            conn.execute(
                "UPDATE wiki_topics SET model_override = ? WHERE id = ?",
                (model_name, topic_id),
            )
            conn.commit()
            print(f"Set model override for topic {topic_id} ({topic_label}): {model_name}")


@wiki_app.command(name="prompt")
def wiki_prompt(
    topic_id: int = typer.Argument(..., help="Topic ID to set prompt for"),
    prompt_text: str | None = typer.Argument(None, help="Editorial prompt text"),
    clear: bool = typer.Option(False, "--clear", help="Remove the editorial prompt"),
) -> None:
    """Set or clear an editorial prompt for a wiki topic.

    The editorial prompt is appended to the LLM system prompt when
    generating or regenerating the article for this topic.

    Examples:
        emdx maintain wiki prompt 5 "Focus on security implications"
        emdx maintain wiki prompt 5 --clear
    """
    from ..database import db

    if clear and prompt_text is not None:
        print("Error: Cannot use --clear with a prompt text")
        raise typer.Exit(1)

    if not clear and prompt_text is None:
        # Show current prompt
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT topic_label, editorial_prompt FROM wiki_topics WHERE id = ?",
                (topic_id,),
            ).fetchone()
        if not row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)
        label = row[0]
        current = row[1]
        if current:
            print(f"Topic {topic_id} ({label}):\n{current}")
        else:
            print(f"Topic {topic_id} ({label}): no editorial prompt set")
        return

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT topic_label FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
        if not row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)
        label = row[0]

        new_value = None if clear else prompt_text
        conn.execute(
            "UPDATE wiki_topics SET editorial_prompt = ? WHERE id = ?",
            (new_value, topic_id),
        )
        conn.commit()

    if clear:
        print(f"Cleared editorial prompt for topic {topic_id} ({label})")
    else:
        print(f"Set editorial prompt for topic {topic_id} ({label})")


@wiki_app.command(name="merge")
def wiki_merge(
    topic_id_1: int = typer.Argument(..., help="Target topic ID (will be kept)"),
    topic_id_2: int = typer.Argument(..., help="Source topic ID (will be deleted)"),
) -> None:
    """Merge two wiki topics into one.

    Combines the members of both topics under the first topic's ID.
    The merged label is "Label A & Label B". The second topic and its
    wiki article (if any) are deleted.

    Examples:
        emdx maintain wiki merge 5 12        # Merge topic 12 into topic 5
    """
    from ..database import db

    if topic_id_1 == topic_id_2:
        print("Error: cannot merge a topic with itself")
        raise typer.Exit(1)

    with db.get_connection() as conn:
        # Look up both topics
        row1 = conn.execute(
            "SELECT topic_label FROM wiki_topics WHERE id = ?",
            (topic_id_1,),
        ).fetchone()
        if not row1:
            print(f"Topic {topic_id_1} not found")
            raise typer.Exit(1)

        row2 = conn.execute(
            "SELECT topic_label FROM wiki_topics WHERE id = ?",
            (topic_id_2,),
        ).fetchone()
        if not row2:
            print(f"Topic {topic_id_2} not found")
            raise typer.Exit(1)

        label1 = row1[0]
        label2 = row2[0]
        merged_label = f"{label1} & {label2}"
        merged_slug = slugify_label(merged_label)

        # Check slug uniqueness (excluding both topics being merged)
        conflict = conn.execute(
            "SELECT id FROM wiki_topics WHERE topic_slug = ? AND id NOT IN (?, ?)",
            (merged_slug, topic_id_1, topic_id_2),
        ).fetchone()
        if conflict:
            print(f"Error: slug '{merged_slug}' already in use by topic {conflict[0]}")
            raise typer.Exit(1)

        # Move members from topic 2 to topic 1 (skip duplicates)
        members_2 = conn.execute(
            "SELECT document_id, relevance_score, is_primary "
            "FROM wiki_topic_members WHERE topic_id = ?",
            (topic_id_2,),
        ).fetchall()

        moved = 0
        for doc_id, relevance, is_primary in members_2:
            existing = conn.execute(
                "SELECT 1 FROM wiki_topic_members WHERE topic_id = ? AND document_id = ?",
                (topic_id_1, doc_id),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO wiki_topic_members "
                    "(topic_id, document_id, relevance_score, is_primary) "
                    "VALUES (?, ?, ?, ?)",
                    (topic_id_1, doc_id, relevance, is_primary),
                )
                moved += 1

        # Delete wiki article for topic 2 if it exists
        article_row = conn.execute(
            "SELECT document_id FROM wiki_articles WHERE topic_id = ?",
            (topic_id_2,),
        ).fetchone()
        article_deleted = False
        if article_row:
            article_doc_id = article_row[0]
            conn.execute(
                "DELETE FROM wiki_article_sources WHERE article_id IN "
                "(SELECT id FROM wiki_articles WHERE topic_id = ?)",
                (topic_id_2,),
            )
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = ?", (topic_id_2,))
            conn.execute(
                "UPDATE documents SET is_deleted = 1 WHERE id = ?",
                (article_doc_id,),
            )
            article_deleted = True

        # Delete topic 2 members and topic row
        conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = ?", (topic_id_2,))
        conn.execute("DELETE FROM wiki_topics WHERE id = ?", (topic_id_2,))

        # Update topic 1 label and slug
        conn.execute(
            "UPDATE wiki_topics SET topic_label = ?, topic_slug = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (merged_label, merged_slug, topic_id_1),
        )

        # Mark topic 1's article as stale if it exists
        conn.execute(
            "UPDATE wiki_articles SET is_stale = 1, stale_reason = 'topic merged' "
            "WHERE topic_id = ?",
            (topic_id_1,),
        )

        conn.commit()

    # Count total members after merge
    with db.get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM wiki_topic_members WHERE topic_id = ?",
            (topic_id_1,),
        ).fetchone()[0]

    print(f"Merged topic {topic_id_2} ({label2}) into topic {topic_id_1} ({label1})")
    print(f"  New label: {merged_label}")
    print(f"  New slug:  {merged_slug}")
    print(f"  Members moved: {moved}")
    print(f"  Total members: {total}")
    if article_deleted:
        print(f"  Deleted wiki article for topic {topic_id_2}")


@wiki_app.command(name="split")
def wiki_split(
    topic_id: int = typer.Argument(..., help="Topic ID to split"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name to split by"),
) -> None:
    """Split a wiki topic by extracting docs that mention an entity.

    Finds documents in the topic whose title or content mentions the
    entity name, moves them to a new topic with a label derived from
    the entity, and keeps remaining docs in the original topic.

    Examples:
        emdx maintain wiki split 5 --entity "OAuth"
        emdx maintain wiki split 12 -e "SQLite"
    """
    from ..database import db

    with db.get_connection() as conn:
        # Verify topic exists
        topic_row = conn.execute(
            "SELECT topic_label FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
        if not topic_row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)

        original_label = topic_row[0]

        # Get all member docs with their titles and content
        members = conn.execute(
            "SELECT m.document_id, d.title, d.content "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE m.topic_id = ?",
            (topic_id,),
        ).fetchall()

        if not members:
            print(f"Topic {topic_id} has no members")
            raise typer.Exit(1)

        # Find docs mentioning the entity (case-insensitive)
        entity_lower = entity.lower()
        matching_doc_ids: list[int] = []
        remaining_doc_ids: list[int] = []

        for doc_id, title, content in members:
            text = f"{title or ''} {content or ''}".lower()
            if entity_lower in text:
                matching_doc_ids.append(doc_id)
            else:
                remaining_doc_ids.append(doc_id)

        if not matching_doc_ids:
            print(f"No documents in topic {topic_id} mention '{entity}'")
            raise typer.Exit(1)

        if not remaining_doc_ids:
            print(
                f"All documents in topic {topic_id} mention '{entity}' "
                "— nothing would remain. Use rename instead."
            )
            raise typer.Exit(1)

        # Create new topic for the split-off docs
        new_label = entity
        new_slug = slugify_label(new_label)

        # Ensure slug uniqueness by appending a suffix if needed
        base_slug = new_slug
        suffix = 0
        while True:
            conflict = conn.execute(
                "SELECT id FROM wiki_topics WHERE topic_slug = ?",
                (new_slug,),
            ).fetchone()
            if not conflict:
                break
            suffix += 1
            new_slug = f"{base_slug}-{suffix}"

        conn.execute(
            "INSERT INTO wiki_topics "
            "(topic_slug, topic_label, entity_fingerprint, status) "
            "VALUES (?, ?, '', 'active')",
            (new_slug, new_label),
        )
        new_topic_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Move matching docs to the new topic
        for doc_id in matching_doc_ids:
            conn.execute(
                "DELETE FROM wiki_topic_members WHERE topic_id = ? AND document_id = ?",
                (topic_id, doc_id),
            )
            conn.execute(
                "INSERT INTO wiki_topic_members "
                "(topic_id, document_id, relevance_score, is_primary) "
                "VALUES (?, ?, 1.0, 1)",
                (new_topic_id, doc_id),
            )

        # Mark original topic's article as stale if it exists
        conn.execute(
            "UPDATE wiki_articles SET is_stale = 1, stale_reason = 'topic split' "
            "WHERE topic_id = ?",
            (topic_id,),
        )

        conn.commit()

    print(f"Split topic {topic_id} ({original_label}) by entity '{entity}'")
    print(f"  New topic: {new_topic_id} ({new_label})")
    print(f"  New slug:  {new_slug}")
    print(f"  Moved {len(matching_doc_ids)} doc(s): {matching_doc_ids}")
    print(f"  Remaining in original: {len(remaining_doc_ids)} doc(s)")


@wiki_app.command(name="sources")
def wiki_sources(
    topic_id: int = typer.Argument(..., help="Topic ID to list sources for"),
) -> None:
    """List source documents for a wiki topic with weights and status.

    Shows each source document's relevance_score and whether it is
    included (is_primary=1) or excluded (is_primary=0).

    Examples:
        emdx maintain wiki sources 5
    """
    from ..database import db as _db

    with _db.get_connection() as conn:
        topic_row = conn.execute(
            "SELECT topic_label FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
        if not topic_row:
            print(f"Topic {topic_id} not found")
            raise typer.Exit(1)

        rows = conn.execute(
            "SELECT m.document_id, d.title, m.relevance_score, m.is_primary "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE m.topic_id = ? "
            "ORDER BY m.relevance_score DESC, m.document_id",
            (topic_id,),
        ).fetchall()

    label = topic_row[0]
    print(f"Sources for topic {topic_id} ({label}):")
    print()
    if not rows:
        print("  No source documents")
        return

    for row in rows:
        doc_id, title, weight, is_primary = row[0], row[1], row[2], row[3]
        status = "included" if is_primary else "EXCLUDED"
        print(f"  #{doc_id:<6} w={weight:.2f}  [{status}]  {title}")


@wiki_app.command(name="weight")
def wiki_weight(
    topic_id: int = typer.Argument(..., help="Topic ID"),
    doc_id: int = typer.Argument(..., help="Document ID"),
    weight: float = typer.Argument(..., help="Relevance weight (0.0-1.0)"),
) -> None:
    """Set relevance weight for a source document within a topic.

    The weight (0.0-1.0) scales how much a source document contributes
    to the synthesized wiki article. Higher weight = more content included.

    Examples:
        emdx maintain wiki weight 5 42 0.5     # Half weight
        emdx maintain wiki weight 5 42 1.0     # Full weight (default)
    """
    from ..database import db as _db

    if not 0.0 <= weight <= 1.0:
        print("Weight must be between 0.0 and 1.0")
        raise typer.Exit(1)

    with _db.get_connection() as conn:
        row = conn.execute(
            "SELECT m.relevance_score, d.title "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE m.topic_id = ? AND m.document_id = ?",
            (topic_id, doc_id),
        ).fetchone()

        if not row:
            print(f"Document #{doc_id} is not a member of topic {topic_id}")
            raise typer.Exit(1)

        old_weight = row[0]
        title = row[1]
        conn.execute(
            "UPDATE wiki_topic_members SET relevance_score = ? "
            "WHERE topic_id = ? AND document_id = ?",
            (weight, topic_id, doc_id),
        )
        conn.commit()

    print(f"Updated weight for #{doc_id} ({title}) in topic {topic_id}:")
    print(f"  {old_weight:.2f} -> {weight:.2f}")


@wiki_app.command(name="exclude")
def wiki_exclude(
    topic_id: int = typer.Argument(..., help="Topic ID"),
    doc_id: int = typer.Argument(..., help="Document ID to exclude"),
) -> None:
    """Exclude a source document from a wiki topic's synthesis.

    Sets is_primary=0 so the document is skipped during article generation.
    The membership record is preserved so it can be re-included later.

    Examples:
        emdx maintain wiki exclude 5 42
    """
    from ..database import db as _db

    with _db.get_connection() as conn:
        row = conn.execute(
            "SELECT m.is_primary, d.title "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE m.topic_id = ? AND m.document_id = ?",
            (topic_id, doc_id),
        ).fetchone()

        if not row:
            print(f"Document #{doc_id} is not a member of topic {topic_id}")
            raise typer.Exit(1)

        title = row[1]
        conn.execute(
            "UPDATE wiki_topic_members SET is_primary = 0 WHERE topic_id = ? AND document_id = ?",
            (topic_id, doc_id),
        )
        conn.commit()

    print(f"Excluded #{doc_id} ({title}) from topic {topic_id}")


@wiki_app.command(name="include")
def wiki_include(
    topic_id: int = typer.Argument(..., help="Topic ID"),
    doc_id: int = typer.Argument(..., help="Document ID to include"),
) -> None:
    """Re-include a previously excluded source document in a topic.

    Sets is_primary=1 so the document is used during article generation.

    Examples:
        emdx maintain wiki include 5 42
    """
    from ..database import db as _db

    with _db.get_connection() as conn:
        row = conn.execute(
            "SELECT m.is_primary, d.title "
            "FROM wiki_topic_members m "
            "JOIN documents d ON m.document_id = d.id "
            "WHERE m.topic_id = ? AND m.document_id = ?",
            (topic_id, doc_id),
        ).fetchone()

        if not row:
            print(f"Document #{doc_id} is not a member of topic {topic_id}")
            raise typer.Exit(1)

        title = row[1]
        conn.execute(
            "UPDATE wiki_topic_members SET is_primary = 1 WHERE topic_id = ? AND document_id = ?",
            (topic_id, doc_id),
        )
        conn.commit()

    print(f"Included #{doc_id} ({title}) in topic {topic_id}")


@wiki_app.command(name="export")
def wiki_export(
    output_dir: Path = typer.Argument(..., help="Directory to write MkDocs site to"),
    site_name: str = typer.Option(
        "Knowledge Base Wiki", "--site-name", "-n", help="Site name for mkdocs.yml"
    ),
    build: bool = typer.Option(False, "--build", help="Run mkdocs build after export"),
    deploy: bool = typer.Option(False, "--deploy", help="Run mkdocs gh-deploy after export"),
    remote: str = typer.Option(
        "",
        "--remote",
        "-r",
        help="Git remote name for gh-deploy (deploy to a different repo)",
    ),
    init_repo: bool = typer.Option(
        False,
        "--init-repo",
        help="Initialize output dir as a git repo with optional GitHub remote",
    ),
    github_repo: str = typer.Option(
        "",
        "--github-repo",
        help="GitHub repo to create/use with --init-repo (e.g. user/private-wiki)",
    ),
    private: bool = typer.Option(
        True,
        "--private/--public",
        help="Make the GitHub repo private (default: private)",
    ),
    site_url: str = typer.Option(
        "",
        "--site-url",
        help="Base URL for the published site (e.g. https://you.github.io/wiki/)",
    ),
    repo_url: str = typer.Option(
        "",
        "--repo-url",
        help="Repository URL for 'edit this page' links in the wiki",
    ),
    topic: int | None = typer.Option(
        None,
        "--topic",
        "-t",
        help="Export only the article for this topic ID",
    ),
) -> None:
    """Export wiki articles as a MkDocs site.

    Dumps all wiki articles and entity glossary pages as markdown files,
    generates mkdocs.yml with Material theme, and optionally builds or
    deploys to GitHub Pages.

    Use --topic <id> to export a single topic's article, leaving existing
    files untouched. Entity pages, index, and mkdocs.yml are not regenerated.

    Use --init-repo to bootstrap a separate git repo for your wiki, and
    --remote to deploy to it. This keeps your wiki output separate from
    your source KB repo.

    Examples:
        emdx maintain wiki export ./wiki-site
        emdx maintain wiki export ./wiki-site --topic 42
        emdx maintain wiki export ./wiki-site --build
        emdx maintain wiki export ./wiki-site --deploy
        emdx maintain wiki export ./wiki-site --deploy --remote wiki
        emdx maintain wiki export ./wiki-site -n "My Wiki"

        # Bootstrap a private wiki repo and deploy in one shot:
        emdx maintain wiki export ./wiki-site --init-repo \\
            --github-repo myuser/work-wiki --deploy
    """
    from ..services.wiki_export_service import export_mkdocs

    # --init-repo: bootstrap the output dir as a git repo
    if init_repo:
        _init_wiki_repo(output_dir, github_repo=github_repo, private=private)

    result = export_mkdocs(
        output_dir, site_name=site_name, site_url=site_url, repo_url=repo_url, topic_id=topic
    )

    print(f"Exported to {result.output_dir}/")
    print(f"  Articles:     {result.articles_exported}")
    print(f"  Entity pages: {result.entity_pages_exported}")
    print(f"  mkdocs.yml:   {'yes' if result.mkdocs_yml_generated else 'no'}")

    if result.errors:
        print(f"  Errors:       {len(result.errors)}")
        for err in result.errors:
            print(f"    - {err}")

    if not build and not deploy:
        print(f"\nTo preview: cd {output_dir} && mkdocs serve")
        print(f"To build:   cd {output_dir} && mkdocs build")
        deploy_hint = f"cd {output_dir} && mkdocs gh-deploy"
        if remote:
            deploy_hint += f" --remote-name {remote}"
        print(f"To deploy:  {deploy_hint}")
        return

    # Check mkdocs is installed
    import shutil

    mkdocs_bin = shutil.which("mkdocs")
    if not mkdocs_bin:
        print("\nError: mkdocs not found. Install with: pip install mkdocs mkdocs-material")
        raise typer.Exit(1)

    if deploy:
        cmd = ["mkdocs", "gh-deploy", "--force"]
        if remote:
            cmd.extend(["--remote-name", remote])
        remote_label = f" to remote '{remote}'" if remote else ""
        print(f"\nRunning mkdocs gh-deploy{remote_label}...")
        proc = subprocess.run(
            cmd,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"Error: mkdocs gh-deploy failed:\n{proc.stderr}")
            raise typer.Exit(1)
        print(f"Deployed to GitHub Pages{remote_label}")
    elif build:
        print("\nRunning mkdocs build...")
        proc = subprocess.run(
            ["mkdocs", "build"],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"Error: mkdocs build failed:\n{proc.stderr}")
            raise typer.Exit(1)
        print(f"Built to {output_dir}/site/")


def _init_wiki_repo(
    output_dir: Path,
    github_repo: str = "",
    private: bool = True,
) -> None:
    """Initialize the output directory as a git repo for wiki deployment.

    If the directory already has a .git, this is a no-op (safe to re-run).
    If --github-repo is provided, creates the repo on GitHub and adds it
    as the 'origin' remote.
    """
    import shutil

    output_dir.mkdir(parents=True, exist_ok=True)
    git_dir = output_dir / ".git"

    if not git_dir.exists():
        # git init
        proc = subprocess.run(
            ["git", "init"],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"Error: git init failed:\n{proc.stderr}")
            raise typer.Exit(1)
        print(f"Initialized git repo in {output_dir}/")

        # Write .gitignore
        gitignore = output_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("site/\n")
    else:
        print(f"Git repo already exists in {output_dir}/")

    # Create GitHub repo if requested
    if github_repo:
        gh_bin = shutil.which("gh")
        if not gh_bin:
            print("Error: gh CLI not found. Install from https://cli.github.com/")
            raise typer.Exit(1)

        # Check if remote already exists
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            print(f"Remote 'origin' already set to {proc.stdout.strip()}")
            return

        # Create the repo on GitHub
        visibility = "--private" if private else "--public"
        proc = subprocess.run(
            ["gh", "repo", "create", github_repo, visibility, "--confirm"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # Repo might already exist — that's fine
            if "already exists" not in proc.stderr:
                print(f"Error creating repo: {proc.stderr}")
                raise typer.Exit(1)
            print(f"Repo {github_repo} already exists")

        # Add as remote
        remote_url = f"git@github.com:{github_repo}.git"
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
        )
        print(f"Added remote 'origin' -> {remote_url}")
