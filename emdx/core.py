"""
Core CRUD operations for emdx
"""

import typer
from typing import Optional, List
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown

from emdx.database import db
from emdx.utils import get_git_project

app = typer.Typer()
console = Console()


@app.command()
def save(
    file: Path = typer.Argument(..., help="Markdown file to save"),
    title: Optional[str] = typer.Argument(None, help="Document title (defaults to filename)"),
    project: Optional[str] = typer.Argument(None, help="Project name (auto-detected from git)"),
):
    """Save a markdown file to the knowledge base"""
    # Check if file exists
    if not file.exists():
        console.print(f"[red]Error: File '{file}' not found[/red]")
        raise typer.Exit(1)
    
    # Read file content
    try:
        content = file.read_text(encoding='utf-8')
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        raise typer.Exit(1)
    
    # Use filename as title if not provided
    if not title:
        title = file.stem  # filename without extension
    
    # Auto-detect project from git if not provided
    if not project:
        detected_project = get_git_project(file.parent)
        if detected_project:
            project = detected_project
    
    # Ensure database schema exists
    try:
        db.ensure_schema()
    except Exception as e:
        console.print(f"[red]Database error: {e}[/red]")
        raise typer.Exit(1)
    
    # Save to database
    try:
        doc_id = db.save_document(title, content, project)
        console.print(f"[green]✅ Saved as #{doc_id}:[/green] [cyan]{title}[/cyan]")
        if project:
            console.print(f"   [dim]Project:[/dim] {project}")
    except Exception as e:
        console.print(f"[red]Error saving document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def find(
    query: List[str] = typer.Argument(..., help="Search terms"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    snippets: bool = typer.Option(False, "--snippets", "-s", help="Show content snippets"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Use fuzzy search"),
):
    """Search the knowledge base with full-text search"""
    search_query = " ".join(query)
    
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Search database
        results = db.search_documents(search_query, project=project, limit=limit, fuzzy=fuzzy)
        
        if not results:
            console.print(f"[yellow]No results found for '[/yellow]{search_query}[yellow]'[/yellow]")
            return
        
        # Display results
        console.print(f"\n[bold]🔍 Found {len(results)} results for '[cyan]{search_query}[/cyan]'[/bold]\n")
        
        for i, result in enumerate(results, 1):
            # Display result header
            console.print(f"[bold cyan]#{result['id']}[/bold cyan] [bold]{result['title']}[/bold]")
            
            # Display metadata
            metadata = []
            if result['project']:
                metadata.append(f"[green]{result['project']}[/green]")
            metadata.append(f"[yellow]{result['created_at'].strftime('%Y-%m-%d')}[/yellow]")
            
            if 'rank' in result:
                metadata.append(f"[dim]relevance: {result['rank']:.3f}[/dim]")
            elif 'score' in result:
                metadata.append(f"[dim]similarity: {result['score']:.3f}[/dim]")
            
            console.print(" • ".join(metadata))
            
            # Display snippet if requested
            if snippets and 'snippet' in result:
                # Clean up the snippet (remove HTML tags from highlighting)
                snippet = result['snippet'].replace('<b>', '[bold yellow]').replace('</b>', '[/bold yellow]')
                console.print(f"[dim]...{snippet}...[/dim]")
            
            # Add spacing between results
            if i < len(results):
                console.print()
        
        # Show tip for viewing documents
        if len(results) > 0:
            console.print(f"\n[dim]💡 Use 'emdx view <id>' to view a document[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error searching documents: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def view(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Show raw markdown without formatting"),
):
    """View a document from the knowledge base"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Fetch document
        doc = db.get_document(identifier)
        
        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)
        
        # Check if we should use mdcat
        import subprocess
        import tempfile
        import os
        
        use_mdcat = False
        if not raw:
            try:
                result = subprocess.run(['which', 'mdcat'], capture_output=True)
                use_mdcat = result.returncode == 0
            except:
                pass
        
        if use_mdcat:
            # Create full markdown document with header
            full_content = f"""# {doc['title']}

**Document ID:** #{doc['id']}  
**Project:** {doc['project'] or 'None'}  
**Created:** {doc['created_at'].strftime('%Y-%m-%d %H:%M')}  
**Views:** {doc['access_count']}

---

{doc['content']}"""
            
            # Use mdcat with pager
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(full_content)
                temp_path = f.name
            
            try:
                # Run mdcat with automatic pager detection
                subprocess.run(['mdcat', '--paginate', temp_path])
            finally:
                os.unlink(temp_path)
        else:
            # Fall back to Rich rendering
            # Display document header
            console.print(f"\n[bold cyan]#{doc['id']}:[/bold cyan] [bold]{doc['title']}[/bold]")
            console.print("=" * 60)
            
            # Display metadata
            console.print(f"[dim]Project:[/dim] {doc['project'] or 'None'}")
            console.print(f"[dim]Created:[/dim] {doc['created_at'].strftime('%Y-%m-%d %H:%M')}")
            console.print(f"[dim]Views:[/dim] {doc['access_count']}")
            console.print("=" * 60 + "\n")
            
            # Display content
            if raw:
                console.print(doc['content'])
            else:
                markdown = Markdown(doc['content'])
                console.print(markdown)
        
    except Exception as e:
        console.print(f"[red]Error viewing document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def edit(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor to use"),
):
    """Edit a document in the knowledge base"""
    # TODO: Lookup document
    # TODO: Create temp file with content
    # TODO: Open in editor (use $EDITOR if not specified)
    # TODO: Save changes back to database
    # TODO: Update search vector
    
    typer.echo(f"📝 Editing document: {identifier}")


@app.command()
def delete(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a document from the knowledge base"""
    if not force:
        # TODO: Show document title for confirmation
        confirm = typer.confirm(f"Are you sure you want to delete '{identifier}'?")
        if not confirm:
            typer.echo("Deletion cancelled.")
            raise typer.Abort()
    
    # TODO: Delete from database
    # TODO: Also delete any attachments
    
    typer.echo(f"🗑️  Deleted document: {identifier}")
