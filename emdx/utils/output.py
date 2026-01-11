"""Shared console output utilities."""

from rich.console import Console

# Shared console instance for all CLI output
# Uses force_terminal=True to ensure color output even when not connected to a terminal
console = Console(force_terminal=True, color_system="auto")
