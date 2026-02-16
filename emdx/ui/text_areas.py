#!/usr/bin/env python3
"""
Text area widgets for EMDX TUI.
"""

from typing import Any

from textual import events
from textual.widgets import TextArea

# Set up logging using shared utility
from ..utils.logging_utils import setup_tui_logging
from .protocols import SelectionModeHost

logger, _key_logger = setup_tui_logging(__name__)


class SelectionTextArea(TextArea):
    """TextArea that captures 's' key to exit selection mode."""

    def __init__(self, app_instance: SelectionModeHost, *args: Any, **kwargs: Any) -> None:
        # Textual 6.x changed defaults - explicitly set the behavior we want
        kwargs.setdefault("soft_wrap", False)
        kwargs.setdefault("show_line_numbers", True)
        kwargs.setdefault("tab_behavior", "indent")
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance

    def on_key(self, event: events.Key) -> None:
        try:
            # Only allow specific keys in selection mode:
            # - 's' and 'escape' to exit selection mode
            # - 'ctrl+c' to copy
            # - Arrow keys and mouse for navigation/selection
            allowed_keys = {
                "escape",
                "ctrl+c",
                "up",
                "down",
                "left",
                "right",
                "page_up",
                "page_down",
                "home",
                "end",
                "shift+up",
                "shift+down",
                "shift+left",
                "shift+right",
            }

            if event.key == "escape" or (hasattr(event, "character") and event.character == "s"):
                # Exit selection mode
                event.stop()
                event.prevent_default()
                self.app_instance.action_toggle_selection_mode()
                return
            elif event.key == "ctrl+c":
                # Allow copy operation - let it bubble up to main app
                return
            elif event.key in allowed_keys:
                # Allow navigation keys for text selection
                return
            else:
                # Block ALL other keys (typing, shortcuts, etc.)
                event.stop()
                event.prevent_default()
                return

        except Exception as e:
            logger.error(f"Error in SelectionTextArea.on_key: {e}", exc_info=True)
