"""
Core CRUD operations for emdx
"""

import typer
from typing import Optional, List
from pathlib import Path
from datetime import datetime
import tempfile
import subprocess
import os
from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.table import Table

from emdx.sqlite_database import db
from emdx.utils import get_git_project
from emdx.tags import add_tags_to_document, get_document_tags, search_by_tags

app = typer.Typer()
console = Console()


@app.command()
def save(
    input: Optional[str] = typer.Argument(None, help="File path or content to save (reads from stdin if not provided)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Document title"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name (auto-detected from git)"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
):
    """Save content to the knowledge base (from file, stdin, or direct text)"""
    import sys
    
    content = None
    source_type = None
    
    # Priority 1: Check if stdin has data
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        source_type = "stdin"
        if not title:
            title = f"Piped content - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Priority 2: Check if input is provided
    elif input:
        # Check if it's a file path
        file_path = Path(input)
        if file_path.exists() and file_path.is_file():
            # It's a file
            try:
                content = file_path.read_text(encoding='utf-8')
                source_type = "file"
                if not title:
                    title = file_path.stem  # filename without extension
                # Auto-detect project from git if not provided
                if not project:
                    detected_project = get_git_project(file_path.parent)
                    if detected_project:
                        project = detected_project
            except Exception as e:
                console.print(f"[red]Error reading file: {e}[/red]")
                raise typer.Exit(1)
        else:
            # Treat as direct content
            content = input
            source_type = "direct"
            if not title:
                # Create title from first line or truncated content
                first_line = content.split('\n')[0].strip()
                if first_line:
                    title = first_line[:50] + "..." if len(first_line) > 50 else first_line
                else:
                    title = f"Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # No input provided
    else:
        console.print("[red]Error: No input provided. Provide a file path, text content, or pipe data via stdin[/red]")
        raise typer.Exit(1)
    
    # Auto-detect project from current directory if not provided and not from file
    if not project and source_type != "file":
        detected_project = get_git_project(Path.cwd())
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
        
        # Add tags if provided
        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            if tag_list:
                added_tags = add_tags_to_document(doc_id, tag_list)
                if added_tags:
                    console.print(f"   [dim]Tags:[/dim] {', '.join(added_tags)}")
    except Exception as e:
        console.print(f"[red]Error saving document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def find(
    query: List[str] = typer.Argument(None, help="Search terms (optional if using --tags)"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    snippets: bool = typer.Option(False, "--snippets", "-s", help="Show content snippets"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Use fuzzy search"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    any_tags: bool = typer.Option(False, "--any-tags", help="Match ANY tag instead of ALL tags"),
):
    """Search the knowledge base with full-text search"""
    search_query = " ".join(query) if query else ""
    
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Validate that we have something to search for
        if not search_query and not tags:
            console.print("[red]Error: Provide search terms or use --tags option[/red]")
            raise typer.Exit(1)
        
        # Handle tag-based search
        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            tag_mode = 'any' if any_tags else 'all'
            
            # If we have both tags and search query, we need to combine results
            if search_query:
                # Get documents matching tags
                tag_results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit)
                tag_doc_ids = {doc['id'] for doc in tag_results}
                
                # Get documents matching search query
                search_results = db.search_documents(search_query, project=project, limit=limit*2, fuzzy=fuzzy)
                
                # Combine: only show documents that match both criteria
                results = [doc for doc in search_results if doc['id'] in tag_doc_ids][:limit]
                
                if not results:
                    console.print(f"[yellow]No results found matching both '[/yellow]{search_query}[yellow]' and tags: {', '.join(tag_list)}[/yellow]")
                    return
            else:
                # Tag-only search
                results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit)
                if not results:
                    mode_desc = "all" if not any_tags else "any"
                    console.print(f"[yellow]No results found with {mode_desc} tags: {', '.join(tag_list)}[/yellow]")
                    return
                search_query = f"tags: {', '.join(tag_list)}"
        else:
            # Regular search without tags
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
            
            # Display tags
            doc_tags = get_document_tags(result['id'])
            if doc_tags:
                console.print(f"[dim]Tags: {', '.join(doc_tags)}[/dim]")
            
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
    no_pager: bool = typer.Option(False, "--no-pager", help="Disable pager (for piping output)"),
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
        
        # Display document with or without pager
        if no_pager:
            # Direct output without pager
            console.print(f"\n[bold cyan]#{doc['id']}:[/bold cyan] [bold]{doc['title']}[/bold]")
            console.print("=" * 60)
            console.print(f"[dim]Project:[/dim] {doc['project'] or 'None'}")
            console.print(f"[dim]Created:[/dim] {doc['created_at'].strftime('%Y-%m-%d %H:%M')}")
            console.print(f"[dim]Views:[/dim] {doc['access_count']}")
            # Show tags
            doc_tags = get_document_tags(doc['id'])
            if doc_tags:
                console.print(f"[dim]Tags:[/dim] {', '.join(doc_tags)}")
            console.print("=" * 60 + "\n")
            
            if raw:
                console.print(doc['content'])
            else:
                markdown = Markdown(doc['content'])
                console.print(markdown)
        else:
            # Use Rich's pager
            with console.pager():
                console.print(f"\n[bold cyan]#{doc['id']}:[/bold cyan] [bold]{doc['title']}[/bold]")
                console.print("=" * 60)
                console.print(f"[dim]Project:[/dim] {doc['project'] or 'None'}")
                console.print(f"[dim]Created:[/dim] {doc['created_at'].strftime('%Y-%m-%d %H:%M')}")
                console.print(f"[dim]Views:[/dim] {doc['access_count']}")
                # Show tags
                doc_tags = get_document_tags(doc['id'])
                if doc_tags:
                    console.print(f"[dim]Tags:[/dim] {', '.join(doc_tags)}")
                console.print("=" * 60 + "\n")
                
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
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Update title without editing content"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor to use (default: $EDITOR)"),
):
    """Edit a document in the knowledge base"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Fetch document
        doc = db.get_document(identifier)
        
        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)
        
        # Quick title update without editing content
        if title:
            success = db.update_document(doc['id'], title, doc['content'])
            if success:
                console.print(f"[green]✅ Updated title of #{doc['id']} to:[/green] [cyan]{title}[/cyan]")
            else:
                console.print(f"[red]Error updating document title[/red]")
                raise typer.Exit(1)
            return
        
        # Determine editor to use
        if not editor:
            editor = os.environ.get('EDITOR', 'nano')
        
        # Create temporary file with current content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp_file:
            # Write header comment
            tmp_file.write(f"# Editing: {doc['title']} (ID: {doc['id']})\n")
            tmp_file.write(f"# Project: {doc['project'] or 'None'}\n")
            tmp_file.write(f"# Created: {doc['created_at'].strftime('%Y-%m-%d %H:%M')}\n")
            tmp_file.write(f"# Lines starting with '#' will be removed\n")
            tmp_file.write("#\n")
            tmp_file.write("# First line (after comments) will be used as the title\n")
            tmp_file.write("# The rest will be the content\n")
            tmp_file.write("#\n")
            
            # Write title and content
            tmp_file.write(f"{doc['title']}\n\n")
            tmp_file.write(doc['content'])
            tmp_file_path = tmp_file.name
        
        try:
            # Open editor
            console.print(f"[dim]Opening {editor}...[/dim]")
            result = subprocess.run([editor, tmp_file_path])
            
            if result.returncode != 0:
                console.print(f"[red]Editor exited with error code {result.returncode}[/red]")
                raise typer.Exit(1)
            
            # Read edited content
            with open(tmp_file_path, 'r') as f:
                lines = f.readlines()
            
            # Remove comment lines
            lines = [line for line in lines if not line.strip().startswith('#')]
            
            # Extract title and content
            if not lines:
                console.print("[yellow]No changes made (empty file)[/yellow]")
                return
            
            # First non-empty line is the title
            new_title = ""
            content_start = 0
            for i, line in enumerate(lines):
                if line.strip():
                    new_title = line.strip()
                    content_start = i + 1
                    break
            
            if not new_title:
                console.print("[yellow]No changes made (no title found)[/yellow]")
                return
            
            # Rest is content
            new_content = ''.join(lines[content_start:]).strip()
            
            # Check if anything changed
            if new_title == doc['title'] and new_content == doc['content'].strip():
                console.print("[yellow]No changes made[/yellow]")
                return
            
            # Update document
            success = db.update_document(doc['id'], new_title, new_content)
            
            if success:
                console.print(f"[green]✅ Updated #{doc['id']}:[/green] [cyan]{new_title}[/cyan]")
                if new_title != doc['title']:
                    console.print(f"   [dim]Title changed from:[/dim] {doc['title']}")
                console.print(f"   [dim]Content updated[/dim]")
            else:
                console.print(f"[red]Error updating document[/red]")
                raise typer.Exit(1)
                
        finally:
            # Clean up temp file
            os.unlink(tmp_file_path)
            
    except Exception as e:
        console.print(f"[red]Error editing document: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def delete(
    identifiers: List[str] = typer.Argument(..., help="Document ID(s) or title(s) to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete (cannot be restored)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting"),
):
    """Delete one or more documents (soft delete by default)"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Collect documents to delete
        docs_to_delete = []
        not_found = []
        
        for identifier in identifiers:
            doc = db.get_document(identifier)
            if doc:
                docs_to_delete.append(doc)
            else:
                not_found.append(identifier)
        
        # Report not found
        if not_found:
            console.print(f"[yellow]Warning: The following documents were not found:[/yellow]")
            for nf in not_found:
                console.print(f"  [dim]• {nf}[/dim]")
            console.print()
        
        if not docs_to_delete:
            console.print("[red]No valid documents to delete[/red]")
            raise typer.Exit(1)
        
        # Show what will be deleted
        console.print(f"\n[bold]{'Would delete' if dry_run else 'Will delete'} {len(docs_to_delete)} document(s):[/bold]\n")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="green")
        table.add_column("Created", style="yellow")
        table.add_column("Type", style="red" if hard else "yellow")
        
        for doc in docs_to_delete:
            table.add_row(
                str(doc['id']),
                doc['title'][:50] + "..." if len(doc['title']) > 50 else doc['title'],
                doc['project'] or "[dim]None[/dim]",
                doc['created_at'].strftime('%Y-%m-%d'),
                "[red]PERMANENT[/red]" if hard else "[yellow]Soft delete[/yellow]"
            )
        
        console.print(table)
        
        if dry_run:
            console.print("\n[dim]This is a dry run. No documents were deleted.[/dim]")
            return
        
        # Confirmation
        if not force:
            if hard:
                console.print(f"\n[red bold]⚠️  WARNING: This will PERMANENTLY delete {len(docs_to_delete)} document(s)![/red bold]")
                console.print("[red]This action cannot be undone![/red]\n")
                confirm = typer.confirm("Are you absolutely sure?", abort=True)
                if confirm:
                    # Extra confirmation for hard delete
                    confirm2 = typer.confirm("Type 'yes' to confirm permanent deletion", abort=True)
            else:
                console.print(f"\n[yellow]This will move {len(docs_to_delete)} document(s) to trash.[/yellow]")
                console.print("[dim]You can restore them later with 'emdx restore'[/dim]\n")
                confirm = typer.confirm("Continue?", abort=True)
        
        # Perform deletion
        deleted_count = 0
        failed = []
        
        for doc in docs_to_delete:
            success = db.delete_document(str(doc['id']), hard_delete=hard)
            if success:
                deleted_count += 1
            else:
                failed.append(doc)
        
        # Report results
        if deleted_count > 0:
            if hard:
                console.print(f"\n[green]✅ Permanently deleted {deleted_count} document(s)[/green]")
            else:
                console.print(f"\n[green]✅ Moved {deleted_count} document(s) to trash[/green]")
                console.print("[dim]💡 Use 'emdx trash' to view deleted documents[/dim]")
                console.print("[dim]💡 Use 'emdx restore <id>' to restore documents[/dim]")
        
        if failed:
            console.print(f"\n[red]Failed to delete {len(failed)} document(s):[/red]")
            for doc in failed:
                console.print(f"  [dim]• #{doc['id']}: {doc['title']}[/dim]")
        
    except typer.Abort:
        console.print("[yellow]Deletion cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error deleting documents: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def trash(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Show items deleted in last N days"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum results to return"),
):
    """List all soft-deleted documents"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get deleted documents
        deleted_docs = db.list_deleted_documents(days=days, limit=limit)
        
        if not deleted_docs:
            if days:
                console.print(f"[yellow]No documents deleted in the last {days} days[/yellow]")
            else:
                console.print("[yellow]No documents in trash[/yellow]")
            return
        
        # Display results
        if days:
            console.print(f"\n[bold]🗑️  Documents deleted in the last {days} days:[/bold]\n")
        else:
            console.print(f"\n[bold]🗑️  Documents in trash ({len(deleted_docs)} items):[/bold]\n")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="green")
        table.add_column("Deleted", style="red")
        table.add_column("Views", style="yellow", justify="right")
        
        for doc in deleted_docs:
            table.add_row(
                str(doc['id']),
                doc['title'][:50] + "..." if len(doc['title']) > 50 else doc['title'],
                doc['project'] or "[dim]None[/dim]",
                doc['deleted_at'].strftime('%Y-%m-%d %H:%M'),
                str(doc['access_count'])
            )
        
        console.print(table)
        console.print("\n[dim]💡 Use 'emdx restore <id>' to restore documents[/dim]")
        console.print("[dim]💡 Use 'emdx purge' to permanently delete all items in trash[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error listing deleted documents: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def restore(
    identifiers: List[str] = typer.Argument(None, help="Document ID(s) or title(s) to restore"),
    all: bool = typer.Option(False, "--all", help="Restore all deleted documents"),
):
    """Restore soft-deleted document(s)"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Validate arguments
        if not identifiers and not all:
            console.print("[red]Error: Provide document ID(s) to restore or use --all[/red]")
            raise typer.Exit(1)
        
        if all:
            # Restore all deleted documents
            deleted_docs = db.list_deleted_documents()
            if not deleted_docs:
                console.print("[yellow]No documents to restore[/yellow]")
                return
            
            console.print(f"\n[bold]Will restore {len(deleted_docs)} document(s)[/bold]")
            confirm = typer.confirm("Continue?", abort=True)
            
            restored_count = 0
            for doc in deleted_docs:
                if db.restore_document(str(doc['id'])):
                    restored_count += 1
            
            console.print(f"\n[green]✅ Restored {restored_count} document(s)[/green]")
        else:
            # Restore specific documents
            restored = []
            not_found = []
            
            for identifier in identifiers:
                if db.restore_document(identifier):
                    restored.append(identifier)
                else:
                    not_found.append(identifier)
            
            if restored:
                console.print(f"\n[green]✅ Restored {len(restored)} document(s):[/green]")
                for r in restored:
                    console.print(f"  [dim]• {r}[/dim]")
            
            if not_found:
                console.print(f"\n[yellow]Could not restore {len(not_found)} document(s):[/yellow]")
                for nf in not_found:
                    console.print(f"  [dim]• {nf} (not found in trash)[/dim]")
        
    except typer.Abort:
        console.print("[yellow]Restore cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error restoring documents: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def purge(
    older_than: Optional[int] = typer.Option(None, "--older-than", help="Only purge items deleted more than N days ago"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Permanently delete all items in trash"""
    try:
        # Ensure database schema exists
        db.ensure_schema()
        
        # Get count of documents to purge
        if older_than:
            deleted_docs = db.list_deleted_documents()
            # Filter by age
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=older_than)
            docs_to_purge = [d for d in deleted_docs if d['deleted_at'] < cutoff]
            count = len(docs_to_purge)
        else:
            deleted_docs = db.list_deleted_documents()
            count = len(deleted_docs)
        
        if count == 0:
            if older_than:
                console.print(f"[yellow]No documents deleted more than {older_than} days ago[/yellow]")
            else:
                console.print("[yellow]No documents in trash to purge[/yellow]")
            return
        
        # Show warning
        console.print(f"\n[red bold]⚠️  WARNING: This will PERMANENTLY delete {count} document(s) from trash![/red bold]")
        console.print("[red]This action cannot be undone![/red]\n")
        
        if not force:
            confirm = typer.confirm("Are you absolutely sure?", abort=True)
        
        # Perform purge
        purged_count = db.purge_deleted_documents(older_than_days=older_than)
        
        console.print(f"\n[green]✅ Permanently deleted {purged_count} document(s) from trash[/green]")
        
    except typer.Abort:
        console.print("[yellow]Purge cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error purging documents: {e}[/red]")
        raise typer.Exit(1)
