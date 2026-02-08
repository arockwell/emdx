"""
Keybinding configuration loader.

Loads user keybinding customizations from ~/.config/emdx/keybindings.yaml
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from emdx.config.constants import EMDX_CONFIG_DIR
from .context import Context
from .registry import KeybindingEntry

logger = logging.getLogger(__name__)

# Default config path
DEFAULT_CONFIG_PATH = EMDX_CONFIG_DIR / "keybindings.yaml"

# Example config content for new users
EXAMPLE_CONFIG = """# EMDX Keybinding Configuration
#
# This file allows you to customize keybindings for the emdx TUI.
#
# Format:
#   overrides:
#     - key: "t"                      # The key to bind
#       action: "add_tags"            # The action to perform
#       context: "document:normal"    # Where this binding applies
#
# Available contexts:
#   global              - Always active
#   document:normal     - Document browser
#   document:edit       - Editing a document
#   agent:normal        - Agent browser
#   file:normal         - File browser
#   task:normal         - Task browser
#   workflow:normal     - Workflow browser
#   log:normal          - Log browser
#   control:normal      - Control center
#   vim:normal          - Vim normal mode in editor
#   vim:insert          - Vim insert mode
#   modal:*             - Various modal dialogs
#
# To see all available actions, run: emdx keybindings --list-actions
#
# Example: Change theme selector from backslash to ctrl+t
# overrides:
#   - key: "ctrl+t"
#     action: "cycle_theme"
#     context: "global"

overrides: []
"""


def get_config_path() -> Path:
    """Get the path to the keybindings config file."""
    return DEFAULT_CONFIG_PATH


def load_config() -> Dict[str, Any]:
    """
    Load keybinding configuration from YAML file.

    Returns:
        Dictionary with configuration, or empty dict if file doesn't exist
    """
    config_path = get_config_path()

    if not config_path.exists():
        return {"overrides": []}

    try:
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f)

        if config is None:
            return {"overrides": []}

        return config

    except ImportError:
        logger.warning("PyYAML not installed, skipping keybinding config")
        return {"overrides": []}

    except Exception as e:
        logger.error(f"Failed to load keybindings config: {e}")
        return {"overrides": []}


def save_example_config() -> bool:
    """
    Save example config file if it doesn't exist.

    Returns:
        True if file was created, False if it already exists
    """
    config_path = get_config_path()

    if config_path.exists():
        return False

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(EXAMPLE_CONFIG)
        logger.info(f"Created example keybindings config at {config_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create keybindings config: {e}")
        return False


def parse_overrides(config: Dict[str, Any]) -> List[KeybindingEntry]:
    """
    Parse override entries from config into KeybindingEntry objects.

    Args:
        config: The loaded configuration dictionary

    Returns:
        List of KeybindingEntry objects for overrides
    """
    entries = []
    overrides = config.get("overrides", [])

    if not overrides:
        return entries

    for override in overrides:
        try:
            # Parse context
            context_str = override.get("context", "global")
            context = _parse_context(context_str)

            if context is None:
                logger.warning(f"Unknown context '{context_str}' in override, skipping")
                continue

            entry = KeybindingEntry(
                key=override["key"],
                action=override["action"],
                context=context,
                widget_class="UserOverride",
                description=override.get("description", "User override"),
                priority=override.get("priority", False),
            )
            entries.append(entry)

        except KeyError as e:
            logger.warning(f"Missing required field {e} in override, skipping")
        except Exception as e:
            logger.warning(f"Failed to parse override: {e}")

    return entries


def _parse_context(context_str: str) -> Optional[Context]:
    """Parse a context string into a Context enum value."""
    # Try direct match
    for ctx in Context:
        if ctx.value == context_str:
            return ctx

    # Try without prefix
    for ctx in Context:
        if ctx.value.endswith(context_str):
            return ctx

    return None


class KeybindingConfig:
    """
    Manages keybinding configuration loading and validation.

    Usage:
        config = KeybindingConfig()
        config.load()

        # Get overrides to apply to registry
        overrides = config.get_overrides()

        # Check if a key is overridden
        if config.is_overridden("t", Context.DOCUMENT_NORMAL):
            new_action = config.get_override("t", Context.DOCUMENT_NORMAL)
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or get_config_path()
        self.config: Dict[str, Any] = {}
        self.overrides: List[KeybindingEntry] = []
        self._override_map: Dict[tuple, KeybindingEntry] = {}

    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            self.config = load_config()
        else:
            self.config = {"overrides": []}

        self.overrides = parse_overrides(self.config)

        # Build lookup map
        self._override_map = {}
        for entry in self.overrides:
            key = (entry.key, entry.context)
            self._override_map[key] = entry

    def get_overrides(self) -> List[KeybindingEntry]:
        """Get all override entries."""
        return self.overrides

    def is_overridden(self, key: str, context: Context) -> bool:
        """Check if a key is overridden in a context."""
        return (key, context) in self._override_map

    def get_override(self, key: str, context: Context) -> Optional[KeybindingEntry]:
        """Get the override for a key in a context."""
        return self._override_map.get((key, context))

    def create_example(self) -> bool:
        """Create example config file."""
        return save_example_config()
