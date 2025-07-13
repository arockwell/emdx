#!/usr/bin/env python3
"""
Minimal textual browser that signals for external nvim handling.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rich.markdown import Markdown
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Input, Label, RichLog, TextArea

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.models.executions import (
    Execution,
    save_execution,
    get_recent_executions,
    update_execution_status,
)
from emdx.ui.formatting import format_tags, order_tags, truncate_emoji_safe
from emdx.utils.emoji_aliases import expand_aliases

# Set up logging
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
logger.info("EMDX TUI starting up")


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
        elif key == "j" or key == "down":
            key_logger.info(f"Moving down by {count} - BEFORE move_cursor_relative")
            try:
                self.move_cursor_relative(rows=count)
                key_logger.info(f"Moving down by {count} - AFTER move_cursor_relative SUCCESS")
            except Exception as e:
                key_logger.error(f"CRASH in move_cursor_relative(rows={count}): {e}")
                raise
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
            self._cursor_to_line_start()
        elif char == "$":
            self._cursor_to_line_end()
        elif char == "g":
            if self.pending_command == "g":
                # gg - go to first line
                self._cursor_to_start()
                self.pending_command = ""
            else:
                self.pending_command = "g"
                return
        elif char == "G":
            # Go to last line
            self._cursor_to_end()
        
        # Mode changes
        elif char == "i":
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "a":
            self.move_cursor_relative(columns=1)
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "I":
            self._cursor_to_line_start()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "A":
            self._cursor_to_line_end()
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "o":
            self._cursor_to_line_end()
            self.insert("\n")
            self.vim_mode = self.VIM_INSERT
            self._update_cursor_style()
            self.app_instance._update_vim_status()
        elif char == "O":
            self._cursor_to_line_start()
            self.insert("\n")
            self.move_cursor_relative(rows=-1)
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
        
        # Handle Tab to switch to title input
        elif key == "tab":
            # Try to focus title input
            try:
                title_input = self.app_instance.query_one("#title-input", TitleInput)
                title_input.focus()
            except:
                pass  # Title input might not exist
        
        # Clear pending command if not handled
        if char not in ["g", "d", "y"]:
            self.pending_command = ""
    
    def _handle_insert_mode(self, event: events.Key) -> None:
        """Handle keys in INSERT mode - just pass through for normal editing."""
        # Let TextArea handle all keys in insert mode
        super().on_key(event)
    
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


class FullScreenView(Screen):
    """Full screen document viewer."""

    CSS = """
    FullScreenView {
        align: center middle;
    }

    #doc-viewer {
        width: 100%;
        height: 100%;
        padding: 0;
    }

    #header {
        dock: top;
        height: 3;
        background: $surface;
        padding: 0 2;
    }

    #footer {
        dock: bottom;
        height: 1;
        background: $surface;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("q", "close", "Close"),
        ("escape", "close", "Close"),
        ("j", "scroll_down", "Down"),
        ("k", "scroll_up", "Up"),
        ("ctrl+d", "page_down", "Page down"),
        ("ctrl+u", "page_up", "Page up"),
        ("g", "scroll_top", "Top"),
        ("shift+g", "scroll_bottom", "Bottom"),
    ]

    def __init__(self, doc_id: int):
        """Initialize the full screen viewer.

        Args:
            doc_id: The ID of the document to display.

        """
        super().__init__()
        self.doc_id = doc_id

    def compose(self) -> ComposeResult:
        # Just the document content - no header metadata
        with ScrollableContainer(id="doc-viewer"):
            yield RichLog(id="content", wrap=True, highlight=True, markup=True, auto_scroll=False)

        # Footer
        yield Label("Press q or ESC to return", id="footer")

    def on_mount(self) -> None:
        """Load document content when mounted."""
        doc = get_document(str(self.doc_id))
        if doc:
            content_log = self.query_one("#content", RichLog)
            content_log.clear()

            # Smart title handling - avoid double titles
            content = doc["content"].strip()

            # Check if content already starts with the title as H1
            content_lines = content.split("\n")
            first_line = content_lines[0].strip() if content_lines else ""

            if first_line == f"# {doc['title']}":
                # Content already has the title, just show content
                markdown_content = content
            else:
                # Add title if not already present
                markdown_content = f"""# {doc['title']}

{content}"""
            md = Markdown(markdown_content, code_theme="monokai")
            content_log.write(md)
            content_log.scroll_to(0, 0, animate=False)

    def action_close(self) -> None:
        """Close the viewer."""
        self.dismiss()

    def action_scroll_down(self) -> None:
        """Scroll down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=1)

    def action_scroll_up(self) -> None:
        """Scroll up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-1)

    def action_page_down(self) -> None:
        """Page down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=10)

    def action_page_up(self) -> None:
        """Page up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-10)

    def action_scroll_top(self) -> None:
        """Scroll to top."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_to(0, 0, animate=False)

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom."""
        container = self.query_one("#doc-viewer", ScrollableContainer)
        container.scroll_to(0, container.max_scroll_y, animate=False)

    def action_copy_content(self) -> None:
        """Copy current document content to clipboard."""
        try:
            doc = get_document(str(self.doc_id))
            if doc:
                self.copy_to_clipboard(doc["content"])
        except Exception:
            # Silently ignore copy errors in full screen view
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key events that aren't bindings."""
        # Let 's' key pass through - handled by main app
        pass

    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess

        # Try pbcopy on macOS first
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"], input=text, text=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(
                        ["xsel", "--clipboard", "--input"], input=text, text=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass


