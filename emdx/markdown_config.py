#!/usr/bin/env python3
"""
Configuration for markdown rendering in emdx.

This module provides configuration options for improving markdown rendering,
including code syntax highlighting themes and formatting options.
"""

import os

from rich.console import Console
from rich.markdown import Markdown


class MarkdownConfig:
    """Configuration for markdown rendering."""

    # Code themes that work well for different terminal backgrounds
    THEMES = {
        "dark": {
            "default": "monokai",
            "alternatives": ["dracula", "nord", "one-dark", "gruvbox-dark"],
        },
        "light": {"default": "manni", "alternatives": ["tango", "perldoc", "friendly", "colorful"]},
    }

    @staticmethod
    def get_code_theme():
        """Get the appropriate code theme based on terminal background."""
        # Check environment variable for user preference
        theme = os.environ.get("EMDX_CODE_THEME")
        if theme:
            return theme

        # Try to detect terminal background (this is a simplified approach)
        # In practice, you might want to use more sophisticated detection
        # or let users configure this in a config file
        terminal_bg = os.environ.get("COLORFGBG", "").split(";")[-1]

        # If background is light (15 is white in many terminals)
        if terminal_bg == "15":
            return MarkdownConfig.THEMES["light"]["default"]
        else:
            return MarkdownConfig.THEMES["dark"]["default"]

    @staticmethod
    def create_markdown(content, code_theme=None):
        """Create a Rich Markdown object with optimal settings."""
        if code_theme is None:
            code_theme = MarkdownConfig.get_code_theme()

        return Markdown(
            content,
            code_theme=code_theme,
            hyperlinks=True,  # Enable clickable links
            inline_code_lexer="python",  # Default lexer for inline code
        )

    @staticmethod
    def render_markdown(content, console=None, code_theme=None):
        """Render markdown content to console with optimal settings."""
        if console is None:
            console = Console()

        md = MarkdownConfig.create_markdown(content, code_theme)
        console.print(md)
        return console


# Example enhanced markdown rendering function
def render_enhanced_markdown(content, code_theme=None):
    """
    Render markdown with enhanced formatting.

    This function can be used as a drop-in replacement for basic markdown rendering
    with better code syntax highlighting and formatting.
    """
    console = Console(
        force_terminal=True,  # Ensure colors work
        width=None,  # Use full terminal width
        highlight=True,  # Enable syntax highlighting
        markup=True,  # Enable Rich markup
    )

    return MarkdownConfig.render_markdown(content, console, code_theme)


# Utility function to list available themes
def list_available_themes():
    """List all available code themes for both dark and light terminals."""
    print("Available code themes:")
    print("\nFor dark terminals:")
    for theme in MarkdownConfig.THEMES["dark"]["alternatives"]:
        print(f"  - {theme}")
    print("\nFor light terminals:")
    for theme in MarkdownConfig.THEMES["light"]["alternatives"]:
        print(f"  - {theme}")
    print("\nSet EMDX_CODE_THEME environment variable to use a specific theme.")
