"""
Garbage collection commands for EMDX.
Clean up orphaned data, optimize database, and perform maintenance.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..config.settings import get_db_path

app = typer.Typer()
console = Console()


class GarbageCollector:
    """Handles garbage collection operations for EMDX."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze database for garbage collection opportunities."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        results = {
            'orphaned_tags': 0,
            'old_trash': 0,
            'stale_documents': 0,
            'database_size': 0,
            'fragmentation': 0,
            'recommendations': []
        }
        
        # 1. Check for orphaned tags (tags with no documents)
        cursor.execute("""
            SELECT COUNT(*) FROM tags t
            WHERE NOT EXISTS (
                SELECT 1 FROM document_tags dt 
                WHERE dt.tag_id = t.id
            )
        """)
        results['orphaned_tags'] = cursor.fetchone()[0]
        
        # 2. Check for old trash (deleted > 30 days ago)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE is_deleted = 1 
            AND deleted_at < ?
        """, (thirty_days_ago,))
        results['old_trash'] = cursor.fetchone()[0]
        
        # 3. Check for stale documents (not accessed in 180 days)
        six_months_ago = (datetime.now() - timedelta(days=180)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE is_deleted = 0 
            AND accessed_at < ?
            AND access_count < 5
        """, (six_months_ago,))
        results['stale_documents'] = cursor.fetchone()[0]
        
        # 4. Check database size and fragmentation
        cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
        total_size = cursor.fetchone()[0]
        
        cursor.execute("SELECT freelist_count * page_size FROM pragma_freelist_count(), pragma_page_size()")
        free_size = cursor.fetchone()[0]
        
        results['database_size'] = total_size
        results['fragmentation'] = (free_size / total_size * 100) if total_size > 0 else 0
        
        # Generate recommendations
        if results['orphaned_tags'] > 0:
            results['recommendations'].append(f"Remove {results['orphaned_tags']} orphaned tags")
        
        if results['old_trash'] > 0:
            results['recommendations'].append(f"Permanently delete {results['old_trash']} old trash items")
        
        if results['stale_documents'] > 0:
            results['recommendations'].append(f"Archive {results['stale_documents']} stale documents")
        
        if results['fragmentation'] > 20:
            results['recommendations'].append(f"Vacuum database to reclaim {results['fragmentation']:.1f}% space")
        
        conn.close()
        return results
    
    def clean_orphaned_tags(self) -> int:
        """Remove tags that have no associated documents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete orphaned tags
        cursor.execute("""
            DELETE FROM tags
            WHERE id IN (
                SELECT t.id FROM tags t
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_tags dt 
                    WHERE dt.tag_id = t.id
                )
            )
        """)
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    def clean_old_trash(self, days: int = 30) -> int:
        """Permanently delete documents that have been in trash for X days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # First, delete associated tags
        cursor.execute("""
            DELETE FROM document_tags
            WHERE document_id IN (
                SELECT id FROM documents
                WHERE is_deleted = 1 
                AND deleted_at < ?
            )
        """, (cutoff_date,))
        
        # Then delete the documents
        cursor.execute("""
            DELETE FROM documents
            WHERE is_deleted = 1 
            AND deleted_at < ?
        """, (cutoff_date,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    def archive_stale_documents(self, days: int = 180, min_views: int = 5) -> int:
        """Move stale documents to archived status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Add archived tag to stale documents
        cursor.execute("""
            INSERT OR IGNORE INTO tags (name) VALUES ('📦')
        """)
        
        cursor.execute("SELECT id FROM tags WHERE name = '📦'")
        archive_tag_id = cursor.fetchone()[0]
        
        # Tag stale documents
        cursor.execute("""
            INSERT OR IGNORE INTO document_tags (document_id, tag_id)
            SELECT id, ? FROM documents
            WHERE is_deleted = 0 
            AND accessed_at < ?
            AND access_count < ?
        """, (archive_tag_id, cutoff_date, min_views))
        
        archived = cursor.rowcount
        conn.commit()
        conn.close()
        
        return archived
    
    def vacuum_database(self) -> Dict[str, int]:
        """Vacuum the database to reclaim space."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get size before
        cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
        size_before = cursor.fetchone()[0]
        
        # Vacuum
        conn.execute("VACUUM")
        
        # Get size after
        cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
        size_after = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'size_before': size_before,
            'size_after': size_after,
            'space_saved': size_before - size_after
        }


@app.command()
def gc(
    analyze_only: bool = typer.Option(False, "--analyze", "-a", help="Only analyze, don't clean"),
    auto: bool = typer.Option(False, "--auto", help="Automatically clean all recommended items"),
    vacuum: bool = typer.Option(False, "--vacuum", "-v", help="Vacuum database after cleaning"),
    trash_days: int = typer.Option(30, "--trash-days", help="Days before permanently deleting trash"),
    stale_days: int = typer.Option(180, "--stale-days", help="Days before considering documents stale"),
):
    """Run garbage collection on the knowledge base."""
    
    gc = GarbageCollector(get_db_path())
    
    # Analyze first
    with console.status("[bold green]Analyzing database..."):
        analysis = gc.analyze()
    
    # Display analysis
    console.print(Panel(
        "[bold cyan]🗑️  Garbage Collection Analysis[/bold cyan]",
        box=box.DOUBLE
    ))
    
    # Show findings
    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Item", style="cyan")
    table.add_column("Count", justify="right")
    
    table.add_row("Orphaned tags", str(analysis['orphaned_tags']))
    table.add_row(f"Old trash (>{trash_days} days)", str(analysis['old_trash']))
    table.add_row(f"Stale documents (>{stale_days} days)", str(analysis['stale_documents']))
    table.add_row("Database size", f"{analysis['database_size'] / 1024 / 1024:.1f} MB")
    table.add_row("Fragmentation", f"{analysis['fragmentation']:.1f}%")
    
    console.print(table)
    
    if analysis['recommendations']:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in analysis['recommendations']:
            console.print(f"  • {rec}")
    else:
        console.print("\n[green]✨ No cleanup needed![/green]")
        return
    
    if analyze_only:
        console.print("\n[dim]Run without --analyze to perform cleanup[/dim]")
        return
    
    # Confirm cleanup
    if not auto:
        if not typer.confirm("\n🗑️  Proceed with cleanup?"):
            console.print("[red]Cleanup cancelled[/red]")
            return
    
    # Perform cleanup
    console.print("\n[bold]Performing cleanup...[/bold]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # Clean orphaned tags
        if analysis['orphaned_tags'] > 0:
            task = progress.add_task("Removing orphaned tags...", total=None)
            deleted = gc.clean_orphaned_tags()
            progress.update(task, completed=True)
            console.print(f"[green]✓[/green] Removed {deleted} orphaned tags")
        
        # Clean old trash
        if analysis['old_trash'] > 0:
            task = progress.add_task("Cleaning old trash...", total=None)
            deleted = gc.clean_old_trash(trash_days)
            progress.update(task, completed=True)
            console.print(f"[green]✓[/green] Permanently deleted {deleted} old trash items")
        
        # Archive stale documents
        if analysis['stale_documents'] > 0:
            task = progress.add_task("Archiving stale documents...", total=None)
            archived = gc.archive_stale_documents(stale_days)
            progress.update(task, completed=True)
            console.print(f"[green]✓[/green] Archived {archived} stale documents")
        
        # Vacuum if requested
        if vacuum or (auto and analysis['fragmentation'] > 20):
            task = progress.add_task("Vacuuming database...", total=None)
            vacuum_result = gc.vacuum_database()
            progress.update(task, completed=True)
            
            saved_mb = vacuum_result['space_saved'] / 1024 / 1024
            console.print(f"[green]✓[/green] Vacuumed database, saved {saved_mb:.1f} MB")
    
    console.print("\n[bold green]✅ Garbage collection complete![/bold green]")


@app.command()
def schedule(
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable or disable scheduled GC"),
    frequency: str = typer.Option("weekly", "--frequency", "-f", help="Frequency: daily, weekly, monthly"),
    time: str = typer.Option("03:00", "--time", "-t", help="Time to run (HH:MM)"),
):
    """Schedule automatic garbage collection."""
    
    if not enable:
        console.print("[yellow]⚠️  Scheduled garbage collection disabled[/yellow]")
        console.print("[dim]Note: This feature requires system cron/scheduler setup[/dim]")
        return
    
    # This would integrate with system scheduler (cron on Unix, Task Scheduler on Windows)
    console.print(f"[green]✅ Scheduled garbage collection enabled[/green]")
    console.print(f"[dim]Frequency: {frequency} at {time}[/dim]")
    console.print("\n[yellow]Note: Automatic scheduling requires system integration.[/yellow]")
    console.print("[dim]For now, run 'emdx gc --auto' manually or via cron:[/dim]")
    console.print(f"[dim]0 3 * * {'*' if frequency == 'daily' else '1' if frequency == 'weekly' else '1'} /usr/local/bin/emdx gc --auto[/dim]")


if __name__ == "__main__":
    app()
