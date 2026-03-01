"""
Unified maintain command for EMDX.
Consolidates all modification and maintenance operations.

Uses the MaintenanceApplication service layer to orchestrate maintenance
operations, breaking bidirectional dependencies between commands and services.
"""

from __future__ import annotations

import logging
import subprocess
import time

# Removed CommandDefinition import - using standard typer pattern
from typing import TYPE_CHECKING

import typer
from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from ..applications import MaintenanceApplication
from ..utils.output import console, is_non_interactive

if TYPE_CHECKING:
    from ..services.contradiction_service import ContradictionResult

logger = logging.getLogger(__name__)


def maintain(
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically fix all issues"),
    clean: bool = typer.Option(
        False, "--clean", "-c", help="Remove duplicates and empty documents"
    ),  # noqa: E501
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge similar documents"),
    tags: bool = typer.Option(False, "--tags", "-t", help="Auto-tag untagged documents"),
    gc: bool = typer.Option(False, "--gc", "-g", help="Run garbage collection"),
    dry_run: bool = typer.Option(
        True, "--execute/--dry-run", help="Execute actions (default: dry run)"
    ),  # noqa: E501
    threshold: float = typer.Option(0.7, "--threshold", help="Similarity threshold for merging"),
) -> None:
    """
    Maintain your knowledge base by fixing issues and optimizing content.

    This command performs various maintenance operations to keep your
    knowledge base clean, organized, and efficient.

    Examples:
        emdx maintain                # Interactive wizard
        emdx maintain --auto         # Fix all issues automatically
        emdx maintain --clean        # Remove duplicates and empty docs
        emdx maintain --tags         # Auto-tag documents
        emdx maintain --execute      # Actually perform changes
    """

    # If no specific maintenance requested, run interactive wizard
    if not any([auto, clean, merge, tags, gc]):
        _interactive_wizard(dry_run)
        return

    # If --auto is specified, enable everything
    if auto:
        clean = merge = tags = gc = True

    # Header
    console.print(Panel("[bold cyan]🧹 Knowledge Base Maintenance[/bold cyan]", box=box.DOUBLE))

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]\n")

    # Track what was done
    actions_taken = []

    # Clean duplicates and empty documents
    if clean:
        console.print("[bold]Cleaning duplicates and empty documents...[/bold]")
        cleaned = _clean_documents(dry_run)
        if cleaned:
            actions_taken.append(cleaned)
        console.print()

    # Auto-tag documents
    if tags:
        console.print("[bold]Auto-tagging documents...[/bold]")
        tagged = _auto_tag_documents(dry_run)
        if tagged:
            actions_taken.append(tagged)
        console.print()

    # Merge similar documents
    if merge:
        console.print("[bold]Merging similar documents...[/bold]")
        merged = _merge_documents(dry_run, threshold)
        if merged:
            actions_taken.append(merged)
        console.print()

    # Run garbage collection
    if gc:
        console.print("[bold]Running garbage collection...[/bold]")
        collected = _garbage_collect(dry_run)
        if collected:
            actions_taken.append(collected)
        console.print()

    # Summary
    if actions_taken:
        console.print("[bold green]✅ Maintenance Summary:[/bold green]")
        for action in actions_taken:
            console.print(f"  • {action}")
    else:
        console.print("[green]✨ No maintenance needed![/green]")

    if dry_run and actions_taken:
        console.print("\n[dim]Run with --execute to perform these actions[/dim]")


