"""
Theme-aware color helpers for Rich markup.

Rich markup like [red]text[/red] uses hardcoded ANSI colors that don't
respect Textual themes. This module provides helpers to get theme-appropriate
colors for use in Rich markup within the TUI.
"""

from typing import Optional

from textual.app import App

# Semantic color names to standard Rich color fallbacks
# Used when no app context is available (e.g., CLI commands)
FALLBACK_COLORS = {
    "error": "red",
    "success": "green",
    "warning": "yellow",
    "primary": "cyan",
    "secondary": "magenta",
    "accent": "bright_magenta",
    "muted": "dim",
    "text": "white",
}


def get_theme_color(app: Optional[App], semantic: str) -> str:
    """
    Get a Rich-compatible color string for a semantic color name.

    Args:
        app: The Textual App instance (can be None for fallback behavior)
        semantic: Semantic color name: 'error', 'success', 'warning',
                 'primary', 'secondary', 'accent', 'muted', 'text'

    Returns:
        Color string usable in Rich markup (hex like '#F85149' or name like 'red')
    """
    if app is None:
        return FALLBACK_COLORS.get(semantic, semantic)

    # Try to get theme from app
    try:
        theme_name = app.theme
        theme = app.get_theme(theme_name)
        if theme is None:
            return FALLBACK_COLORS.get(semantic, semantic)
    except (AttributeError, TypeError):
        return FALLBACK_COLORS.get(semantic, semantic)

    # Map semantic names to theme properties
    color_map = {
        "error": theme.error,
        "success": theme.success,
        "warning": theme.warning,
        "primary": theme.primary,
        "secondary": theme.secondary,
        "accent": theme.accent,
        "text": theme.foreground,
        "muted": theme.foreground,  # Will be styled with dim
    }

    color = color_map.get(semantic)
    if color:
        return color

    # Fall back to standard colors
    return FALLBACK_COLORS.get(semantic, semantic)


def themed(app: Optional[App], semantic: str, text: str) -> str:
    """
    Create Rich markup with theme-aware color.

    Args:
        app: The Textual App instance (can be None)
        semantic: Semantic color name
        text: Text to wrap in color markup

    Returns:
        Rich markup string like '[#F85149]text[/]'

    Example:
        >>> themed(app, 'error', 'Failed!')
        '[#F85149]Failed![/]'
    """
    color = get_theme_color(app, semantic)

    # Special handling for 'muted' - add dim style
    if semantic == "muted":
        return f"[dim {color}]{text}[/]"

    return f"[{color}]{text}[/]"


def themed_bold(app: Optional[App], semantic: str, text: str) -> str:
    """
    Create bold Rich markup with theme-aware color.

    Args:
        app: The Textual App instance (can be None)
        semantic: Semantic color name
        text: Text to wrap

    Returns:
        Rich markup string with bold style
    """
    color = get_theme_color(app, semantic)
    return f"[bold {color}]{text}[/]"


# Convenience functions for common patterns
def error_text(app: Optional[App], text: str) -> str:
    """Create error-colored text."""
    return themed(app, "error", text)


def success_text(app: Optional[App], text: str) -> str:
    """Create success-colored text."""
    return themed(app, "success", text)


def warning_text(app: Optional[App], text: str) -> str:
    """Create warning-colored text."""
    return themed(app, "warning", text)


def muted_text(app: Optional[App], text: str) -> str:
    """Create muted/secondary text."""
    return themed(app, "muted", text)


def primary_text(app: Optional[App], text: str) -> str:
    """Create primary-colored text."""
    return themed(app, "primary", text)


# Status color mapping for task states
def get_status_color(app: Optional[App], status: str) -> str:
    """
    Get theme-aware color for task status.

    Args:
        app: The Textual App instance
        status: Task status ('open', 'active', 'blocked', 'done', 'failed')

    Returns:
        Color string for Rich markup
    """
    status_semantic_map = {
        "open": "text",
        "active": "success",
        "blocked": "warning",
        "done": "muted",
        "failed": "error",
    }
    semantic = status_semantic_map.get(status, "text")
    return get_theme_color(app, semantic)


def status_text(app: Optional[App], status: str, text: str) -> str:
    """
    Create status-colored text.

    Args:
        app: The Textual App instance
        status: Task status
        text: Text to color

    Returns:
        Rich markup string
    """
    color = get_status_color(app, status)
    if status == "done":
        return f"[dim {color}]{text}[/]"
    return f"[{color}]{text}[/]"
