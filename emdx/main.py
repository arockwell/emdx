#!/usr/bin/env python3
"""
Main CLI entry point for emdx

This module uses lazy loading for heavy commands to improve startup performance.
Core KB commands (save, find, view, tag, list) are imported eagerly since they're
fast. Heavy commands (cascade, delegate, ai, etc.) are only imported when
actually invoked.
"""

import os
from collections.abc import Callable

import typer

from emdx import __build_id__, __version__
from emdx.utils.lazy_group import LazyTyperGroup, register_lazy_commands

# =============================================================================
# LAZY COMMANDS - Heavy features (defer import until invoked)
# =============================================================================
# Format: "command_name": "module.path:object_name"
# IMPORTANT: Register BEFORE any Typer app creation
LAZY_SUBCOMMANDS = {
    # Execution/orchestration (imports subprocess, async, executor)
    "recipe": "emdx.commands.recipe:app",
    "cascade": "emdx.commands.cascade:app",
    "delegate": "emdx.commands.delegate:app",
    # AI features (imports ML libraries, can be slow)
    "ai": "emdx.commands.ask:app",
    "distill": "emdx.commands.distill:app",
    "compact": "emdx.commands.compact:app",
}

# Pre-computed help strings so --help doesn't trigger imports
LAZY_HELP = {
    "recipe": "Manage and run EMDX recipes",
    "cascade": "Cascade ideas through stages to working code",
    "delegate": "One-shot AI execution (parallel, chain, worktree, PR)",
    "ai": "AI-powered Q&A and semantic search",
    "distill": "Distill KB content into audience-aware summaries",
    "compact": "Compact related documents through AI-powered synthesis",
}


def is_safe_mode() -> bool:
    """Check if EMDX is running in safe mode.

    Safe mode disables execution commands (cascade, delegate, recipe).
    Enable with EMDX_SAFE_MODE=1 environment variable.
    """
    return os.environ.get("EMDX_SAFE_MODE", "0").lower() in ("1", "true", "yes")


# Commands disabled in safe mode
UNSAFE_COMMANDS = {"cascade", "delegate", "recipe"}


def get_lazy_subcommands() -> dict[str, str]:
    """Get lazy subcommands, with safe mode commands excluded."""
    if is_safe_mode():
        # In safe mode, exclude unsafe commands from lazy loading
        # They'll be added as disabled commands eagerly instead
        return {k: v for k, v in LAZY_SUBCOMMANDS.items() if k not in UNSAFE_COMMANDS}
    return LAZY_SUBCOMMANDS


def get_lazy_help() -> dict[str, str]:
    """Get lazy help strings, filtering for safe mode."""
    if is_safe_mode():
        return {k: v for k, v in LAZY_HELP.items() if k not in UNSAFE_COMMANDS}
    return LAZY_HELP


def create_disabled_command(name: str) -> Callable[[], None]:
    """Create a command that shows a disabled message in safe mode."""
    def disabled_command() -> None:
        typer.echo(
            f"Command '{name}' is disabled in safe mode. "
            f"Set EMDX_SAFE_MODE=0 to enable.",
            err=True
        )
        raise typer.Exit(1)

    disabled_command.__doc__ = f"[DISABLED in safe mode] Execute {name} operations"
    return disabled_command


# Register lazy commands BEFORE importing any Typer apps
# This ensures the registry is populated when LazyTyperGroup is instantiated
register_lazy_commands(get_lazy_subcommands(), get_lazy_help())

# =============================================================================
# EAGER IMPORTS - Core KB commands (fast, always needed)
# Imports are after lazy registration - this is intentional for the loading pattern
# =============================================================================
from emdx.commands.briefing import briefing as briefing_command  # noqa: E402
from emdx.commands.browse import app as browse_app  # noqa: E402
from emdx.commands.categories import app as categories_app  # noqa: E402
from emdx.commands.core import app as core_app  # noqa: E402
from emdx.commands.epics import app as epics_app  # noqa: E402
from emdx.commands.executions import app as executions_app  # noqa: E402
from emdx.commands.gist import app as gist_app  # noqa: E402
from emdx.commands.groups import app as groups_app  # noqa: E402
from emdx.commands.maintain import app as maintain_app  # noqa: E402
from emdx.commands.prime import prime as prime_command  # noqa: E402
from emdx.commands.review import app as review_app  # noqa: E402
from emdx.commands.stale import app as stale_app  # noqa: E402
from emdx.commands.stale import touch as touch_command  # noqa: E402
from emdx.commands.status import status as status_command  # noqa: E402
from emdx.commands.tags import app as tag_app  # noqa: E402
from emdx.commands.tasks import app as tasks_app  # noqa: E402
from emdx.commands.trash import app as trash_app  # noqa: E402
from emdx.ui.gui import gui as gui_command  # noqa: E402

# Create main app with lazy loading support
app = typer.Typer(
    name="emdx",
    help="Documentation Index Management System - A powerful knowledge base for developers",
    add_completion=True,
    rich_markup_mode="rich",
    cls=LazyTyperGroup,
)

# We need to set these after creation because Typer's __init__ doesn't pass them through
# to the underlying Click group properly
app_info = app.info
app_info.cls = LazyTyperGroup


# =============================================================================
# Register eager commands
# =============================================================================

# Core commands (save, find, view, edit, delete, etc.)
for command in core_app.registered_commands:
    app.registered_commands.append(command)

# Browse commands (list, recent, stats)
for command in browse_app.registered_commands:
    app.registered_commands.append(command)

