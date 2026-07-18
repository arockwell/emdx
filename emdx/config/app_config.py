"""EMDX application configuration.

General-purpose settings store with dotted-key access, persisted to
``~/.config/emdx/config.json`` (override location for tests/scripts via
the ``EMDX_CONFIG_FILE`` environment variable).

Known settings:

- ``maintain.auto_link_on_save`` (bool, default True): whether ``emdx save``
  runs semantic auto-linking synchronously. Turning this off makes saves
  fast on large knowledge bases; run ``emdx maintain index`` and
  ``emdx maintain link --all`` out of band to catch up (#1038).
- ``ui.list_height`` / ``ui.sidebar_width`` (int %, defaults 40/30): TUI
  panel sizes — see ``emdx/ui/layout_config.py`` (#891).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .constants import EMDX_CONFIG_DIR

ConfigValue = str | int | float | bool | None

# Known settings and their defaults. Unknown keys are allowed (forward
# compatibility) but `emdx config list` shows these even when unset.
KNOWN_SETTINGS: dict[str, ConfigValue] = {
    "maintain.auto_link_on_save": True,
    # TUI panel sizes (#891) — percentages, clamped to 10-90 at load
    "ui.list_height": 40,
    "ui.sidebar_width": 30,
}


def get_config_file_path() -> Path:
    """Path to the app config file (env-overridable for tests)."""
    override = os.environ.get("EMDX_CONFIG_FILE")
    if override:
        return Path(override)
    return EMDX_CONFIG_DIR / "config.json"


def load_config() -> dict[str, ConfigValue]:
    """Load the config file as a flat {dotted.key: value} dict.

    Returns an empty dict when the file is missing or unreadable —
    config is never allowed to break a command.
    """
    path = get_config_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, str | int | float | bool | None)}


def save_config(config: dict[str, ConfigValue]) -> None:
    """Persist the config dict, creating the parent directory if needed."""
    path = get_config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_config_value(key: str, default: ConfigValue = None) -> ConfigValue:
    """Get a single setting by dotted key, falling back to known defaults."""
    config = load_config()
    if key in config:
        return config[key]
    if default is not None:
        return default
    return KNOWN_SETTINGS.get(key)


def set_config_value(key: str, value: ConfigValue) -> None:
    """Set a single setting by dotted key and persist."""
    config = load_config()
    config[key] = value
    save_config(config)


def unset_config_value(key: str) -> bool:
    """Remove a setting, reverting to its default. Returns True if it was set."""
    config = load_config()
    if key not in config:
        return False
    del config[key]
    save_config(config)
    return True


def parse_config_value(raw: str) -> ConfigValue:
    """Parse a CLI-provided string into a typed config value.

    'true'/'false' (case-insensitive) → bool, integer/float literals →
    numbers, 'null' → None, anything else stays a string.
    """
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw
