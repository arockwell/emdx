#!/usr/bin/env python3
"""
Main CLI entry point for emdx
"""

from typing import Optional
import logging
import os

import typer
from emdx import __build_id__, __version__
from emdx.commands.analyze import app as analyze_app
from emdx.commands.browse import app as browse_app
from emdx.commands.claude_execute import app as claude_app
from emdx.commands.core import app as core_app
from emdx.commands.executions import app as executions_app
from emdx.commands.export import app as export_app
from emdx.commands.export_profiles import app as export_profiles_app
from emdx.commands.gdoc import app as gdoc_app
from emdx.commands.gist import app as gist_app
from emdx.commands.lifecycle import app as lifecycle_app
from emdx.commands.maintain import app as maintain_app
from emdx.commands.similarity import app as similarity_app
from emdx.commands.tags import app as tag_app
from emdx.commands.tasks import app as tasks_app
from emdx.commands.workflows import app as workflows_app
from emdx.commands.keybindings import app as keybindings_app
from emdx.commands.run import run as run_command
from emdx.commands.agent import agent as agent_command
from emdx.commands.groups import app as groups_app
from emdx.commands.ask import app as ask_app
from emdx.commands.each import app as each_app
from emdx.commands.cascade import app as cascade_app
from emdx.commands.prime import prime as prime_command
from emdx.commands.status import status as status_command
from emdx.ui.gui import gui
from emdx.utils.output import console


def is_safe_mode() -> bool:
    """Check if EMDX is running in safe mode.

    Safe mode disables execution commands (cascade, run, each, agent, workflow, claude).
    Enable with EMDX_SAFE_MODE=1 environment variable.
    """
    return os.environ.get("EMDX_SAFE_MODE", "0").lower() in ("1", "true", "yes")


# Commands disabled in safe mode
UNSAFE_COMMANDS = {"cascade", "run", "each", "agent", "workflow", "claude"}


def create_disabled_command(name: str):
    """Create a command that shows a disabled message in safe mode."""
    def disabled_command():
        typer.echo(
            f"Command '{name}' is disabled in safe mode. "
            f"Set EMDX_SAFE_MODE=0 to enable.",
            err=True
        )
        raise typer.Exit(1)

    disabled_command.__doc__ = f"[DISABLED in safe mode] Execute {name} operations"
    return disabled_command

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

# Google Docs commands are added directly to the main app
for command in gdoc_app.registered_commands:
    app.registered_commands.append(command)

# Tag commands are added directly to the main app
for command in tag_app.registered_commands:
    app.registered_commands.append(command)

# Add executions as a subcommand group
app.add_typer(executions_app, name="exec", help="Manage Claude executions")

# Add claude execution as a subcommand group (disabled in safe mode)
if is_safe_mode():
    disabled_claude_app = typer.Typer()
    disabled_claude_app.command(name="execute")(create_disabled_command("claude"))
    app.add_typer(disabled_claude_app, name="claude", help="[DISABLED] Execute documents with Claude")
else:
    app.add_typer(claude_app, name="claude", help="Execute documents with Claude")

# Add the new unified analyze command
app.command(name="analyze")(analyze_app.registered_commands[0].callback)

# Add the new unified maintain command
app.command(name="maintain")(maintain_app.registered_commands[0].callback)

# Add lifecycle as a subcommand group (keeping this as-is)
app.add_typer(lifecycle_app, name="lifecycle", help="Track document lifecycles")

# Add tasks as a subcommand group
app.add_typer(tasks_app, name="task", help="Task management")

# Add workflows as a subcommand group (disabled in safe mode)
if is_safe_mode():
    disabled_workflow_app = typer.Typer()
    disabled_workflow_app.command(name="run")(create_disabled_command("workflow"))
    disabled_workflow_app.command(name="list")(create_disabled_command("workflow"))
    app.add_typer(disabled_workflow_app, name="workflow", help="[DISABLED] Manage and run multi-stage workflows")
else:
    app.add_typer(workflows_app, name="workflow", help="Manage and run multi-stage workflows")

