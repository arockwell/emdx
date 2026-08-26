"""Shared console output utilities."""

import json
import os
import sys
from typing import Any

from rich.console import Console
from rich.table import Table as _RichTable


def use_styling() -> bool:
    """Decide whether output should carry ANSI styling.

    FORCE_COLOR always styles (for humans piping through `less -R`, etc).
    NO_COLOR always suppresses styling, even on a real TTY.
    Otherwise styling follows whether stdout is a TTY.
    """
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _make_console() -> Console:
    styled = use_styling()
    return Console(force_terminal=styled, no_color=not styled)


# Shared console instance for all CLI output.
# Styled on a real TTY, plain (no ANSI) when stdout is piped/redirected —
# agents are the primary consumers of piped output, and stray escape
# sequences fragment IDs and other tokens they need to parse cleanly.
console = _make_console()


class Table(_RichTable):
    """rich Table that degrades to plain aligned columns when not styled.

    Drop-in replacement for `rich.table.Table` — same constructor and
    methods. Box-drawing characters aren't ANSI, so they'd otherwise
    survive a piped, non-TTY invocation even after Console stops
    emitting color; this strips them under the same conditions
    `use_styling()` uses to decide on color.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not use_styling():
            kwargs["box"] = None
            kwargs.setdefault("show_edge", False)
            kwargs.setdefault("pad_edge", False)
        super().__init__(*args, **kwargs)


def is_non_interactive() -> bool:
    """Return True when stdin is not a TTY (e.g. running inside Claude Code).

    Used to auto-confirm destructive prompts that would otherwise hang agents.
    """
    return not sys.stdin.isatty()


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout.

    Handles common non-serializable types like datetime by converting them to strings.
    """
    print(json.dumps(data, indent=2, default=str))
