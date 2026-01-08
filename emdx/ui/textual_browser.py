#!/usr/bin/env python3
"""
Minimal textual browser that signals for external nvim handling.

This file now serves as a compatibility layer that imports components from their new locations.
"""

import logging
import sys
from pathlib import Path

from .document_viewer import FullScreenView
from .inputs import TitleInput
from .modals import DeleteConfirmScreen

# Import extracted components
from .text_areas import EditTextArea, SelectionTextArea, VimEditTextArea

# DEPRECATED: These functions have been removed (main_browser.py was deleted)
def MinimalDocumentBrowser(*args, **kwargs):
    """Deprecated stub - raises RuntimeError."""
    raise RuntimeError("MinimalDocumentBrowser has been removed. Use 'emdx gui' for the modern interface.")


def run_minimal():
    """Deprecated stub - raises RuntimeError."""
    raise RuntimeError("run_minimal() has been removed. Use 'emdx gui' for the modern interface.")

# Import the VimLineNumbers class that was missed in the initial extraction
from textual.widgets import Static

# Set up logging - needed for VimLineNumbers
log_dir = Path.home() / ".config" / "emdx"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "tui_debug.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # logging.StreamHandler()  # Uncomment for console output
    ],
)

# Also create a dedicated key events log
key_log_file = log_dir / "key_events.log"
key_logger = logging.getLogger("key_events")
key_handler = logging.FileHandler(key_log_file)
key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
key_logger.addHandler(key_handler)
key_logger.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


class VimLineNumbers(Static):
    """Line numbers widget for vim editing mode."""

    def __init__(self, edit_textarea, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.edit_textarea = edit_textarea
        self.add_class("vim-line-numbers")

    def update_line_numbers(self):
        """Update the line numbers display based on cursor position."""
        try:
            if not hasattr(self.edit_textarea, 'cursor_location'):
                return

            current_line = self.edit_textarea.cursor_location[0]
            total_lines = len(self.edit_textarea.text.split('\n'))

            # Build relative line numbers like vim
            lines = []
            for i in range(total_lines):
                if i == current_line:
                    lines.append(f"{i+1:3}")  # Current line shows absolute number
                else:
                    relative = abs(i - current_line)
                    lines.append(f"{relative:3}")

            self.update("\n".join(lines))

            # Sync scroll position with the text area
            try:
                # Try to match the scroll position of the text area
                container = self.edit_textarea.parent
                if container and hasattr(container, 'scroll_offset'):
                    self.scroll_to(y=container.scroll_offset.y, animate=False)
            except Exception:
                pass  # Scroll sync is nice-to-have

        except Exception as e:
            logger.error(f"Error updating line numbers: {e}")


# For backward compatibility, re-export everything
__all__ = [
    'SelectionTextArea',
    'TitleInput',
    'VimEditTextArea',
    'EditTextArea',
    'VimLineNumbers',
    'FullScreenView',
    'DeleteConfirmScreen',
    'MinimalDocumentBrowser',
    'run_minimal'
]


if __name__ == "__main__":
    sys.exit(run_minimal())