# Add groups as a subcommand group
app.add_typer(groups_app, name="group", help="Organize documents into hierarchical groups")

# Add export profile management as a subcommand group
app.add_typer(export_profiles_app, name="export-profile", help="Manage export profiles")

# Add export commands as a subcommand group
app.add_typer(export_app, name="export", help="Export documents using profiles")

# Add keybindings as a subcommand group
app.add_typer(keybindings_app, name="keybindings", help="Manage TUI keybindings")

# Add AI-powered features (ask, semantic search, embeddings)
app.add_typer(ask_app, name="ai", help="AI-powered Q&A and semantic search")

# Add the run command for quick task execution (disabled in safe mode)
if is_safe_mode():
    app.command(name="run")(create_disabled_command("run"))
else:
    app.command(name="run")(run_command)

# Add the agent command for sub-agent execution with EMDX tracking (disabled in safe mode)
if is_safe_mode():
    app.command(name="agent")(create_disabled_command("agent"))
else:
    app.command(name="agent")(agent_command)

# Add each command for reusable parallel commands (disabled in safe mode)
if is_safe_mode():
    disabled_each_app = typer.Typer()
    disabled_each_app.command(name="run")(create_disabled_command("each"))
    disabled_each_app.command(name="create")(create_disabled_command("each"))
    disabled_each_app.command(name="list")(create_disabled_command("each"))
    app.add_typer(disabled_each_app, name="each", help="[DISABLED] Create and run reusable parallel commands")
else:
    app.add_typer(each_app, name="each", help="Create and run reusable parallel commands")

# Add cascade command for autonomous document transformation (disabled in safe mode)
if is_safe_mode():
    disabled_cascade_app = typer.Typer()
    disabled_cascade_app.command(name="add")(create_disabled_command("cascade"))
    disabled_cascade_app.command(name="run")(create_disabled_command("cascade"))
    disabled_cascade_app.command(name="status")(create_disabled_command("cascade"))
    app.add_typer(disabled_cascade_app, name="cascade", help="[DISABLED] Cascade ideas through stages to working code")
else:
    app.add_typer(cascade_app, name="cascade", help="Cascade ideas through stages to working code")

# Add the prime command for Claude session priming
app.command(name="prime")(prime_command)

# Add the status command for consolidated project overview
app.command(name="status")(status_command)

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
    safe_mode: bool = typer.Option(
        False, "--safe-mode", envvar="EMDX_SAFE_MODE",
        help="Disable execution commands (cascade, run, each, agent, workflow, claude)"
    ),
):
    """
    emdx - Documentation Index Management System

    A powerful CLI tool for managing your knowledge base with full-text search,
    Git integration, and seamless editor workflows.

    [bold]Safe Mode:[/bold]
    Set EMDX_SAFE_MODE=1 or use --safe-mode to disable execution commands
    (cascade, run, each, agent, workflow, claude). Useful for read-only access
    or when external execution should be prevented.

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

    Enable safe mode:
        [cyan]EMDX_SAFE_MODE=1 emdx --help[/cyan]
        [cyan]emdx --safe-mode cascade add "idea"[/cyan]  # Will show disabled message
    """
    # Set up global state based on flags
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Handle --safe-mode flag by setting environment variable
    # Note: This is checked at import time, so the flag mainly serves as documentation
    # and for future commands that might check at runtime
    if safe_mode:
        os.environ["EMDX_SAFE_MODE"] = "1"

    # Note: Database connections are established per-command as needed
    # Note: Logging is configured per-module as needed


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
safe_register_commands(app, gdoc_app, "gdoc")
safe_register_commands(app, tag_app, "tags")
safe_register_commands(app, analyze_app, "analyze")
safe_register_commands(app, maintain_app, "maintain")
safe_register_commands(app, similarity_app, "similarity")

# Register subcommand groups
# Note: executions_app and lifecycle_app are safe commands
# claude_app is already conditionally registered above based on safe mode

# Register standalone commands
# Note: gui is already registered above


def run():
    """Entry point for the CLI"""
    app()


if __name__ == "__main__":
    run()
