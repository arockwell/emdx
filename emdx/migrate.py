"""
Migration tool to move data from PostgreSQL to SQLite
"""

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from typing import Optional
import sys

app = typer.Typer()
console = Console()


@app.command()
def migrate(
    postgres_url: Optional[str] = typer.Option(None, "--postgres-url", "-p", help="PostgreSQL connection URL"),
    sqlite_path: Optional[str] = typer.Option(None, "--sqlite-path", "-s", help="SQLite database path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be migrated without doing it"),
):
    """Migrate documents from PostgreSQL to SQLite"""
    
    # Import both database types
    try:
        from .database_postgres import PostgresDatabase
        from .sqlite_database import SQLiteDatabase
    except ImportError as e:
        console.print(f"[red]Error importing database modules: {e}[/red]")
        console.print("[yellow]Make sure you have psycopg installed for migration:[/yellow]")
        console.print("  pip install psycopg[binary]")
        raise typer.Exit(1)
    
    # Initialize databases
    console.print("[bold]🚀 emdx PostgreSQL → SQLite Migration[/bold]\n")
    
    # Set up PostgreSQL connection
    if postgres_url:
        console.print(f"[blue]Using provided PostgreSQL URL[/blue]")
        pg_db = PostgresDatabase(postgres_url)
    else:
        console.print("[blue]Using PostgreSQL configuration from environment[/blue]")
        pg_db = PostgresDatabase()
    
    # Set up SQLite connection
    if sqlite_path:
        from pathlib import Path
        sqlite_db = SQLiteDatabase(Path(sqlite_path))
        console.print(f"[blue]Using SQLite database at: {sqlite_path}[/blue]")
    else:
        sqlite_db = SQLiteDatabase()
        console.print(f"[blue]Using default SQLite database at: {sqlite_db.db_path}[/blue]")
    
    try:
        # Test PostgreSQL connection and get document count
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Connecting to PostgreSQL...", total=None)
            
            pg_db.ensure_schema()
            all_docs = pg_db.list_documents(limit=10000)  # Get all documents
            
            progress.update(task, completed=True)
        
        if not all_docs:
            console.print("[yellow]No documents found in PostgreSQL database[/yellow]")
            raise typer.Exit(0)
        
        console.print(f"\n[green]Found {len(all_docs)} documents to migrate[/green]")
        
        if dry_run:
            # Show summary table
            table = Table(title="Documents to Migrate (first 10)")
            table.add_column("ID", style="cyan")
            table.add_column("Title", style="magenta")
            table.add_column("Project", style="green")
            table.add_column("Created", style="yellow")
            
            for doc in all_docs[:10]:
                table.add_row(
                    str(doc['id']),
                    doc['title'][:40] + "..." if len(doc['title']) > 40 else doc['title'],
                    doc['project'] or "None",
                    doc['created_at'].strftime('%Y-%m-%d')
                )
            
            console.print(table)
            
            if len(all_docs) > 10:
                console.print(f"\n[dim]... and {len(all_docs) - 10} more documents[/dim]")
            
            console.print("\n[yellow]Dry run mode - no changes made[/yellow]")
            raise typer.Exit(0)
        
        # Confirm migration
        if not typer.confirm(f"\nMigrate {len(all_docs)} documents from PostgreSQL to SQLite?"):
            console.print("[red]Migration cancelled[/red]")
            raise typer.Exit(0)
        
        # Initialize SQLite database
        console.print("\n[blue]Initializing SQLite database...[/blue]")
        sqlite_db.ensure_schema()
        
        # Migrate documents
        migrated = 0
        failed = 0
        
        with Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            "[green]{task.completed}/{task.total}[/green]",
            console=console,
        ) as progress:
            task = progress.add_task("Migrating documents...", total=len(all_docs))
            
            for doc_summary in all_docs:
                try:
                    # Fetch full document from PostgreSQL
                    full_doc = pg_db.get_document(str(doc_summary['id']))
                    
                    if full_doc:
                        # Save to SQLite
                        sqlite_db.save_document(
                            title=full_doc['title'],
                            content=full_doc['content'],
                            project=full_doc['project']
                        )
                        migrated += 1
                    else:
                        console.print(f"[red]Failed to fetch document {doc_summary['id']}[/red]")
                        failed += 1
                    
                except Exception as e:
                    console.print(f"[red]Error migrating document {doc_summary['id']}: {e}[/red]")
                    failed += 1
                
                progress.update(task, advance=1)
        
        # Show results
        console.print(f"\n[green]✅ Migration complete![/green]")
        console.print(f"   [green]Successfully migrated: {migrated} documents[/green]")
        if failed > 0:
            console.print(f"   [red]Failed: {failed} documents[/red]")
        
        # Verify migration
        console.print("\n[blue]Verifying migration...[/blue]")
        sqlite_count = len(sqlite_db.list_documents(limit=10000))
        console.print(f"   PostgreSQL documents: {len(all_docs)}")
        console.print(f"   SQLite documents: {sqlite_count}")
        
        if sqlite_count == migrated:
            console.print("\n[green]✨ Migration verified successfully![/green]")
            console.print(f"\nYour knowledge base is now at: [cyan]{sqlite_db.db_path}[/cyan]")
            console.print("\nYou can now use emdx without PostgreSQL! 🎉")
        else:
            console.print("\n[yellow]⚠️  Document counts don't match. Please verify manually.[/yellow]")
        
    except Exception as e:
        console.print(f"\n[red]Migration failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()