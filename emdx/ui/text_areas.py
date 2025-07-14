#!/usr/bin/env python3
"""
Text area widgets for EMDX TUI.
"""

import logging
import re
from textual import events
from textual.widgets import TextArea

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
    
    # Also create a dedicated key events log
    key_log_file = log_dir / "key_events.log"
    key_logger = logging.getLogger("key_events")
    key_handler = logging.FileHandler(key_log_file)
    key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    key_logger.addHandler(key_handler)
    key_logger.setLevel(logging.DEBUG)
    logger = logging.getLogger(__name__)
except Exception:
    # Fallback if logging setup fails
    import logging
    key_logger = logging.getLogger("key_events")
    logger = logging.getLogger(__name__)


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
                
        except Exception as e:
            key_logger.error(f"CRASH in SelectionTextArea.on_key: {e}")
            logger.error(f"Error in SelectionTextArea.on_key: {e}", exc_info=True)
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
        self.original_content = kwargs.get('text', '') if 'text' in kwargs else args[0] if args else ''
        
        # Set initial cursor style for NORMAL mode (solid, non-blinking)
        self.show_cursor = True
        self.cursor_blink = False
        
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
    
    def _update_line_numbers(self):
        """Update line numbers widget if it exists."""
        try:
            if hasattr(self, 'line_numbers_widget') and self.line_numbers_widget:
                # Use selection.end for cursor position as it's more reliable
                if hasattr(self, 'selection') and self.selection:
                    current_line = self.selection.end[0]
                elif hasattr(self, 'cursor_location'):
                    current_line = self.cursor_location[0]
                else:
                    current_line = 0
                
                # The cursor position is consistently 2 lines ahead of visual position
                # This happens because the content has the title removed but cursor
                # position still references the original document structure
                # We need to adjust by subtracting 2 to match visual position
                visual_current_line = max(0, current_line - 2)
                
                total_lines = len(self.text.split('\n'))
                
                logger.debug(f"🔍 LINE NUMBERS: cursor={current_line}, visual={visual_current_line}, total={total_lines}")
                
                # Pass self reference so line numbers can check focus
                self.line_numbers_widget.set_line_numbers(visual_current_line, total_lines, self)
        except Exception as e:
            logger.debug(f"Error updating line numbers: {e}")
        
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
                    self.app_instance._update_vim_status()
                    return
                else:
                    # Second ESC exits edit mode entirely
                    event.stop()
                    event.prevent_default()
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
                
        except Exception as e:
            key_logger.error(f"CRASH in VimEditTextArea.on_key: {e}")
            logger.error(f"Error in VimEditTextArea.on_key: {e}", exc_info=True)
            # Try to continue without crashing the app
            try:
                self.app_instance._update_vim_status(f"Error: {str(e)[:50]}")
            except:
                pass
    
    def _handle_normal_mode(self, event: events.Key) -> None:
        """Handle keys in NORMAL mode."""
        key = event.key
        char = event.character if hasattr(event, 'character') else None
        
        key_logger.info(f"VimEditTextArea._handle_normal_mode: key={key}, char={char}")
        
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
            key_logger.info(f"Moving left by {count}")
            self.move_cursor_relative(columns=-count)
            self._update_line_numbers()
        elif key == "j" or key == "down":
            key_logger.info(f"Moving down by {count}")
            self.move_cursor_relative(rows=count)
            self._update_line_numbers()
        elif key == "k" or key == "up":
            key_logger.info(f"Moving up by {count}")
            self.move_cursor_relative(rows=-count)
            self._update_line_numbers()
        elif key == "l" or key == "right":
            self.move_cursor_relative(columns=count)
            self._update_line_numbers()
        
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
            # Go to last line
            self._cursor_to_end()
            self._update_line_numbers()
        
        # Mode changes
        elif char == "i":
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "a":
            self.move_cursor_relative(columns=1)
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "I":
            self._cursor_to_line_start()
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "A":
            self._cursor_to_line_end()
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "o":
            self._cursor_to_line_end()
            self.insert("\n")
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "O":
            self._cursor_to_line_start()
            self.insert("\n")
            self.move_cursor_relative(rows=-1)
            self._update_line_numbers()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        
        # Visual modes
        elif char == "v":
            self.vim_mode = self.VIM_VISUAL
            self._update_cursor_style()
            self.visual_start = self.cursor_location
            self.app_instance._update_vim_status()
        elif char == "V":
            self.vim_mode = self.VIM_VISUAL_LINE
            self._update_cursor_style()
            self.visual_start = self.cursor_location
            self.app_instance._update_vim_status()
        
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
            self.app_instance._update_vim_status()
        
        # Tab key - no special handling needed without title input
        elif key == "tab":
            pass  # Could add tab functionality later
        
        # Clear pending command if not handled
        if char not in ["g", "d", "y"]:
            self.pending_command = ""
    
    def _handle_insert_mode(self, event: events.Key) -> None:
        """Handle keys in INSERT mode - just pass through for normal editing."""
        # Let TextArea handle all keys in insert mode
        super().on_key(event)
        # Only update line numbers for operations that might change line count
        if event.key in ["enter", "backspace", "delete"]:
            self._update_line_numbers()
    
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
            self.app_instance._update_vim_status()
        else:
            # For other keys, let TextArea handle them
            super().on_key(event)
    
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
            self.app_instance._update_vim_status()
        else:
            # For other keys, let TextArea handle them
            super().on_key(event)
    
    def _handle_command_mode(self, event: events.Key) -> None:
        """Handle keys in COMMAND mode."""
        event.stop()
        event.prevent_default()
        
        if event.key == "escape":
            # Cancel command
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
            self.app_instance._update_vim_status()
        elif event.key == "enter":
            # Execute command
            self._execute_vim_command()
        elif event.key == "backspace":
            # Remove last character
            if len(self.command_buffer) > 1:
                self.command_buffer = self.command_buffer[:-1]
            else:
                # Exit command mode if we delete the colon
                self.vim_mode = self.VIM_NORMAL
                self._update_cursor_style()
                self.command_buffer = ""
            self.app_instance._update_vim_status()
        elif hasattr(event, 'character') and event.character and hasattr(event, 'is_printable') and event.is_printable:
            # Add character to command buffer
            self.command_buffer += event.character
            self.app_instance._update_vim_status()
    
    def _execute_vim_command(self):
        """Execute the vim command in the buffer."""
        cmd = self.command_buffer[1:].strip()  # Remove the colon
        
        if cmd in ["w", "write"]:
            # Save
            self.app_instance.action_save_document()
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
        elif cmd in ["q", "quit"]:
            # Quit without saving (check for changes)
            if self.text != self.original_content:
                # Show error - changes not saved
                self.app_instance._update_vim_status("No write since last change (add ! to override)")
                self.command_buffer = ""
                return
            else:
                self.app_instance.action_save_and_exit_edit()
        elif cmd in ["q!", "quit!"]:
            # Force quit without saving
            self.app_instance.action_cancel_edit()
        elif cmd in ["wq", "x"]:
            # Save and quit
            self.app_instance.action_save_and_exit_edit()
        elif cmd in ["wa", "wall"]:
            # Save all (just save current in our case)
            self.app_instance.action_save_document()
            self.vim_mode = self.VIM_NORMAL
            self._update_cursor_style()
            self.command_buffer = ""
        else:
            # Unknown command
            self.app_instance._update_vim_status(f"Not an editor command: {cmd}")
            self.command_buffer = ""
            return
        
        self.app_instance._update_vim_status()
    
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
        self.cursor_location = (last_line, len(lines[last_line]))
    
    def _delete_right_safe(self) -> None:
        """Delete character to the right, safely handling boundaries."""
        try:
            self.action_delete_right()
        except:
            # Ignore if at end of document
            pass


# For backward compatibility, alias the old name
EditTextArea = VimEditTextArea