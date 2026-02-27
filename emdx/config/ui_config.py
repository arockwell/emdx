"""
EMDX UI Configuration.

Handles persistence of UI preferences including theme selection and layout.
Config is stored in ~/.config/emdx/ui_config.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from .constants import EMDX_CONFIG_DIR


class LayoutConfig(TypedDict):
    """Panel layout configuration for the TUI."""

    list_height_pct: int
    sidebar_width_pct: int
    sidebar_threshold: int


# Layout defaults: list panel gets 40% of vertical space, sidebar gets 30% of horizontal
DEFAULT_LAYOUT: LayoutConfig = {
    "list_height_pct": 40,
    "sidebar_width_pct": 30,
    "sidebar_threshold": 120,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "theme": "emdx-dark",
    "code_theme": "auto",
    "layout": {**DEFAULT_LAYOUT},
}


def get_ui_config_path() -> Path:
    """
    Get path to UI config file.

    Returns:
        Path to ~/.config/emdx/ui_config.json
    """
    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "ui_config.json"


def load_ui_config() -> dict[str, Any]:
    """
    Load UI configuration from file.

    Returns:
        Config dict, or defaults if file doesn't exist or is invalid
    """
    path = get_ui_config_path()
    if path.exists():
        try:
            config = json.loads(path.read_text())
            # Merge with defaults to handle missing keys
            return {**DEFAULT_CONFIG, **config}
        except (json.JSONDecodeError, OSError):
            # Return defaults on error
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_ui_config(config: dict[str, Any]) -> None:
    """
    Save UI configuration to file.

    Args:
        config: Configuration dict to save
    """
    path = get_ui_config_path()
    try:
        path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError:
        # Silently fail - config is non-critical
        pass


def get_theme() -> str:
    """
    Get current theme name from config.

    Returns:
        Theme name string
    """
    return str(load_ui_config().get("theme", "emdx-dark"))


def set_theme(theme_name: str) -> None:
    """
    Set and persist theme preference.

    Args:
        theme_name: Name of theme to set
    """
    config = load_ui_config()
    config["theme"] = theme_name
    save_ui_config(config)


def get_code_theme() -> str:
    """
    Get code syntax highlighting theme from config.

    Returns:
        Code theme name, or "auto" for automatic detection
    """
    return str(load_ui_config().get("code_theme", "auto"))


def get_layout() -> LayoutConfig:
    """Get panel layout configuration, merged with defaults."""
    raw = load_ui_config().get("layout", {})
    if not isinstance(raw, dict):
        return {**DEFAULT_LAYOUT}
    return {**DEFAULT_LAYOUT, **raw}  # type: ignore[typeddict-item]


def set_layout(layout: LayoutConfig) -> None:
    """Persist panel layout configuration."""
    config = load_ui_config()
    config["layout"] = dict(layout)
    save_ui_config(config)
