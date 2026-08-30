"""Shared console output utilities.

rich is deliberately NOT imported at module level: importing
``rich.console``/``rich.table`` costs ~10ms, a large slice of the CLI's
startup floor (#1067), and this module is imported by nearly every command
module. ``console`` is a lazy proxy and ``Table`` is materialized on first
attribute access via the module-level ``__getattr__`` (PEP 562), so rich is
only imported when something actually renders output.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from rich.console import Console
    from rich.table import Table as Table  # redundant alias: re-export for type checkers


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
    from rich.console import Console

    styled = use_styling()
    return Console(force_terminal=styled, no_color=not styled)


class _ConsoleProxy:
    """Lazy stand-in for the shared Console instance.

    Creates the real Console on first attribute access and delegates
    everything to it, so ``from emdx.utils.output import console`` stays
    import-time cheap. Note the styling decision (``use_styling()``) is
    made at first use rather than at import time; both happen before any
    output is written, so the behavior is identical.
    """

    __slots__ = ("_real",)

    def __init__(self) -> None:
        self._real: Console | None = None

    def _load(self) -> Console:
        real = self._real
        if real is None:
            real = self._real = _make_console()
        return real

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)

    # Special methods bypass __getattr__, so the context-manager protocol —
    # used by rich internals (Progress/Live enter the console they're given)
    # — must be delegated explicitly.
    def __enter__(self) -> Console:
        return self._load().__enter__()

    def __exit__(self, *args: Any) -> None:
        self._load().__exit__(*args)


# Shared console instance for all CLI output.
# Styled on a real TTY, plain (no ANSI) when stdout is piped/redirected —
# agents are the primary consumers of piped output, and stray escape
# sequences fragment IDs and other tokens they need to parse cleanly.
console = cast("Console", _ConsoleProxy())


def _build_table_class() -> type[Table]:
    from rich.table import Table as _RichTable

    class LazyTable(_RichTable):
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

    LazyTable.__name__ = "Table"
    LazyTable.__qualname__ = "Table"
    return LazyTable


def __getattr__(name: str) -> Any:
    """Materialize the rich-backed ``Table`` class on first access (PEP 562)."""
    if name == "Table":
        table_class = _build_table_class()
        globals()["Table"] = table_class
        return table_class
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
