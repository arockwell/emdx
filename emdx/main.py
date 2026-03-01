#!/usr/bin/env python3
"""
Main CLI entry point for emdx

This module uses lazy loading for heavy commands to improve startup performance.
Core KB commands (save, find, view, tag, etc.) are imported eagerly since they're
fast. Heavy commands (distill, explore, etc.) are only imported when
actually invoked.
"""

import typer

from emdx import __version__
from emdx.utils.lazy_group import LazyTyperGroup, register_aliases, register_lazy_commands

# =============================================================================
# LAZY COMMANDS - Heavy features (defer import until invoked)
# =============================================================================
# Format: "command_name": "module.path:object_name"
# IMPORTANT: Register BEFORE any Typer app creation
LAZY_SUBCOMMANDS = {
    "explore": "emdx.commands.explore:app",
    "distill": "emdx.commands.distill:app",
}

# Pre-computed help strings so --help doesn't trigger imports
LAZY_HELP = {
    "explore": "Explore what your knowledge base knows",
    "distill": "Distill KB content into audience-aware summaries",
}


# Register lazy commands BEFORE importing any Typer apps
# This ensures the registry is populated when LazyTyperGroup is instantiated
register_lazy_commands(LAZY_SUBCOMMANDS, LAZY_HELP)

# Register top-level command aliases (alias -> canonical name)
register_aliases({"show": "view"})

# =============================================================================
# EAGER IMPORTS - Core KB commands (fast, always needed)
# Imports are after lazy registration - this is intentional for the loading pattern
# =============================================================================
from emdx.commands.briefing import briefing as briefing_command  # noqa: E402
from emdx.commands.core import app as core_app  # noqa: E402
from emdx.commands.gist import app as gist_app  # noqa: E402
from emdx.commands.maintain import app as maintain_app  # noqa: E402
from emdx.commands.prime import prime as prime_command  # noqa: E402
from emdx.commands.serve import serve as serve_command  # noqa: E402
from emdx.commands.status import status as status_command  # noqa: E402
from emdx.commands.tags import app as tag_app  # noqa: E402
from emdx.commands.tasks import app as tasks_app  # noqa: E402
from emdx.commands.trash import app as trash_app  # noqa: E402
from emdx.ui.gui import gui as gui_command  # noqa: E402

# Create main app with lazy loading support
app = typer.Typer(
    name="emdx",
    help="A powerful knowledge base for developers and AI agents",
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


# Gist commands
for command in gist_app.registered_commands:
    app.registered_commands.append(command)

# Tag commands (subcommand group: emdx tag <subcommand>)
app.add_typer(tag_app, name="tag", help="Manage document tags")

# Trash commands (subcommand group: emdx trash <subcommand>)
app.add_typer(trash_app, name="trash", help="Manage deleted documents")

# Add tasks as a subcommand group
app.add_typer(tasks_app, name="task", help="Agent work queue")

# Add maintain as a subcommand group (includes maintain, cleanup, cleanup-dirs)
app.add_typer(maintain_app, name="maintain", help="Maintenance and analysis tools")

# Add the prime command for Claude session priming
app.command(name="prime")(prime_command)

# Add the status command for consolidated project overview
app.command(name="status")(status_command)

# Add the briefing command for activity summary
app.command(name="briefing")(briefing_command)

# Add the gui command for interactive TUI browser
app.command(name="gui")(gui_command)

# Add the serve command for IDE integrations (JSON-RPC over stdin/stdout)
app.command(name="serve")(serve_command)


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
) -> None:
    """
    emdx - A knowledge base for developers and AI agents

    Save research, manage tasks, and search everything
    with full-text and semantic search.

    Examples:

    Save a file:
        [cyan]emdx save --file README.md[/cyan]

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
    # Handle --version flag
    if version:
        typer.echo(f"emdx {__version__}")
        raise typer.Exit()

    # Set up global state based on flags
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Ensure database schema is up to date (idempotent, runs pending migrations)
    if ctx.invoked_subcommand is not None:
        from emdx.database import db

        db.ensure_schema()


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
        tag_idx = next(i for i in range(1, len(argv)) if argv[i] == "tag")
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
