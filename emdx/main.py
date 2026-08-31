#!/usr/bin/env python3
"""
Main CLI entry point for emdx

This module uses lazy loading to keep startup cost off every invocation (#1067).
Only the core KB commands (save, find, view, edit, delete) and the db group are
imported eagerly; every other command — sub-apps (task, tag, maintain, ...) and
standalone commands (status, prime, context, ...) — is only imported when
actually invoked, via the registry below.
"""

import typer

from emdx.utils.lazy_group import LazyTyperGroup, register_aliases, register_lazy_commands

# =============================================================================
# LAZY COMMANDS - defer import until invoked
# =============================================================================
# Format: "command_name": "module.path:object_name"
# The target may be a Typer sub-app (dispatched as a group) or a plain
# command function (wrapped in a single Typer command on load).
# IMPORTANT: Register BEFORE any Typer app creation
LAZY_SUBCOMMANDS = {
    "explore": "emdx.commands.explore:app",
    "distill": "emdx.commands.distill:app",
    "compact": "emdx.commands.compact:app",
    "maintain": "emdx.commands.maintain:app",
    "labs": "emdx.commands.labs:app",
    "wiki": "emdx.commands.wiki:wiki_app",
    "task": "emdx.commands.tasks:app",
    "tag": "emdx.commands.tags:app",
    "trash": "emdx.commands.trash:app",
    "epic": "emdx.commands.epics:app",
    "briefing": "emdx.commands.briefing:app",
    "config": "emdx.commands.config_cmd:app",
    "kb": "emdx.commands.kb_cmd:app",
    "context": "emdx.commands.context:context",
    "diff": "emdx.commands.history:diff",
    "gist": "emdx.commands.gist:create",
    "gui": "emdx.ui.gui:gui",
    "history": "emdx.commands.history:history",
    "prime": "emdx.commands.prime:prime",
    "serve": "emdx.commands.serve:serve",
    "setup": "emdx.commands.setup:setup",
    "stale": "emdx.commands.stale:stale_command",
    "status": "emdx.commands.status:status",
    "touch": "emdx.commands.stale:touch_command",
}

# Pre-computed help strings so --help doesn't trigger imports.
# These must match the first line of each command's docstring so `emdx --help`
# reads the same as it would with eager registration.
LAZY_HELP = {
    "explore": "Explore what your knowledge base knows",
    "distill": "Distill KB content into audience-aware summaries",
    "compact": "Reduce KB redundancy through AI synthesis",
    "maintain": "Maintenance and analysis tools",
    "labs": "Experimental commands (may change or be removed)",
    "wiki": "Auto-wiki from your knowledge base",
    "task": "Agent work queue",
    "tag": "Manage document tags",
    "trash": "Manage deleted documents",
    "epic": "Manage task epics",
    "briefing": "Show recent emdx activity briefing",
    "config": "Manage emdx settings",
    "kb": "Named knowledge bases (isolated databases)",
    "context": "Walk the wiki link graph and assemble a context bundle.",
    "diff": "Show diff between current content and a previous version.",
    "gist": "Create or update a GitHub Gist from a document.",
    "gui": "TUI browser for the EMDX knowledge base.",
    "history": "Show version history for a document.",
    "prime": "Output priming context for Claude Code session injection.",
    "serve": "Start a JSON-RPC server over stdin/stdout for IDE integrations.",
    "setup": "Install emdx integrations (Claude Code skills).",
    "stale": "Show documents needing review, grouped by urgency tier.",
    "status": "Show knowledge base status and health.",
    "touch": "Mark documents as reviewed without incrementing view count.",
}


# Register lazy commands BEFORE importing any Typer apps
# This ensures the registry is populated when LazyTyperGroup is instantiated
register_lazy_commands(LAZY_SUBCOMMANDS, LAZY_HELP)

# Register top-level command aliases (alias -> canonical name)
register_aliases({"show": "view", "list": "find", "recent": "find"})

# =============================================================================
# EAGER IMPORTS - Core KB commands (fast, always needed)
# Imports are after lazy registration - this is intentional for the loading pattern
# =============================================================================
from emdx.commands.core import app as core_app  # noqa: E402
from emdx.commands.db_manage import app as db_app  # noqa: E402

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


# Everything else — tag, trash, task, wiki, maintain, briefing, config, and
# the standalone commands (context, prime, status, gui, serve, gist,
# history/diff, stale/touch) — is lazy-loaded (see LAZY_SUBCOMMANDS): the
# combined imports otherwise dominate CLI startup (#1067)

# Add db as a subcommand group
app.add_typer(db_app, name="db", help="Database management")


