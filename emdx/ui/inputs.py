#!/usr/bin/env python3
"""
Input widgets for EMDX TUI.
"""

from textual import events
from textual.widgets import Input

# Set up logging using shared utility
from ..utils.logging import setup_tui_logging
logger, key_logger = setup_tui_logging(__name__)


class TitleInput(Input):
    """Custom Input that handles Tab to switch to content editor."""
    
    def __init__(self, app_instance, *args, **kwargs):
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
        """Handle Tab to switch to content editor in new document mode."""
        logger.debug(f"TitleInput.on_key: key={event.key}")
        
        # Handle Ctrl+S to save
        if event.key == "ctrl+s":
            self.app_instance.action_save_and_exit_edit()
            event.stop()
            event.prevent_default()
            return
        
        if event.key == "tab":
            # Switch focus to vim editor container
            try:
                from .vim_editor import VimEditor
                vim_editor = self.app_instance.query_one("#vim-editor-container", VimEditor)
                vim_editor.focus_editor()
                
                # First time tabbing to content?
                if not hasattr(vim_editor.text_area, '_has_been_focused'):
                    vim_editor.text_area._has_been_focused = True
                    # For NEW documents, start in INSERT mode
                    # For EDIT documents, start in NORMAL mode
                    if hasattr(self.app_instance, 'new_document_mode') and self.app_instance.new_document_mode:
                        vim_editor.text_area.vim_mode = "INSERT"
                    else:
                        vim_editor.text_area.vim_mode = "NORMAL"
                
                vim_editor.text_area._update_cursor_style()
                mode_name = vim_editor.text_area.vim_mode
                self.app_instance._update_vim_status(f"{mode_name} | Tab=switch to title | Ctrl+S=save | ESC=exit")
                event.stop()
                event.prevent_default()
                return
            except Exception as e:
                logger.debug(f"Could not switch to vim editor: {e}")
                pass  # Editor might not exist
        
        # For other keys (typing), let Input handle normally
        # Input widget doesn't have on_key method, so don't call super()
