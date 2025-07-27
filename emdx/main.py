#!/usr/bin/env python3
"""
Main CLI entry point for emdx
"""

from typing import Optional

import typer
from rich.console import Console

from emdx import __version__, __build_id__
from emdx.cli.command_registry import CommandRegistryFoundation, safe_register_subapp, safe_register_function
from emdx.commands.browse import app as browse_app
from emdx.commands.core import app as core_app
from emdx.commands.gist import app as gist_app
from emdx.commands.tags import app as tag_app
from emdx.commands.executions import app as executions_app
from emdx.commands.claude_execute import app as claude_app
from emdx.commands.lifecycle import app as lifecycle_app
from emdx.ui.gui import gui

console = Console()

# Initialize command registry foundation
registry = CommandRegistryFoundation()


# Create main app
app = typer.Typer(
    name="emdx",
    help="Documentation Index Management System - A powerful knowledge base for developers",
    add_completion=True,
    rich_markup_mode="rich",
)

# Add subcommand groups using safe registration
registry.register_module_safe(app, core_app, "core")
registry.register_module_safe(app, browse_app, "browse")
registry.register_module_safe(app, gist_app, "gist")
registry.register_module_safe(app, tag_app, "tags")

# Add executions as a subcommand group
safe_register_subapp(app, executions_app, "exec", "Manage Claude executions")

# Add claude execution as a subcommand group
safe_register_subapp(app, claude_app, "claude", "Execute documents with Claude")

# Add the new unified analyze command (safe direct import)
from emdx.commands.analyze import analyze
from emdx.commands.maintain import maintain

safe_register_function(app, analyze, "analyze")
safe_register_function(app, maintain, "maintain")

# Add lifecycle as a subcommand group
safe_register_subapp(app, lifecycle_app, "lifecycle", "Track document lifecycles")

# Add the gui command
safe_register_function(app, gui)


# Version command
@app.command()
def version():
    """Show emdx version"""
    typer.echo(f"emdx version {__version__}")
    typer.echo(f"Build ID: {__build_id__}")
    typer.echo("Documentation Index Management System")


# Callback for global options
@app.callback()
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


def run():
    """Entry point for the CLI"""
    # Validate command registration before starting
    if not registry.validate_app(app):
        console.print("[red]Warning: Command registration validation failed[/red]")
        status = registry.get_status()
        for error in status["errors"]:
            console.print(f"  [red]•[/red] {error}")
    
    app()


if __name__ == "__main__":
    run()