# Callback for global options
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
    kb: str | None = typer.Option(
        None,
        "--kb",
        help="Use a named knowledge base for this invocation (see `emdx kb list`)",
        envvar="EMDX_KB",
        show_envvar=True,
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
        # Deferred: emdx.__version__ resolves via importlib.metadata (~14ms),
        # which shouldn't be paid on invocations that never print the version
        from emdx import __version__

        typer.echo(f"emdx {__version__}")
        raise typer.Exit()

    # Set up global state based on flags
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet are mutually exclusive", err=True)
        raise typer.Exit(1)

    # --kb selects a named knowledge base; export it so every get_db_path()
    # call in this process (and child processes) agrees on the choice.
    from emdx.config.knowledge_bases import KnowledgeBaseError

    try:
        if kb:
            import os

            os.environ["EMDX_KB"] = kb
            # The global connection resolved its path at import time (before
            # this flag was parsed) — re-point it so the whole process agrees.
            from emdx.config.settings import get_db_path
            from emdx.database import connection

            connection.db_connection.db_path = get_db_path()

        # Ensure database schema is up to date (idempotent, runs pending migrations)
        # `emdx kb create` must be able to target a KB that doesn't exist yet.
        if ctx.invoked_subcommand is not None and ctx.invoked_subcommand != "kb":
            from emdx.database import db

            db.ensure_schema()
    except KnowledgeBaseError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None


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

    Supports `emdx list` / `emdx recent [N]` as working shorthand for
    `emdx find --all` / `emdx find --recent N` (see #1130):
        `list` and `recent` are registered as top-level *name* aliases for
        `find`, but aliasing only renames the resolved command — it doesn't
        imply a flag, so a bare `emdx list` still hit find's "provide search
        terms..." error. Inject the flag the alias name implies whenever the
        rest of the invocation doesn't already supply search criteria of its
        own.
    """
    import sys

    # Convert trailing 'help' to '--help' for convenience
    # e.g., 'emdx save help' becomes 'emdx save --help'
    if len(sys.argv) >= 2 and sys.argv[-1] == "help":
        sys.argv[-1] = "--help"

    # Shorthand: `emdx tag 42 active` → `emdx tag add 42 active`
    # When the first arg after `tag` is not a known subcommand, insert `add`.
    _rewrite_tag_shorthand(sys.argv)

    # Shorthand: `emdx list` → `emdx find --all`, `emdx recent [N]` →
    # `emdx find --recent [N]`.
    _rewrite_list_recent_shorthand(sys.argv)

    app()


# Flags that already give `find` valid search criteria on their own — when
# any of these follow `list`/`recent`, the alias shorthand below leaves the
# invocation untouched rather than injecting a possibly-conflicting flag.
_FIND_CRITERIA_FLAGS = {
    "--all",
    "-a",
    "--tags",
    "--tag",
    "--tag-search",
    "-t",
    "--recent",
    "--similar",
    "--context",
    "--created-after",
    "--created-before",
    "--modified-after",
    "--modified-before",
}


def _rewrite_list_recent_shorthand(argv: list[str]) -> None:
    """Insert the implied flag after a bare `list`/`recent` alias invocation.

    `emdx list` -> `emdx find --all`
    `emdx recent` -> `emdx find --recent 10`
    `emdx recent 20` -> `emdx find --recent 20`

    Left untouched (mutation-free) when the rest of the invocation already
    supplies find criteria of its own (`--tags`, `--all`, a non-numeric
    search query, etc.) — those cases keep working exactly as a plain
    `find` alias, same as before this shorthand existed.

    Only fires when `list`/`recent` is the top-level command itself (the
    first non-flag token after `emdx`, skipping leading global flags like
    `--verbose`). A subcommand's own `list` verb — `emdx task list`,
    `emdx tag list`, `emdx task dep list` — is a different command with its
    own flags and must never be rewritten into a `find` invocation.
    Mutates argv in-place.
    """
    try:
        idx = next(i for i in range(1, len(argv)) if not argv[i].startswith("-"))
    except StopIteration:
        return

    if argv[idx] not in ("list", "recent"):
        return

    cmd = argv[idx]
    rest = argv[idx + 1 :]

    if rest and rest[0] in ("--help", "-h"):
        return

    if any(token in _FIND_CRITERIA_FLAGS for token in rest):
        return

    has_query = bool(rest) and not rest[0].startswith("-")

    if cmd == "list":
        if not has_query:
            argv.insert(idx + 1, "--all")
    else:  # recent
        if has_query and rest[0].isdigit():
            # `emdx recent 20` -> `emdx find --recent 20`
            argv[idx + 1] = "--recent"
            argv.insert(idx + 2, rest[0])
        elif not has_query:
            argv[idx + 1 : idx + 1] = ["--recent", "10"]


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
