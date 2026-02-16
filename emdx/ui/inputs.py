#!/usr/bin/env python3
"""
Input widgets for EMDX TUI.
"""

from typing import Any

from textual import events
from textual.widgets import Input

from ..utils.logging_utils import setup_tui_logging

logger, _key_logger = setup_tui_logging(__name__)


class TitleInput(Input):
    """Custom Input that handles Tab to switch to content editor."""

    def __init__(self, app_instance: Any, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance
        self._saved_cursor_position = 0

    def on_focus(self) -> None:
        """Handle focus event - restore cursor position."""
        # Input widget doesn't have on_focus, so don't call super
        # Just restore our saved cursor position after a refresh
        self.call_after_refresh(self._restore_cursor_position)
        # Also use a timer as backup
        self.set_timer(0.05, self._restore_cursor_position)

    def _restore_cursor_position(self) -> None:
        """Restore the saved cursor position without selection."""
        try:
            # Move cursor to end which should clear selection
            self.action_end()
            # Then restore to saved position if needed
            if self._saved_cursor_position < len(self.value):
                # Move back to saved position
                for _ in range(len(self.value) - self._saved_cursor_position):
                    self.action_cursor_left()
        except Exception as e:
            logger.debug(f"Error restoring cursor: {e}")

    def on_blur(self) -> None:
        """Save cursor position when losing focus."""
        self._saved_cursor_position = self.cursor_position
        # Input widget might not have on_blur either

    def on_key(self, event: events.Key) -> None:
        """Handle Tab and other special keys."""
        logger.debug(f"TitleInput.on_key: key={event.key}")

        # Handle Ctrl+S to save
        if event.key == "ctrl+s":
            self.app_instance.action_save_and_exit_edit()
            event.stop()
            event.prevent_default()
            return

        # For other keys (typing), let Input handle normally
        # Input widget doesn't have on_key method, so don't call super()
