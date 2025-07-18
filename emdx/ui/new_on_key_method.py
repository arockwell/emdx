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
            
            # Handle remaining global navigation keys that work in all modes
            handled = False
            
            if event.key == "j" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                self.action_cursor_down()
                handled = True
            elif event.key == "k" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                self.action_cursor_up()
                handled = True
            elif event.key == "g" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                self.action_cursor_top()
                handled = True
            elif event.key == "G" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                self.action_cursor_bottom()
                handled = True
            elif event.key == "ctrl+d" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                # Page down
                table = self.query_one("#doc-table", DataTable)
                visible_rows = table.visible_size.height - 2
                for _ in range(max(1, visible_rows // 2)):
                    self.action_cursor_down()
                handled = True
            elif event.key == "ctrl+u" and self.mode not in ["SEARCH", "TAG", "EDIT"]:
                # Page up
                table = self.query_one("#doc-table", DataTable)
                visible_rows = table.visible_size.height - 2
                for _ in range(max(1, visible_rows // 2)):
                    self.action_cursor_up()
                handled = True
            
            if handled:
                event.prevent_default()
                event.stop()
                
        except Exception as e:
            key_logger.error(f"Exception in on_key: {e}", exc_info=True)
            logger.error(f"Exception in on_key: {e}", exc_info=True)