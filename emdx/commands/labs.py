"""
Labs namespace for experimental emdx commands.

Commands under 'emdx labs' are experimental and may be changed or removed
in future releases. They are fully functional but their APIs are not yet
committed to for 1.0 stability.
"""

from __future__ import annotations

import sys

import typer

from emdx.commands.backup import app as cloud_backup_app
from emdx.commands.briefing import briefing as briefing_command
from emdx.commands.code_drift import code_drift_command
from emdx.commands.compact import app as compact_app
from emdx.commands.context import context as context_command
from emdx.commands.distill import app as distill_app
from emdx.commands.explore import app as explore_app
from emdx.commands.labs_ask import (
    ask_app,
    watch_app,
)
from emdx.commands.labs_ask import (
    wander as wander_command,
)
from emdx.commands.maintain import contradictions, drift, gaps
from emdx.commands.maintain_index import (
    entities_command,
    wikify_command,
)
from emdx.commands.serve import serve as serve_command
from emdx.commands.wiki import wiki_app

app = typer.Typer(
    name="labs",
    help="Experimental commands (may change or be removed in future releases)",
    rich_markup_mode="rich",
)


_WARNING_PRINTED = False


@app.callback()
def labs_callback(ctx: typer.Context) -> None:
    """Print experimental warning before any labs subcommand."""
    global _WARNING_PRINTED  # noqa: PLW0603
    if not _WARNING_PRINTED:
        print(
            "Warning: experimental command — may change or be removed in a future release.",
            file=sys.stderr,
        )
        _WARNING_PRINTED = True


# =============================================================================
# Register experimental commands
# =============================================================================

# Wiki (entire group)
app.add_typer(wiki_app, name="wiki", help="Auto-wiki from your knowledge base (experimental)")

# Explore (topic clustering)
app.add_typer(
    explore_app,
    name="explore",
    help="Explore what your knowledge base knows (experimental)",
)

# Distill (audience-aware synthesis)
app.add_typer(
    distill_app,
    name="distill",
    help="Distill KB content into audience-aware summaries (experimental)",
)

# Compact (AI-powered merge)
app.add_typer(
    compact_app,
    name="compact",
    help="Reduce KB redundancy through AI synthesis (experimental)",
)

# Context (graph-walk)
app.command(name="context")(context_command)

# Briefing (activity summary)
app.command(name="briefing")(briefing_command)

# Serve (JSON-RPC for IDE integrations)
app.command(name="serve")(serve_command)

# =============================================================================
# Labs maintain — experimental maintenance subcommands
# =============================================================================

labs_maintain_app = typer.Typer(
    help="Experimental maintenance commands (moved from emdx maintain)",
)

labs_maintain_app.command(name="drift")(drift)
labs_maintain_app.command(name="gaps")(gaps)
labs_maintain_app.command(name="contradictions")(contradictions)
labs_maintain_app.command(name="code-drift")(code_drift_command)
labs_maintain_app.command(name="wikify")(wikify_command)
labs_maintain_app.command(name="entities")(entities_command)
labs_maintain_app.add_typer(
    cloud_backup_app,
    name="cloud-backup",
    help="Cloud backup operations (experimental)",
)

app.add_typer(
    labs_maintain_app,
    name="maintain",
    help="Experimental maintenance subcommands",
)

# Ask (AI-powered Q&A — moved from find --ask/--think/--debug)
app.add_typer(
    ask_app,
    name="ask",
    help="AI-powered question answering (experimental)",
)

# Wander (serendipity — moved from find --wander)
app.command(name="wander")(wander_command)

# Watch (standing queries — moved from find --watch*)
app.add_typer(
    watch_app,
    name="watch",
    help="Standing queries that alert on new matches (experimental)",
)
