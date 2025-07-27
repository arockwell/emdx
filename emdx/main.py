#!/usr/bin/env python3
"""
Main CLI entry point for emdx
"""

from typing import Optional

import typer
from rich.console import Console

from emdx import __version__, __build_id__
from emdx.cli.command_registry import CommandRegistry
from emdx.commands.browse import app as browse_app
from emdx.commands.core import app as core_app
from emdx.commands.gist import app as gist_app
from emdx.commands.tags import app as tag_app
from emdx.commands.executions import app as executions_app
from emdx.commands.claude_execute import app as claude_app
from emdx.commands.lifecycle import app as lifecycle_app
from emdx.ui.gui import gui

# Import new-style command modules
from emdx.commands import analyze, maintain

console = Console()


# Version command
def version():
    """Show emdx version"""
    typer.echo(f"emdx version {__version__}")
    typer.echo(f"Build ID: {__build_id__}")
    typer.echo("Documentation Index Management System")


# Callback for global options
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    db_url: Optional[str] = typer.Option(
        None, "--db-url", envvar="EMDX_DATABASE_URL", help="Database connection URL"
    ),
):
    """
    emdx - Documentation Index Management System

    A sophisticated SQLite-based knowledge management system with instant full-text search,
    automatic project detection, and seamless integration with daily development workflows.

    [bold]Examples:[/bold]

    Save a file:
        [cyan]emdx save README.md[/cyan]

    Save text directly:
        [cyan]emdx save "Remember to fix the API endpoint"[/cyan]

    Save from pipe:
        [cyan]docker ps | emdx save --title "Running containers"[/cyan]

    Search for content:
        [cyan]emdx find "docker compose"[/cyan]

    View a document:
        [cyan]emdx view 42[/cyan]
        [cyan]emdx view "My Document Title"[/cyan]
    """
    # Set up global state based on flags
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet are mutually exclusive", err=True)
        raise typer.Exit(1)

    # TODO: Set up database connection using db_url
    # TODO: Set up logging based on verbose/quiet flags


def create_app() -> typer.Typer:
    """Create and configure the main CLI application"""
    registry = CommandRegistry()
    
    # Register new-style command modules
    registry.register_module(analyze)
    registry.register_module(maintain)
    
    # Register legacy command modules (still using old typer apps)
    from emdx.cli.command_registry import safe_register_commands
    
    # Create temporary app for legacy registration
    temp_app = typer.Typer()
    safe_register_commands(temp_app, core_app, "core")
    safe_register_commands(temp_app, browse_app, "browse") 
    safe_register_commands(temp_app, gist_app, "gist")
    safe_register_commands(temp_app, tag_app, "tags")
    
    # Extract commands from temp app and add to registry
    if hasattr(temp_app, 'registered_commands'):
        for cmd in temp_app.registered_commands:
            if hasattr(cmd, 'callback') and callable(cmd.callback):
                registry.register_function(cmd.callback, getattr(cmd, 'name', cmd.callback.__name__))
    
    # Register subcommand groups
    registry.register_subapp(executions_app, "exec", "Manage Claude executions")
    registry.register_subapp(claude_app, "claude", "Execute documents with Claude")
    registry.register_subapp(lifecycle_app, "lifecycle", "Track document lifecycles")
    
    # Register standalone functions
    registry.register_function(gui)
    registry.register_function(version)
    
    # Build and return the app
    app = registry.build_app()
    
    # Add global callback
    app.callback()(main)
    
    # Validate registry
    if not registry.validate():
        console.print("[red]Warning: Command registry validation failed[/red]")
        status = registry.get_status()
        for error in status["errors"]:
            console.print(f"  [red]•[/red] {error}")
    
    return app


# Create the app instance
app = create_app()


def run():
    """Entry point for the CLI"""
    app()


if __name__ == "__main__":
    run()
