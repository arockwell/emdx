"""
EMDX UI Configuration.

Handles persistence of UI preferences including theme selection.
Config is stored in ~/.config/emdx/ui_config.json
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .constants import EMDX_CONFIG_DIR


DEFAULT_CONFIG: dict[str, Any] = {
    "theme": "emdx-dark",
    "code_theme": "auto",
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
    except OSError as e:
        # Config is non-critical but log for debugging
        logger.debug("Failed to save UI config to %s: %s", path, e)


def get_theme() -> str:
    """
    Get current theme name from config.

    Returns:
        Theme name string
    """
    return load_ui_config().get("theme", "emdx-dark")


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
    return load_ui_config().get("code_theme", "auto")


def set_code_theme(theme_name: str) -> None:
    """
    Set and persist code theme preference.

    Args:
        theme_name: Name of Pygments theme, or "auto"
    """
    config = load_ui_config()
    config["code_theme"] = theme_name
    save_ui_config(config)
