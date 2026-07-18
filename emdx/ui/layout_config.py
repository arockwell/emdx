"""Panel size configuration for the TUI (#891).

Reads panel percentages from the app config (``emdx config``) and
substitutes them into view CSS. Values are read when the view modules
load, so changing them takes effect on the next ``emdx gui`` launch.

Settings:

- ``ui.list_height`` (default 40): height %% of the top list band in the
  docs and tasks browsers; the preview/detail pane gets the rest.
- ``ui.sidebar_width`` (default 30): width %% of the right sidebar in the
  docs and tasks browsers; the list gets the rest.
"""

from __future__ import annotations

from emdx.config.app_config import get_config_value

DEFAULT_LIST_HEIGHT = 40
DEFAULT_SIDEBAR_WIDTH = 30

# Clamp bounds — outside this range a panel becomes unusable or invisible.
MIN_PANEL_PERCENT = 10
MAX_PANEL_PERCENT = 90


def _clamped_percent(key: str, default: int) -> int:
    """Read an integer percentage setting, clamped to sane bounds.

    Non-numeric or missing values fall back to the default — a bad config
    value must never break the TUI.
    """
    value = get_config_value(key, default)
    try:
        pct = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(MIN_PANEL_PERCENT, min(MAX_PANEL_PERCENT, pct))


def get_list_height() -> int:
    """Height % of the top list band (preview pane gets the rest)."""
    return _clamped_percent("ui.list_height", DEFAULT_LIST_HEIGHT)


def get_sidebar_width() -> int:
    """Width % of the right sidebar (list section gets the rest)."""
    return _clamped_percent("ui.sidebar_width", DEFAULT_SIDEBAR_WIDTH)


def apply_panel_sizes(css: str) -> str:
    """Substitute panel size tokens in a view's CSS template.

    Tokens: ``__LIST_HEIGHT__``, ``__PREVIEW_HEIGHT__``,
    ``__SIDEBAR_WIDTH__``, ``__LIST_WIDTH__``. Heights and widths are
    complementary pairs so panels always fill the screen.
    """
    list_height = get_list_height()
    sidebar_width = get_sidebar_width()
    return (
        css.replace("__LIST_HEIGHT__", f"{list_height}%")
        .replace("__PREVIEW_HEIGHT__", f"{100 - list_height}%")
        .replace("__SIDEBAR_WIDTH__", f"{sidebar_width}%")
        .replace("__LIST_WIDTH__", f"{100 - sidebar_width}%")
    )