class DeleteConfirmScreen(ModalScreen):
    """Modal screen for delete confirmation."""

    CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 2;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }

    #question {
        column-span: 2;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    Button {
        width: 100%;
    }
    """

    BINDINGS = [
        ("y", "confirm_delete", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, doc_id: int, doc_title: str):
        super().__init__()
        self.doc_id = doc_id
        self.doc_title = doc_title

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(
                f'Delete document #{self.doc_id}?\n"{self.doc_title}"\n\n'
                f"[dim]Press [bold]y[/bold] to delete, [bold]n[/bold] to cancel[/dim]",
                id="question",
            )
            yield Button("Cancel (n)", variant="primary", id="cancel")
            yield Button("Delete (y)", variant="error", id="delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_delete(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MinimalDocumentBrowser(App):
    """Minimal document browser that signals external wrapper for nvim."""

    ENABLE_COMMAND_PALETTE = False
    # Disable mouse support to prevent coordinate spam
    MOUSE_DISABLED = True
    # Enable text selection globally
    ALLOW_SELECT = True

    CSS = """
    #sidebar {
        width: 50%;
        border-right: solid $primary;
    }

    #preview-container {
        width: 50%;
    }
    
    #vim-mode-indicator {
        height: 1;
        background: $primary;
        padding: 0 1;
        text-align: center;
        color: $text;
        display: none;
        border-bottom: solid $accent;
    }
    
    #vim-mode-indicator.visible {
        display: block;
    }
    
    #preview {
        width: 100%;
        padding: 0;
        overflow: auto;
        scrollbar-gutter: stable;
    }
    
    #preview TextArea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
    }
    
    .constrained-textarea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
        box-sizing: border-box !important;
        padding: 0 1 !important;
    }
    
    #edit-wrapper {
        width: 100%;
        height: 100%;
        overflow-x: auto;
        overflow-y: auto;
    }
    .edit-title-input {
        width: 100%;
        margin-bottom: 1;
        background: $background;
        border: tall $primary;
    }
    .edit-title-input:focus {
        border: tall $accent;
    }
    
    /* Vim mode styling - using background colors instead of cursor */
    .vim-insert-mode {
        background: $background;
    }
    
    .vim-normal-mode {
        background: $background;
    }

    RichLog {
        width: 100%;
        height: 100%;
        padding: 0 1;
        background: $background;
    }

    RichLog:focus {
        border: thick $accent;
    }

    #preview-textarea {
        width: 100%;
        height: 100%;
        max-width: 100%;
        min-width: 0;
        padding: 0 1;
        background: $background;
        overflow-x: hidden;
        overflow-y: auto;
        box-sizing: border-box;
    }

    #preview-textarea:focus {
        border: thick $accent;
    }

    DataTable {
        height: 100%;
    }


    Input {
        dock: top;
        margin: 0 1;
        display: none;
    }

    Input.visible {
        display: block;
    }

    #tag-input {
        display: none;
    }

    #tag-input.visible {
        display: block;
    }

    #tag-selector {
        dock: top;
        display: none;
        height: 1;
        margin: 0 1;
        text-align: center;
    }

    #tag-selector.visible {
        display: block;
    }

    #status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("escape", "quit", "Quit", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("shift+g", "cursor_bottom", "Bottom", show=False),
        Binding("/", "search_mode", "Search", key_display="/"),
        Binding("r", "refresh", "Refresh", key_display="r"),
        Binding("n", "new_note", "New Note", key_display="n"),
        Binding("e", "toggle_edit_mode", "Edit in place", key_display="e"),
        Binding("d", "delete", "Delete", show=False),
        Binding("enter", "view", "View", show=False),
        Binding("t", "tag_mode", "Tag", key_display="t"),
        Binding("shift+t", "untag_mode", "Untag", show=False),
        Binding("tab", "focus_preview", "Focus Preview", key_display="Tab"),
        Binding("s", "toggle_selection_mode", "Select Text", key_display="s"),
        Binding("ctrl+c", "copy_selected", "Copy Selection", show=False),
        Binding("h", "tmux_split_horizontal", "Split →", key_display="h"),
        Binding("v", "tmux_split_vertical", "Split ↓", key_display="v"),
        Binding("x", "claude_execute", "Execute", key_display="x"),
        Binding("l", "log_browser", "Log Browser", key_display="l"),
    ]

    mode = reactive("NORMAL")
    search_query = reactive("")
    tag_action = reactive("")  # "add" or "remove"
    current_tag_completion = reactive(0)  # Current completion index
    selection_mode = reactive(False)  # Text selection mode
    edit_mode = reactive(False)  # Edit mode for in-place editing
    editing_doc_id = None  # Track which document is being edited

    def __init__(self):
        super().__init__()
        self.documents = []
        self.filtered_docs = []
        self.current_doc_id = None
        self.refresh_timer = None  # Timer for auto-dismissing refresh status
        # Log browser state
        self.executions = []  # List of Execution objects
        self.current_execution_index = 0
        self.current_log_file = None

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input",
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")

        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with Vertical(id="preview-container"):
                yield Label("", id="vim-mode-indicator")
                with ScrollableContainer(id="preview"):
                    yield RichLog(
                        id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
                    )

        yield Label("", id="status")

    def on_mount(self) -> None:
        try:
            self.load_documents()
            self.setup_table()
            self.update_status()
            if self.filtered_docs:
                self.on_row_selected()
        except Exception as e:
            # If there's any error during mount, ensure we have a usable state
            import traceback

            logger.error(f"Error during on_mount(): {e}")
            traceback.print_exc()
            self.exit(message=f"Error during startup: {e}")

    def load_documents(self):
        try:
            db.ensure_schema()
            docs = db.list_documents(limit=1000)

            # Add tags to each document
            for doc in docs:
                doc["tags"] = get_document_tags(doc["id"])

            self.documents = docs
            self.filtered_docs = docs
        except Exception as e:
            self.exit(message=f"Error loading documents: {e}")

    def setup_table(self):
        table = self.query_one("#doc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Only add columns if they don't already exist
        if len(table.columns) == 0:
            table.add_columns("ID", "Title", "Tags")

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[: title_space - 3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars with emoji-safe truncation
            formatted_tags = format_tags(doc.get("tags", []))
            tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
            if was_truncated:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        table.focus()

    def on_row_selected(self):
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            self.current_doc_id = doc["id"]
            self.update_preview(doc["id"])

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        if message.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[message.cursor_row]
            
            # Don't allow switching documents while in edit mode
            if self.edit_mode:
                # Show warning and prevent switch
                status = self.query_one("#status", Label)
                self.cancel_refresh_timer()
                status.update("⚠️ Exit edit mode (ESC) before switching documents")
                # Move cursor back to editing document
                if self.editing_doc_id:
                    for i, d in enumerate(self.filtered_docs):
                        if d["id"] == self.editing_doc_id:
                            table = self.query_one("#doc-table", DataTable)
                            table.cursor_coordinate = (i, 0)
                            break
                return
            
            self.current_doc_id = doc["id"]
            self.update_preview(doc["id"])

    def update_preview(self, doc_id: int):
        try:
            doc = get_document(str(doc_id))
            if doc:
                # Check if we're in selection mode or formatted mode
                try:
                    preview_area = self.query_one("#preview-content", RichLog)
                    # We're in formatted mode
                    preview_area.clear()

                    content = doc["content"].strip()
                    content_lines = content.split("\n")
                    first_line = content_lines[0].strip() if content_lines else ""

                    if first_line == f"# {doc['title']}":
                        markdown_content = content
                    else:
                        markdown_content = f"# {doc['title']}\n\n{content}"

                    from rich.markdown import Markdown

                    md = Markdown(markdown_content, code_theme="monokai")
                    preview_area.write(md)

                except Exception:
                    # Might be in selection mode with TextArea
                    try:
                        preview_area = self.query_one("#preview-content")
                        content = doc["content"].strip()
                        if not content.startswith(f"# {doc['title']}"):
                            plain_content = f"# {doc['title']}\n\n{content}"
                        else:
                            plain_content = content
                        preview_area.text = plain_content
                    except Exception:
                        pass

        except Exception as e:
            # Try to show error in whatever widget we have
            try:
                preview_area = self.query_one("#preview-content", RichLog)
                preview_area.clear()
                preview_area.write(f"[red]Error loading preview: {e}[/red]")
            except Exception:
                try:
                    preview_area = self.query_one("#preview-content")
                    preview_area.text = f"Error loading preview: {e}"
                except Exception:
                    pass

    def update_status(self):
        # Cancel any pending refresh timer when updating status
        self.cancel_refresh_timer()

        status = self.query_one("#status", Label)
        search_input = self.query_one("#search-input", Input)

        # Build status with document count
        status_parts = []
        if search_input.value and search_input.value.startswith("tags:"):
            tag_query = search_input.value[5:].strip()
            status_parts.append(
                f"{len(self.filtered_docs)}/{len(self.documents)} docs (tag: {tag_query})"
            )
        elif search_input.value:
            status_parts.append(
                f"{len(self.filtered_docs)}/{len(self.documents)} docs (search: {search_input.value})"
            )
        else:
            status_parts.append(f"{len(self.filtered_docs)}/{len(self.documents)} docs")
        
        # Add key hints for normal mode
        if self.mode == "NORMAL":
            status_parts.append("n=new | e=edit | /=search | t=tag | q=quit")
        elif self.mode == "SEARCH":
            status_parts.append("Enter=apply | ESC=cancel")
        elif self.mode == "TAG":
            if self.tag_action == "add":
                status_parts.append("Enter=add tags | ESC=cancel")
            else:
                status_parts.append("Tab=select | Enter=remove | ESC=cancel")
        
        status.update(" | ".join(status_parts))

    def _update_vim_status(self, message=None):
        """Update status bar to show vim mode when in edit mode."""
        if self.edit_mode and hasattr(self, 'edit_textarea') and hasattr(self.edit_textarea, 'vim_mode'):
            vim_mode = self.edit_textarea.vim_mode
            pending = getattr(self.edit_textarea, 'pending_command', '')
            repeat = getattr(self.edit_textarea, 'repeat_count', '')
            command_buffer = getattr(self.edit_textarea, 'command_buffer', '')
            
            # Update vim mode indicator in preview pane
            try:
                vim_indicator = self.query_one("#vim-mode-indicator", Label)
                vim_indicator.add_class("visible")
            except Exception as e:
                logger.error(f"Failed to update vim mode indicator: {e}")
            
            # Build mode indicator text with subtle cursor hints (vim-like)
            try:
                if vim_mode == "INSERT":
                    vim_indicator.update("[bold green]-- INSERT --[/bold green]")
                elif vim_mode == "NORMAL":
                    mode_text = "-- NORMAL --"
                    if repeat:
                        mode_text = f"-- NORMAL ({repeat}) --"
                    if pending:
                        mode_text = f"-- NORMAL ({pending}) --"
                    vim_indicator.update(f"[bold blue]{mode_text}[/bold blue]")
                elif vim_mode == "VISUAL":
                    vim_indicator.update("[bold yellow]-- VISUAL --[/bold yellow]")
                elif vim_mode == "V-LINE":
                    vim_indicator.update("[bold yellow]-- VISUAL LINE --[/bold yellow]")
                elif vim_mode == "COMMAND":
                    vim_indicator.update(f"[bold magenta]{command_buffer}[/bold magenta]")
            except Exception as e:
                logger.error(f"Failed to update vim indicator text: {e}")
            
            # Build status message
            status_parts = [f"EDIT MODE: #{self.editing_doc_id}"]
            
            # Add message if provided
            if message:
                status_parts.append(f"[red]{message}[/red]")
            else:
                # Add instructions
                if vim_mode == "INSERT":
                    status_parts.append("ESC=normal | Ctrl+S=save")
                elif vim_mode == "COMMAND":
                    status_parts.append("Enter=execute | ESC=cancel")
                elif vim_mode == "NORMAL":
                    status_parts.append("i=insert | :=command | ESC=exit | Tab=switch title/content")
                else:
                    status_parts.append("ESC=normal/exit")
            
            status = self.query_one("#status", Label)
            status.update(" | ".join(status_parts))
        else:
            # Hide vim mode indicator when not in edit mode
            try:
                vim_indicator = self.query_one("#vim-mode-indicator", Label)
                vim_indicator.remove_class("visible")
                vim_indicator.update("")
            except Exception:
                pass  # Indicator might not exist yet

    def watch_mode(self, old_mode: str, new_mode: str):
        try:
            search = self.query_one("#search-input", Input)
            tag_input = self.query_one("#tag-input", Input)
            tag_selector = self.query_one("#tag-selector", Label)
            table = self.query_one("#doc-table", DataTable)
        except Exception:
            # Widgets don't exist yet (during initialization) - skip mode handling
            return

        if new_mode == "SEARCH":
            search.add_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.focus()
        elif new_mode == "TAG":
            search.remove_class("visible")

            # Show current tags in placeholder
            if self.current_doc_id:
                doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
                if doc:
                    current_tags = doc.get("tags", [])

                    if self.tag_action == "add":
                        # Show input for adding tags
                        tag_input.add_class("visible")
                        tag_selector.remove_class("visible")
                        if current_tags:
                            tag_input.placeholder = f"Add tags (current: {', '.join(current_tags)})"
                        else:
                            tag_input.placeholder = "Add tags (no current tags)"
                        tag_input.focus()
                    else:  # remove
                        # Show visual selector for removing tags
                        tag_input.remove_class("visible")
                        if current_tags:
                            tag_selector.add_class("visible")
                            self.current_tag_completion = 0  # Start with first tag
                            self.update_tag_selector()
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("Tab to navigate, Enter to remove tag, Esc to cancel")
                        else:
                            tag_selector.remove_class("visible")
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No tags to remove")
                            self.mode = "NORMAL"
                            return

                    # Only reset completion index for add mode
                    if self.tag_action == "add":
                        self.current_tag_completion = 0
        else:
            search.remove_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.value = ""
            tag_input.value = ""
            self.current_tag_completion = 0  # Reset completion index
            table.focus()

    def action_search_mode(self):
        self.mode = "SEARCH"

    def action_tag_mode(self):
        if not self.current_doc_id:
            return
        self.tag_action = "add"
        self.mode = "TAG"

    def action_untag_mode(self):
        if not self.current_doc_id:
            return
        self.tag_action = "remove"
        self.mode = "TAG"
    
    def action_new_note(self):
        """Create a new note in the TUI."""
        try:
            # Generate title with timestamp
            from datetime import datetime
            title = f"New Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Detect project from current directory
            from emdx.utils.git import get_git_project
            from pathlib import Path
            project = get_git_project(Path.cwd())
            
            # Create new document in database
            from emdx.models.documents import save_document
            doc_id = save_document(title, "", project)
            
            # Refresh documents list
            self.load_documents()
            self.filter_documents(self.search_query)
            
            # Find the new document in the list and select it
            for i, doc in enumerate(self.filtered_docs):
                if doc["id"] == doc_id:
                    table = self.query_one("#doc-table", DataTable)
                    table.cursor_coordinate = (i, 0)
                    self.on_row_selected()
                    break
            
            # Immediately enter edit mode
            self.action_toggle_edit_mode()
            
            # Update status to show user they're in new note (NORMAL mode)
            self._update_vim_status("New note created - press 'i' to insert")
            
        except Exception as e:
            logger.error(f"Error creating new note: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error creating new note: {str(e)[:50]}...")

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search-input":
            self.search_query = event.value
            self.filter_documents(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self.mode = "NORMAL"
        elif event.input.id == "tag-input":
            # Process tag input for both add and remove
            tags = [tag.strip() for tag in event.value.split() if tag.strip()]
            if tags and self.current_doc_id:
                # Save current position
                table = self.query_one("#doc-table", DataTable)
                current_row = table.cursor_row
                current_doc_id = self.current_doc_id

                try:
                    if self.tag_action == "add":
                        added_tags = add_tags_to_document(self.current_doc_id, tags)
                        if added_tags:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update(f"Added tags: {', '.join(added_tags)}")
                        else:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No new tags added (may already exist)")
                    else:  # remove
                        removed_tags = remove_tags_from_document(self.current_doc_id, tags)
                        if removed_tags:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update(f"Removed tags: {', '.join(removed_tags)}")
                        else:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No tags removed (may not exist)")

                    # Refresh document data and restore position
                    self.load_documents()
                    self.filter_documents(self.search_query)
                    self.restore_table_position(current_doc_id, current_row)

                except Exception as e:
                    self.cancel_refresh_timer()
                    status = self.query_one("#status", Label)
                    status.update(f"Error: {e}")

            self.mode = "NORMAL"

    def on_key(self, event: events.Key) -> None:
        try:
            # Comprehensive logging of ALL key events
            event_attrs = {}
            for attr in ["key", "character", "name", "is_printable", "aliases"]:
                if hasattr(event, attr):
                    try:
                        event_attrs[attr] = getattr(event, attr)
                    except Exception as attr_error:
                        event_attrs[attr] = f"ERROR: {attr_error}"

            key_logger.info(f"App.on_key: {event_attrs}")
            logger.debug(f"Key event: key={event.key}")

            # Handle global Escape key - quit from any mode
            if event.key == "escape":
                # Edit mode ESC is handled by VimEditTextArea - don't interfere
                if self.edit_mode:
                    # Let the edit widget handle ESC
                    return
                
                # Selection mode ESC is handled by SelectionTextArea

                # From any mode/state, ESC should quit
                if self.mode == "SEARCH":
                    self.mode = "NORMAL"
                    self.search_query = ""
                    self.filter_documents("")
                elif self.mode == "TAG":
                    self.mode = "NORMAL"
                else:
                    # From normal mode or preview focus, quit the app
                    self.action_quit()
                event.prevent_default()
                return

            if self.mode == "TAG":
                if event.key == "tab" and self.tag_action == "remove":
                    # Tab cycling for tag removal
                    self.complete_tag_removal()
                    event.prevent_default()
                    event.stop()
                elif event.key == "enter" and self.tag_action == "remove":
                    # Remove the highlighted tag
                    self.remove_highlighted_tag()
                    event.prevent_default()
            elif self.mode == "NORMAL":
                # Handle keys that don't require a document
                if event.key == "tab":
                    event.prevent_default()
                    event.stop()
                    self.action_focus_preview()
                elif event.character == "s":
                    event.prevent_default()
                    event.stop()
                    self.action_toggle_selection_mode()
                elif event.character == "n":
                    event.prevent_default()
                    event.stop()
                    self.action_new_note()
                # Handle keys that require a document
                elif self.current_doc_id:
                    if event.key == "enter":
                        event.prevent_default()
                        event.stop()
                        self.action_view()
                    elif event.character == "e":
                        event.prevent_default()
                        event.stop()
                        self.action_toggle_edit_mode()
                    elif event.character == "d":
                        event.prevent_default()
                        event.stop()
                        self.action_delete()
                    elif event.character == "t":
                        event.prevent_default()
                        event.stop()
                        self.action_tag_mode()
                    elif event.character == "T":
                        event.prevent_default()
                        event.stop()
                        self.action_untag_mode()

        # Note: In Textual 4.0, we should NOT call super().on_key()
        # as Textual automatically handles event propagation

        except Exception as e:
            key_logger.error(f"CRASH in App.on_key: {e}")
            logger.error(f"Error in App.on_key: {e}", exc_info=True)
            # Don't re-raise here - let app continue

    def filter_documents(self, query: str):
        if not query:
            self.filtered_docs = self.documents
        elif query.startswith("tags:"):
            # Tag-based search mode: "tags:docker,kubernetes" or "tags:any:docker,python"
            tag_query = query[5:].strip()  # Remove "tags:" prefix

            if tag_query.startswith("any:"):
                # Search for documents with ANY of the specified tags
                tags = [tag.strip() for tag in tag_query[4:].split(",") if tag.strip()]
                mode = "any"
            else:
                # Default: search for documents with ALL specified tags
                tags = [tag.strip() for tag in tag_query.split(",") if tag.strip()]
                mode = "all"

            if tags:
                try:
                    # Expand aliases before searching
                    expanded_tags = expand_aliases(tags)
                    # Use the existing search_by_tags function
                    results = search_by_tags(expanded_tags, mode=mode, limit=1000)

                    # Convert results to match our document format
                    result_ids = {doc["id"] for doc in results}
                    self.filtered_docs = [doc for doc in self.documents if doc["id"] in result_ids]
                except Exception:
                    # Fall back to simple filtering if search_by_tags fails
                    self.filtered_docs = [
                        doc
                        for doc in self.documents
                        if any(
                            tag.lower() in [t.lower() for t in doc.get("tags", [])] for tag in tags
                        )
                    ]
            else:
                self.filtered_docs = self.documents
        else:
            # Regular search in title, project, and tags
            query_lower = query.lower()
            self.filtered_docs = [
                doc
                for doc in self.documents
                if query_lower in doc["title"].lower()
                or query_lower in (doc["project"] or "").lower()
                or any(query_lower in tag.lower() for tag in doc.get("tags", []))
            ]

        table = self.query_one("#doc-table", DataTable)
        table.clear()

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[: title_space - 3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars with emoji-safe truncation
            formatted_tags = format_tags(doc.get("tags", []))
            tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
            if was_truncated:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        self.update_status()

        if self.filtered_docs and table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_down(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_down()

    def action_cursor_up(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_up()

    def action_cursor_top(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_bottom(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            if table.row_count > 0:
                table.cursor_coordinate = (table.row_count - 1, 0)
                self.on_row_selected()


    def action_delete(self):
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]

            def check_delete(should_delete: bool) -> None:
                if should_delete:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "emdx.cli",
                            "delete",
                            str(self.current_doc_id),
                            "--force",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        self.load_documents()
                        self.filter_documents(self.search_query)

            self.push_screen(DeleteConfirmScreen(doc["id"], doc["title"]), check_delete)

    def action_view(self):
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        self.push_screen(FullScreenView(self.current_doc_id))

    def action_refresh(self):
        """Refresh the document list."""
        # Save current state
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = None

        # Get current document ID if a row is selected
        if current_row is not None and current_row < len(self.filtered_docs):
            current_doc_id = self.filtered_docs[current_row]["id"]

        # Save search state
        search_query = self.search_query if self.mode == "SEARCH" else None

        # Reload documents
        self.load_documents()

        # Clear and rebuild table
        table.clear()
        self.setup_table()

        # Restore search if it was active
        if search_query:
            self.search_query = search_query
            search_input = self.query_one("#search-input", Input)
            search_input.value = search_query
            self.filter_documents(search_query)

        # Restore selection
        if current_doc_id:
            # Try to find the same document
            for idx, doc in enumerate(self.filtered_docs):
                if doc["id"] == current_doc_id:
                    table.cursor_coordinate = (idx, 0)
                    self.on_row_selected()
                    break
            else:
                # Document not found, restore row position if valid
                if current_row is not None and current_row < len(self.filtered_docs):
                    table.cursor_coordinate = (current_row, 0)
                    self.on_row_selected()
                elif self.filtered_docs:
                    # Default to first row if available
                    table.cursor_coordinate = (0, 0)
                    self.on_row_selected()
        elif self.filtered_docs and current_row is not None:
            # No previous doc ID, just restore row position
            new_row = min(current_row, len(self.filtered_docs) - 1)
            table.cursor_coordinate = (new_row, 0)
            self.on_row_selected()

        # Show notification with auto-dismiss after 3 seconds
        status = self.query_one("#status", Label)
        status.update("Documents refreshed")

        # Cancel any existing timer
        if self.refresh_timer:
            self.refresh_timer.stop()

        # Set a timer to restore the normal status after 3 seconds
        self.refresh_timer = self.set_timer(3.0, self.restore_normal_status)

    def update_tag_selector(self):
        """Update the visual tag selector."""
        if not self.current_doc_id:
            return

        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        tag_selector = self.query_one("#tag-selector", Label)

        # Build visual representation: a  [b]  c
        visual_tags = []
        for i, tag in enumerate(current_tags):
            if i == self.current_tag_completion:
                visual_tags.append(f"[reverse]{tag}[/reverse]")
            else:
                visual_tags.append(tag)

        tag_selector.update("    ".join(visual_tags))

    def complete_tag_removal(self):
        """Handle tab cycling for tag removal."""
        if not self.current_doc_id:
            return

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        # Move to next tag
        self.current_tag_completion = (self.current_tag_completion + 1) % len(current_tags)

        # Update visual selector
        self.update_tag_selector()

    def remove_highlighted_tag(self):
        """Remove the currently highlighted tag."""
        if not self.current_doc_id:
            return

        # Save current table position
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = self.current_doc_id

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags or self.current_tag_completion >= len(current_tags):
            return

        # Get the tag to remove
        tag_to_remove = current_tags[self.current_tag_completion]

        try:
            # Remove the tag
            removed_tags = remove_tags_from_document(self.current_doc_id, [tag_to_remove])
            if removed_tags:
                # Show success message
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Removed tag: {tag_to_remove}")

                # Refresh document data but preserve position
                self.load_documents()
                self.filter_documents(self.search_query)

                # Restore table position
                self.restore_table_position(current_doc_id, current_row)

                # Exit tag mode
                self.mode = "NORMAL"
            else:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Failed to remove tag")
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error removing tag: {e}")

    def restore_table_position(self, target_doc_id: int, fallback_row: int):
        """Restore table position to specific document or row."""
        table = self.query_one("#doc-table", DataTable)

        # First try to find the same document
        for idx, doc in enumerate(self.filtered_docs):
            if doc["id"] == target_doc_id:
                table.cursor_coordinate = (idx, 0)
                self.on_row_selected()
                return

        # Document not found (maybe filtered out), restore row position if valid
        if fallback_row is not None and fallback_row < len(self.filtered_docs):
            table.cursor_coordinate = (fallback_row, 0)
            self.on_row_selected()
        elif self.filtered_docs:
            # Default to first row if available
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_copy_selected(self):
        """Copy selected text or full document when Ctrl+C is pressed."""
        logger.debug("action_copy_selected called")
        try:
            if self.selection_mode:
                logger.debug("In selection mode, trying to copy selected text")
                # Try to get selected text from TextArea
                try:
                    text_area = self.query_one("#preview-content", SelectionTextArea)
                    selected_text = text_area.selected_text

                    if selected_text:
                        logger.debug(f"Copying selected text: {len(selected_text)} characters")
                        self.copy_to_clipboard(selected_text)
                        status = self.query_one("#status", Label)
                        self.cancel_refresh_timer()
                        status.update("Selected text copied to clipboard!")
                    else:
                        logger.debug("No text selected, copying full document")
                        self.action_copy_content()
                except Exception as text_error:
                    logger.debug(
                        f"Could not get selected text: {text_error}, copying full document"
                    )
                    self.action_copy_content()
            else:
                logger.debug("Not in selection mode, copying full document")
                # Not in selection mode, copy full document
                self.action_copy_content()
        except Exception as e:
            logger.error(f"Error in action_copy_selected: {e}", exc_info=True)
            # Log error but don't crash
            try:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Copy error: {str(e)[:30]}...")
            except Exception:
                pass

    def action_copy_content(self):
        """Copy current document content to clipboard."""
        logger.debug(f"action_copy_content called, current_doc_id={self.current_doc_id}")
        if self.current_doc_id:
            try:
                doc = get_document(str(self.current_doc_id))
                if doc:
                    content = doc["content"].strip()
                    if not content.startswith(f"# {doc['title']}"):
                        content_to_copy = f"# {doc['title']}\n\n{content}"
                    else:
                        content_to_copy = content

                    logger.debug(f"Copying {len(content_to_copy)} characters to clipboard")
                    self.copy_to_clipboard(content_to_copy)
                    status = self.query_one("#status", Label)
                    self.cancel_refresh_timer()
                    status.update("Full document copied to clipboard!")

            except Exception as e:
                logger.error(f"Error in action_copy_content: {e}", exc_info=True)
                status = self.query_one("#status", Label)
                self.cancel_refresh_timer()
                status.update(f"Copy failed: {e}")

    def action_focus_preview(self):
        """Focus the preview pane."""
        try:
            # Try to get whatever widget is currently in the preview
            preview_area = self.query_one("#preview-content")
            preview_area.focus()
            status = self.query_one("#status", Label)

            if self.selection_mode:
                self.cancel_refresh_timer()
                status.update("TextArea focused - select text with mouse, Esc to return")
            else:
                self.cancel_refresh_timer()
                status.update("Preview focused - use 's' for text selection, Esc to return")
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Focus failed: {e}")

    def action_toggle_selection_mode(self):
        """Toggle between formatted view and text selection mode."""
        try:
            # Check if we're in the right screen/context
            try:
                container = self.query_one("#preview", ScrollableContainer)
                status = self.query_one("#status", Label)
            except Exception:
                # We're not in the main browser screen - selection mode not available
                return

            if not self.selection_mode:
                # Switch to selection mode - use TextArea for native selection support
                self.selection_mode = True

                # Get content based on current mode
                plain_content = "Select and copy text here..."
                
                if self.mode == "LOG_BROWSER":
                    # Extract log content from RichLog
                    plain_content = self._extract_log_content()
                elif self.current_doc_id:
                    doc = get_document(str(self.current_doc_id))
                    if doc:
                        content = doc["content"].strip()
                        if not content.startswith(f"# {doc['title']}"):
                            plain_content = f"# {doc['title']}\n\n{content}"
                        else:
                            plain_content = content

                # Remove old widgets explicitly and safely
                try:
                    # First try to remove by query
                    existing_widget = container.query_one("#preview-content")
                    if existing_widget:
                        existing_widget.remove()
                except Exception:
                    pass
                
                # Then remove all children as backup
                container.remove_children()
                
                # Refresh the container to ensure DOM is clean
                container.refresh(layout=True)

                # Use deferred mounting to avoid ID conflicts
                def mount_text_area():
                    try:
                        text_area = SelectionTextArea(
                            self,  # Pass app instance
                            plain_content,
                            id="preview-content"
                        )
                        # Make it read-only after creation
                        text_area.read_only = True
                        # Keep it focusable for selection
                        text_area.disabled = False
                        text_area.can_focus = True

                        # Apply the constrained-textarea CSS class
                        text_area.add_class("constrained-textarea")

                        # Try to enable word wrap if the property exists
                        if hasattr(text_area, 'word_wrap'):
                            text_area.word_wrap = True

                        # Mount the widget with constraints already applied
                        container.mount(text_area)
                        text_area.focus()

                        self.cancel_refresh_timer()
                        status.update(
                            "SELECTION MODE: Select text with mouse, Ctrl+C to copy, ESC or 's' to exit"
                        )
                    except Exception as mount_error:
                        self.cancel_refresh_timer()
                        status.update(f"Failed to create selection widget: {mount_error}")

                # Use call_after_refresh to ensure DOM is clean before mounting
                self.call_after_refresh(mount_text_area)

            else:
                # Switch back to formatted view
                self.selection_mode = False

                # Remove old widgets explicitly and safely
                try:
                    # First try to remove by query
                    existing_widget = container.query_one("#preview-content")
                    if existing_widget:
                        existing_widget.remove()
                except Exception:
                    pass
                
                # Then remove all children as backup
                container.remove_children()
                
                # Refresh the container to ensure DOM is clean
                container.refresh(layout=True)

                # Use deferred mounting to avoid ID conflicts
                def mount_richlog():
                    richlog = RichLog(
                        id="preview-content",
                        wrap=True,
                        highlight=True,
                        markup=True,
                        auto_scroll=False
                    )

                    # Mount the new widget
                    container.mount(richlog)

                    # Reset container scroll and refresh layout
                    container.scroll_to(0, 0, animate=False)
                    container.refresh(layout=True)

                    # Use deferred content restoration
                    self.call_after_refresh(self._restore_preview_content)

                # Use call_after_refresh to ensure DOM is clean before mounting
                self.call_after_refresh(mount_richlog)

                self.cancel_refresh_timer()
                if self.mode == "LOG_BROWSER":
                    status.update("LOG BROWSER: j/k to navigate logs, 's' for text selection, 'q' to exit")
                else:
                    status.update("FORMATTED MODE: Nice display, 's' for text selection, ESC to quit")

        except Exception as e:
            # Recovery: ensure we have a working widget
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Toggle failed: {e} - restoring view...")

            try:
                # Emergency recovery - ensure we have a preview widget
                container = self.query_one("#preview", ScrollableContainer)
                container.remove_children()

                richlog = RichLog(
                    id="preview-content",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False
                )
                container.mount(richlog)
                self.selection_mode = False

                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)

            except Exception as recovery_error:
                self.cancel_refresh_timer()
                status.update(f"Failed to recover preview: {recovery_error}")

    def _restore_preview_content(self):
        """Restore preview content after switching back from selection mode."""
        try:
            if self.mode == "LOG_BROWSER":
                # Restore log content
                if hasattr(self, 'current_execution_index') and self.executions:
                    self.load_execution_log(self.current_execution_index)
            elif self.current_doc_id:
                # Update the preview with current document
                self.update_preview(self.current_doc_id)

            # Return focus to table
            table = self.query_one("#doc-table", DataTable)
            table.focus()
        except Exception:
            import traceback

            traceback.print_exc()

    def action_toggle_edit_mode(self):
        """Toggle between view and edit modes for current document."""
        logger.info(f"action_toggle_edit_mode called, current_doc_id={self.current_doc_id}, edit_mode={self.edit_mode}")
        if not self.current_doc_id:
            status = self.query_one("#status", Label)
            self.cancel_refresh_timer()
            status.update("Select a document first")
            return
        
        if self.edit_mode:
            # Currently editing - save and exit
            self.action_save_and_exit_edit()
        else:
            # Enter edit mode
            self.action_enter_edit_mode()

    def action_enter_edit_mode(self):
        """Enter edit mode for current document."""
        try:
            logger.info(f"action_enter_edit_mode called, current_doc_id={self.current_doc_id}")
            if not self.current_doc_id:
                return
            
            # Exit selection mode if active
            if self.selection_mode:
                self.action_toggle_selection_mode()
            
            # Get document content
            doc = get_document(str(self.current_doc_id))
            if not doc:
                return
            
            # Get container and status
            container = self.query_one("#preview", ScrollableContainer)
            status = self.query_one("#status", Label)
            
            # Remove all widgets from container (same as selection mode fix)
            container.remove_children()
            
            # Create a wrapper container to enforce width constraints
            from textual.containers import Container
            edit_wrapper = Container(id="edit-wrapper")
            
            # Create title input
            title_input = TitleInput(
                self,
                value=doc["title"],
                placeholder="Enter title...",
                id="title-input"
            )
            title_input.add_class("edit-title-input")
            # Ensure cursor is visible and solid in title input
            title_input.show_cursor = True
            title_input.cursor_blink = False
            
            # Create VimEditTextArea with constraints BEFORE mounting
            edit_area = VimEditTextArea(self, text=doc["content"], id="preview-content")
            self.edit_textarea = edit_area  # Store reference for vim status updates
            self.edit_title_input = title_input  # Store reference for title input
            
            # Make it editable (not read-only like selection mode)
            edit_area.read_only = False
            edit_area.disabled = False
            edit_area.can_focus = True
            
            # Apply the constrained-textarea CSS class
            edit_area.add_class("constrained-textarea")
            
            # CRITICAL: Set word wrap BEFORE any other properties
            edit_area.word_wrap = True
            edit_area.show_line_numbers = False  # Disable line numbers to save space
            
            # Try setting max line length if available
            if hasattr(edit_area, 'max_line_length'):
                edit_area.max_line_length = 80  # Enforce maximum line length
            
            # Mount wrapper in preview container
            container.mount(edit_wrapper)
            
            # Mount title and content in wrapper
            edit_wrapper.mount(title_input)
            edit_wrapper.mount(edit_area)
            
            # Reset container scroll and refresh layout (same as selection mode)
            container.scroll_to(0, 0, animate=False)
            container.refresh(layout=True)
            edit_wrapper.refresh(layout=True)
            
            # Focus the content editor first instead of title input 
            edit_area.focus()
            
            # Debug logging to understand width issues
            logger.info(f"EditTextArea mounted - container width: {container.size.width}")
            logger.info(f"EditTextArea classes: {edit_area.classes}")
            
            # Store current cursor position before entering edit mode
            table = self.query_one("#doc-table", DataTable)
            self.edit_mode_cursor_position = table.cursor_coordinate
            
            # Update state
            self.edit_mode = True
            self.editing_doc_id = self.current_doc_id
            
            # Update status with vim mode and tab hint
            self.cancel_refresh_timer()
            self._update_vim_status()
            
        except Exception as e:
            logger.error(f"Error entering edit mode: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Edit mode failed: {str(e)}")

    def action_save_and_exit_edit(self):
        """Save changes and exit edit mode."""
        try:
            if not self.edit_mode or not self.editing_doc_id:
                return
            
            # Get the container and edit area
            container = self.query_one("#preview", ScrollableContainer)
            status = self.query_one("#status", Label)
            
            # Find the edit area and title input within the wrapper
            try:
                from textual.containers import Container
                edit_wrapper = self.query_one("#edit-wrapper", Container)
                edit_area = edit_wrapper.query_one("#preview-content", EditTextArea)
                title_input = edit_wrapper.query_one("#title-input", TitleInput)
            except:
                # Fallback if wrapper doesn't exist
                edit_area = self.query_one("#preview-content", EditTextArea)
                title_input = None
            
            # Get the edited content and title
            new_content = edit_area.text
            new_title = title_input.value if title_input else None
            
            # Get current document for comparison
            doc = get_document(str(self.editing_doc_id))
            if not doc:
                return
                
            # Check if content or title changed
            content_changed = new_content != edit_area.original_content
            title_changed = new_title and new_title != doc["title"]
            
            if content_changed or title_changed:
                # Update document in database
                from emdx.models.documents import update_document
                
                # Use new title if provided, otherwise keep existing
                final_title = new_title if new_title else doc["title"]
                success = update_document(self.editing_doc_id, final_title, new_content)
                
                if success:
                    self.cancel_refresh_timer()
                    status.update(f"✅ Saved changes to #{self.editing_doc_id}")
                    
                    # Refresh the document list to show updated timestamp
                    self.load_documents()
                    self.filter_documents(self.search_query)
                else:
                    self.cancel_refresh_timer()
                    status.update(f"❌ Failed to save changes to #{self.editing_doc_id}")
            else:
                self.cancel_refresh_timer()
                status.update("No changes made")
            
            # Exit edit mode
            self.edit_mode = False
            self.editing_doc_id = None
            
            # Hide vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.remove_class("visible")
            vim_indicator.update("")
            
            # Remove edit area and restore preview
            container.remove_children()
            
            # Create new RichLog for preview
            richlog = RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False
            )
            container.mount(richlog)
            
            # Reset container scroll and refresh layout (SAME AS SELECTION MODE)
            container.scroll_to(0, 0, animate=False)
            container.refresh(layout=True)
            
            # Use deferred content restoration (SAME AS SELECTION MODE)
            self.call_after_refresh(self._restore_preview_content)
            
            # Restore cursor position to where it was before edit mode
            if hasattr(self, 'edit_mode_cursor_position'):
                table = self.query_one("#doc-table", DataTable)
                try:
                    table.cursor_coordinate = self.edit_mode_cursor_position
                except:
                    pass  # Position might be invalid after refresh
                delattr(self, 'edit_mode_cursor_position')
            
        except Exception as e:
            logger.error(f"Error saving and exiting edit mode: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Save failed: {str(e)}")
            
            # Try to recover
            try:
                self.edit_mode = False
                self.editing_doc_id = None
                container = self.query_one("#preview", ScrollableContainer)
                container.remove_children()
                
                richlog = RichLog(
                    id="preview-content",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False
                )
                container.mount(richlog)
                
                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)
                    
                # Try to restore cursor position even in error recovery
                if hasattr(self, 'edit_mode_cursor_position'):
                    table = self.query_one("#doc-table", DataTable)
                    try:
                        table.cursor_coordinate = self.edit_mode_cursor_position
                    except:
                        pass
                    delattr(self, 'edit_mode_cursor_position')
            except Exception:
                pass  # Give up on recovery

    def action_save_preview(self):
        """Save is now handled by edit mode - show message."""
        self.cancel_refresh_timer()
        status = self.query_one("#status", Label)
        status.update("Use 'e' to edit document in place")
    
    def action_save_document(self):
        """Save the current document without exiting edit mode."""
        try:
            if not self.edit_mode or not self.editing_doc_id:
                return
            
            # Get the edit area and title input
            try:
                from textual.containers import Container
                edit_wrapper = self.query_one("#edit-wrapper", Container)
                edit_area = edit_wrapper.query_one("#preview-content", EditTextArea)
                title_input = edit_wrapper.query_one("#title-input", TitleInput)
            except:
                edit_area = self.query_one("#preview-content", EditTextArea)
                title_input = None
            
            # Get the edited content and title
            new_content = edit_area.text
            new_title = title_input.value if title_input else None
            
            # Update document in database
            from emdx.models.documents import update_document
            
            # Get current document for comparison
            doc = get_document(str(self.editing_doc_id))
            if doc:
                # Use new title if provided, otherwise keep existing
                final_title = new_title if new_title else doc["title"]
                success = update_document(self.editing_doc_id, final_title, new_content)
                
                if success:
                    # Update original content to mark as saved
                    edit_area.original_content = new_content
                    self._update_vim_status("Document saved")
                    
                    # Refresh the document list to show updated timestamp
                    self.load_documents()
                    self.filter_documents(self.search_query)
                else:
                    self._update_vim_status("Failed to save document")
        except Exception as e:
            logger.error(f"Error saving document: {e}", exc_info=True)
            self._update_vim_status(f"Save failed: {str(e)[:30]}...")
    
    def action_cancel_edit(self):
        """Cancel edit mode without saving changes."""
        try:
            if not self.edit_mode:
                return
            
            # Exit edit mode
            self.edit_mode = False
            self.editing_doc_id = None
            
            # Hide vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.remove_class("visible")
            vim_indicator.update("")
            
            # Get container
            container = self.query_one("#preview", ScrollableContainer)
            
            # Remove edit area and restore preview
            container.remove_children()
            
            # Create new RichLog for preview
            richlog = RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False
            )
            container.mount(richlog)
            
            # Reset container scroll and refresh layout
            container.scroll_to(0, 0, animate=False)
            container.refresh(layout=True)
            
            # Use deferred content restoration
            self.call_after_refresh(self._restore_preview_content)
            
            # Update status
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Edit cancelled - changes discarded")
            
        except Exception as e:
            logger.error(f"Error cancelling edit: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Cancel failed: {str(e)}")
            
            # Try to recover
            try:
                self.edit_mode = False
                self.editing_doc_id = None
                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)
            except Exception:
                pass


    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess

        success = False

        # Try pbcopy on macOS first
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            success = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"], input=text, text=True, check=True
                )
                success = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(
                        ["xsel", "--clipboard", "--input"], input=text, text=True, check=True
                    )
                    success = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        status = self.query_one("#status", Label)
        if success:
            self.cancel_refresh_timer()
            status.update("Content copied to clipboard!")
        else:
            self.cancel_refresh_timer()
            status.update("Clipboard not available - manual selection required")

    def restore_normal_status(self):
        """Restore the normal status display after temporary messages."""
        self.update_status()
        self.refresh_timer = None

    def cancel_refresh_timer(self):
        """Cancel the refresh timer if it's active."""
        if self.refresh_timer:
            self.refresh_timer.stop()
            self.refresh_timer = None

    def action_tmux_split_horizontal(self):
        """Spawn a new tmux pane (horizontal split) with the current document."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for tmux split")
            return
            
        if not os.environ.get('TMUX'):
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Not running in tmux session")
            return
            
        self._spawn_tmux_pane(horizontal=True)
        
    def action_tmux_split_vertical(self):
        """Spawn a new tmux pane (vertical split) with the current document."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for tmux split")
            return
            
        if not os.environ.get('TMUX'):
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Not running in tmux session")
            return
            
        self._spawn_tmux_pane(horizontal=False)
        
    def _spawn_tmux_pane(self, horizontal: bool = True):
        """Internal method to spawn tmux pane with current document."""
        try:
            from emdx.models.documents import get_document
            
            # Get the current document
            doc = get_document(str(self.current_doc_id))
            if not doc:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Document not found")
                return
                
            # Create a temporary file with the document content
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(f"# {doc['title']}\n\n")
                f.write(doc['content'])
                temp_path = f.name
            
            # Determine split direction
            split_flag = '-h' if horizontal else '-v'
            
            # For now, just spawn a shell that shows the document
            # You can replace this with your Claude command later
            tmux_command = f"cat {temp_path} && echo '\n\n--- Document loaded ---' && bash"
            
            # Spawn the tmux pane
            result = subprocess.run([
                'tmux', 'split-window', split_flag, tmux_command
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                direction = "right" if horizontal else "below"
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Spawned tmux pane {direction} with: {doc['title']}")
            else:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Failed to spawn tmux pane: {result.stderr}")
                
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error spawning tmux pane: {e}")
    
    def action_claude_execute(self):
        """Execute the current document with claude-auto in a tmux pane."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for execution")
            return
            
        if not os.environ.get('TMUX'):
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Not running in tmux session - Claude execution requires tmux")
            return
            
        try:
            from emdx.models.documents import get_document
            
            # Get the current document
            doc = get_document(str(self.current_doc_id))
            if not doc:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Document not found")
                return
            
            # Create execution ID
            exec_id = f"claude-{self.current_doc_id}-{int(time.time())}"
            
            # Create temp file with document content
            temp_path = f"/tmp/emdx-claude-{self.current_doc_id}.md"
            with open(temp_path, 'w') as f:
                f.write(f"# {doc['title']}\n\n{doc['content']}")
            
            # Create logs directory
            log_dir = Path.home() / ".config/emdx/logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{exec_id}.log"
            
            # Create execution record
            from datetime import datetime
            execution = Execution(
                id=exec_id,
                doc_id=self.current_doc_id,
                doc_title=doc['title'],
                status='running',
                started_at=datetime.now(),
                log_file=str(log_path)
            )
            save_execution(execution)
            
            # Build claude-auto command with proper logging
            fish_source = "source ~/.config/fish/.clauding-backup-20250706_014139/claude-auto.fish; source ~/.config/fish/.clauding-backup-20250706_014139/claude-pretty-parser.fish"
            
            # Create log file with header
            with open(log_path, 'w') as f:
                f.write(f"=== EMDX Claude Execution ===\n")
                f.write(f"ID: {exec_id}\n")
                f.write(f"Document: {doc['title']}\n")
                f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
            
            # Redirect all output to log file
            claude_cmd = f"claude-auto 'Execute this plan: @{temp_path}'"
            background_cmd = f"fish -c '{fish_source}; {claude_cmd}' >> {log_path} 2>&1"
            
            # Start background process
            process = subprocess.Popen(
                background_cmd,
                shell=True,
                start_new_session=True
            )
            
            # Always show success since Popen doesn't wait
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"🚀 Claude executing in background: {doc['title'][:30]}... → {exec_id[:8]} (Press 'l' for logs)")
                
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error starting Claude execution: {e}")
    
    def action_log_browser(self):
        """Switch to log browser mode to view and switch between execution logs."""
        self.mode = "LOG_BROWSER"
        self.setup_log_browser()
    
    def setup_log_browser(self):
        """Set up the log browser interface with execution list and log viewer."""
        try:
            # Load recent executions from database
            self.executions = get_recent_executions(limit=20)
            
            if not self.executions:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("No executions found - Press 'q' to return")
                return
            
            # Start with the most recent execution
            self.current_execution_index = 0
            
            # Replace the documents table with executions table
            table = self.query_one("#doc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("#", "Status", "Document", "Started", "Duration")
            
            # Populate executions table
            for i, execution in enumerate(self.executions):
                status_icon = {
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌'
                }.get(execution.status, '❓')
                
                duration = ""
                if execution.duration:
                    if execution.duration < 60:
                        duration = f"{int(execution.duration)}s"
                    else:
                        mins = int(execution.duration // 60)
                        secs = int(execution.duration % 60)
                        duration = f"{mins}m{secs}s"
                elif execution.status == 'running':
                    duration = "running..."
                
                table.add_row(
                    str(i + 1),  # Number for keyboard selection
                    f"{status_icon} {execution.status}",
                    execution.doc_title[:30],
                    execution.started_at.strftime('%H:%M:%S'),
                    duration
                )
            
            # Select first row and load its log
            table.move_cursor(row=0)
            self.load_execution_log(0)
            
            # Update status with instructions
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"📋 LOG BROWSER: {len(self.executions)} executions (j/k to navigate, 'q' to exit, auto-refresh every 2s)")
            
            # Start monitoring for log updates
            self.start_log_monitoring()
                
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error setting up log browser: {e}")
    
    def _extract_log_content(self) -> str:
        """Extract plain text content from the current log for selection mode."""
        try:
            if self.mode == "LOG_BROWSER" and hasattr(self, 'current_log_file') and self.current_log_file:
                # Get execution info for header
                execution = self.executions[self.current_execution_index] if self.executions else None
                
                # Build header
                lines = []
                if execution:
                    lines.append(f"=== Execution {execution.id} ===")
                    lines.append(f"Document: {execution.doc_title}")
                    lines.append(f"Status: {execution.status}")
                    lines.append(f"Started: {execution.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    if execution.completed_at:
                        lines.append(f"Completed: {execution.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    if execution.duration:
                        lines.append(f"Duration: {execution.duration:.1f}s")
                    lines.append("=== Log Output ===")
                    lines.append("")
                
                # Read actual log file content
                if self.current_log_file.exists():
                    with open(self.current_log_file, 'r') as f:
                        log_content = f.read()
                        if log_content:
                            lines.append(log_content)
                        else:
                            lines.append("(No log content yet)")
                else:
                    lines.append("Log file not found")
                
                return "\n".join(lines)
            else:
                return "No log content available"
        except Exception as e:
            return f"Error extracting log content: {e}"
    
    def start_log_monitoring(self):
        """Start monitoring the log file for changes."""
        if hasattr(self, 'log_monitor_timer'):
            self.log_monitor_timer.stop()
        
        # Monitor every 2 seconds in log browser mode
        self.log_monitor_timer = self.set_interval(2.0, self.update_log_content)
        self.last_log_size = 0
    
    def update_log_content(self):
        """Update log content if file has changed."""
        if not hasattr(self, 'current_log_file') or self.mode != "LOG_BROWSER":
            return
            
        try:
            if not self.current_log_file or not self.current_log_file.exists():
                return
                
            # Check if file has grown
            current_size = self.current_log_file.stat().st_size
            if current_size > self.last_log_size:
                # Read new content
                with open(self.current_log_file, 'r') as f:
                    f.seek(self.last_log_size)
                    new_content = f.read()
                    
                if new_content:
                    try:
                        preview = self.query_one("#preview-content", RichLog)
                        preview.write(new_content)
                        # Auto-scroll to bottom
                        preview.scroll_end(animate=False)
                    except Exception:
                        # Widget doesn't exist (different screen) - skip update
                        pass
                    
                self.last_log_size = current_size
                
        except Exception as e:
            # Silently handle file reading errors
            pass
    
    def load_execution_log(self, index: int):
        """Load the log file for the execution at the given index."""
        if index < 0 or index >= len(self.executions):
            return
            
        try:
            execution = self.executions[index]
            self.current_execution_index = index
            self.current_log_file = Path(execution.log_file)
            
            # Clear preview and load log content
            try:
                preview = self.query_one("#preview-content", RichLog)
            except Exception:
                # Widget doesn't exist (different screen) - cannot load log
                return
            
            preview.clear()
            
            # Show execution header
            preview.write(f"[bold cyan]=== Execution {execution.id} ===[/bold cyan]")
            preview.write(f"[yellow]Document:[/yellow] {execution.doc_title}")
            preview.write(f"[yellow]Status:[/yellow] {execution.status}")
            preview.write(f"[yellow]Started:[/yellow] {execution.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if execution.completed_at:
                preview.write(f"[yellow]Completed:[/yellow] {execution.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if execution.duration:
                preview.write(f"[yellow]Duration:[/yellow] {execution.duration:.1f}s")
            preview.write("[bold cyan]=== Log Output ===[/bold cyan]")
            preview.write("")
            
            # Load log file content
            if self.current_log_file.exists():
                with open(self.current_log_file, 'r') as f:
                    content = f.read()
                    if content:
                        preview.write(content)
                    else:
                        preview.write("[dim](No log content yet)[/dim]")
                
                # Reset size tracking for live updates
                self.last_log_size = self.current_log_file.stat().st_size
            else:
                preview.write("[red]Log file not found[/red]")
                self.last_log_size = 0
            
            # Auto-scroll to bottom
            preview.scroll_end(animate=False)
            
            # Highlight current row in table
            try:
                table = self.query_one("#doc-table", DataTable)
                table.move_cursor(row=index)
            except Exception:
                # Table doesn't exist (different screen) - skip highlighting
                pass
            
        except Exception as e:
            self.cancel_refresh_timer()
            try:
                status = self.query_one("#status", Label)
                status.update(f"Error loading execution log: {e}")
            except Exception:
                # Status widget doesn't exist (different screen) - ignore error
                pass
    
    def action_next_log(self):
        """Switch to next execution log (j in LOG_BROWSER mode)."""
        if self.mode != "LOG_BROWSER":
            return
            
        if hasattr(self, 'current_execution_index') and hasattr(self, 'executions') and self.executions:
            self.current_execution_index = (self.current_execution_index + 1) % len(self.executions)
            self.load_execution_log(self.current_execution_index)
            self.update_status(f"Viewing log {self.current_execution_index + 1}/{len(self.executions)}")
    
    def action_prev_log(self):
        """Switch to previous execution log (k in LOG_BROWSER mode)."""
        if self.mode != "LOG_BROWSER":
            return
            
        if hasattr(self, 'current_execution_index') and hasattr(self, 'executions') and self.executions:
            self.current_execution_index = (self.current_execution_index - 1) % len(self.executions)
            self.load_execution_log(self.current_execution_index)
            self.update_status(f"Viewing log {self.current_execution_index + 1}/{len(self.executions)}")
    
    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially j/k for log switching in LOG_BROWSER mode."""
        try:
            key_logger.info(f"MinimalBrowser.on_key: key={event.key}")
            
            # Handle j/k keys for log switching in log browser mode only
            if hasattr(self, 'mode') and self.mode == "LOG_BROWSER" and hasattr(self, 'executions'):
                if hasattr(event, 'key') and event.key:
                    if event.key == "j":
                        self.action_next_log()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "k":
                        self.action_prev_log()
                        event.stop()
                        event.prevent_default()
                        return
            
            # Note: App class doesn't have on_key method, so we don't call super()
            pass
        except Exception as e:
            # Log error but don't crash
            key_logger.error(f"Error in on_key: {e}")
            # Don't try to call super().on_key() as App doesn't have this method
    
    
    async def on_event(self, event) -> None:
        """Handle all events safely."""
        try:
            await super().on_event(event)
        except Exception as e:
            logger.error(f"Error handling event {type(event).__name__}: {e}")
            # Don't re-raise, just log and continue
    
    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        """Handle row selection in both document and execution modes."""
        try:
            if hasattr(self, 'mode') and self.mode == "LOG_BROWSER":
                # In log browser mode, load the selected execution's log
                if hasattr(self, 'executions') and message.cursor_row < len(self.executions):
                    self.load_execution_log(message.cursor_row)
            else:
                # Original document preview logic
                if hasattr(self, 'filtered_docs') and message.cursor_row < len(self.filtered_docs):
                    doc = self.filtered_docs[message.cursor_row]
                    self.current_doc_id = doc["id"]

                    # Exit selection mode when switching documents
                    if hasattr(self, 'selection_mode') and self.selection_mode:
                        self.action_toggle_selection_mode()

                    self.update_preview(doc["id"])
        except Exception as e:
            logger.error(f"Error in on_data_table_row_highlighted: {e}")
            # Don't crash, just log the error

    def action_quit(self):
        try:
            if hasattr(self, 'mode') and self.mode == "LOG_BROWSER":
                # Exit log browser mode and return to document mode
                self.mode = "NORMAL"
                self.stop_log_monitoring()
                self.reload_documents()
            else:
                self.exit()
        except Exception as e:
            logger.error(f"Error in action_quit: {e}")
            # Fallback to exit
            self.exit()
    
    def stop_log_monitoring(self):
        """Stop the log monitoring timer."""
        if hasattr(self, 'log_monitor_timer'):
            self.log_monitor_timer.stop()
            delattr(self, 'log_monitor_timer')
    
    def reload_documents(self):
        """Reload the document view after exiting log browser."""
        try:
            # Clear and recreate the table with documents
            table = self.query_one("#doc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Title", "Tags")
            
            # Reload documents
            self.load_documents()
            
            # Repopulate the table
            for doc in self.filtered_docs:
                # Format timestamp as MM-DD HH:MM (11 chars)
                timestamp = doc["created_at"].strftime("%m-%d %H:%M")

                # Calculate available space for title (50 total - 11 for timestamp)
                title_space = 50 - 11
                title = doc["title"][:title_space]
                if len(doc["title"]) >= title_space:
                    title = title[:title_space-3] + "..."

                # Right-justify timestamp by padding title to full width
                formatted_title = f"{title:<{title_space}}{timestamp}"

                # Expanded tag display - limit to 30 chars with emoji-safe truncation
                formatted_tags = format_tags(doc.get("tags", []))
                tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
                if was_truncated:
                    tags_str += "..."

                table.add_row(
                    str(doc["id"]),
                    formatted_title,
                    tags_str or "-",
                )
            
            # Focus the table and update preview
            table.focus()
            if self.filtered_docs:
                table.move_cursor(row=0)
                self.current_doc_id = self.filtered_docs[0]["id"]
                self.update_preview(self.current_doc_id)
            
            # Update status
            self.update_status()
            
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error reloading documents: {e}")


def run_minimal():
    """Run the minimal browser and return exit code."""
    try:
        # Check if documents exist
        db.ensure_schema()
        docs = db.list_documents(limit=1)
        if not docs:
            print("No documents found in knowledge base.")
            print("\nGet started with:")
            print("  emdx save <file>         - Save a markdown file")
            print("  emdx direct <title>      - Create a document directly")
            print("  emdx note 'quick note'   - Save a quick note")
            return 0

        # Run the browser
        app = MinimalDocumentBrowser()
        app.run()

        # Check if edit signal exists to determine return code
        edit_signal = f"/tmp/emdx_edit_signal_{os.getpid()}"
        if os.path.exists(edit_signal):
            return 42  # Edit requested
        else:
            return 0  # Normal exit

    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_minimal())
