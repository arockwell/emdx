#!/usr/bin/env python3
"""
Main CLI entry point for emdx
"""

from typing import Optional

import typer

from emdx import __version__
from emdx.commands.browse import app as browse_app
from emdx.commands.core import app as core_app
from emdx.commands.gist import app as gist_app
from emdx.commands.tags import app as tag_app
from emdx.commands.executions import app as executions_app
from emdx.ui.gui import gui

# Create main app
app = typer.Typer(
    name="emdx",
    help="Documentation Index Management System - A powerful knowledge base for developers",
    add_completion=True,
    rich_markup_mode="rich",
)

# Add subcommand groups
# Core commands are added directly to the main app
for command in core_app.registered_commands:
    app.registered_commands.append(command)

# Browse commands are added directly to the main app
for command in browse_app.registered_commands:
    app.registered_commands.append(command)

# Gist commands are added directly to the main app
for command in gist_app.registered_commands:
    app.registered_commands.append(command)

# Tag commands are added directly to the main app
for command in tag_app.registered_commands:
    app.registered_commands.append(command)

# Add executions as a subcommand group
app.add_typer(executions_app, name="exec", help="Manage Claude executions")

# Add the gui command
app.command()(gui)


# Version command
@app.command()
def version():
    """Show emdx version"""
    typer.echo(f"emdx version {__version__}")
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
    app()


if __name__ == "__main__":
    run()
