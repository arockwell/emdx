"""Shared console output utilities."""

import json
from typing import Any

from rich.console import Console

# Shared console instance for all CLI output
# Uses force_terminal=True to ensure color output even when not connected to a terminal
console = Console(force_terminal=True, color_system="auto")


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout.

    Handles common non-serializable types like datetime by converting them to strings.
    """
    print(json.dumps(data, indent=2, default=str))
