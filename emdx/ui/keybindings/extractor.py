"""
Keybinding extractor - scans widgets for BINDINGS declarations.

This module automatically extracts all keybindings from Textual widgets
so they can be registered in the central registry.
"""

import importlib
import inspect
import logging
import pkgutil
from types import ModuleType

from textual.binding import Binding
from textual.widget import Widget

from .context import Context
from .registry import KeybindingEntry

logger = logging.getLogger(__name__)


class KeybindingExtractor:
    """
    Extract BINDINGS from all UI widgets.

    Scans the emdx.ui module and its submodules to find all Widget classes
    with BINDINGS defined, then converts them to KeybindingEntry objects.
    """

    def __init__(self) -> None:
        self.entries: list[KeybindingEntry] = []
        self.scanned_classes: set[type] = set()

    def scan_module(self, module_name: str = "emdx.ui") -> list[KeybindingEntry]:
        """
        Scan a module and all submodules for widgets with BINDINGS.

        Args:
            module_name: The module to scan (default: emdx.ui)

        Returns:
            List of extracted KeybindingEntry objects
        """
        self.entries = []
        self.scanned_classes = set()

        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            logger.error(f"Failed to import module {module_name}: {e}")
            return []

        self._scan_module_recursive(module, module_name)

        logger.info(
            f"Extracted {len(self.entries)} keybindings from "
            f"{len(self.scanned_classes)} widget classes"
        )

        return self.entries

    def _scan_module_recursive(self, module: ModuleType, module_name: str) -> None:
        """Recursively scan a module and its submodules."""
        # Scan the module itself
        self._scan_module_members(module)

        # Scan submodules
        if hasattr(module, "__path__"):
            for _, submodule_name, _ in pkgutil.iter_modules(module.__path__):
                full_name = f"{module_name}.{submodule_name}"
                try:
                    submodule = importlib.import_module(full_name)
                    self._scan_module_recursive(submodule, full_name)
                except ImportError as e:
                    logger.debug(f"Skipping {full_name}: {e}")
                except Exception as e:
                    logger.warning(f"Error scanning {full_name}: {e}")

    def _scan_module_members(self, module: ModuleType) -> None:
        """Scan a module's members for Widget classes with BINDINGS."""
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip if already scanned (class might be imported in multiple places)
            if obj in self.scanned_classes:
                continue

            # Only scan Widget subclasses
            if not issubclass(obj, Widget):
                continue

            # Skip Textual's built-in widgets
            if obj.__module__.startswith("textual."):
                continue

            self.scanned_classes.add(obj)

            # Extract BINDINGS if present
            if hasattr(obj, "BINDINGS") and obj.BINDINGS:
                self._extract_bindings(obj)

    def _extract_bindings(self, widget_class: type[Widget]) -> None:
        """Extract BINDINGS from a widget class."""
        bindings = widget_class.BINDINGS

        # Determine context from widget class name
        context = Context.from_widget_class(widget_class.__name__)

        for binding in bindings:
            if isinstance(binding, Binding):
                entry = self._binding_to_entry(binding, widget_class, context)
                if entry:
                    self.entries.append(entry)
            elif isinstance(binding, tuple):
                # Legacy tuple format: (key, action, description)
                entry = self._tuple_to_entry(binding, widget_class, context)
                if entry:
                    self.entries.append(entry)

    def _binding_to_entry(
        self, binding: Binding, widget_class: type[Widget], context: Context
    ) -> KeybindingEntry | None:
        """Convert a Textual Binding to a KeybindingEntry."""
        try:
            return KeybindingEntry(
                key=binding.key,
                action=binding.action,
                context=context,
                widget_class=widget_class.__name__,
                description=binding.description or "",
                priority=binding.priority,
                show=binding.show,
            )
        except Exception as e:
            logger.warning(f"Failed to convert binding {binding} from {widget_class.__name__}: {e}")
            return None

    def _tuple_to_entry(
        self, binding: tuple[str, ...], widget_class: type[Widget], context: Context
    ) -> KeybindingEntry | None:
        """Convert a legacy tuple binding to a KeybindingEntry."""
        try:
            key = binding[0]
            action = binding[1]
            description = binding[2] if len(binding) > 2 else ""

            return KeybindingEntry(
                key=key,
                action=action,
                context=context,
                widget_class=widget_class.__name__,
                description=description,
            )
        except Exception as e:
            logger.warning(
                f"Failed to convert tuple binding {binding} from {widget_class.__name__}: {e}"
            )
            return None


def extract_all_keybindings() -> list[KeybindingEntry]:
    """
    Convenience function to extract all keybindings from emdx.ui.

    Returns:
        List of all extracted KeybindingEntry objects
    """
    extractor = KeybindingExtractor()
    return extractor.scan_module("emdx.ui")