def _interactive_wizard(dry_run: bool) -> None:
    """Run interactive maintenance wizard using MaintenanceApplication."""
    app = MaintenanceApplication()

    with console.status("[bold green]Analyzing knowledge base..."):
        metrics = app.get_health_metrics()

    # Show current health
    overall_score = metrics["overall_score"] * 100
    health_color = "green" if overall_score >= 80 else "yellow" if overall_score >= 60 else "red"

    console.print(
        f"\n[bold]Current Health: [{health_color}]{overall_score:.0f}%[/{health_color}][/bold]"
    )  # noqa: E501

    # Collect all recommendations
    all_recommendations = []
    for metric in metrics["metrics"].values():
        all_recommendations.extend(metric.recommendations)

    if not all_recommendations:
        console.print("[green]✨ Your knowledge base is in great shape![/green]")
        return

    # Show issues
    console.print("\n[bold]Issues Found:[/bold]")
    for rec in all_recommendations:
        console.print(f"  • {rec}")

    console.print()

    # Ask what to fix - only run cheap checks, defer expensive ones
    actions: list[str | tuple[str, list[tuple[object, ...]]]] = []

    # Check for duplicates (cheap - based on recommendations)
    if "duplicate" in str(all_recommendations).lower():
        if is_non_interactive() or Confirm.ask("Remove duplicate documents?"):
            actions.append("clean")

    # Check for tagging issues (cheap - based on recommendations)
    if "tag" in str(all_recommendations).lower():
        if is_non_interactive() or Confirm.ask("Auto-tag untagged documents?"):
            actions.append("tags")

    # Deduplicate similar documents - now fast with TF-IDF!
    if is_non_interactive() or Confirm.ask("Scan for duplicate documents?"):
        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

        from emdx.services.similarity import SimilarityService

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold green]{task.description}"),
                BarColumn(),
                TextColumn("[cyan]{task.fields[found]} pairs"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Building index...", total=100, found=0)

                def update_progress(current: int, total: int, found: int) -> None:
                    if current < 50:
                        progress.update(
                            task,
                            description="Building TF-IDF index...",
                            completed=current,
                            found=found,
                        )  # noqa: E501
                    else:
                        progress.update(
                            task,
                            description="Finding duplicates...",
                            completed=current,
                            found=found,
                        )  # noqa: E501

                # Get all pairs at 70% threshold
                similarity_service = SimilarityService()
                all_pairs = similarity_service.find_all_duplicate_pairs(
                    min_similarity=0.7,
                    progress_callback=update_progress,
                )
                progress.update(task, completed=100, found=len(all_pairs))
        except ImportError as e:
            console.print(f"  [red]{e}[/red]")
            all_pairs = []

        if not all_pairs:
            console.print("[green]No duplicate documents found[/green]")
        else:
            # Categorize by similarity threshold
            high_sim = [(p, s) for p in all_pairs if (s := p[4]) >= 0.95]  # >95% - obvious dupes
            med_sim = [(p, s) for p in all_pairs if 0.70 <= p[4] < 0.95]  # 70-95% - review

            console.print("\n[bold]Duplicate Analysis:[/bold]")
            n = len(high_sim)
            console.print(
                f"  [red]• {n} obvious duplicates[/red] (>95% similar) - safe to auto-delete"
            )
            console.print(
                f"  [yellow]• {len(med_sim)} similar documents[/yellow] (70-95%) - need review"
            )  # noqa: E501

            # Handle high similarity (auto-delete)
            if high_sim:
                console.print("\n[dim]Obvious duplicates (will delete the less-viewed copy):[/dim]")
                for (_id1, _id2, t1, _t2, sim), _ in high_sim[:5]:
                    console.print(f"  [dim]• {t1[:40]}... ({sim:.0%})[/dim]")
                if len(high_sim) > 5:
                    console.print(f"  [dim]  ...and {len(high_sim) - 5} more[/dim]")

                prompt = f"Auto-delete {len(high_sim)} obvious duplicates?"
                if is_non_interactive() or Confirm.ask(prompt):
                    actions.append(("dedup_high", [p for p, _ in high_sim]))

            # Handle medium similarity (show and ask)
            if med_sim:
                console.print("\n[dim]Similar documents (70-95%):[/dim]")
                for (_id1, _id2, t1, t2, sim), _ in med_sim[:8]:
                    console.print(f"  [dim]• '{t1[:30]}' ↔ '{t2[:30]}' ({sim:.0%})[/dim]")
                if len(med_sim) > 8:
                    console.print(f"  [dim]  ...and {len(med_sim) - 8} more[/dim]")

                console.print("\n[yellow]These need manual review - skipping for now.[/yellow]")
                console.print(
                    "[dim]Use 'emdx ai similar <doc_id>' to review individual documents.[/dim]"
                )  # noqa: E501

    # Garbage collection (cheap check)
    gc_preview = app.garbage_collect(dry_run=True)
    if gc_preview.items_processed > 0:
        console.print("\n[yellow]Database needs cleanup[/yellow]")
        if is_non_interactive() or Confirm.ask("Run garbage collection?"):
            actions.append("gc")

    if not actions:
        console.print("\n[yellow]No actions selected[/yellow]")
        return

    # Execute selected actions - always execute (not dry run) after user confirmation
    console.print("\n[bold]Executing maintenance...[/bold]\n")

    for action in actions:
        if action == "clean":
            _clean_documents(False)
        elif action == "tags":
            _auto_tag_documents(False)
        elif action == "merge":
            _merge_documents(False)
        elif isinstance(action, tuple) and action[0] == "dedup_high":
            _deduplicate_pairs(action[1])
        elif action == "gc":
            _garbage_collect(False)
        console.print()


def _clean_documents(dry_run: bool) -> str | None:
    """Clean duplicates and empty documents using MaintenanceApplication."""
    app = MaintenanceApplication()
    try:
        result = app.clean_duplicates(dry_run=dry_run)
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return None

    if result.items_affected == 0:
        console.print("  ✨ No duplicates or empty documents found!")
        return None

    if dry_run:
        console.print(f"  Found: {result.items_processed} documents to clean")
        return result.message

    # Show details from the result
    for detail in result.details:
        console.print(f"  [green]✓[/green] {detail}")

    return result.message


def _auto_tag_documents(dry_run: bool) -> str | None:
    """Auto-tag untagged documents using MaintenanceApplication."""
    app = MaintenanceApplication()
    result = app.auto_tag_documents(dry_run=dry_run)

    if result.items_processed == 0:
        console.print("  ✨ All documents are already tagged!")
        return None

    console.print(f"  Found: {result.items_processed} untagged documents")

    if dry_run:
        # Show preview from result details
        if result.details:
            console.print("\n  Preview of auto-tagging:")
            for detail in result.details:
                console.print(f"    • {detail}")
        return result.message

    console.print(f"  [green]✓[/green] {result.message}")
    return result.message


def _merge_documents(dry_run: bool, threshold: float = 0.7) -> str | None:
    """Merge similar documents using MaintenanceApplication."""
    app = MaintenanceApplication()
    try:
        result = app.merge_similar(dry_run=dry_run, threshold=threshold)
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return None

    if result.items_processed == 0:
        console.print("  ✨ No similar documents found!")
        return None

    console.print(f"  Found: {result.items_processed} merge candidates")

    if dry_run:
        # Show preview from result details
        if result.details:
            console.print("\n  Top merge candidates:")
            for i, detail in enumerate(result.details, 1):
                console.print(f"    [{i}] {detail}")
        return result.message

    console.print(f"  [green]✓[/green] {result.message}")
    return result.message


def _deduplicate_pairs(pairs: list) -> str | None:
    """Delete duplicate documents from similarity pairs.

    For each pair, keeps the document with more views (or longer content as tiebreaker)
    and soft-deletes the other.
    """
    from ..database import db
    from ..models.documents import delete_document

    deleted_count = 0

    with db.get_connection() as conn:
        cursor = conn.cursor()

        for doc1_id, doc2_id, _title1, _title2, _similarity in pairs:
            # Get access counts to determine which to keep
            cursor.execute(
                "SELECT id, access_count, LENGTH(content) as len FROM documents WHERE id IN (?, ?)",
                (doc1_id, doc2_id),
            )
            docs = {row["id"]: row for row in cursor.fetchall()}

            if len(docs) < 2:
                continue  # One already deleted

            doc1 = docs.get(doc1_id, {"access_count": 0, "len": 0})
            doc2 = docs.get(doc2_id, {"access_count": 0, "len": 0})

            # Determine which to delete (keep the one with more views, then longer content)
            if doc1["access_count"] > doc2["access_count"]:
                delete_id = doc2_id
            elif doc2["access_count"] > doc1["access_count"]:
                delete_id = doc1_id
            elif (doc1["len"] or 0) >= (doc2["len"] or 0):
                delete_id = doc2_id
            else:
                delete_id = doc1_id

            # Soft delete the duplicate
            if delete_document(str(delete_id)):
                deleted_count += 1

    console.print(f"  [green]✓[/green] Deleted {deleted_count} duplicate documents")
    return f"Deleted {deleted_count} duplicates"


def _garbage_collect(dry_run: bool) -> str | None:
    """Run garbage collection using MaintenanceApplication."""
    app = MaintenanceApplication()
    result = app.garbage_collect(dry_run=dry_run)

    if result.items_processed == 0:
        console.print("  ✨ No garbage collection needed!")
        return None

    if dry_run:
        console.print(f"  Found: {result.items_processed} items to clean")
        return result.message

    # Show details from the result
    for detail in result.details:
        console.print(f"  [green]✓[/green] {detail}")

    return result.message


def cleanup_main(
    branches: bool = typer.Option(False, "--branches", "-b", help="Clean up old worktree branches"),  # noqa: E501
    all: bool = typer.Option(False, "--all", "-a", help="Clean up everything"),
    dry_run: bool = typer.Option(
        True, "--execute/--dry-run", help="Execute actions (default: dry run)"
    ),  # noqa: E501
    force: bool = typer.Option(False, "--force", "-f", help="Force delete unmerged branches"),
    age_days: int = typer.Option(7, "--age", help="Only clean branches older than N days"),
) -> None:
    """
    Clean up system resources used by EMDX.

    This command helps clean up:
    - Old git branches from worktrees

    Examples:
        emdx maintain cleanup --all          # Clean everything (dry run)
        emdx maintain cleanup --all --execute # Actually clean everything
        emdx maintain cleanup --branches     # Clean old branches
        emdx maintain cleanup --branches --force # Delete unmerged branches too
    """
    if not any([branches, all]):
        console.print("[yellow]Please specify what to clean up. Use --help for options.[/yellow]")
        return

    if all:
        branches = True

    console.print(Panel("[bold cyan]🧹 EMDX Cleanup[/bold cyan]", box=box.DOUBLE))

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]\n")

    # Track actions
    actions_taken = []

    # Clean branches
    if branches:
        console.print("[bold]Cleaning up old worktree branches...[/bold]")
        cleaned = _cleanup_branches(dry_run, force=force, older_than_days=age_days)
        if cleaned:
            actions_taken.append(cleaned)
        console.print()

    # Summary
    if actions_taken:
        console.print("[bold green]✅ Cleanup Summary:[/bold green]")
        for action in actions_taken:
            console.print(f"  • {action}")
    else:
        console.print("[green]✨ No cleanup needed![/green]")

    if dry_run and actions_taken:
        console.print("\n[dim]Run with --execute to perform these actions[/dim]")


