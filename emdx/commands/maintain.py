"""
Unified maintain command for EMDX.
Consolidates all modification and maintenance operations.

Uses the MaintenanceApplication service layer to orchestrate maintenance
operations, breaking bidirectional dependencies between commands and services.
"""

import logging
import subprocess
import time

# Removed CommandDefinition import - using standard typer pattern
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

import typer
from rich import box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from ..applications import MaintenanceApplication
from ..utils.output import console, is_non_interactive

if TYPE_CHECKING:
    pass

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
    branches: bool = typer.Option(
        False, "--branches", "-b", help="Clean up old execution branches"
    ),  # noqa: E501
    processes: bool = typer.Option(False, "--processes", "-p", help="Clean up zombie processes"),
    executions: bool = typer.Option(False, "--executions", "-e", help="Clean up stuck executions"),
    all: bool = typer.Option(False, "--all", "-a", help="Clean up everything"),
    dry_run: bool = typer.Option(
        True, "--execute/--dry-run", help="Execute actions (default: dry run)"
    ),  # noqa: E501
    force: bool = typer.Option(False, "--force", "-f", help="Force delete unmerged branches"),
    age_days: int = typer.Option(7, "--age", help="Only clean branches older than N days"),
    max_runtime: int = typer.Option(
        2, "--max-runtime", help="Max process runtime in hours before considering stuck"
    ),  # noqa: E501
    timeout_minutes: int = typer.Option(
        30, "--timeout", help="Minutes after which to consider execution stale"
    ),  # noqa: E501
) -> None:
    """
    Clean up system resources used by EMDX executions.

    This command helps clean up:
    - Old git branches from executions
    - Zombie/stuck processes
    - Database execution records stuck in 'running' state

    Examples:
        emdx maintain cleanup --all          # Clean everything (dry run)
        emdx maintain cleanup --all --execute # Actually clean everything
        emdx maintain cleanup --branches     # Clean old branches
        emdx maintain cleanup --branches --force # Delete unmerged branches too
        emdx maintain cleanup --processes    # Kill zombie processes
    """
    if not any([branches, processes, executions, all]):
        console.print("[yellow]Please specify what to clean up. Use --help for options.[/yellow]")
        return

    if all:
        branches = processes = executions = True

    console.print(Panel("[bold cyan]🧹 EMDX Execution Cleanup[/bold cyan]", box=box.DOUBLE))

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]\n")

    # Track actions
    actions_taken = []

    # Clean branches
    if branches:
        console.print("[bold]Cleaning up old execution branches...[/bold]")
        cleaned = _cleanup_branches(dry_run, force=force, older_than_days=age_days)
        if cleaned:
            actions_taken.append(cleaned)
        console.print()

    # Clean processes
    if processes:
        console.print("[bold]Cleaning up zombie processes...[/bold]")
        cleaned = _cleanup_processes(dry_run, max_runtime_hours=max_runtime)
        if cleaned:
            actions_taken.append(cleaned)
        console.print()

    # Clean executions
    if executions:
        console.print("[bold]Cleaning up stuck executions...[/bold]")
        cleaned = _cleanup_executions(dry_run, timeout_minutes=timeout_minutes)
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
    """Clean up old execution branches.

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

        # Find exec-* branches
        exec_branches = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            # Skip remote branches and current branch
            if branch.startswith("remotes/") or branch == current_branch:
                continue
            if branch.startswith("exec-"):
                exec_branches.append(branch)

        if not exec_branches:
            console.print("  ✨ No execution branches found!")
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

        for branch in exec_branches:
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
        console.print(f"  Found: {len(exec_branches)} execution branches")
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


def _cleanup_processes(dry_run: bool, max_runtime_hours: int = 2) -> str | None:
    """Clean up zombie and stuck EMDX processes.

    Args:
        dry_run: If True, only show what would be done
        max_runtime_hours: Maximum runtime before considering a process stuck
    """
    # Lazy import - psutil is slow to import (~16ms)
    import psutil

    from ..models.executions import get_running_executions

    # Categorize problematic processes
    zombie_procs = []
    stuck_procs = []
    orphaned_procs = []

    # Get running executions from database
    running_execs = get_running_executions()
    known_pids = {exec.pid for exec in running_execs if exec.pid}

    # Find EMDX-related processes
    for proc in psutil.process_iter(["pid", "name", "cmdline", "status", "create_time"]):
        try:
            # Check if it's EMDX-related
            cmdline = proc.info.get("cmdline", []) or []
            cmdline_str = " ".join(cmdline)

            # Look for EMDX execution processes
            patterns = [
                "emdx delegate",
                "emdx exec",
                "claude_wrapper.py",
                "emdx-exec",
                "claude --print",
            ]
            if not any(pattern in cmdline_str for pattern in patterns):
                continue

            # Get process info
            pid = proc.info["pid"]
            status = proc.info.get("status", "")

            # Check if it's a zombie
            if status == psutil.STATUS_ZOMBIE or status == "zombie":
                zombie_procs.append((proc, "zombie"))
                continue

            # Check runtime
            try:
                create_time = proc.info["create_time"]
                runtime_hours = (time.time() - create_time) / 3600

                # Check if process is stuck (running too long)
                if runtime_hours > max_runtime_hours:
                    stuck_procs.append((proc, f"{runtime_hours:.1f}h runtime"))
                    continue

                # Check if process is orphaned (not in database)
                if pid not in known_pids and "claude" in cmdline_str:
                    orphaned_procs.append((proc, f"orphaned, {runtime_hours:.1f}h old"))

            except Exception as e:
                logger.debug("Could not get process runtime: %s", e)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Combine all problematic processes
    all_procs = zombie_procs + stuck_procs + orphaned_procs

    if not all_procs:
        console.print("  ✨ No problematic processes found!")
        return None

    # Report findings
    console.print(f"  Found: {len(all_procs)} problematic processes")
    if zombie_procs:
        console.print(f"  • {len(zombie_procs)} zombie processes")
    if stuck_procs:
        console.print(f"  • {len(stuck_procs)} stuck (running > {max_runtime_hours}h)")
    if orphaned_procs:
        console.print(f"  • {len(orphaned_procs)} orphaned (not in database)")

    if dry_run:
        console.print("\n  Processes to terminate:")
        for proc, reason in all_procs[:10]:
            try:
                # Get process details
                cmdline = proc.cmdline()
                if len(cmdline) > 3:
                    cmd_display = " ".join(cmdline[:3]) + "..."
                else:
                    cmd_display = " ".join(cmdline)

                # Get memory usage
                mem_str = ""
                try:
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    mem_str = f", {mem_mb:.0f}MB"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Memory info unavailable for this process
                    logger.debug("Could not get memory info for PID %s", proc.pid)

                console.print(f"    • PID {proc.pid}: {cmd_display} ({reason}{mem_str})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                console.print(f"    • PID {proc.pid}: [process info unavailable] ({reason})")

        if len(all_procs) > 10:
            console.print(f"    ... and {len(all_procs) - 10} more")

        return f"Would terminate {len(all_procs)} processes"

    # Kill processes
    terminated = 0
    killed = 0
    failed = 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Terminating processes...", total=len(all_procs))

        for proc, _reason in all_procs:
            try:
                # Try graceful termination first
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                    terminated += 1
                except psutil.TimeoutExpired:
                    # Force kill if terminate didn't work
                    proc.kill()
                    proc.wait(timeout=1)
                    killed += 1
            except psutil.NoSuchProcess:
                # Process already gone - count as success
                logger.debug("Process already terminated during cleanup")
                terminated += 1
            except Exception as e:
                logger.warning("Failed to terminate process: %s", e)
                failed += 1

            progress.update(task, advance=1)

    # Report results
    if terminated > 0:
        console.print(f"  [green]✓[/green] Terminated {terminated} processes gracefully")
    if killed > 0:
        console.print(f"  [yellow]⚠[/yellow] Force killed {killed} processes")
    if failed > 0:
        console.print(f"  [red]✗[/red] Failed to terminate {failed} processes")

    total_removed = terminated + killed
    return f"Terminated {total_removed} processes" if total_removed > 0 else None


def _cleanup_executions(
    dry_run: bool, timeout_minutes: int = 30, check_heartbeat: bool = True
) -> str | None:  # noqa: E501
    """Clean up stuck executions in the database.

    Args:
        dry_run: If True, only show what would be done
        timeout_minutes: Minutes after which to consider execution stale
        check_heartbeat: Whether to use heartbeat checking (if available)
    """
    from ..models.executions import (
        get_execution_stats,
        get_running_executions,
        get_stale_executions,
        update_execution_status,
    )
    from ..services.execution_monitor import ExecutionMonitor

    # Initialize monitor
    monitor = ExecutionMonitor(stale_timeout_seconds=timeout_minutes * 60)

    # Get various categories of stuck executions
    stale_heartbeat = []
    dead_process = []
    no_pid_old = []
    long_running = []

    # Get running executions
    running = get_running_executions()

    # Get stale executions based on heartbeat (if enabled)
    if check_heartbeat:
        stale_heartbeat = get_stale_executions(timeout_seconds=timeout_minutes * 60)
        # Create a set of IDs for faster lookup
        stale_ids = {exec.id for exec in stale_heartbeat}
    else:
        stale_ids = set()

    # Check each running execution
    for exec in running:
        # Skip if already categorized as stale
        if exec.id in stale_ids:
            continue

        # Calculate runtime
        runtime_minutes = (datetime.now(timezone.utc) - exec.started_at).total_seconds() / 60

        # Check process health
        health = monitor.check_process_health(exec)

        if health["is_zombie"] or (not health["process_exists"] and exec.pid):
            dead_process.append((exec, health["reason"] or "unknown"))
        elif not exec.pid and runtime_minutes > 60:
            # No PID and > 1 hour old = likely stuck
            no_pid_old.append((exec, f"No PID, {runtime_minutes:.0f}m old"))
        elif runtime_minutes > 180:  # 3 hours
            # Very long running, might be stuck
            long_running.append((exec, f"Running for {runtime_minutes:.0f}m"))

    # Get stats for context
    stats = get_execution_stats()

    # Combine all problematic executions
    all_stuck = []
    if stale_heartbeat:
        all_stuck.extend([(e, "no heartbeat") for e in stale_heartbeat])
    all_stuck.extend(dead_process)
    all_stuck.extend(no_pid_old)

    # Report current state
    console.print(f"  Total executions in DB: {stats['total']}")
    console.print(f"  Currently marked running: {stats['running']}")

    if not all_stuck and not long_running:
        console.print("  ✨ All running executions appear healthy!")
        return None

    # Report findings
    if all_stuck:
        console.print(f"\n  [red]Found {len(all_stuck)} stuck executions:[/red]")
        if stale_heartbeat:
            console.print(f"  • {len(stale_heartbeat)} with no heartbeat")
        if dead_process:
            console.print(f"  • {len(dead_process)} with dead processes")
        if no_pid_old:
            console.print(f"  • {len(no_pid_old)} old executions without PID")

    if long_running:
        n = len(long_running)
        console.print(f"\n  [yellow]Found {n} long-running executions (may be normal):[/yellow]")

    if dry_run:
        # Show details
        if all_stuck:
            console.print("\n  Executions to mark as failed:")
            for exec, reason in all_stuck[:10]:
                age_minutes = int(
                    (datetime.now(timezone.utc) - exec.started_at).total_seconds() / 60
                )  # noqa: E501
                console.print(
                    f"    • #{exec.id}: {exec.doc_title[:30]}... ({reason}, {age_minutes}m old)"
                )  # noqa: E501
            if len(all_stuck) > 10:
                console.print(f"    ... and {len(all_stuck) - 10} more")

        if long_running:
            console.print("\n  Long-running executions (review manually):")
            for exec, reason in long_running[:5]:
                console.print(f"    • #{exec.id}: {exec.doc_title[:30]}... ({reason})")
            if len(long_running) > 5:
                console.print(f"    ... and {len(long_running) - 5} more")

        return f"Would mark {len(all_stuck)} executions as failed"

    # Mark stuck executions as failed
    updated = 0
    failed_updates = 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Updating execution status...", total=len(all_stuck))

        for exec, reason in all_stuck:
            try:
                # Choose appropriate exit code based on reason
                if "heartbeat" in reason:
                    exit_code = 124  # timeout
                elif "zombie" in reason or "dead" in reason:
                    exit_code = 137  # killed
                elif "No PID" in reason:
                    exit_code = -1  # unknown error
                else:
                    exit_code = 1  # general error

                update_execution_status(exec.id, "failed", exit_code)
                updated += 1
            except Exception as e:
                logger.warning("Failed to update execution %s status: %s", exec.id, e)
                failed_updates += 1

            progress.update(task, advance=1)

    # Report results
    if updated > 0:
        console.print(f"  [green]✓[/green] Marked {updated} executions as failed")
    if failed_updates > 0:
        console.print(f"  [yellow]⚠[/yellow] Failed to update {failed_updates} executions")

    # Also report on long-running for awareness
    if long_running:
        console.print(
            f"  [dim]Note: {len(long_running)} long-running executions left untouched[/dim]"
        )  # noqa: E501

    return f"Marked {updated} executions as failed" if updated > 0 else None


def cleanup_temp_dirs(
    dry_run: bool = typer.Option(
        True, "--execute/--dry-run", help="Execute actions (default: dry run)"
    ),  # noqa: E501
    age_hours: int = typer.Option(24, "--age", help="Clean directories older than N hours"),
) -> None:
    """
    Clean up temporary execution directories.

    EMDX creates temporary directories for each execution in /tmp.
    This command cleans up old directories that are no longer needed.

    Examples:
        emdx maintain cleanup-dirs              # Show what would be cleaned
        emdx maintain cleanup-dirs --execute    # Actually clean directories
        emdx maintain cleanup-dirs --age 48     # Clean dirs older than 48 hours
    """
    import shutil
    import tempfile
    from datetime import timedelta

    temp_base = Path(tempfile.gettempdir())
    pattern = "emdx-exec-*"

    console.print(
        Panel("[bold cyan]🗑️ Cleaning Temporary Execution Directories[/bold cyan]", box=box.DOUBLE)
    )

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]\n")

    # Find EMDX execution directories
    exec_dirs = list(temp_base.glob(pattern))

    if not exec_dirs:
        console.print("[green]✨ No execution directories found![/green]")
        return

    # Filter by age
    cutoff_time = datetime.now() - timedelta(hours=age_hours)
    old_dirs = []
    total_size = 0

    for dir_path in exec_dirs:
        try:
            stat = dir_path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if mtime < cutoff_time:
                old_dirs.append((dir_path, mtime))
                # Calculate size
                size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                total_size += size
        except OSError as e:
            logger.warning(f"Could not scan directory {dir_path}: {e}")

    if not old_dirs:
        console.print(f"[green]✨ No directories older than {age_hours} hours![/green]")
        return

    # Sort by age
    old_dirs.sort(key=lambda x: x[1])

    console.print(
        f"Found [yellow]{len(old_dirs)}[/yellow] directories older than {age_hours} hours"
    )  # noqa: E501
    console.print(f"Total space used: [cyan]{total_size / 1024 / 1024:.1f} MB[/cyan]\n")

    # Show preview
    console.print("[bold]Directories to remove:[/bold]")
    for dir_path, mtime in old_dirs[:10]:
        age = datetime.now() - mtime
        age_str = f"{int(age.total_seconds() / 3600)}h ago"
        console.print(f"  • {dir_path.name} ({age_str})")

    if len(old_dirs) > 10:
        console.print(f"  ... and {len(old_dirs) - 10} more")

    if dry_run:
        console.print(f"\n[dim]Run with --execute to remove {len(old_dirs)} directories[/dim]")
        return

    # Actually remove directories
    removed = 0
    freed_space = 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Removing directories...", total=len(old_dirs))

        failed = 0
        for dir_path, _ in old_dirs:
            try:
                # Calculate size before removal
                size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                shutil.rmtree(dir_path)
                removed += 1
                freed_space += size
            except OSError as e:
                logger.warning(f"Failed to remove directory {dir_path}: {e}")
                failed += 1
            progress.update(task, advance=1)

    console.print(f"\n[green]✅ Removed {removed} directories[/green]")
    console.print(f"[green]💾 Freed {freed_space / 1024 / 1024:.1f} MB of disk space[/green]")
    if failed > 0:
        console.print(f"[yellow]⚠️ Failed to remove {failed} directories (check logs)[/yellow]")


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
        cleanup      Clean up execution resources (branches, processes)
        cleanup-dirs Clean up temporary directories
        analyze      Analyze knowledge base health and patterns
        stale        Knowledge decay and staleness tracking
    """
    if ctx.invoked_subcommand is not None:
        return
    maintain(
        auto=auto, clean=clean, merge=merge, tags=tags, gc=gc, dry_run=dry_run, threshold=threshold
    )


