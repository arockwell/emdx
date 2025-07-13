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
    
    def on_key(self, event: events.Key) -> None:
        """Handle Tab and vim keys to switch to content editor."""
        logger.debug(f"TitleInput.on_key: key={event.key}")
        # Vim keys that should switch focus to content editor
        vim_keys = {'j', 'k', 'h', 'l', 'i', 'a', 'o', 'x', 'd', 'y', 'p', 'v', 'g', 'w', 'b', 'e', '0', '$', 'u'}
        vim_special_keys = {'up', 'down', 'left', 'right', 'enter'}
        
        char = event.character if hasattr(event, 'character') else None
        
        if event.key == "tab" or event.key == "escape" or char in vim_keys or event.key in vim_special_keys:
            # Switch focus to content editor for vim keys
            try:
                from .text_areas import VimEditTextArea
                edit_area = self.app_instance.query_one("#preview-content", VimEditTextArea)
                edit_area.focus()
                # Let the edit area handle this key event
                edit_area.on_key(event)
                event.stop()
                event.prevent_default()
                return
            except:
                pass  # Editor might not exist
        
        # For other keys (typing), let Input handle normally
        # Input widget doesn't have on_key method, so don't call super()