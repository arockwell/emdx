#!/usr/bin/env python3
"""
Prototype implementation of VimEditTextArea for EMDX TUI.
This demonstrates how vim-like keybindings could be added to the edit mode.
"""

from textual import events
from textual.widgets import TextArea
from textual.reactive import reactive
import re


class VimEditTextArea(TextArea):
    """TextArea with vim-like keybindings for EMDX."""
    
    # Vim modes
    VIM_NORMAL = "NORMAL"
    VIM_INSERT = "INSERT"
    VIM_VISUAL = "VISUAL"
    VIM_VISUAL_LINE = "V-LINE"
    
    # Reactive state for vim mode
    vim_mode = reactive(VIM_INSERT)
    
    def __init__(self, app_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance
        self.visual_start = None
        self.visual_end = None
        self.last_command = None
        self.pending_command = ""
        self.repeat_count = ""
        self.register = None
        self.yanked_text = ""
        
    def on_key(self, event: events.Key) -> None:
        """Handle key events with vim-like behavior."""
        # Global ESC handling - exit edit mode from any vim mode
        if event.key == "escape":
            if self.vim_mode == self.VIM_INSERT:
                # First ESC goes to normal mode
                self.vim_mode = self.VIM_NORMAL
                event.stop()
                event.prevent_default()
                self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
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
    
    def _handle_normal_mode(self, event: events.Key) -> None:
        """Handle keys in NORMAL mode."""
        key = event.key
        char = event.character if hasattr(event, 'character') else None
        
        # Stop event from bubbling up
        event.stop()
        event.prevent_default()
        
        # Handle repeat counts (e.g., 3j to move down 3 lines)
        if char and char.isdigit() and (self.repeat_count or char != '0'):
            self.repeat_count += char
            return
        
        # Get repeat count as integer
        count = int(self.repeat_count) if self.repeat_count else 1
        self.repeat_count = ""  # Reset after use
        
        # Movement commands
        if key == "h" or key == "left":
            self.move_cursor_relative(columns=-count)
        elif key == "j" or key == "down":
            self.move_cursor_relative(rows=count)
        elif key == "k" or key == "up":
            self.move_cursor_relative(rows=-count)
        elif key == "l" or key == "right":
            self.move_cursor_relative(columns=count)
        
        # Word movement
        elif char == "w":
            self._move_word_forward(count)
        elif char == "b":
            self._move_word_backward(count)
        elif char == "e":
            self._move_word_end(count)
        
        # Line movement
        elif char == "0":
            self.cursor_to_line_start()
        elif char == "$":
            self.cursor_to_line_end()
        elif char == "g":
            if self.pending_command == "g":
                # gg - go to first line
                self.cursor_to_start()
                self.pending_command = ""
            else:
                self.pending_command = "g"
                return
        elif char == "G":
            # Go to last line
            self.cursor_to_end()
        
        # Mode changes
        elif char == "i":
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "a":
            self.move_cursor_relative(columns=1)
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "I":
            self.cursor_to_line_start()
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "A":
            self.cursor_to_line_end()
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "o":
            self.cursor_to_line_end()
            self.insert("\n")
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "O":
            self.cursor_to_line_start()
            self.insert("\n")
            self.move_cursor_relative(rows=-1)
            self.vim_mode = self.VIM_INSERT
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        
        # Visual modes
        elif char == "v":
            self.vim_mode = self.VIM_VISUAL
            self.visual_start = self.cursor_location
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        elif char == "V":
            self.vim_mode = self.VIM_VISUAL_LINE
            self.visual_start = self.cursor_location
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
        
        # Editing commands
        elif char == "x":
            # Delete character under cursor
            for _ in range(count):
                self.delete_right()
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
        
        # Clear pending command if not handled
        if char not in ["g", "d", "y"]:
            self.pending_command = ""
    
    def _handle_insert_mode(self, event: events.Key) -> None:
        """Handle keys in INSERT mode - just pass through for normal editing."""
        # Let TextArea handle all keys in insert mode
        pass
    
    def _handle_visual_mode(self, event: events.Key) -> None:
        """Handle keys in VISUAL mode."""
        # For now, just handle ESC to return to normal
        if event.key == "escape":
            self.vim_mode = self.VIM_NORMAL
            self.visual_start = None
            self.visual_end = None
            event.stop()
            event.prevent_default()
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
    
    def _handle_visual_line_mode(self, event: events.Key) -> None:
        """Handle keys in VISUAL LINE mode."""
        # For now, just handle ESC to return to normal
        if event.key == "escape":
            self.vim_mode = self.VIM_NORMAL
            self.visual_start = None
            self.visual_end = None
            event.stop()
            event.prevent_default()
            self.app_instance.update_status(f"Edit Mode - {self.vim_mode}")
    
    def _move_word_forward(self, count: int = 1) -> None:
        """Move cursor forward by word boundaries."""
        text = self.text
        pos = self.cursor_location[1]  # Current column position
        line = self.cursor_location[0]  # Current row
        
        # Simple word boundary detection
        for _ in range(count):
            # Skip current word
            while pos < len(text) and text[pos].isalnum():
                pos += 1
            # Skip whitespace
            while pos < len(text) and not text[pos].isalnum():
                pos += 1
        
        # Move cursor to new position
        self.cursor_location = (line, pos)
    
    def _move_word_backward(self, count: int = 1) -> None:
        """Move cursor backward by word boundaries."""
        text = self.text
        pos = self.cursor_location[1]
        line = self.cursor_location[0]
        
        for _ in range(count):
            # Skip whitespace
            while pos > 0 and not text[pos-1].isalnum():
                pos -= 1
            # Skip to beginning of word
            while pos > 0 and text[pos-1].isalnum():
                pos -= 1
        
        self.cursor_location = (line, pos)
    
    def _move_word_end(self, count: int = 1) -> None:
        """Move cursor to end of word."""
        text = self.text
        pos = self.cursor_location[1]
        line = self.cursor_location[0]
        
        for _ in range(count):
            # Skip whitespace
            while pos < len(text) and not text[pos].isalnum():
                pos += 1
            # Skip to end of word
            while pos < len(text) and text[pos].isalnum():
                pos += 1
            pos -= 1  # Back up one to be on last char of word
        
        self.cursor_location = (line, pos)
    
    def _delete_line(self, count: int = 1) -> None:
        """Delete entire line(s)."""
        # Get current line
        lines = self.text.split('\n')
        current_line = self.cursor_location[0]
        
        # Yank before deleting
        self.yanked_text = '\n'.join(lines[current_line:current_line+count]) + '\n'
        
        # Delete the lines
        for _ in range(count):
            self.cursor_to_line_start()
            self.delete_to_end_of_line()
            if self.cursor_location[0] < len(lines) - 1:
                self.delete_right()  # Delete newline
    
    def _yank_line(self, count: int = 1) -> None:
        """Yank (copy) entire line(s)."""
        lines = self.text.split('\n')
        current_line = self.cursor_location[0]
        self.yanked_text = '\n'.join(lines[current_line:current_line+count]) + '\n'
    
    def cursor_to_line_start(self) -> None:
        """Move cursor to start of current line."""
        row, _ = self.cursor_location
        self.cursor_location = (row, 0)
    
    def cursor_to_line_end(self) -> None:
        """Move cursor to end of current line."""
        lines = self.text.split('\n')
        row, _ = self.cursor_location
        if row < len(lines):
            self.cursor_location = (row, len(lines[row]))
    
    def cursor_to_start(self) -> None:
        """Move cursor to start of document."""
        self.cursor_location = (0, 0)
    
    def cursor_to_end(self) -> None:
        """Move cursor to end of document."""
        lines = self.text.split('\n')
        last_line = len(lines) - 1
        self.cursor_location = (last_line, len(lines[last_line]))
    
    def delete_to_end_of_line(self) -> None:
        """Delete from cursor to end of line."""
        row, col = self.cursor_location
        lines = self.text.split('\n')
        if row < len(lines):
            line = lines[row]
            if col < len(line):
                # Delete from cursor to end of line
                for _ in range(len(line) - col):
                    self.delete_right()


# Example integration with the main TUI browser
"""
# In textual_browser.py, replace EditTextArea with VimEditTextArea:

def action_toggle_edit_mode(self) -> None:
    if not self.edit_mode:
        # Create VimEditTextArea instead of EditTextArea
        self.edit_textarea = VimEditTextArea(
            self,
            doc["content"],
            language="markdown",
            theme="monokai",
            show_line_numbers=True,
            tab_behavior="indent"
        )
        # ... rest of the implementation
"""