"""
Refactored on_key method that uses BrowserModeRouter.

This shows how to simplify the massive on_key method using the mode router.
"""

def on_key(self, event: events.Key) -> None:
    """Handle key presses with mode-based routing."""
    try:
        # Check if any modal or screen is active
        if len(self.screen_stack) > 1:
            # Another screen is active, let it handle the key event
            active_screen = self.screen_stack[-1]
            screen_type = type(active_screen).__name__
            key_logger.info(f"{screen_type} active, passing key event through: key={event.key}")
            return
        
        # Log key event for debugging
        key_logger.info(f"App.on_key: key={event.key}, mode={self.mode}")
        logger.debug(f"Key event: key={event.key}")
        
        # Special handling for edit mode (let text area handle it)
        if self.edit_mode and event.key in ["escape", "ctrl+s"]:
            # Let the edit widget handle these keys
            return
        
        # Global Tab prevention (except in TAG mode for cycling)
        if event.key == "tab":
            if self.mode == "TAG" and self.tag_action == "remove":
                # Allow Tab for tag cycling
                pass
            else:
                # Block Tab in all other modes
                event.prevent_default()
                event.stop()
                return
        
        # Let mode router handle the key
        if self.mode_router.handle_key(event):
            event.prevent_default()
            event.stop()
            return
        
        # Handle remaining global navigation keys
        if event.key == "j":
            self.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.action_cursor_up()
            event.prevent_default()
        elif event.key == "g":
            self.action_cursor_top()
            event.prevent_default()
        elif event.key == "G":
            self.action_cursor_bottom()
            event.prevent_default()
        elif event.key == "ctrl+d":
            # Page down
            self._page_down()
            event.prevent_default()
        elif event.key == "ctrl+u":
            # Page up
            self._page_up()
            event.prevent_default()
            
    except Exception as e:
        key_logger.error(f"Exception in on_key: {e}", exc_info=True)
        logger.error(f"Exception in on_key: {e}", exc_info=True)