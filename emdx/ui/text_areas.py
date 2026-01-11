#!/usr/bin/env python3
"""
Text area widgets for EMDX TUI.
"""

import re

from textual import events
from textual.widgets import TextArea

# Set up logging using shared utility
from ..utils.logging import setup_tui_logging
logger, key_logger = setup_tui_logging(__name__)


class SelectionTextArea(TextArea):
    """TextArea that captures 's' key to exit selection mode."""

    def __init__(self, app_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance

    def on_key(self, event: events.Key) -> None:
        try:
            # Comprehensive logging of key event attributes
            event_attrs = {}
            for attr in ['key', 'character', 'name', 'is_printable', 'aliases']:
                if hasattr(event, attr):
                    event_attrs[attr] = getattr(event, attr)

            key_logger.info(f"SelectionTextArea.on_key: {event_attrs}")
            logger.debug(f"SelectionTextArea.on_key: key={event.key}")

            # Only allow specific keys in selection mode:
            # - 's' and 'escape' to exit selection mode
            # - 'ctrl+c' to copy
            # - Arrow keys and mouse for navigation/selection
            allowed_keys = {'escape', 'ctrl+c', 'up', 'down', 'left', 'right',
                          'page_up', 'page_down', 'home', 'end',
                          'shift+up', 'shift+down', 'shift+left', 'shift+right'}

            if event.key == "escape" or (hasattr(event, 'character') and event.character == "s"):
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

        except (AttributeError, RuntimeError) as e:
            key_logger.error(f"Known error in SelectionTextArea.on_key: {type(e).__name__}: {e}")
            logger.error(f"Error in SelectionTextArea.on_key: {type(e).__name__}: {e}", exc_info=True)
            # Don't re-raise - let app continue
        except Exception as e:
            key_logger.error(f"Unexpected error in SelectionTextArea.on_key: {type(e).__name__}: {e}")
            logger.error(f"Unexpected error in SelectionTextArea.on_key: {type(e).__name__}: {e}", exc_info=True)
            # Don't re-raise - let app continue


class VimEditTextArea(TextArea):
    """TextArea with vim-like keybindings for EMDX."""

    # Vim modes
    VIM_NORMAL = "NORMAL"
    VIM_INSERT = "INSERT"
    VIM_VISUAL = "VISUAL"
    VIM_VISUAL_LINE = "V-LINE"
    VIM_COMMAND = "COMMAND"

    def __init__(self, app_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance
        self.vim_mode = self.VIM_NORMAL  # Start in normal mode like vim
        self.visual_start = None
        self.visual_end = None
        self.last_command = None
        self.pending_command = ""
        self.repeat_count = ""
        self.register = None
        self.yanked_text = ""
        self.command_buffer = ""  # For vim commands like :w, :q, etc.
        # Store original content to detect changes
        self.original_content = (
            kwargs.get('text', '') if 'text' in kwargs else args[0] if args else ''
        )

        # Set initial cursor style for NORMAL mode (solid, non-blinking)
        self.show_cursor = True
        self.cursor_blink = False

        # Hook into TextArea's cursor position changes
        self.watch_cursor_position = True

        # Watch for cursor position changes
        self.watch("cursor_location", self._on_cursor_changed)
        self.watch("selection", self._on_selection_changed)

        # Watch for text changes to update line count
        self.watch("text", self._on_text_changed)

    def _update_cursor_style(self):
        """Update cursor style based on vim mode."""
        # Keep all cursors solid (non-blinking)
        self.cursor_blink = False
        self.show_cursor = True

        # Try to change cursor color via CSS classes
        self.remove_class("vim-insert-mode")
        self.remove_class("vim-normal-mode")

        if self.vim_mode == self.VIM_INSERT or self.vim_mode == self.VIM_COMMAND:
            self.add_class("vim-insert-mode")
        else:
            self.add_class("vim-normal-mode")

    def _on_cursor_changed(self, old_cursor, new_cursor):
        """Handle cursor position changes via TextArea watcher."""
        try:
            key_logger.info(
                f"CURSOR WATCHER: cursor_location changed from {old_cursor} to {new_cursor}"
            )
            self._update_line_numbers()
        except Exception as e:
            key_logger.error(f"ERROR in _on_cursor_changed: {e}")

    def _on_selection_changed(self, old_selection, new_selection):
        """Handle selection changes via TextArea watcher."""
        try:
            key_logger.info(
                f"SELECTION WATCHER: selection changed from {old_selection} to {new_selection}"
            )
            self._update_line_numbers()
        except Exception as e:
            key_logger.error(f"ERROR in _on_selection_changed: {e}")

    def _on_text_changed(self, old_text, new_text):
        """Handle text changes via TextArea watcher."""
        try:
            old_lines = len(old_text.split('\n')) if old_text else 0
            new_lines = len(new_text.split('\n')) if new_text else 0
            key_logger.info(f"TEXT WATCHER: text changed, lines: {old_lines} -> {new_lines}")

            # Special handling for line count changes
            if old_lines != new_lines:
                key_logger.info(f"LINE COUNT CHANGED: {old_lines} -> {new_lines}")

                # Check if this was a new line addition
                if new_lines > old_lines:
                    key_logger.info(f"NEW LINE ADDED: +{new_lines - old_lines} lines")
                else:
                    key_logger.info(f"LINES REMOVED: -{old_lines - new_lines} lines")

            # Update line numbers when text changes (for line count changes)
            self._update_line_numbers()
        except Exception as e:
            key_logger.error(f"ERROR in _on_text_changed: {e}")

    def get_current_line(self):
        """Get the current line number - SINGLE SOURCE OF TRUTH."""
        try:
            # This is the definitive method for getting current line
            current_line = self.cursor_location[0]
            key_logger.debug(f"get_current_line: {current_line}")
            return current_line
        except Exception as e:
            key_logger.error(f"ERROR in get_current_line: {e}")
            return 0  # Safe fallback

    def _update_line_numbers(self):
        """Update line numbers widget - SIMPLIFIED to use only TextArea's native cursor."""
        try:
            key_logger.info("STEP 1: Starting SIMPLIFIED line numbers update")

            # Check if line numbers widget exists
            if not hasattr(self, 'line_numbers_widget'):
                key_logger.info("No line_numbers_widget attribute")
                return

            if not self.line_numbers_widget:
                key_logger.info("line_numbers_widget is None")
                return

            key_logger.info("STEP 2: line_numbers_widget exists")

            # Use the single source of truth method
            current_line = self.get_current_line()

            # Defensive programming: bounds checking
            if not hasattr(self, 'text') or self.text is None:
                key_logger.info("STEP 3: text is None, defaulting to empty")
                total_lines = 1
            else:
                total_lines = len(self.text.split('\n'))

            # Ensure current_line is within valid bounds
            if current_line < 0:
                key_logger.info(f"STEP 3: current_line {current_line} < 0, clamping to 0")
                current_line = 0
            elif current_line >= total_lines:
                key_logger.info(
                    f"STEP 3: current_line {current_line} >= total_lines {total_lines}, "
                    f"clamping to {total_lines-1}"
                )
                current_line = max(0, total_lines - 1)

            key_logger.info(f"STEP 3: cursor from get_current_line(): {current_line}")
            key_logger.info(f"STEP 4: total_lines={total_lines}")

            # Log the actual cursor position to debug
            logger.debug(
                f"SIMPLIFIED LINE NUMBERS: current_line={current_line}, "
                f"total_lines={total_lines}"
            )

            # Call the line numbers widget with defensive checks
            try:
                key_logger.info(
                    f"STEP 5: Calling set_line_numbers({current_line}, {total_lines}, self)"
                )
                self.line_numbers_widget.set_line_numbers(current_line, total_lines, self)
                key_logger.info("STEP 6: set_line_numbers completed")
            except Exception as widget_error:
                key_logger.error(f"ERROR in set_line_numbers: {widget_error}")
                logger.error(f"Widget error: {widget_error}", exc_info=True)

        except Exception as e:
            key_logger.error(f"ERROR in SIMPLIFIED _update_line_numbers: {e}")
            logger.error(f"Error updating line numbers: {e}", exc_info=True)

    def on_key(self, event: events.Key) -> None:
        """Handle key events with vim-like behavior."""
        try:
            key_logger.info(f"VimEditTextArea.on_key: key={event.key}, mode={self.vim_mode}")

            # Global ESC handling - exit edit mode from any vim mode
            if event.key == "escape":
                if self.vim_mode == self.VIM_INSERT:
                    # First ESC goes to normal mode
                    self.vim_mode = self.VIM_NORMAL
                    self._update_cursor_style()
                    event.stop()
                    event.prevent_default()
                    self.app_instance._update_vim_status("NORMAL | ESC=exit")
                    return
                else:
                    # Second ESC exits edit mode entirely
                    event.stop()
                    event.prevent_default()
                    # Use call_after_refresh to avoid blocking the UI
                    # Call the appropriate exit method
                    try:
                        if hasattr(self.app_instance, 'file_browser'):
                            # For FileBrowserVimApp, call the method directly
                            self.app_instance.file_browser.call_after_refresh(self.app_instance.action_save_and_exit_edit)
                        else:
                            # For main browser, call the action directly
                            self.app_instance.call_after_refresh(self.app_instance.action_save_and_exit_edit)
                    except Exception as e:
                        # Fallback - just call the action method directly
                        self.app_instance.action_save_and_exit_edit()
                    return

            # Route to appropriate handler based on mode
            if self.vim_mode == self.VIM_NORMAL:
                self._handle_normal_mode(event)
            elif self.vim_mode == self.VIM_INSERT:
                self._handle_insert_mode(event)
            elif self.vim_mode == self.VIM_VISUAL:
                self._handle_visual_mode(event)
            elif self.vim_mode == self.VIM_VISUAL_LINE:
                self._handle_visual_line_mode(event)
            elif self.vim_mode == self.VIM_COMMAND:
                self._handle_command_mode(event)

        except (AttributeError, RuntimeError) as e:
            key_logger.error(f"Known error in VimEditTextArea.on_key: {type(e).__name__}: {e}")
            logger.error(f"Error in VimEditTextArea.on_key: {type(e).__name__}: {e}", exc_info=True)
            # Try to continue without crashing the app
            try:
                self.app_instance._update_vim_status(f"Error: {str(e)[:50]}")
            except (AttributeError, RuntimeError):
                pass
        except Exception as e:
            key_logger.error(f"Unexpected error in VimEditTextArea.on_key: {type(e).__name__}: {e}")
            logger.error(f"Unexpected error in VimEditTextArea.on_key: {type(e).__name__}: {e}", exc_info=True)
            # Try to continue without crashing the app
            try:
                self.app_instance._update_vim_status(f"Error: {str(e)[:50]}")
            except (AttributeError, RuntimeError):
                pass

    def _handle_normal_mode(self, event: events.Key) -> None:
        """Handle keys in NORMAL mode."""
        key = event.key
        char = event.character if hasattr(event, 'character') else None

        key_logger.info(f"VimEditTextArea._handle_normal_mode: key={key}, char={char}")

        # Handle Ctrl+S to save
        if key == "ctrl+s":
            self.app_instance.action_save_and_exit_edit()
            return

        # Stop event from bubbling up
        event.stop()
        event.prevent_default()

        # Handle repeat counts (e.g., 3j to move down 3 lines)
        if char and char.isdigit() and (self.repeat_count or char != '0'):
            self.repeat_count += char
            key_logger.info(f"Added to repeat count: {self.repeat_count}")
            return

        # Get repeat count as integer
        count = int(self.repeat_count) if self.repeat_count else 1
        self.repeat_count = ""  # Reset after use

        key_logger.info(f"Processing command with count={count}")

        # Movement commands
        if key == "h" or key == "left":
            try:
                key_logger.info(f"STEP 1: Moving left by {count}")
                self.move_cursor_relative(columns=-count)
                key_logger.info("STEP 2: Move left completed")
                self._update_line_numbers()
                key_logger.info("STEP 3: Line numbers updated after left")
            except Exception as e:
                key_logger.error(f"ERROR in left movement: {e}")
                logger.error(f"Exception in left movement: {e}", exc_info=True)
        elif key == "j" or key == "down":
            try:
                key_logger.info(f"STEP 1: Moving down by {count}")
                self.move_cursor_relative(rows=count)
                key_logger.info("STEP 2: Move down completed")
                self._update_line_numbers()
                key_logger.info("STEP 3: Line numbers updated after down")
            except Exception as e:
                key_logger.error(f"ERROR in down movement: {e}")
                logger.error(f"Exception in down movement: {e}", exc_info=True)
        elif key == "k" or key == "up":
            try:
                key_logger.info(f"STEP 1: Moving up by {count}")
                self.move_cursor_relative(rows=-count)
                key_logger.info("STEP 2: Move up completed")
                self._update_line_numbers()
                key_logger.info("STEP 3: Line numbers updated after up")
            except Exception as e:
                key_logger.error(f"ERROR in up movement: {e}")
                logger.error(f"Exception in up movement: {e}", exc_info=True)
        elif key == "l" or key == "right":
            try:
                key_logger.info(f"STEP 1: Moving right by {count}")
                self.move_cursor_relative(columns=count)
                key_logger.info("STEP 2: Move right completed")
                self._update_line_numbers()
                key_logger.info("STEP 3: Line numbers updated after right")
            except Exception as e:
                key_logger.error(f"ERROR in right movement: {e}")
                logger.error(f"Exception in right movement: {e}", exc_info=True)

        # Word movement
        elif char == "w":
            self._move_word_forward(count)
            self._update_line_numbers()
        elif char == "b":
            self._move_word_backward(count)
            self._update_line_numbers()
        elif char == "e":
            self._move_word_end(count)
            self._update_line_numbers()

        # Line movement
        elif char == "0":
            self._cursor_to_line_start()
            self._update_line_numbers()
        elif char == "$":
            self._cursor_to_line_end()
            self._update_line_numbers()
        elif char == "g":
            if self.pending_command == "g":
                # gg - go to first line
                self._cursor_to_start()
                self._update_line_numbers()
                self.pending_command = ""
            else:
                self.pending_command = "g"
                return
        elif char == "G":
            try:
                key_logger.info("STEP 1: G command - going to last line")
                self._cursor_to_end()
                key_logger.info("STEP 2: G command - cursor moved to end")
                self._update_line_numbers()
                key_logger.info("STEP 3: G command - line numbers updated")
            except Exception as e:
                key_logger.error(f"ERROR in G command: {e}")
                logger.error(f"Exception in G command: {e}", exc_info=True)

        # Mode changes
        elif char == "i":
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")
        elif char == "a":
            self.move_cursor_relative(columns=1)
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")
        elif char == "I":
            self._cursor_to_line_start()
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")
        elif char == "A":
            self._cursor_to_line_end()
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")
        elif char == "o":
            self._cursor_to_line_end()
            self.insert("\n")
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")
        elif char == "O":
            self._cursor_to_line_start()
            self.insert("\n")
            self.move_cursor_relative(rows=-1)
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status("INSERT")

        # Visual modes
        elif char == "v":
            self.vim_mode = self.VIM_VISUAL
            self._update_cursor_style()
            self.visual_start = self.cursor_location
            self.app_instance._update_vim_status("VISUAL")
        elif char == "V":
            self.vim_mode = self.VIM_VISUAL_LINE
            self._update_cursor_style()
            self.visual_start = self.cursor_location
            self.app_instance._update_vim_status("V-LINE")

        # Editing commands
        elif char == "x":
            # Delete character under cursor
            for _ in range(count):
                self._delete_right_safe()
        elif char == "d":
            if self.pending_command == "d":
                # dd - delete line
                self._delete_line(count)
                self.pending_command = ""
            else:
                self.pending_command = "d"
                return
        elif char == "y":
            if self.pending_command == "y":
                # yy - yank line
                self._yank_line(count)
                self.pending_command = ""
            else:
                self.pending_command = "y"
                return
        elif char == "p":
            # Paste after cursor
            if self.yanked_text:
                self.insert(self.yanked_text)
        elif char == "P":
            # Paste before cursor
            if self.yanked_text:
                self.move_cursor_relative(columns=-1)
                self.insert(self.yanked_text)

        # Command mode
        elif char == ":":
            self.vim_mode = self.VIM_COMMAND
            self._update_cursor_style()
            self.command_buffer = ":"
            self.app_instance._update_vim_status("COMMAND :")

        # Tab key - switch back to title in new or edit document mode
        elif key == "tab":
            # Check if we have a title input (works for both new and edit modes)
            try:
                title_input = self.app_instance.query_one("#title-input")
                title_input.focus()
                # Update status based on mode
                if hasattr(self.app_instance, 'new_document_mode') and self.app_instance.new_document_mode:
                    self.app_instance._update_vim_status("NEW DOCUMENT | Enter title | Tab=switch to content | Ctrl+S=save | ESC=cancel")
                else:
                    self.app_instance._update_vim_status("EDIT DOCUMENT | Tab=switch fields | Ctrl+S=save | ESC=cancel")
                event.stop()
                return
            except Exception as e:
                logger.debug(f"Error switching to title: {e}")
                pass  # Title input might not exist

        # Clear pending command if not handled
        if char not in ["g", "d", "y"]:
            self.pending_command = ""

    def _handle_insert_mode(self, event: events.Key) -> None:
        """Handle keys in INSERT mode - just pass through for normal editing."""
        # Handle Ctrl+S to save
        if event.key == "ctrl+s":
            self.app_instance.action_save_and_exit_edit()
            event.stop()
            return

        # Handle Tab in new or edit document mode
        if event.key == "tab":
            try:
                title_input = self.app_instance.query_one("#title-input")
                title_input.focus()
                # Update status based on mode
                if hasattr(self.app_instance, 'new_document_mode') and self.app_instance.new_document_mode:
                    self.app_instance._update_vim_status("NEW DOCUMENT | Enter title | Tab=switch to content | Ctrl+S=save | ESC=cancel")
                else:
                    self.app_instance._update_vim_status("EDIT DOCUMENT | Tab=switch fields | Ctrl+S=save | ESC=cancel")
                event.stop()
                return
            except Exception:
                pass  # Title input might not exist

        # Don't stop the event - let it bubble up naturally for TextArea to handle
        # Only update line numbers for operations that might change line count
        # Use call_after_refresh to ensure TextArea has processed the event first
        if event.key in ["enter", "backspace", "delete"]:
            self.call_after_refresh(lambda: self._update_line_numbers())

    def _handle_visual_mode(self, event: events.Key) -> None:
        """Handle keys in VISUAL mode."""
        # For now, just handle ESC to return to normal
        if event.key == "escape":
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.visual_start = None
            self.visual_end = None
            event.stop()
            event.prevent_default()
            self.app_instance._update_vim_status("NORMAL | ESC=exit")
        else:
            # For other keys, don't stop the event - let it bubble up
            pass

    def _handle_visual_line_mode(self, event: events.Key) -> None:
        """Handle keys in VISUAL LINE mode."""
        # For now, just handle ESC to return to normal
        if event.key == "escape":
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.visual_start = None
            self.visual_end = None
            event.stop()
            event.prevent_default()
            self.app_instance._update_vim_status("NORMAL | ESC=exit")
        else:
            # For other keys, don't stop the event - let it bubble up
            pass

    def _handle_command_mode(self, event: events.Key) -> None:
        """Handle keys in COMMAND mode."""
        event.stop()
        event.prevent_default()

        if event.key == "escape":
            # Cancel command
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
            self.app_instance._update_vim_status("NORMAL | ESC=exit")
        elif event.key == "enter":
            # Execute command
            self._execute_vim_command()
        elif event.key == "backspace":
            # Remove last character
            if len(self.command_buffer) > 1:
                self.command_buffer = self.command_buffer[:-1]
                self.app_instance._update_vim_status(f"COMMAND {self.command_buffer}")
            else:
                # Exit command mode if we delete the colon
                self.vim_mode = self.VIM_NORMAL
                self._update_cursor_style()
                self.command_buffer = ""
                self.app_instance._update_vim_status("NORMAL | ESC=exit")
        elif hasattr(event, 'character') and event.character and hasattr(event, 'is_printable') and event.is_printable:
            # Add character to command buffer
            self.command_buffer += event.character
            self.app_instance._update_vim_status(f"COMMAND {self.command_buffer}")

    def _execute_vim_command(self):
        """Execute the vim command in the buffer."""
        cmd = self.command_buffer[1:].strip()  # Remove the colon

        if cmd in ["w", "write"]:
            # Save without exiting
            if hasattr(self.app_instance, 'save_document_without_exit'):
                # Try new save method
                self.app_instance.save_document_without_exit()
            elif hasattr(self.app_instance, 'action_save_and_exit_edit'):
                # Fall back to save and exit, but return to edit mode
                self.app_instance.action_save_and_exit_edit()
                return

            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
            self.app_instance._update_vim_status("NORMAL | Saved")
        elif cmd in ["q", "quit"]:
            # Quit without saving (check for changes)
            if self.text != self.original_content:
                # Show error - changes not saved
                self.app_instance._update_vim_status(
                    "No write since last change (add ! to override)"
                )
                self.command_buffer = ""
                return
            else:
                self.app_instance.action_save_and_exit_edit()
        elif cmd in ["q!", "quit!"]:
            # Force quit without saving - use the exit method
            if hasattr(self.app_instance, 'exit_edit_mode'):
                import asyncio
                asyncio.create_task(self.app_instance.exit_edit_mode())
            else:
                self.app_instance.action_save_and_exit_edit()
        elif cmd in ["wq", "x"]:
            # Save and quit
            self.app_instance.action_save_and_exit_edit()
        elif cmd in ["wa", "wall"]:
            # Save all (just save current in our case)
            if hasattr(self.app_instance, 'action_save_document'):
                self.app_instance.action_save_document()
            elif hasattr(self.app_instance, 'action_save'):
                self.app_instance.action_save()
            else:
                # Fallback: just update status to indicate save attempt
                self.app_instance._update_vim_status("NORMAL | Save not available in this context")
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
        else:
            # Unknown command
            self.app_instance._update_vim_status(f"Not an editor command: {cmd}")
            self.command_buffer = ""
            return

        self.app_instance._update_vim_status("NORMAL | ESC=exit")

    def _move_word_forward(self, count: int = 1) -> None:
        """Move cursor forward by word boundaries."""
        text = self.text
        lines = text.split('\n')
        row, col = self.cursor_location

        for _ in range(count):
            if row >= len(lines):
                break

            line = lines[row]
            # Find next word boundary
            remaining = line[col:]
            match = re.search(r'\b\w', remaining)

            if match:
                col += match.start()
            else:
                # Move to next line
                row += 1
                col = 0
                if row < len(lines):
                    # Find first word on next line
                    match = re.search(r'\b\w', lines[row])
                    if match:
                        col = match.start()

        self.cursor_location = (row, col)

    def _move_word_backward(self, count: int = 1) -> None:
        """Move cursor backward by word boundaries."""
        text = self.text
        lines = text.split('\n')
        row, col = self.cursor_location

        for _ in range(count):
            if row < 0:
                break

            if col > 0:
                line = lines[row]
                # Find previous word boundary
                before = line[:col]
                matches = list(re.finditer(r'\b\w', before))
                if matches:
                    col = matches[-1].start()
                else:
                    col = 0
            else:
                # Move to previous line
                row -= 1
                if row >= 0:
                    col = len(lines[row])

        self.cursor_location = (row, col)

    def _move_word_end(self, count: int = 1) -> None:
        """Move cursor to end of word."""
        text = self.text
        lines = text.split('\n')
        row, col = self.cursor_location

        for _ in range(count):
            if row >= len(lines):
                break

            line = lines[row]
            # Find end of current/next word
            remaining = line[col:]
            match = re.search(r'\w+', remaining)

            if match:
                col += match.end() - 1
            else:
                # Move to next line
                row += 1
                col = 0
                if row < len(lines):
                    match = re.search(r'\w+', lines[row])
                    if match:
                        col = match.end() - 1

        self.cursor_location = (row, col)

    def _delete_line(self, count: int = 1) -> None:
        """Delete entire line(s)."""
        lines = self.text.split('\n')
        current_line = self.cursor_location[0]

        if current_line < len(lines):
            # Yank before deleting
            end_line = min(current_line + count, len(lines))
            self.yanked_text = '\n'.join(lines[current_line:end_line]) + '\n'

            # Create new text without the deleted lines
            new_lines = lines[:current_line] + lines[end_line:]
            new_text = '\n'.join(new_lines)

            # Replace all text
            self.text = new_text

            # Position cursor at start of line (or end if we deleted the last lines)
            if current_line < len(new_lines):
                self.cursor_location = (current_line, 0)
            elif new_lines:
                self.cursor_location = (len(new_lines) - 1, 0)
            else:
                self.cursor_location = (0, 0)

    def _yank_line(self, count: int = 1) -> None:
        """Yank (copy) entire line(s)."""
        lines = self.text.split('\n')
        current_line = self.cursor_location[0]

        if current_line < len(lines):
            end_line = min(current_line + count, len(lines))
            self.yanked_text = '\n'.join(lines[current_line:end_line]) + '\n'

    def _cursor_to_line_start(self) -> None:
        """Move cursor to start of current line."""
        row, _ = self.cursor_location
        self.cursor_location = (row, 0)

    def _cursor_to_line_end(self) -> None:
        """Move cursor to end of current line."""
        lines = self.text.split('\n')
        row, _ = self.cursor_location
        if row < len(lines):
            self.cursor_location = (row, len(lines[row]))

    def _cursor_to_start(self) -> None:
        """Move cursor to start of document."""
        self.cursor_location = (0, 0)

    def _cursor_to_end(self) -> None:
        """Move cursor to end of document."""
        lines = self.text.split('\n')
        last_line = len(lines) - 1
        last_col = len(lines[last_line]) if last_line >= 0 else 0

        key_logger.info(f"_cursor_to_end: moving to line {last_line}, col {last_col}")

        # Ensure we're moving to a valid position
        if last_line >= 0:
            self.cursor_location = (last_line, last_col)
            key_logger.info(f"_cursor_to_end: cursor set to ({last_line}, {last_col})")
        else:
            # Empty document
            self.cursor_location = (0, 0)
            key_logger.info("_cursor_to_end: empty document, cursor set to (0, 0)")

    def _delete_right_safe(self) -> None:
        """Delete character to the right, safely handling boundaries."""
        try:
            self.action_delete_right()
        except Exception:
            # Ignore if at end of document
            pass

    def _clear_title_selection(self, title_input) -> None:
        """Clear selection in title input."""
        try:
            # Position cursor at end without selection
            title_input.cursor_position = len(title_input.value)
            if hasattr(title_input, 'selection'):
                title_input.selection = (title_input.cursor_position, title_input.cursor_position)
        except Exception:
            pass


# For backward compatibility, alias the old name
EditTextArea = VimEditTextArea