# Gist commands
for command in gist_app.registered_commands:
    app.registered_commands.append(command)

# Tag commands (subcommand group: emdx tag <subcommand>)
app.add_typer(tag_app, name="tag", help="Manage document tags")

# Trash commands (subcommand group: emdx trash <subcommand>)
app.add_typer(trash_app, name="trash", help="Manage deleted documents")

# Add executions as a subcommand group
app.add_typer(executions_app, name="exec", help="Manage Claude executions")

# Add tasks as a subcommand group
app.add_typer(tasks_app, name="task", help="Agent work queue")

# Add groups as a subcommand group
app.add_typer(groups_app, name="group", help="Organize documents into hierarchical groups")

# Add epics and categories as subcommand groups
app.add_typer(epics_app, name="epic", help="Manage task epics")
app.add_typer(categories_app, name="cat", help="Manage task categories")

# Add review commands for triaging agent outputs
app.add_typer(review_app, name="review", help="Triage agent-produced documents")

# Add maintain as a subcommand group (includes maintain, cleanup, cleanup-dirs, analyze)
app.add_typer(maintain_app, name="maintain", help="Maintenance and analysis tools")

# Add stale as a subcommand group for knowledge decay
app.add_typer(stale_app, name="stale", help="Knowledge decay and staleness tracking")

# Add touch as a top-level command for convenience
app.command(name="touch")(touch_command)

# Add the prime command for Claude session priming
app.command(name="prime")(prime_command)

# Add the status command for consolidated project overview
app.command(name="status")(status_command)

# Add the briefing command for activity summary
app.command(name="briefing")(briefing_command)

# Add the gui command for interactive TUI browser
app.command(name="gui")(gui_command)



# =============================================================================
# Handle safe mode for unsafe commands
# =============================================================================
if is_safe_mode():
    # Add disabled versions of unsafe commands that would otherwise be lazy-loaded
    for cmd_name in UNSAFE_COMMANDS:
        if cmd_name in LAZY_SUBCOMMANDS:
            app.command(name=cmd_name)(create_disabled_command(cmd_name))


# Version command
@app.command()
def version() -> None:
    """Show emdx version"""
    typer.echo(f"emdx version {__version__}")
    typer.echo(f"Build ID: {__build_id__}")
    typer.echo("Documentation Index Management System")


# Callback for global options
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    db_url: str | None = typer.Option(
        None, "--db-url", envvar="EMDX_DATABASE_URL", help="Database connection URL"
    ),
    safe_mode: bool = typer.Option(
        False, "--safe-mode", envvar="EMDX_SAFE_MODE",
        help="Disable execution commands (cascade, delegate, recipe)"
    ),
) -> None:
    """
    emdx - Documentation Index Management System

    A powerful CLI tool for managing your knowledge base with full-text search,
    Git integration, and seamless editor workflows.

    [bold]Safe Mode:[/bold]
    Set EMDX_SAFE_MODE=1 or use --safe-mode to disable execution commands
    (cascade, delegate, recipe). Useful for read-only access
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
    # Handle --version flag
    if version:
        typer.echo(f"emdx {__version__}")
        raise typer.Exit()

    # Set up global state based on flags
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Handle --safe-mode flag by setting environment variable
    # Note: This is checked at import time, so the flag mainly serves as documentation
    # and for future commands that might check at runtime
    if safe_mode:
        os.environ["EMDX_SAFE_MODE"] = "1"


# Known subcommands of `emdx tag` — used for shorthand routing
_TAG_SUBCOMMANDS = {"add", "remove", "list", "rename", "merge", "batch", "--help", "-h", "help"}


def run() -> None:
    """Entry point for the CLI.

    Supports trailing 'help' as alternative to --help:
        emdx save help      → emdx save --help
        emdx task help      → emdx task --help
        emdx task create help → emdx task create --help

    Supports `emdx tag 42 active` shorthand for `emdx tag add 42 active`:
        When `tag` is followed by something that is NOT a known subcommand
        (i.e. a doc ID or flag), insert `add` automatically.
    """
    import sys

    # Convert trailing 'help' to '--help' for convenience
    # e.g., 'emdx save help' becomes 'emdx save --help'
    if len(sys.argv) >= 2 and sys.argv[-1] == "help":
        sys.argv[-1] = "--help"

    # Shorthand: `emdx tag 42 active` → `emdx tag add 42 active`
    # When the first arg after `tag` is not a known subcommand, insert `add`.
    _rewrite_tag_shorthand(sys.argv)

    app()


def _rewrite_tag_shorthand(argv: list[str]) -> None:
    """Insert 'add' after 'tag' when the next token isn't a subcommand.

    Handles global flags (--verbose, --quiet, etc.) that may appear before 'tag'.
    Mutates argv in-place.
    """
    # Find the position of 'tag' in argv (skip argv[0] which is the program name)
    try:
        tag_idx = next(
            i for i in range(1, len(argv))
            if argv[i] == "tag"
        )
    except StopIteration:
        return

    # Check the token immediately after 'tag'
    next_idx = tag_idx + 1
    if next_idx >= len(argv):
        return  # `emdx tag` with no args — let Typer show help

    next_token = argv[next_idx]
    if next_token not in _TAG_SUBCOMMANDS:
        # Not a known subcommand — insert 'add' so `emdx tag 42 active`
        # becomes `emdx tag add 42 active`
        argv.insert(next_idx, "add")


if __name__ == "__main__":
    run()
