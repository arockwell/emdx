"""
GitHub Gist integration for emdx
"""

import os
import typer
from typing import Optional
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from github import Github, GithubException

from emdx.database import db
from emdx.utils import get_git_project

app = typer.Typer()
console = Console()


def get_github_client() -> Github:
    """Get authenticated GitHub client"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        console.print("[red]Error: GITHUB_TOKEN environment variable not set[/red]")
        console.print("\n[yellow]To use GitHub gist features, you need to set a GitHub personal access token:[/yellow]")
        console.print("1. Go to https://github.com/settings/tokens")
        console.print("2. Create a new token with 'gist' scope")
        console.print("3. Set the token: export GITHUB_TOKEN='your-token-here'")
        console.print("   Or add it to ~/.config/emdx/.env")
        raise typer.Exit(1)
    
    try:
        return Github(token)
    except Exception as e:
        console.print(f"[red]Error connecting to GitHub: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def create(
    identifier: str = typer.Argument(..., help="Document ID or title to create gist from"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Gist description"),
    public: bool = typer.Option(False, "--public", "-p", help="Make gist public (default: private)"),
    filename: Optional[str] = typer.Option(None, "--filename", "-f", help="Filename for the gist (default: title.md)"),
):
    """Create a GitHub gist from a document"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get the document
        doc = db.get_document(identifier)
        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)
        
        # Get GitHub client
        g = get_github_client()
        user = g.get_user()
        
        # Prepare gist data
        if not filename:
            # Clean title for filename
            filename = f"{doc['title'].replace(' ', '_').replace('/', '-')}.md"
        
        if not description:
            description = f"emdx: {doc['title']}"
            if doc['project']:
                description += f" (Project: {doc['project']})"
        
        # Create the gist
        console.print(f"[yellow]Creating gist from document #{doc['id']}: {doc['title']}...[/yellow]")
        
        try:
            gist = user.create_gist(
                public=public,
                files={filename: {"content": doc['content']}},
                description=description
            )
            
            # Save gist mapping to database
            save_gist_mapping(doc['id'], gist.id, gist.html_url)
            
            console.print(f"[green]✅ Created gist successfully![/green]")
            console.print(f"[cyan]Gist URL:[/cyan] {gist.html_url}")
            console.print(f"[cyan]Gist ID:[/cyan] {gist.id}")
            
            if public:
                console.print("[yellow]Note: This gist is public and visible to everyone[/yellow]")
            else:
                console.print("[dim]This gist is private (only visible to you)[/dim]")
                
        except GithubException as e:
            console.print(f"[red]GitHub API error: {e}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error creating gist: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def update(
    identifier: str = typer.Argument(..., help="Document ID or title to update gist from"),
    gist_id: Optional[str] = typer.Option(None, "--gist-id", "-g", help="Specific gist ID to update"),
):
    """Update an existing gist with latest document content"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get the document
        doc = db.get_document(identifier)
        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)
        
        # Get gist mapping if not provided
        if not gist_id:
            mapping = get_gist_mapping(doc['id'])
            if not mapping:
                console.print(f"[red]Error: No gist found for document #{doc['id']}[/red]")
                console.print("[yellow]Tip: Use 'emdx gist create' to create a new gist[/yellow]")
                raise typer.Exit(1)
            gist_id = mapping['gist_id']
        
        # Get GitHub client and gist
        g = get_github_client()
        
        try:
            gist = g.get_gist(gist_id)
            
            # Update the gist
            console.print(f"[yellow]Updating gist {gist_id}...[/yellow]")
            
            # Get the first file in the gist (we'll update it)
            filename = list(gist.files.keys())[0] if gist.files else f"{doc['title'].replace(' ', '_')}.md"
            
            gist.edit(
                files={filename: {"content": doc['content']}}
            )
            
            # Update sync timestamp
            update_gist_sync_time(doc['id'], gist_id)
            
            console.print(f"[green]✅ Updated gist successfully![/green]")
            console.print(f"[cyan]Gist URL:[/cyan] {gist.html_url}")
            
        except GithubException as e:
            if e.status == 404:
                console.print(f"[red]Error: Gist {gist_id} not found or not accessible[/red]")
            else:
                console.print(f"[red]GitHub API error: {e}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error updating gist: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def sync(
    identifier: str = typer.Argument(..., help="Document ID or title to sync"),
    direction: str = typer.Option("push", "--direction", "-d", help="Sync direction: 'push' or 'pull'"),
):
    """Sync document with its gist (push local changes or pull remote changes)"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get the document
        doc = db.get_document(identifier)
        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)
        
        # Get gist mapping
        mapping = get_gist_mapping(doc['id'])
        if not mapping:
            console.print(f"[red]Error: No gist found for document #{doc['id']}[/red]")
            console.print("[yellow]Tip: Use 'emdx gist create' to create a new gist[/yellow]")
            raise typer.Exit(1)
        
        # Get GitHub client and gist
        g = get_github_client()
        
        try:
            gist = g.get_gist(mapping['gist_id'])
            
            if direction == "push":
                # Push local changes to gist
                console.print(f"[yellow]Pushing local changes to gist {mapping['gist_id']}...[/yellow]")
                
                filename = list(gist.files.keys())[0] if gist.files else f"{doc['title'].replace(' ', '_')}.md"
                gist.edit(files={filename: {"content": doc['content']}})
                
                update_gist_sync_time(doc['id'], mapping['gist_id'])
                console.print(f"[green]✅ Pushed changes to gist successfully![/green]")
                
            elif direction == "pull":
                # Pull remote changes from gist
                console.print(f"[yellow]Pulling changes from gist {mapping['gist_id']}...[/yellow]")
                
                # Get gist content
                if not gist.files:
                    console.print("[red]Error: Gist has no files[/red]")
                    raise typer.Exit(1)
                
                # Get the first file content
                filename = list(gist.files.keys())[0]
                content = gist.files[filename].content
                
                # Show what will be updated
                console.print(f"\n[bold]Document:[/bold] #{doc['id']} - {doc['title']}")
                console.print(f"[bold]Gist file:[/bold] {filename}")
                console.print(f"[bold]Last synced:[/bold] {mapping['synced_at'] or 'Never'}")
                
                if Confirm.ask("\nDo you want to overwrite the local document with gist content?"):
                    # Update document
                    db.update_document(doc['id'], doc['title'], content)
                    update_gist_sync_time(doc['id'], mapping['gist_id'])
                    console.print(f"[green]✅ Pulled changes from gist successfully![/green]")
                else:
                    console.print("[yellow]Sync cancelled[/yellow]")
            else:
                console.print(f"[red]Error: Invalid direction '{direction}'. Use 'push' or 'pull'[/red]")
                raise typer.Exit(1)
                
        except GithubException as e:
            console.print(f"[red]GitHub API error: {e}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error syncing gist: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="import")
def import_gist(
    gist_id: str = typer.Argument(..., help="GitHub gist ID or URL to import"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Document title (default: gist description or filename)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name (auto-detected from git)"),
):
    """Import a GitHub gist into the knowledge base"""
    try:
        # Extract gist ID from URL if provided
        if "/" in gist_id:
            # It's likely a URL, extract the ID
            gist_id = gist_id.rstrip("/").split("/")[-1]
        
        # Get GitHub client
        g = get_github_client()
        
        console.print(f"[yellow]Fetching gist {gist_id}...[/yellow]")
        
        try:
            gist = g.get_gist(gist_id)
            
            # Get content from the first file
            if not gist.files:
                console.print("[red]Error: Gist has no files[/red]")
                raise typer.Exit(1)
            
            # Use the first file
            filename = list(gist.files.keys())[0]
            content = gist.files[filename].content
            
            # Determine title
            if not title:
                if gist.description:
                    title = gist.description
                else:
                    # Use filename without extension as title
                    title = Path(filename).stem
            
            # Auto-detect project from git if not provided
            if not project:
                project = get_git_project()
            
            # Add gist metadata to content
            metadata = f"\n\n---\n*Imported from gist: {gist.html_url}*\n*Original filename: {filename}*"
            full_content = content + metadata
            
            # Save to database
            db.ensure_schema()
            doc_id = db.save_document(title, full_content, project)
            
            # Save gist mapping
            save_gist_mapping(doc_id, gist.id, gist.html_url)
            
            console.print(f"[green]✅ Imported gist as #{doc_id}:[/green] [cyan]{title}[/cyan]")
            if project:
                console.print(f"   [dim]Project:[/dim] {project}")
            console.print(f"   [dim]Gist:[/dim] {gist.html_url}")
            
        except GithubException as e:
            if e.status == 404:
                console.print(f"[red]Error: Gist {gist_id} not found or not accessible[/red]")
                console.print("[yellow]Note: Private gists require authentication[/yellow]")
            else:
                console.print(f"[red]GitHub API error: {e}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error importing gist: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of gist mappings to show"),
):
    """List documents that have associated gists"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        ensure_gist_table()
        
        # Get gist mappings
        mappings = get_all_gist_mappings(limit)
        
        if not mappings:
            console.print("[yellow]No documents with gists found[/yellow]")
            console.print("[dim]Tip: Use 'emdx gist create <doc-id>' to create a gist from a document[/dim]")
            return
        
        console.print(f"\n[bold]📄 Documents with GitHub Gists[/bold]\n")
        
        for mapping in mappings:
            # Get document info
            doc = db.get_document(str(mapping['document_id']))
            if doc:
                console.print(f"[bold cyan]#{doc['id']}[/bold cyan] [bold]{doc['title']}[/bold]")
                console.print(f"   [green]Gist:[/green] {mapping['gist_url']}")
                console.print(f"   [yellow]Gist ID:[/yellow] {mapping['gist_id']}")
                if mapping['synced_at']:
                    console.print(f"   [dim]Last synced:[/dim] {mapping['synced_at'].strftime('%Y-%m-%d %H:%M')}")
                else:
                    console.print(f"   [dim]Last synced:[/dim] Never")
                console.print()
        
    except Exception as e:
        console.print(f"[red]Error listing gist mappings: {e}[/red]")
        raise typer.Exit(1)


# Database helper functions

def ensure_gist_table():
    """Ensure the gist_mappings table exists"""
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gist_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                gist_id TEXT NOT NULL,
                gist_url TEXT NOT NULL,
                synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, gist_id)
            )
        """)
        conn.commit()


