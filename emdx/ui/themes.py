"""
EMDX TUI Theme Definitions.

This module defines custom themes for the EMDX TUI application
using Textual's theming system.
"""

from typing import Any

from textual.theme import Theme

# =============================================================================
# EMDX Dark Theme (Default)
# Modern dark theme with cyan/blue accents inspired by terminal aesthetics
# =============================================================================

EMDX_DARK = Theme(
    name="emdx-dark",
    primary="#0178D4",      # Blue - matches Textual default
    secondary="#004578",    # Darker blue - secondary accent
    accent="#ffa62b",       # Orange - selection/highlight
    foreground="#e0e0e0",   # Primary text
    background="#121212",   # Dark background
    surface="#1e1e1e",      # Slightly lighter for cards/panels
    panel="#252526",        # Sidebar backgrounds
    boost="#2d2d2d",        # Status bars, headers
    success="#4EBF71",      # Green - success states
    warning="#ffa62b",      # Orange - warning states
    error="#ba3c5b",        # Red - error states
    dark=True,
)

# =============================================================================
# EMDX Light Theme
# Clean, professional light theme with blue accents
# =============================================================================

EMDX_LIGHT = Theme(
    name="emdx-light",
    primary="#0969DA",      # Blue - main accent
    secondary="#8250DF",    # Purple - secondary accent
    accent="#BF3989",       # Magenta - selection/highlight
    foreground="#1F2328",   # Primary text (near black)
    background="#FFFFFF",   # Pure white
    surface="#F6F8FA",      # Light gray for cards/panels
    panel="#F0F2F5",        # Slightly darker for sidebars
    boost="#DFE3E8",        # Status bars, headers
    success="#1A7F37",      # Dark green - visible on light
    warning="#9A6700",      # Dark amber - visible on light
    error="#CF222E",        # Dark red - visible on light
    dark=False,
)

# =============================================================================
# EMDX Nord Theme
# Muted, low-contrast theme based on the popular Nord palette
# =============================================================================

EMDX_NORD = Theme(
    name="emdx-nord",
    primary="#88C0D0",      # Frost blue
    secondary="#B48EAD",    # Aurora purple
    accent="#EBCB8B",       # Aurora yellow
    foreground="#ECEFF4",   # Snow storm
    background="#2E3440",   # Polar night
    surface="#3B4252",      # Polar night (lighter)
    panel="#434C5E",        # Polar night (lighter)
    boost="#4C566A",        # Polar night (lightest)
    success="#A3BE8C",      # Aurora green
    warning="#EBCB8B",      # Aurora yellow
    error="#BF616A",        # Aurora red
    dark=True,
)

# =============================================================================
# EMDX Solarized Dark Theme
# Classic Solarized dark for those who prefer it
# =============================================================================

EMDX_SOLARIZED_DARK = Theme(
    name="emdx-solarized-dark",
    primary="#268BD2",      # Blue
    secondary="#6C71C4",    # Violet
    accent="#2AA198",       # Cyan
    foreground="#839496",   # Base0
    background="#002B36",   # Base03
    surface="#073642",      # Base02
    panel="#073642",        # Base02
    boost="#586E75",        # Base01
    success="#859900",      # Green
    warning="#B58900",      # Yellow
    error="#DC322F",        # Red
    dark=True,
)

# =============================================================================
# EMDX Solarized Light Theme
# Classic Solarized light variant
# =============================================================================

EMDX_SOLARIZED_LIGHT = Theme(
    name="emdx-solarized-light",
    primary="#268BD2",      # Blue
    secondary="#6C71C4",    # Violet
    accent="#2AA198",       # Cyan
    foreground="#657B83",   # Base00
    background="#FDF6E3",   # Base3
    surface="#EEE8D5",      # Base2
    panel="#EEE8D5",        # Base2
    boost="#93A1A1",        # Base1
    success="#859900",      # Green
    warning="#B58900",      # Yellow
    error="#DC322F",        # Red
    dark=False,
)

