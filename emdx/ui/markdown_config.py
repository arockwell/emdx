#!/usr/bin/env python3
"""
Configuration for markdown rendering in emdx.

This module provides configuration options for improving markdown rendering,
including code syntax highlighting themes and formatting options.
"""

import os

from rich.markdown import Markdown

from ..utils.output import console as shared_console


class MarkdownConfig:
    """Configuration for markdown rendering."""

    # Code themes that work well for different terminal backgrounds
    THEMES = {
        "dark": {
            "default": "monokai",
            "alternatives": ["dracula", "nord", "one-dark", "gruvbox-dark"],
        },
        "light": {
            "default": "tango",
            "alternatives": ["manni", "perldoc", "friendly", "colorful"],
        },
    }

    @staticmethod
    def get_code_theme():
        """Get the appropriate code theme based on UI config or terminal background."""
        # Check environment variable for user preference (highest priority)
        theme = os.environ.get("EMDX_CODE_THEME")
        if theme:
            return theme

        # Try to get theme from UI config
        try:
            from emdx.config.ui_config import load_ui_config
            from emdx.ui.themes import get_code_theme as get_theme_code_theme

            config = load_ui_config()
            code_theme = config.get("code_theme", "auto")

            if code_theme != "auto":
                return code_theme

            # Auto mode: derive from main UI theme
            main_theme = config.get("theme", "emdx-dark")
            return get_theme_code_theme(main_theme)
        except ImportError:
            # UI config not available, fall back to terminal detection
            pass

        # Try to detect terminal background (fallback approach)
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
            inline_code_theme=code_theme,
            hyperlinks=True,
        )

    @staticmethod
    def render_markdown(content, console=None, code_theme=None):
        """Render markdown content to console with optimal settings."""
        if console is None:
            console = shared_console

        md = MarkdownConfig.create_markdown(content, code_theme)
        console.print(md)
        return console


def render_enhanced_markdown(content, code_theme=None):
    """
    Render markdown with enhanced formatting.

    This function can be used as a drop-in replacement for basic markdown rendering
    with better code syntax highlighting and formatting.
    """
    return MarkdownConfig.render_markdown(content, shared_console, code_theme)


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