app.command(name="cleanup")(cleanup_main)
app.command(name="cleanup-dirs")(cleanup_temp_dirs)

# Import and register analyze as a subcommand of maintain
# Late import to avoid circular dependencies
from emdx.commands.analyze import analyze as analyze_cmd  # noqa: E402

app.command(name="analyze")(analyze_cmd)

# Register compact as a subcommand of maintain
from emdx.commands.compact import app as compact_app  # noqa: E402

app.add_typer(compact_app, name="compact", help="Compact related documents via AI synthesis")


# AI infrastructure commands (moved from `ai` command group)
@app.command(name="index")
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


@app.command(name="link")
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
    from rich.progress import Progress, SpinnerColumn, TextColumn

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


@app.command(name="unlink")
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


@app.command(name="wikify")
def wikify_command(
    doc_id: int | None = typer.Argument(None, help="Document ID to wikify"),
    all_docs: bool = typer.Option(False, "--all", help="Wikify all documents"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show matches without creating links"),
) -> None:
    """Create title-match links between documents (auto-wikification).

    Scans document content for mentions of other documents' titles
    and creates links. No AI or embeddings required.

    Examples:
        emdx maintain wikify 42                # Wikify a single document
        emdx maintain wikify --all             # Backfill all documents
        emdx maintain wikify 42 --dry-run      # Preview matches
        emdx maintain wikify --all --dry-run   # Preview all matches
    """
    from ..services.wikify_service import title_match_wikify, wikify_all

    if all_docs:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Wikifying all documents...", total=None)
            total_created, docs_processed = wikify_all(dry_run=dry_run)
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

    result = title_match_wikify(doc_id, dry_run=dry_run)

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


@app.command(name="entities")
def entities_command(
    doc_id: int | None = typer.Argument(None, help="Document ID to extract entities from"),
    all_docs: bool = typer.Option(False, "--all", help="Extract entities for all documents"),
    wikify: bool = typer.Option(
        True, "--wikify/--no-wikify", help="Also create entity-match links"
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Clear entity-match links before regenerating"
    ),
    cleanup: bool = typer.Option(
        False, "--cleanup", help="Remove noisy entities and re-extract with current filters"
    ),
) -> None:
    """Extract entities from documents and create entity-match links.

    Extracts key concepts, technical terms, and proper nouns from
    markdown structure (headings, backtick terms, bold text, capitalized
    phrases). Then cross-references entities across documents to
    create links. No AI required.

    Examples:
        emdx maintain entities 42              # Extract + link one document
        emdx maintain entities --all           # Backfill all documents
        emdx maintain entities 42 --no-wikify  # Extract only, no linking
        emdx maintain entities --cleanup       # Clean noise + re-extract
    """
    from ..services.entity_service import (
        cleanup_noisy_entities,
        entity_match_wikify,
        entity_wikify_all,
        extract_and_save_entities,
    )

    if cleanup:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Cleaning noisy entities & re-extracting...", total=None)
            deleted, re_extracted = cleanup_noisy_entities()
            progress.update(task, completed=True)
        console.print(
            f"[green]Cleaned up entities, re-extracted for {re_extracted} documents[/green]"
        )
        if wikify:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Rebuilding entity-match links...", total=None)
                total_entities, total_links, docs = entity_wikify_all(rebuild=True)
                progress.update(task, completed=True)
            console.print(
                f"[green]Created {total_links} entity-match links across {docs} documents[/green]"
            )
        return

    if all_docs:
        if wikify:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Extracting entities & linking...", total=None)
                total_entities, total_links, docs = entity_wikify_all(
                    rebuild=rebuild,
                )
                progress.update(task, completed=True)
            console.print(
                f"[green]Extracted {total_entities} entities, "
                f"created {total_links} links across {docs} documents[/green]"
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
            ) as progress:
                task = progress.add_task("Extracting entities...", total=None)
                for did in doc_ids_list:
                    total += extract_and_save_entities(did)
                progress.update(task, completed=True)
            console.print(
                f"[green]Extracted {total} entities from {len(doc_ids_list)} documents[/green]"
            )
        return

    if doc_id is None:
        console.print("[red]Error: provide a document ID or use --all[/red]")
        raise typer.Exit(1)

    if wikify:
        result = entity_match_wikify(doc_id)
        console.print(
            f"Extracted [cyan]{result.entities_extracted}[/cyan] entities from document #{doc_id}"
        )
        if result.links_created > 0:
            console.print(f"[green]Created {result.links_created} entity-match link(s)[/green]")
            for lid in result.linked_doc_ids:
                console.print(f"  [cyan]#{lid}[/cyan]")
        else:
            console.print("[dim]No new entity-match links created[/dim]")
    else:
        count = extract_and_save_entities(doc_id)
        console.print(f"Extracted [cyan]{count}[/cyan] entities from document #{doc_id}")


# ── Wiki commands ─────────────────────────────────────────────────────

wiki_app = typer.Typer(help="Auto-wiki generation from knowledge base")


@wiki_app.command(name="topics")
def wiki_topics(
    resolution: float = typer.Option(0.005, "--resolution", "-r", help="Clustering resolution"),
    save: bool = typer.Option(False, "--save", help="Save discovered topics to DB"),
    min_size: int = typer.Option(3, "--min-size", help="Minimum cluster size"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show extra columns (model override)"
    ),
) -> None:
    """Discover topic clusters using Leiden community detection.

    Examples:
        emdx maintain wiki topics              # Preview topics
        emdx maintain wiki topics --save       # Save to DB
        emdx maintain wiki topics -r 0.01      # Finer resolution
        emdx maintain wiki topics --verbose    # Show model overrides
    """
    from ..services.wiki_clustering_service import discover_topics, save_topics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Discovering topics...", total=None)
        result = discover_topics(resolution=resolution, min_cluster_size=min_size)
        progress.update(task, completed=True)

    console.print(
        f"\n[bold]Found {len(result.clusters)} topics[/bold] "
        f"covering {result.docs_clustered}/{result.total_docs} docs "
        f"({result.docs_unclustered} unclustered)"
    )

    from rich.table import Table

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
) -> None:
    """Generate wiki articles from topic clusters.

    Examples:
        emdx maintain wiki generate --dry-run        # Estimate costs
        emdx maintain wiki generate 5                # Generate for topic 5
        emdx maintain wiki generate --all -l 50      # Generate up to 50
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

    # Build topic list
    topic_list: list[int]
    if topic_id is not None:
        topic_list = [topic_id]
    else:
        topics_data = _get_topics()
        topic_list = [cast(int, t["id"]) for t in topics_data]

    # Create a run record
    run_model = model or "claude-sonnet-4-5-20250929"
    run_id = create_wiki_run(model=run_model, dry_run=dry_run)

    generated = 0
    skipped = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0
    topics_attempted = 0
    batch_start = _time.time()

    for i, tid in enumerate(topic_list):
        if generated >= limit:
            break

        topics_attempted += 1
        label = f"[{i + 1}/{len(topic_list)}]"
        console.print(f"  {label} topic {tid}...", end=" ")
        start = _time.time()

        result = generate_article(
            topic_id=tid,
            audience=audience,
            model=model,
            dry_run=dry_run,
        )
        elapsed = _time.time() - start

        if result.skipped:
            skipped += 1
            console.print(f"[dim]{result.skip_reason} ({elapsed:.1f}s)[/dim]")
        else:
            generated += 1
            console.print(
                f"[green]#{result.document_id}[/green] "
                f"'{result.topic_label[:40]}' "
                f"({result.input_tokens:,}+{result.output_tokens:,} tok, "
                f"${result.cost_usd:.4f}, {elapsed:.1f}s)"
            )
            if result.warnings:
                for w in result.warnings:
                    console.print(f"    [yellow]⚠ {w}[/yellow]")

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
    console.print(
        f"\n[bold]{action} {generated} article(s)[/bold] "
        f"(skipped {skipped}) in {total_elapsed:.1f}s\n"
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


def _format_ms(ms: int) -> str:
    """Format milliseconds into a human-readable string."""
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    return f"{ms}ms"


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
    import re

    from ..database import db

    def _slugify_label(label: str) -> str:
        slug = label.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s-]+", "-", slug)
        return slug[:80].strip("-")

    new_slug = _slugify_label(new_label)

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


app.add_typer(wiki_app, name="wiki", help="Auto-wiki generation")

# Register stale as a subcommand group of maintain
from emdx.commands.stale import app as stale_app  # noqa: E402

app.add_typer(stale_app, name="stale", help="Knowledge decay and staleness tracking")


if __name__ == "__main__":
    app()