def _cleanup_branches(dry_run: bool, force: bool = False, older_than_days: int = 7) -> str | None:
    """Clean up old worktree branches.

    Args:
        dry_run: If True, only show what would be done
        force: If True, delete unmerged branches as well
        older_than_days: Only delete branches older than this many days
    """
    try:
        # First check if we're in a git repository
        git_check = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True)
        if git_check.returncode != 0:
            console.print("  [yellow]⚠[/yellow] Not in a git repository")
            return None

        # Get current branch
        current_result = subprocess.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True, check=True
        )
        current_branch = current_result.stdout.strip()

        # List all branches
        result = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True, check=True)

        # Find worktree/* branches
        worktree_branches = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            # Skip remote branches and current branch
            if branch.startswith("remotes/") or branch == current_branch:
                continue
            if branch.startswith("worktree/") or branch.startswith("worktree-"):
                worktree_branches.append(branch)

        if not worktree_branches:
            console.print("  ✨ No worktree branches found!")
            return None

        # Get main/master branch name
        main_branch = "main"
        main_check = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/main"])
        if main_check.returncode != 0:
            # Try master
            master_check = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"]
            )  # noqa: E501
            if master_check.returncode == 0:
                main_branch = "master"

        # Check which branches are merged and their age
        branches_to_delete = []
        unmerged_branches = []

        for branch in worktree_branches:
            # Get branch age
            age_cmd = subprocess.run(
                ["git", "log", "-1", "--format=%ct", branch], capture_output=True, text=True
            )

            if age_cmd.returncode == 0:
                branch_timestamp = int(age_cmd.stdout.strip())
                branch_age_days = (time.time() - branch_timestamp) / (24 * 60 * 60)

                # Skip branches that are too new
                if branch_age_days < older_than_days:
                    continue

            # Check if branch is merged
            merge_check = subprocess.run(
                ["git", "branch", "--merged", main_branch], capture_output=True, text=True
            )

            is_merged = branch in merge_check.stdout

            if is_merged:
                branches_to_delete.append((branch, "merged", int(branch_age_days)))
            elif force:
                # For unmerged branches, check if they have any unique commits
                unique_commits = subprocess.run(
                    ["git", "rev-list", f"{main_branch}..{branch}"], capture_output=True, text=True
                )
                has_unique_commits = bool(unique_commits.stdout.strip())
                if not has_unique_commits:
                    branches_to_delete.append((branch, "no unique commits", int(branch_age_days)))
                else:
                    unmerged_branches.append((branch, int(branch_age_days)))
            else:
                unmerged_branches.append((branch, int(branch_age_days)))

        # Report findings
        console.print(f"  Found: {len(worktree_branches)} worktree branches")
        if branches_to_delete:
            console.print(f"  • {len(branches_to_delete)} can be deleted")
        if unmerged_branches:
            console.print(f"  • {len(unmerged_branches)} unmerged (use --force to delete)")

        if dry_run:
            if branches_to_delete:
                console.print("\n  Branches to delete:")
                for branch, reason, age in branches_to_delete[:10]:
                    console.print(f"    • {branch} ({reason}, {age}d old)")
                if len(branches_to_delete) > 10:
                    console.print(f"    ... and {len(branches_to_delete) - 10} more")

            if unmerged_branches and not force:
                console.print("\n  [yellow]Unmerged branches (use --force):[/yellow]")
                for branch, age in unmerged_branches[:5]:
                    console.print(f"    • {branch} ({age}d old)")
                if len(unmerged_branches) > 5:
                    console.print(f"    ... and {len(unmerged_branches) - 5} more")

            return f"Would delete {len(branches_to_delete)} branches"

        # Delete branches
        deleted = 0
        failed = 0

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Deleting branches...", total=len(branches_to_delete))

            for branch, reason, _age in branches_to_delete:
                try:
                    # Use -D for force delete if needed
                    delete_flag = "-D" if force and reason != "merged" else "-d"
                    subprocess.run(
                        ["git", "branch", delete_flag, branch], capture_output=True, check=True
                    )
                    deleted += 1
                except subprocess.CalledProcessError as e:
                    logger.debug("Failed to delete branch %s: %s", branch, e)
                    failed += 1
                progress.update(task, advance=1)

        if deleted > 0:
            console.print(f"  [green]✓[/green] Deleted {deleted} branches")
        if failed > 0:
            console.print(f"  [yellow]⚠[/yellow] Failed to delete {failed} branches")

        return f"Deleted {deleted} branches"

    except subprocess.CalledProcessError as e:
        console.print(f"  [red]✗[/red] Git error: {e}")
        return None


