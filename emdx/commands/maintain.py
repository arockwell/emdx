"""
Unified maintain command for EMDX.
Consolidates all modification and maintenance operations.
"""

import logging
import shutil
import sqlite3
import subprocess
import time

# Removed CommandDefinition import - using standard typer pattern
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer

if TYPE_CHECKING:
    import psutil
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from ..commands.gc import GarbageCollector
from ..config.settings import get_db_path
from ..models.tags import add_tags_to_document
from ..services.auto_tagger import AutoTagger
from ..services.document_merger import DocumentMerger
from ..services.duplicate_detector import DuplicateDetector
from ..services.health_monitor import HealthMonitor
from ..services.lifecycle_tracker import LifecycleTracker

logger = logging.getLogger(__name__)
console = Console()


def maintain(
    auto: bool = typer.Option(False, "--auto", "-a", help="Automatically fix all issues"),
    clean: bool = typer.Option(False, "--clean", "-c", help="Remove duplicates and empty documents"),
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge similar documents"),
    tags: bool = typer.Option(False, "--tags", "-t", help="Auto-tag untagged documents"),
    gc: bool = typer.Option(False, "--gc", "-g", help="Run garbage collection"),
    lifecycle: bool = typer.Option(False, "--lifecycle", "-l", help="Auto-transition stale gameplans"),
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute actions (default: dry run)"),
    threshold: float = typer.Option(0.7, "--threshold", help="Similarity threshold for merging"),
):
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
    if not any([auto, clean, merge, tags, gc, lifecycle]):
        _interactive_wizard(dry_run)
        return
    
    # If --auto is specified, enable everything
    if auto:
        clean = merge = tags = gc = lifecycle = True
    
    # Header
    console.print(Panel(
        "[bold cyan]🧹 Knowledge Base Maintenance[/bold cyan]",
        box=box.DOUBLE
    ))
    
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
    
    # Auto-transition lifecycle
    if lifecycle:
        console.print("[bold]Auto-transitioning gameplans...[/bold]")
        transitioned = _auto_transition_lifecycle(dry_run)
        if transitioned:
            actions_taken.append(transitioned)
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


def _interactive_wizard(dry_run: bool):
    """Run interactive maintenance wizard."""
    monitor = HealthMonitor()
    
    with console.status("[bold green]Analyzing knowledge base..."):
        metrics = monitor.calculate_overall_health()
    
    # Show current health
    overall_score = metrics["overall_score"] * 100
    health_color = (
        "green" if overall_score >= 80 else
        "yellow" if overall_score >= 60 else
        "red"
    )
    
    console.print(f"\n[bold]Current Health: [{health_color}]{overall_score:.0f}%[/{health_color}][/bold]")
    
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
    
    # Ask what to fix
    actions = []
    
    # Check for duplicates
    if "duplicate" in str(all_recommendations).lower():
        if Confirm.ask("Remove duplicate documents?"):
            actions.append("clean")
    
    # Check for tagging issues
    if "tag" in str(all_recommendations).lower():
        if Confirm.ask("Auto-tag untagged documents?"):
            actions.append("tags")
    
    # Check for similar documents
    detector = DuplicateDetector()
    merger = DocumentMerger()
    candidates = merger.find_merge_candidates(similarity_threshold=0.7)
    if candidates:
        console.print(f"\n[yellow]Found {len(candidates)} similar document pairs[/yellow]")
        if Confirm.ask("Merge similar documents?"):
            actions.append("merge")
    
    # Check for lifecycle issues
    tracker = LifecycleTracker()
    transitions = tracker.auto_detect_transitions()
    if transitions:
        console.print(f"\n[yellow]Found {len(transitions)} gameplans needing transitions[/yellow]")
        if Confirm.ask("Auto-transition stale gameplans?"):
            actions.append("lifecycle")
    
    # Check for garbage collection needs
    gc_analyzer = GarbageCollector(get_db_path())
    gc_analysis = gc_analyzer.analyze()
    if gc_analysis["recommendations"]:
        console.print(f"\n[yellow]Database needs cleanup[/yellow]")
        if Confirm.ask("Run garbage collection?"):
            actions.append("gc")
    
    if not actions:
        console.print("\n[yellow]No actions selected[/yellow]")
        return
    
    # Execute selected actions
    console.print(f"\n[bold]Executing maintenance...[/bold]\n")
    
    for action in actions:
        if action == "clean":
            _clean_documents(dry_run)
        elif action == "tags":
            _auto_tag_documents(dry_run)
        elif action == "merge":
            _merge_documents(dry_run)
        elif action == "lifecycle":
            _auto_transition_lifecycle(dry_run)
        elif action == "gc":
            _garbage_collect(dry_run)
        console.print()