# =============================================================================
# Theme Registry
# =============================================================================

EMDX_THEMES: dict[str, Theme] = {
    "emdx-dark": EMDX_DARK,
    "emdx-light": EMDX_LIGHT,
    "emdx-nord": EMDX_NORD,
    "emdx-solarized-dark": EMDX_SOLARIZED_DARK,
    "emdx-solarized-light": EMDX_SOLARIZED_LIGHT,
}

# Code theme mapping (Pygments themes)
CODE_THEME_MAP: dict[str, str] = {
    "emdx-dark": "monokai",
    "emdx-light": "tango",
    "emdx-nord": "nord",
    "emdx-solarized-dark": "solarized-dark",
    "emdx-solarized-light": "solarized-light",
    # Built-in Textual themes
    "textual-dark": "monokai",
    "textual-light": "tango",
    "nord": "nord",
    "gruvbox": "gruvbox-dark",
    "tokyo-night": "one-dark",
    "dracula": "dracula",
}

# Light themes for detection
LIGHT_THEMES: set[str] = {
    "emdx-light",
    "emdx-solarized-light",
    "textual-light",
}


def register_all_themes(app: Any) -> None:
    """
    Register all custom EMDX themes with the app.

    Args:
        app: The Textual App instance
    """
    for theme in EMDX_THEMES.values():
        app.register_theme(theme)


def get_code_theme(theme_name: str) -> str:
    """
    Get the matching Pygments code theme for syntax highlighting.

    Args:
        theme_name: The main theme name

    Returns:
        Pygments theme name for code highlighting
    """
    return CODE_THEME_MAP.get(theme_name, "monokai")


def is_dark_theme(theme_name: str) -> bool:
    """
    Check if a theme is dark or light.

    Args:
        theme_name: The theme name to check

    Returns:
        True if dark theme, False if light theme
    """
    return theme_name not in LIGHT_THEMES


def get_theme_names() -> list[str]:
    """Get list of all available EMDX theme names."""
    return list(EMDX_THEMES.keys())


def get_theme_display_info() -> list[dict[str, str]]:
    """
    Get display information for theme selector UI.

    Returns:
        List of dicts with 'name', 'display_name', 'description'
    """
    return [
        {
            "name": "emdx-dark",
            "display_name": "EMDX Dark",
            "description": "Modern dark theme with cyan accents",
        },
        {
            "name": "emdx-light",
            "display_name": "EMDX Light",
            "description": "Clean professional light theme",
        },
        {
            "name": "emdx-nord",
            "display_name": "EMDX Nord",
            "description": "Muted dark theme based on Nord palette",
        },
        {
            "name": "emdx-solarized-dark",
            "display_name": "Solarized Dark",
            "description": "Classic Solarized dark theme",
        },
        {
            "name": "emdx-solarized-light",
            "display_name": "Solarized Light",
            "description": "Classic Solarized light theme",
        },
    ]


# Theme pairs for quick toggle (dark <-> light)
THEME_PAIRS: dict[str, str] = {
    "emdx-dark": "emdx-light",
    "emdx-light": "emdx-dark",
    "emdx-nord": "emdx-light",  # Nord (dark) -> Light
    "emdx-solarized-dark": "emdx-solarized-light",
    "emdx-solarized-light": "emdx-solarized-dark",
}


def get_opposite_theme(theme_name: str) -> str:
    """
    Get the opposite (dark/light) theme for quick toggle.

    Args:
        theme_name: Current theme name

    Returns:
        Paired theme name for toggle, or emdx-dark as fallback
    """
    return THEME_PAIRS.get(theme_name, "emdx-dark")


def get_theme_indicator(theme_name: str) -> str:
    """
    Get a short theme indicator for status bars.

    Args:
        theme_name: Current theme name

    Returns:
        Short string like "🌙" for dark or "☀️" for light
    """
    if is_dark_theme(theme_name):
        return "🌙"
    return "☀️"
