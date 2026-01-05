#!/usr/bin/env python3
"""
Main CLI entry point for emdx
"""

from typing import Optional

import typer
from rich.console import Console

from emdx import __build_id__, __version__
from emdx.commands.analyze import app as analyze_app
from emdx.commands.browse import app as browse_app
from emdx.commands.claude_execute import app as claude_app
from emdx.commands.core import app as core_app
from emdx.commands.executions import app as executions_app
from emdx.commands.gist import app as gist_app
from emdx.commands.lifecycle import app as lifecycle_app
from emdx.commands.maintain import app as maintain_app
from emdx.commands.agents import app as agents_app
from emdx.commands.tags import app as tag_app
from emdx.ui.gui import gui

console = Console()

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

# Add claude execution as a subcommand group
app.add_typer(claude_app, name="claude", help="Execute documents with Claude")

# Add the new unified analyze command
app.command(name="analyze")(analyze_app.registered_commands[0].callback)

# Add the new unified maintain command
app.command(name="maintain")(maintain_app.registered_commands[0].callback)

# Add lifecycle as a subcommand group (keeping this as-is)
app.add_typer(lifecycle_app, name="lifecycle", help="Track document lifecycles")

# Add agents as a subcommand group
app.add_typer(agents_app, name="agent", help="Manage and run AI agents")

# Add the gui command
app.command()(gui)


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

    A powerful CLI tool for managing your knowledge base with full-text search,
    Git integration, and seamless editor workflows.

    Examples:

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


def safe_register_commands(target_app, source_app, prefix=""):
    """Safely register commands from source app to target app"""
    try:
        if hasattr(source_app, 'registered_commands'):
            for command in source_app.registered_commands:
                if hasattr(command, 'callback') and callable(command.callback):
                    target_app.command(name=command.name)(command.callback)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not register {prefix} commands: {e}[/yellow]")


# Register all command groups
safe_register_commands(app, core_app, "core")
safe_register_commands(app, browse_app, "browse")
safe_register_commands(app, gist_app, "gist")
safe_register_commands(app, tag_app, "tags")
safe_register_commands(app, analyze_app, "analyze")
safe_register_commands(app, maintain_app, "maintain")

# Register subcommand groups
app.add_typer(executions_app, name="exec", help="Manage Claude executions")
app.add_typer(claude_app, name="claude", help="Execute documents with Claude")
app.add_typer(lifecycle_app, name="lifecycle", help="Track document lifecycles")

# Register standalone commands
app.command()(gui)


def run():
    """Entry point for the CLI"""
    app()


if __name__ == "__main__":
    run()