def _clean_documents(dry_run: bool) -> Optional[str]:
    """Clean duplicates and empty documents."""
    detector = DuplicateDetector()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find duplicates
    duplicates = detector.find_duplicates()
    duplicate_count = sum(len(group) - 1 for group in duplicates) if duplicates else 0
    
    # Find empty documents
    cursor.execute("""
        SELECT COUNT(*) FROM documents
        WHERE is_deleted = 0 AND LENGTH(content) < 10
    """)
    empty_count = cursor.fetchone()[0]
    conn.close()
    
    if not duplicate_count and not empty_count:
        console.print("  ✨ No duplicates or empty documents found!")
        return None
    
    console.print(f"  Found: {duplicate_count} duplicates, {empty_count} empty documents")
    
    if dry_run:
        return f"Would remove {duplicate_count + empty_count} documents"
    
    # Remove duplicates
    if duplicate_count > 0:
        docs_to_delete = detector.get_documents_to_delete(duplicates, "highest-views")
        deleted_dupes = detector.delete_documents(docs_to_delete)
        console.print(f"  [green]✓[/green] Removed {deleted_dupes} duplicate documents")
    
    # Remove empty documents
    if empty_count > 0:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE documents 
            SET is_deleted = 1, deleted_at = ?
            WHERE is_deleted = 0 AND LENGTH(content) < 10
        """, (datetime.now().isoformat(),))
        conn.commit()
        conn.close()
        console.print(f"  [green]✓[/green] Removed {empty_count} empty documents")
    
    return f"Removed {duplicate_count + empty_count} documents"


def _auto_tag_documents(dry_run: bool) -> Optional[str]:
    """Auto-tag untagged documents."""
    tagger = AutoTagger()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find untagged documents
    cursor.execute("""
        SELECT d.id, d.title, d.content
        FROM documents d
        WHERE d.is_deleted = 0
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
        LIMIT 100
    """)
    
    untagged = cursor.fetchall()
    conn.close()
    
    if not untagged:
        console.print("  ✨ All documents are already tagged!")
        return None
    
    console.print(f"  Found: {len(untagged)} untagged documents")
    
    if dry_run:
        # Show preview
        console.print("\n  Preview of auto-tagging:")
        for doc in untagged[:3]:
            suggestions = tagger.analyze_document(doc['title'], doc['content'])
            if suggestions:
                tags = [tag for tag, conf in suggestions[:3] if conf > 0.5]
                if tags:
                    console.print(f"    • #{doc['id']}: '{doc['title']}' → {', '.join(tags)}")
        return f"Would auto-tag {len(untagged)} documents"
    
    # Actually tag documents
    tagged_count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Auto-tagging documents...", total=len(untagged))
        
        for doc in untagged:
            suggestions = tagger.analyze_document(doc['title'], doc['content'])
            if suggestions:
                tags = [tag for tag, conf in suggestions if conf > 0.6][:3]  # Top 3 confident tags
                if tags:
                    add_tags_to_document(doc['id'], tags)
                    tagged_count += 1
            progress.update(task, advance=1)
    
    console.print(f"  [green]✓[/green] Auto-tagged {tagged_count} documents")
    return f"Auto-tagged {tagged_count} documents"


def _merge_documents(dry_run: bool, threshold: float = 0.7) -> Optional[str]:
    """Merge similar documents."""
    merger = DocumentMerger()
    
    # Find merge candidates
    candidates = merger.find_merge_candidates(similarity_threshold=threshold)
    
    if not candidates:
        console.print("  ✨ No similar documents found!")
        return None
    
    console.print(f"  Found: {len(candidates)} merge candidates")
    
    if dry_run:
        # Show preview
        console.print("\n  Top merge candidates:")
        for i, candidate in enumerate(candidates[:3], 1):
            console.print(f"    [{i}] '{candidate.doc1['title']}' ↔ '{candidate.doc2['title']}' "
                         f"({candidate.similarity:.0%} similar)")
        return f"Would merge {len(candidates)} document pairs"
    
    # Actually merge documents
    merged_count = 0
    for candidate in candidates:
        try:
            # Keep the document with more views
            if candidate.doc1['access_count'] >= candidate.doc2['access_count']:
                keep, remove = candidate.doc1, candidate.doc2
            else:
                keep, remove = candidate.doc2, candidate.doc1
            
            # Merge content
            merged_content = merger._merge_content(keep['content'], remove['content'])
            
            # Update the kept document
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE documents 
                SET content = ?, updated_at = ?
                WHERE id = ?
            """, (merged_content, datetime.now().isoformat(), keep['id']))
            
            # Delete the other document
            cursor.execute("""
                UPDATE documents 
                SET is_deleted = 1, deleted_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), remove['id']))
            
            conn.commit()
            conn.close()
            merged_count += 1
        except Exception:
            continue
    
    console.print(f"  [green]✓[/green] Merged {merged_count} document pairs")
    return f"Merged {merged_count} document pairs"


def _garbage_collect(dry_run: bool) -> Optional[str]:
    """Run garbage collection."""
    gc = GarbageCollector(get_db_path())
    
    # Analyze first
    analysis = gc.analyze()
    
    if not analysis['recommendations']:
        console.print("  ✨ No garbage collection needed!")
        return None
    
    console.print(f"  Found: {analysis['orphaned_tags']} orphaned tags, "
                 f"{analysis['old_trash']} old trash items")
    
    if dry_run:
        return f"Would clean {analysis['orphaned_tags'] + analysis['old_trash']} items"
    
    # Clean orphaned tags
    if analysis['orphaned_tags'] > 0:
        deleted_tags = gc.clean_orphaned_tags()
        console.print(f"  [green]✓[/green] Removed {deleted_tags} orphaned tags")
    
    # Clean old trash
    if analysis['old_trash'] > 0:
        deleted_trash = gc.clean_old_trash()
        console.print(f"  [green]✓[/green] Permanently deleted {deleted_trash} old trash items")
    
    # Vacuum if needed
    if analysis['fragmentation'] > 20:
        vacuum_result = gc.vacuum_database()
        saved_mb = vacuum_result['space_saved'] / 1024 / 1024
        console.print(f"  [green]✓[/green] Vacuumed database, saved {saved_mb:.1f} MB")
    
    return f"Cleaned {analysis['orphaned_tags'] + analysis['old_trash']} items"


def _auto_transition_lifecycle(dry_run: bool) -> Optional[str]:
    """Auto-transition stale gameplans."""
    tracker = LifecycleTracker()
    
    # Find transition suggestions
    suggestions = tracker.auto_detect_transitions()
    
    if not suggestions:
        console.print("  ✨ All gameplans are in appropriate stages!")
        return None
    
    console.print(f"  Found: {len(suggestions)} gameplans needing transitions")
    
    if dry_run:
        # Show preview
        console.print("\n  Suggested transitions:")
        for s in suggestions[:3]:
            console.print(f"    • '{s['title']}': {s['current_stage']} → {s['suggested_stage']} "
                         f"({s['reason']})")
        return f"Would transition {len(suggestions)} gameplans"
    
    # Apply transitions
    success_count = 0
    for s in suggestions:
        if tracker.transition_document(
            s['doc_id'], 
            s['suggested_stage'], 
            f"Auto-detected: {s['reason']}"
        ):
            success_count += 1
    
    console.print(f"  [green]✓[/green] Transitioned {success_count} gameplans")
    return f"Transitioned {success_count} gameplans"


def cleanup_main(
    branches: bool = typer.Option(False, "--branches", "-b", help="Clean up old execution branches"),
    processes: bool = typer.Option(False, "--processes", "-p", help="Clean up zombie processes"),
    executions: bool = typer.Option(False, "--executions", "-e", help="Clean up stuck executions"),
    all: bool = typer.Option(False, "--all", "-a", help="Clean up everything"),
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute actions (default: dry run)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete unmerged branches"),
    age_days: int = typer.Option(7, "--age", help="Only clean branches older than N days"),
    max_runtime: int = typer.Option(2, "--max-runtime", help="Max process runtime in hours before considering stuck"),
    timeout_minutes: int = typer.Option(30, "--timeout", help="Minutes after which to consider execution stale"),
):
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
    
    console.print(Panel(
        "[bold cyan]🧹 EMDX Execution Cleanup[/bold cyan]",
        box=box.DOUBLE
    ))
    
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


def _cleanup_branches(dry_run: bool, force: bool = False, older_than_days: int = 7) -> Optional[str]:
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
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = current_result.stdout.strip()
        
        # List all branches
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Find exec-* branches
        exec_branches = []
        for line in result.stdout.strip().split('\n'):
            branch = line.strip().lstrip('* ')
            # Skip remote branches and current branch
            if branch.startswith('remotes/') or branch == current_branch:
                continue
            if branch.startswith('exec-'):
                exec_branches.append(branch)
        
        if not exec_branches:
            console.print("  ✨ No execution branches found!")
            return None
        
        # Get main/master branch name
        main_branch = "main"
        main_check = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/main"])
        if main_check.returncode != 0:
            # Try master
            master_check = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/master"])
            if master_check.returncode == 0:
                main_branch = "master"
        
        # Check which branches are merged and their age
        branches_to_delete = []
        unmerged_branches = []
        
        for branch in exec_branches:
            # Get branch age
            age_cmd = subprocess.run(
                ["git", "log", "-1", "--format=%ct", branch],
                capture_output=True,
                text=True
            )
            
            if age_cmd.returncode == 0:
                branch_timestamp = int(age_cmd.stdout.strip())
                branch_age_days = (time.time() - branch_timestamp) / (24 * 60 * 60)
                
                # Skip branches that are too new
                if branch_age_days < older_than_days:
                    continue
            
            # Check if branch is merged
            merge_check = subprocess.run(
                ["git", "branch", "--merged", main_branch],
                capture_output=True,
                text=True
            )
            
            is_merged = branch in merge_check.stdout
            
            if is_merged:
                branches_to_delete.append((branch, "merged", int(branch_age_days)))
            elif force:
                # For unmerged branches, check if they have any unique commits
                unique_commits = subprocess.run(
                    ["git", "rev-list", f"{main_branch}..{branch}"],
                    capture_output=True,
                    text=True
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
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Deleting branches...", total=len(branches_to_delete))
            
            for branch, reason, age in branches_to_delete:
                try:
                    # Use -D for force delete if needed
                    delete_flag = "-D" if force and reason != "merged" else "-d"
                    subprocess.run(
                        ["git", "branch", delete_flag, branch],
                        capture_output=True,
                        check=True
                    )
                    deleted += 1
                except subprocess.CalledProcessError:
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


def _cleanup_processes(dry_run: bool, max_runtime_hours: int = 2) -> Optional[str]:
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
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status', 'create_time']):
        try:
            # Check if it's EMDX-related
            cmdline = proc.info.get('cmdline', []) or []
            cmdline_str = ' '.join(cmdline)
            
            # Look for EMDX execution processes
            patterns = ['emdx exec', 'claude_wrapper.py', 'emdx-exec', 'claude --print']
            if not any(pattern in cmdline_str for pattern in patterns):
                continue
            
            # Get process info
            pid = proc.info['pid']
            status = proc.info.get('status', '')
            
            # Check if it's a zombie
            if status == psutil.STATUS_ZOMBIE or status == 'zombie':
                zombie_procs.append((proc, 'zombie'))
                continue
            
            # Check runtime
            try:
                create_time = proc.info['create_time']
                runtime_hours = (time.time() - create_time) / 3600
                
                # Check if process is stuck (running too long)
                if runtime_hours > max_runtime_hours:
                    stuck_procs.append((proc, f'{runtime_hours:.1f}h runtime'))
                    continue
                
                # Check if process is orphaned (not in database)
                if pid not in known_pids and 'claude' in cmdline_str:
                    orphaned_procs.append((proc, f'orphaned, {runtime_hours:.1f}h old'))
                    
            except Exception:
                pass
                
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
                    cmd_display = ' '.join(cmdline[:3]) + '...'
                else:
                    cmd_display = ' '.join(cmdline)
                
                # Get memory usage
                try:
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    mem_str = f", {mem_mb:.0f}MB"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    mem_str = ""

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
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Terminating processes...", total=len(all_procs))
        
        for proc, reason in all_procs:
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
                # Process already gone
                terminated += 1
            except Exception:
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


def _cleanup_executions(dry_run: bool, timeout_minutes: int = 30, check_heartbeat: bool = True) -> Optional[str]:
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
        
        if health['is_zombie'] or (health['process_exists'] == False and exec.pid):
            dead_process.append((exec, health['reason']))
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
        console.print(f"\n  [yellow]Found {len(long_running)} long-running executions (may be normal):[/yellow]")
    
    if dry_run:
        # Show details
        if all_stuck:
            console.print("\n  Executions to mark as failed:")
            for exec, reason in all_stuck[:10]:
                age_minutes = int((datetime.now(timezone.utc) - exec.started_at).total_seconds() / 60)
                console.print(f"    • #{exec.id}: {exec.doc_title[:30]}... ({reason}, {age_minutes}m old)")
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
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
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
                    exit_code = -1   # unknown error
                else:
                    exit_code = 1    # general error
                
                update_execution_status(exec.id, "failed", exit_code)
                updated += 1
            except Exception as e:
                failed_updates += 1
                
            progress.update(task, advance=1)
    
    # Report results
    if updated > 0:
        console.print(f"  [green]✓[/green] Marked {updated} executions as failed")
    if failed_updates > 0:
        console.print(f"  [yellow]⚠[/yellow] Failed to update {failed_updates} executions")
    
    # Also report on long-running for awareness
    if long_running:
        console.print(f"  [dim]Note: {len(long_running)} long-running executions left untouched[/dim]")
    
    return f"Marked {updated} executions as failed" if updated > 0 else None


def cleanup_temp_dirs(
    dry_run: bool = typer.Option(True, "--execute/--dry-run", help="Execute actions (default: dry run)"),
    age_hours: int = typer.Option(24, "--age", help="Clean directories older than N hours"),
):
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
    
    console.print(Panel(
        "[bold cyan]🗑️ Cleaning Temporary Execution Directories[/bold cyan]",
        box=box.DOUBLE
    ))
    
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
                size = sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())
                total_size += size
        except OSError as e:
            logger.warning(f"Could not scan directory {dir_path}: {e}")
    
    if not old_dirs:
        console.print(f"[green]✨ No directories older than {age_hours} hours![/green]")
        return
    
    # Sort by age
    old_dirs.sort(key=lambda x: x[1])
    
    console.print(f"Found [yellow]{len(old_dirs)}[/yellow] directories older than {age_hours} hours")
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
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Removing directories...", total=len(old_dirs))
        
        failed = 0
        for dir_path, _ in old_dirs:
            try:
                # Calculate size before removal
                size = sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())
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
app = typer.Typer()
app.command()(maintain)
app.command(name="cleanup")(cleanup_main)
app.command(name="cleanup-dirs")(cleanup_temp_dirs)


if __name__ == "__main__":
    app()
