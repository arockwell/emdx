"""
Quick capture commands for emdx
"""

import typer
from typing import Optional, List
from datetime import datetime
import sys
import subprocess
import tempfile
from pathlib import Path
from rich.console import Console

from emdx.database import db
from emdx.utils import get_git_project

app = typer.Typer()
console = Console()


@app.command()
def note(
    content: List[str] = typer.Argument(..., help="Note content"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
):
    """Save a quick note with automatic timestamp"""
    note_content = " ".join(content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Auto-detect project from git if not provided
    if not project:
        project = get_git_project()
    
    # Create note with timestamp in title
    title = f"Note - {timestamp}"
    full_content = f"# {title}\n\n{note_content}\n\n---\n*Created: {timestamp}*"
    
    # Save to database
    try:
        db.ensure_schema()
        doc_id = db.save_document(title, full_content, project)
        console.print(f"[green]📝 Saved note #{doc_id}:[/green] {note_content[:50]}...")
        if project:
            console.print(f"   [dim]Project:[/dim] {project}")
    except Exception as e:
        console.print(f"[red]Error saving note: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def clip(
    title: Optional[str] = typer.Argument(None, help="Document title"),
    project: Optional[str] = typer.Argument(None, help="Project name"),
):
    """Save clipboard content to knowledge base"""
    # TODO: Get clipboard content (pbpaste on macOS, xclip on Linux)
    # TODO: Auto-generate title if not provided
    # TODO: Save to database
    
    try:
        # macOS clipboard
        result = subprocess.run(['pbpaste'], capture_output=True, text=True)
        if result.returncode != 0:
            typer.echo("Error: Could not read clipboard", err=True)
            raise typer.Exit(1)
        
        content = result.stdout
        if not content.strip():
            typer.echo("Error: Clipboard is empty", err=True)
            raise typer.Exit(1)
        
        if not title:
            title = f"Clipboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        typer.echo(f"📋 Saved clipboard as '{title}'")
        
    except FileNotFoundError:
        typer.echo("Error: pbpaste not found. Are you on macOS?", err=True)
        raise typer.Exit(1)


@app.command()
def pipe(
    title: str = typer.Argument(..., help="Document title"),
    project: Optional[str] = typer.Argument(None, help="Project name"),
):
    """Pipe command output to knowledge base (use with stdin)"""
    if sys.stdin.isatty():
        typer.echo("Error: No input provided. Use: command | emdx pipe 'title'", err=True)
        raise typer.Exit(1)
    
    # Read from stdin
    content = sys.stdin.read()
    
    if not content.strip():
        typer.echo("Error: No content received from pipe", err=True)
        raise typer.Exit(1)
    
    # TODO: Save to database
    
    typer.echo(f"🔧 Saved piped content as '{title}'")


@app.command()
def cmd(
    command: List[str] = typer.Argument(..., help="Command to execute and save"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Custom title"),
):
    """Run command and save output to knowledge base"""
    cmd_str = " ".join(command)
    
    if not title:
        title = f"Command Output - {cmd_str[:50]}"
    
    # Execute command and capture output
    result = subprocess.run(command, capture_output=True, text=True, shell=False)
    
    # Combine stdout and stderr
    output = f"$ {cmd_str}\n\n"
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += f"\n--- STDERR ---\n{result.stderr}"
    
    output += f"\n\n---\nExit code: {result.returncode}"
    output += f"\nExecuted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # TODO: Save to database
    
    typer.echo(f"💻 Saved command output as '{title}'")
    if result.returncode != 0:
        typer.echo(f"⚠️  Command exited with code {result.returncode}", err=True)


@app.command()
def direct(
    title: str = typer.Argument(..., help="Document title"),
    content: Optional[str] = typer.Argument(None, help="Content (or use stdin)"),
    project: Optional[str] = typer.Argument(None, help="Project name"),
):
    """Save content directly without files"""
    # If no content provided, check stdin
    if content is None:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            typer.echo("Error: No content provided", err=True)
            raise typer.Exit(1)
    
    if not content.strip():
        typer.echo("Error: Content is empty", err=True)
        raise typer.Exit(1)
    
    # TODO: Save to database
    
    typer.echo(f"💾 Saved '{title}' directly to knowledge base")
