#!/usr/bin/env python3
"""
Configuration for markdown rendering in emdx.

This module provides configuration options for improving markdown rendering,
including code syntax highlighting themes and formatting options.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from textual.widgets import RichLog

from rich.console import Console
from rich.markdown import Markdown

from ..utils.output import console as shared_console


class MarkdownConfig:
    """Configuration for markdown rendering."""

    # Code themes that work well for different terminal backgrounds
    THEMES: dict[str, dict[str, Any]] = {
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
    def get_code_theme() -> str:
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
                return str(code_theme)

            # Auto mode: derive from main UI theme
            main_theme = config.get("theme", "emdx-dark")
            return str(get_theme_code_theme(main_theme))
        except ImportError:
            pass  # Fall back to terminal detection

        # Try to detect terminal background (fallback approach)
        terminal_bg = os.environ.get("COLORFGBG", "").split(";")[-1]

        # If background is light (15 is white in many terminals)
        if terminal_bg == "15":
            return str(MarkdownConfig.THEMES["light"]["default"])
        else:
            return str(MarkdownConfig.THEMES["dark"]["default"])

    @staticmethod
    def create_markdown(content: str, code_theme: str | None = None) -> Markdown:
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
    def render_markdown(
        content: str,
        console: Console | None = None,
        code_theme: str | None = None,
    ) -> Console:
        """Render markdown content to console with optimal settings."""
        if console is None:
            console = shared_console

        md = MarkdownConfig.create_markdown(content, code_theme)
        console.print(md)
        return console


MAX_PREVIEW_LENGTH = 50000


def prepare_document_content(content: str, title: str) -> str:
    """Prepare document content for markdown preview.

    Prepends a title heading if the content doesn't already start with one,
    and truncates overly long content.
    """
    if len(content) > MAX_PREVIEW_LENGTH:
        content = content[:MAX_PREVIEW_LENGTH] + "\n\n[dim]... (truncated)[/dim]"

    content_stripped = content.lstrip()
    has_title_header = content_stripped.startswith(f"# {title}") or content_stripped.startswith(
        "# "
    )

    if has_title_header:
        return content
    return f"# {title}\n\n{content}"


def render_markdown_to_richlog(
    richlog: RichLog,
    content: str,
    title: str = "Untitled",
    *,
    clear: bool = True,
) -> str:
    """Render document content as markdown into a RichLog widget.

    Handles title prepending, truncation, and fallback on render errors.
    Returns the raw content (before markdown rendering) for copy mode.

    Args:
        richlog: Target RichLog widget.
        content: Markdown content to render.
        title: Document title (prepended as heading if missing).
        clear: Whether to clear the RichLog before writing. Set to False
            when appending after a metadata preamble.
    """
    prepared = prepare_document_content(content, title)
    if clear:
        richlog.clear()

    if not prepared.strip():
        richlog.write("[dim]Empty document[/dim]")
        return content[:MAX_PREVIEW_LENGTH] if content else ""

    try:
        md = MarkdownConfig.create_markdown(prepared)
        richlog.write(md)
    except Exception:
        richlog.write(prepared)

    return content[:MAX_PREVIEW_LENGTH] if content else ""


def render_enhanced_markdown(content: str, code_theme: str | None = None) -> Console:
    """
    Render markdown with enhanced formatting.

    This function can be used as a drop-in replacement for basic markdown rendering
    with better code syntax highlighting and formatting.
    """
    return MarkdownConfig.render_markdown(content, shared_console, code_theme)


def list_available_themes() -> None:
    """List all available code themes for both dark and light terminals."""
    print("Available code themes:")
    print("\nFor dark terminals:")
    for theme in MarkdownConfig.THEMES["dark"]["alternatives"]:
        print(f"  - {theme}")
    print("\nFor light terminals:")
    for theme in MarkdownConfig.THEMES["light"]["alternatives"]:
        print(f"  - {theme}")
    print("\nSet EMDX_CODE_THEME environment variable to use a specific theme.")