def save_gist_mapping(document_id: int, gist_id: str, gist_url: str):
    """Save a document-to-gist mapping"""
    ensure_gist_table()
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO gist_mappings (document_id, gist_id, gist_url, synced_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (document_id, gist_id, gist_url))
        conn.commit()


def get_gist_mapping(document_id: int) -> Optional[dict]:
    """Get gist mapping for a document"""
    ensure_gist_table()
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM gist_mappings WHERE document_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (document_id,))
        row = cursor.fetchone()
        if row:
            mapping = dict(row)
            if mapping['synced_at'] and isinstance(mapping['synced_at'], str):
                mapping['synced_at'] = datetime.fromisoformat(mapping['synced_at'])
            return mapping
        return None


def update_gist_sync_time(document_id: int, gist_id: str):
    """Update the sync timestamp for a gist mapping"""
    with db.get_connection() as conn:
        conn.execute("""
            UPDATE gist_mappings 
            SET synced_at = CURRENT_TIMESTAMP
            WHERE document_id = ? AND gist_id = ?
        """, (document_id, gist_id))
        conn.commit()


def get_all_gist_mappings(limit: int = 10) -> list:
    """Get all gist mappings"""
    ensure_gist_table()
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM gist_mappings 
            ORDER BY synced_at DESC 
            LIMIT ?
        """, (limit,))
        mappings = []
        for row in cursor.fetchall():
            mapping = dict(row)
            if mapping['synced_at'] and isinstance(mapping['synced_at'], str):
                mapping['synced_at'] = datetime.fromisoformat(mapping['synced_at'])
            mappings.append(mapping)
        return mappings