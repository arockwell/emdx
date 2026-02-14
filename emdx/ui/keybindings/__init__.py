"""
EMDX Keybinding System.

Central registry for all keybindings with conflict detection and user customization.

Usage:
    from emdx.ui.keybindings import KeybindingRegistry, Context

    # At app startup
    registry = KeybindingRegistry()
    registry.scan_and_register()
    conflicts = registry.detect_conflicts()

    if conflicts:
        for conflict in conflicts:
            logger.warning(conflict.to_string())
"""

from .config import KeybindingConfig, get_config_path, load_config
from .context import Context
from .extractor import KeybindingExtractor, extract_all_keybindings
from .registry import (
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    KeybindingEntry,
    KeybindingRegistry,
)

__all__ = [
    "Context",
    "KeybindingEntry",
    "KeybindingRegistry",
    "ConflictReport",
    "ConflictType",
    "ConflictSeverity",
    "KeybindingExtractor",
    "extract_all_keybindings",
    "KeybindingConfig",
    "load_config",
    "get_config_path",
]
