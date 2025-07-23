#!/usr/bin/env python3
"""
Input widgets for EMDX TUI.
"""

import logging
from textual import events
from textual.widgets import Input

# Set up logging
log_dir = None
try:
    from pathlib import Path
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
    
    logger = logging.getLogger(__name__)
except Exception:
    # Fallback if logging setup fails
    import logging
    logger = logging.getLogger(__name__)


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
    
    def _format_title_with_box(self, title: str) -> str:
        """Format title with unicode box for content area."""
        # Calculate box width - make it wider than the title for better appearance
        box_width = max(len(title) + 4, 80)
        
        # Center the title within the box
        padded_title = title.center(box_width - 2)
        
        # Create the unicode box
        top_line = "╔" + "═" * (box_width - 2) + "╗"
        title_line = "║" + padded_title + "║"
        bottom_line = "╚" + "═" * (box_width - 2) + "╝"
        
        # Return with extra newlines for spacing
        return f"{top_line}\n{title_line}\n{bottom_line}\n\n"
    
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
                
                # First time tabbing to content? Start in INSERT mode and add formatted title
                if not hasattr(vim_editor.text_area, '_has_been_focused'):
                    vim_editor.text_area._has_been_focused = True
                    vim_editor.text_area.vim_mode = "INSERT"
                    
                    # Insert formatted title if content is empty
                    if not vim_editor.text_area.text.strip() and self.value.strip():
                        formatted_title = self._format_title_with_box(self.value.strip())
                        vim_editor.text_area.insert(formatted_title)
                        # Position cursor after the formatted title
                        vim_editor.text_area.move_cursor((len(formatted_title.split('\n')), 0))
                
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