def drift(
    days: int = typer.Option(30, "--days", "-d", help="Staleness threshold in days"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Detect abandoned or forgotten work in your knowledge base.

    Analyzes task and epic timestamps to surface:
    - Stale epics with no recent activity
    - Orphaned active tasks not touched in >14 days (or --days/2)
    - Documents linked to stale tasks
    - Epics with burst-then-stop activity patterns

    Examples:
        emdx maintain drift              # Default 30-day threshold
        emdx maintain drift --days 7     # More aggressive threshold
        emdx maintain drift --json       # Machine-readable output
    """
    from emdx.commands._drift import run_drift

    run_drift(days=days, json_output=json_output)


def contradictions(
    limit: int = typer.Option(100, "--limit", "-n", help="Max pairs to check"),
    project: str = typer.Option(None, "--project", "-p", help="Scope to project"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    threshold: float = typer.Option(
        0.7, "--threshold", help="Similarity threshold for candidate pairs"
    ),
) -> None:
    """
    Detect conflicting information across documents.

    Uses a 3-stage funnel:
    1. Find candidate pairs via embedding similarity
    2. Screen for contradictions (NLI model or heuristic fallback)
    3. Report contradicting excerpts with confidence levels

    Examples:
        emdx maintain contradictions
        emdx maintain contradictions --threshold 0.8 --limit 50
        emdx maintain contradictions --project myproject --json
    """
    import json as json_mod

    from ..services.contradiction_service import ContradictionService

    svc = ContradictionService()

    # Check embeddings exist
    if not svc._check_embeddings_exist():
        if json_output:
            print(
                json_mod.dumps(
                    {
                        "error": "No embedding index found",
                        "hint": "Run `emdx maintain index` first",
                    }
                )
            )
        else:
            console.print(
                "[yellow]Run `emdx maintain index` first to enable "
                "contradiction detection.[/yellow]"
            )
        raise typer.Exit(1)

    # Show method info
    use_nli = svc._check_nli_available()
    if not json_output:
        method = "NLI (cross-encoder)" if use_nli else "heuristic"
        if not use_nli:
            console.print(
                "[dim]NLI model not available, using heuristic "
                "fallback. Install sentence-transformers for "
                "higher accuracy.[/dim]\n"
            )
        console.print(
            f"[bold cyan]Scanning for contradictions[/bold cyan] "
            f"(method={method}, threshold={threshold}, "
            f"limit={limit})\n"
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        disable=json_output,
    ) as progress:
        task = progress.add_task("Finding candidate pairs...", total=None)

        results = svc.find_contradictions(
            limit=limit,
            project=project if project else None,
            threshold=threshold,
        )

        progress.update(task, description="Done", completed=True)

    # Stage 3: Report
    if json_output:
        print(
            json_mod.dumps(
                [r.to_dict() for r in results],
                indent=2,
            )
        )
        return

    if not results:
        console.print("No contradictions detected across checked document pairs. [green]OK[/green]")
        return

    console.print(f"[bold red]Found {len(results)} contradicting document pair(s):[/bold red]\n")

    for result in results:
        console.print(
            Panel(
                _format_contradiction(result),
                title=(
                    f"#{result.doc1_id} vs #{result.doc2_id} (similarity: {result.similarity:.2f})"
                ),
                box=box.ROUNDED,
            )
        )


def _format_contradiction(result: ContradictionResult) -> str:
    """Format a ContradictionResult for Rich display."""
    lines = [
        f"[bold]{result.doc1_title}[/bold] (#{result.doc1_id})",
        f"  vs  [bold]{result.doc2_title}[/bold] (#{result.doc2_id})",
        "",
    ]

    for i, match in enumerate(result.matches, 1):
        confidence_color = "red" if match.confidence > 0.7 else "yellow"
        lines.append(
            f"  [{confidence_color}]Contradiction {i}[/{confidence_color}]"
            f" ({match.method}, confidence: {match.confidence:.2f})"
        )
        lines.append(f"    Doc A: {match.excerpt1[:120]}...")
        lines.append(f"    Doc B: {match.excerpt2[:120]}...")
        lines.append("")

    return "\n".join(lines)


def freshness(
    stale: bool = typer.Option(
        False, "--stale", help="Show only documents below the freshness threshold"
    ),
    threshold: float = typer.Option(
        0.3, "--threshold", "-t", help="Staleness threshold (0-1, default 0.3)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Score document freshness and identify stale documents.

    Combines multiple signals into a 0-1 freshness score:
    - Age decay (exponential, ~30-day half-life)
    - View recency (when last accessed)
    - Link health (are linked docs still active?)
    - Content length (short stubs score lower)
    - Tag signals ("active" boosts, "done" penalizes)

    Examples:
        emdx maintain freshness              # Score all documents
        emdx maintain freshness --stale      # Show only stale docs
        emdx maintain freshness -t 0.5       # Custom threshold
        emdx maintain freshness --json       # Machine-readable output
    """
    from emdx.commands._freshness import run_freshness

    run_freshness(threshold=threshold, stale_only=stale, json_output=json_output)


def gaps(
    top: int = typer.Option(10, "--top", "-n", help="Number of gaps to show per category"),
    stale_days: int = typer.Option(
        60, "--stale-days", "-s", help="Days threshold for stale topics"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Detect knowledge gaps and areas with sparse coverage.

    Analyzes the knowledge base to identify:
    - Tags with very few documents compared to the average
    - Documents with incoming links but no outgoing links (dead-ends)
    - Documents with zero links (orphaned knowledge)
    - Tags where all documents are old with no recent activity
    - Projects with few documents relative to their task count

    Examples:
        emdx maintain gaps              # Default gap analysis
        emdx maintain gaps --top 5      # Show top 5 gaps per category
        emdx maintain gaps --stale-days 30  # 30-day staleness threshold
        emdx maintain gaps --json       # Machine-readable output
    """
    from emdx.commands._gaps import run_gaps

    run_gaps(top=top, stale_days=stale_days, json_output=json_output)


# Create typer app for this module
app = typer.Typer(help="Database maintenance and cleanup operations")


@app.callback(invoke_without_command=True)
def maintain_callback(
    ctx: typer.Context,
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically fix all issues"),
    clean: bool = typer.Option(
        False, "--clean", "-c", help="Remove duplicates and empty documents"
    ),  # noqa: E501
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge similar documents"),
    tags: bool = typer.Option(False, "--tags", "-t", help="Auto-tag untagged documents"),
    gc: bool = typer.Option(False, "--gc", "-g", help="Run garbage collection"),
    dry_run: bool = typer.Option(
        True, "--execute/--dry-run", help="Execute actions (default: dry run)"
    ),  # noqa: E501
    threshold: float = typer.Option(0.7, "--threshold", help="Similarity threshold for merging"),
) -> None:
    """
    Maintain your knowledge base — fix issues, optimize, and analyze.

    Run with no subcommand for the maintenance wizard.

    Subcommands:
        cleanup      Clean up old worktree branches
        stale        Knowledge decay and staleness tracking

    See also:
        emdx status --health    Knowledge base health metrics
    """
    if ctx.invoked_subcommand is not None:
        return
    maintain(
        auto=auto, clean=clean, merge=merge, tags=tags, gc=gc, dry_run=dry_run, threshold=threshold
    )


app.command(name="cleanup")(cleanup_main)
app.command(name="drift")(drift)
app.command(name="freshness")(freshness)
app.command(name="gaps")(gaps)

# Register code-drift as a direct subcommand of maintain
from emdx.commands.code_drift import code_drift_command  # noqa: E402

app.command(name="code-drift")(code_drift_command)


def backup_command(
    list_backups: bool = typer.Option(False, "--list", "-l", help="List existing backups"),
    restore: str = typer.Option(None, "--restore", "-r", help="Restore from a backup file"),
    no_compress: bool = typer.Option(False, "--no-compress", help="Skip gzip compression"),
    no_retention: bool = typer.Option(
        False, "--no-retention", help="Disable automatic pruning (keep all backups)"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output (for hook use)"),
    json_output: bool = typer.Option(False, "--json", help="Structured JSON output"),
) -> None:
    """Create, list, or restore knowledge base backups.

    By default, creates a compressed backup with logarithmic retention
    (keeps ~19 backups covering 2 years of history).

    Examples:
        emdx maintain backup              # Create compressed backup
        emdx maintain backup --list       # List existing backups
        emdx maintain backup --restore emdx-backup-2026-02-28_143022.db.gz
        emdx maintain backup --no-compress # Create uncompressed backup
        emdx maintain backup --quiet      # Silent (for hooks)
        emdx maintain backup --json       # JSON output
    """
    import json as json_mod
    from pathlib import Path

    from ..config.settings import get_db_path
    from ..services.backup_service import BackupService

    db_path = get_db_path()
    svc = BackupService(db_path=db_path, retention=not no_retention)

    if list_backups:
        backups = svc.list_backups()
        if json_output:
            from ..services.types import BackupInfo

            items: list[BackupInfo] = []
            for bp in backups:
                dt = svc._parse_backup_date(bp)
                items.append(
                    BackupInfo(
                        filename=bp.name,
                        path=str(bp),
                        size_bytes=bp.stat().st_size,
                        created_at=dt.isoformat() if dt else "",
                    )
                )
            print(json_mod.dumps(items, indent=2))
        elif backups:
            for bp in backups:
                size_kb = bp.stat().st_size / 1024
                dt = svc._parse_backup_date(bp)
                date_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "unknown"
                print(f"{bp.name}  {size_kb:.0f}KB  {date_str}")
        else:
            if not quiet:
                print("No backups found.")
        return

    if restore:
        restore_path = Path(restore)
        # Allow just the filename (look in backup dir)
        if not restore_path.exists():
            restore_path = svc.backup_dir / restore
        if not restore_path.exists():
            msg = f"Backup file not found: {restore}"
            if json_output:
                print(json_mod.dumps({"success": False, "message": msg}))
            else:
                print(msg)
            raise typer.Exit(code=1)

        result = svc.restore_backup(restore_path)
        if json_output:
            print(
                json_mod.dumps(
                    {
                        "success": result.success,
                        "message": result.message,
                        "duration_seconds": round(result.duration_seconds, 2),
                    }
                )
            )
        elif not quiet:
            if result.success:
                print(
                    f"Restored from {result.path.name if result.path else restore}"  # type: ignore[union-attr]
                    f" in {result.duration_seconds:.1f}s"
                )
            else:
                print(result.message)
        if not result.success:
            raise typer.Exit(code=1)
        return

    # Default: create backup
    if not db_path.exists():
        msg = f"Database not found: {db_path}"
        if json_output:
            print(json_mod.dumps({"success": False, "message": msg}))
        elif not quiet:
            print(msg)
        raise typer.Exit(code=1)

    result = svc.create_backup(compress=not no_compress)
    if json_output:
        print(
            json_mod.dumps(
                {
                    "success": result.success,
                    "path": str(result.path) if result.path else None,
                    "size_bytes": result.size_bytes,
                    "duration_seconds": round(result.duration_seconds, 2),
                    "pruned_count": result.pruned_count,
                    "message": result.message,
                }
            )
        )
    elif not quiet:
        if result.success:
            size_kb = result.size_bytes / 1024
            print(
                f"Backup created: {result.path.name if result.path else 'unknown'}"  # type: ignore[union-attr]
                f" ({size_kb:.0f}KB, {result.duration_seconds:.1f}s)"
            )
            if result.pruned_count > 0:
                print(f"Pruned {result.pruned_count} old backup(s)")
        else:
            print(result.message)
    if not result.success:
        raise typer.Exit(code=1)


app.command(name="backup")(backup_command)

# Register compact as a subcommand of maintain
from emdx.commands.compact import app as compact_app  # noqa: E402

app.add_typer(compact_app, name="compact", help="Compact related documents via AI synthesis")

# Register index/link/entity commands from maintain_index as direct subcommands
from emdx.commands.maintain_index import (  # noqa: E402
    create_links,
    entities_command,
    index_embeddings,
    remove_link,
    wikify_command,
)

app.command(name="index")(index_embeddings)
app.command(name="link")(create_links)
app.command(name="unlink")(remove_link)
app.command(name="wikify")(wikify_command)
app.command(name="entities")(entities_command)

# Register wiki as a subcommand group
from emdx.commands.wiki import wiki_app  # noqa: E402

app.add_typer(wiki_app, name="wiki", help="Auto-wiki generation")

# Register stale as a subcommand group of maintain
from emdx.commands.stale import app as stale_app  # noqa: E402

app.add_typer(stale_app, name="stale", help="Knowledge decay and staleness tracking")

# Register contradictions command
app.command(name="contradictions")(contradictions)

# Register cloud-backup as a subcommand group
from emdx.commands.backup import app as cloud_backup_app  # noqa: E402

app.add_typer(cloud_backup_app, name="cloud-backup", help="Cloud backup operations")

if __name__ == "__main__":
    app()
