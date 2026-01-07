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

# DEPRECATED: These imports now generate warnings
try:
    from .main_browser import MinimalDocumentBrowser, run_minimal
except RuntimeError:
    # Handle case where these have been fully removed
    def MinimalDocumentBrowser(*args, **kwargs):
        raise RuntimeError("MinimalDocumentBrowser has been removed. Use 'emdx gui' for the modern interface.")
    
    def run_minimal():
        raise RuntimeError("run_minimal() has been removed. Use 'emdx gui' for the modern interface.")

# Import the VimLineNumbers class that was missed in the initial extraction
from textual.widgets import Static

# Set up logging - only enable debug logging if EMDX_DEBUG is set
import os
debug_enabled = os.getenv("EMDX_DEBUG", "").lower() in ("1", "true", "yes", "on")
logger = logging.getLogger(__name__)

if debug_enabled:
    log_dir = Path.home() / ".config" / "emdx"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tui_debug.log"

    # Set up file logging for debug
    debug_handler = logging.FileHandler(log_file)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(debug_handler)
    logger.setLevel(logging.DEBUG)
else:
    # Production mode - only log warnings and errors
    logger.setLevel(logging.WARNING)


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
            except:
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
