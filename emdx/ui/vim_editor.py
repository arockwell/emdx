#!/usr/bin/env python3
"""
Unified vim editor component for EMDX TUI.
Provides consistent vim editing experience across main browser and file browser.
"""

import logging
import os

from textual.containers import Horizontal, Vertical

from .text_areas import VimEditTextArea

logger = logging.getLogger(__name__)

# Only enable debug logging if explicitly requested
debug_enabled = os.environ.get("EMDX_DEBUG", "").lower() in ("1", "true", "yes")


def debug_log(message):
    """Log debug message only if debug mode is enabled."""
    if debug_enabled:
        logger.debug(message)


# Import line numbers implementation
from .vim_line_numbers import SimpleVimLineNumbers


class VimEditor(Vertical):
    """Unified vim editor with line numbers and proper layout."""
    
    def __init__(self, app_instance, content="", **kwargs):
        """Initialize vim editor.
        
        Args:
            app_instance: The application instance for vim callbacks
            content: Initial text content
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        
        # Ensure VimEditor takes full available space
        self.styles.width = "100%"
        self.styles.height = "100%"
        
        # Create the vim text area
        debug_log(f"🔍 VimEditor.__init__: Creating VimEditTextArea with content length: {len(content)}")
        debug_log(f"🔍 VimEditor.__init__: First 100 chars: {repr(content[:100])}")
        # Pass content as first positional argument (required by VimEditTextArea)
        self.text_area = VimEditTextArea(
            app_instance,
            content,  # First positional arg after app_instance
            read_only=False,
            id="vim-text-area"
        )
        debug_log(f"🔍 VimEditor.__init__: VimEditTextArea created")
        
        # Apply styling
        self.text_area.show_line_numbers = False  # Using custom vim relative numbers
        self.text_area.word_wrap = False  # Disable to maintain line alignment
        
        # Create line numbers widget
        self.line_numbers = SimpleVimLineNumbers(id="vim-line-numbers")
        self.text_area.line_numbers_widget = self.line_numbers
        
        # Create horizontal container for line numbers and text area
        self.edit_container = Horizontal(id="vim-edit-container")
        self.edit_container.styles.width = "100%"
        self.edit_container.styles.height = "100%"
    
    def compose(self):
        """Compose the vim editor layout."""
        yield self.edit_container
    
    def on_mount(self):
        """Set up the vim editor after mounting."""
        # Configure text area to take full space
        self.text_area.styles.width = "100%"
        self.text_area.styles.padding = (0, 1)  # Add horizontal padding
        
        # Mount only text area (no line numbers for now)
        self.edit_container.mount(self.text_area)
        
        debug_log(f"🔍 VimEditor.on_mount: Components mounted")
        debug_log(f"🔍 VimEditor.on_mount: TextArea text length: {len(self.text_area.text)}")
        debug_log(f"🔍 VimEditor.on_mount: First 50 chars of text: {repr(self.text_area.text[:50])}")
        
        # Note: Container scroll_to() disabled due to first line visibility issues
        
        # Focus the text area and initialize line numbers
        self.text_area.can_focus = True
        self.call_after_refresh(lambda: self._initialize_editor())
        
        # WORKAROUND: Schedule a second positioning attempt slightly later
        # This handles cases where TextArea's internal logic overrides our initial positioning
        self.set_timer(0.1, lambda: self._delayed_positioning_check())
    
    def get_text(self):
        """Get the current text content."""
        return self.text_area.text
    
    def set_text(self, content):
        """Set the text content."""
        self.text_area.text = content
    
    def focus_editor(self):
        """Focus the text editor."""
        self.text_area.focus()
    
    def _calculate_line_number_width(self, total_lines):
        """Calculate required width for line numbers based on total lines."""
        # Account for the largest line number + 1 space padding
        max_digits = len(str(total_lines))
        # Minimum 3 chars (like vim), add 1 for padding
        width = max(3, max_digits) + 1
        debug_log(f"🔢 Line number width calculation: total_lines={total_lines}, max_digits={max_digits}, width={width}")
        return width
    
    def _update_line_number_width(self):
        """Update line number widget width based on current content."""
        total_lines = len(self.text_area.text.split('\n'))
        line_number_width = self._calculate_line_number_width(total_lines)
        
        # Update width if it changed
        if self.line_numbers.styles.width != line_number_width:
            self.line_numbers.styles.width = line_number_width
            self.line_numbers.styles.min_width = line_number_width
            self.line_numbers.styles.max_width = line_number_width
    
    def _initialize_editor(self):
        """Initialize editor after mounting - focus and set up line numbers."""
        try:
            debug_log(f"🔢 VimEditor _initialize_editor starting")
            
            # DEBUG: Check TextArea state
            debug_log(f"🔍 DEBUG TextArea state:")
            debug_log(f"🔍   - text length: {len(self.text_area.text)}")
            debug_log(f"🔍   - text first 50: {repr(self.text_area.text[:50])}")
            debug_log(f"🔍   - has_focus: {self.text_area.has_focus}")
            debug_log(f"🔍   - display: {self.text_area.display}")
            debug_log(f"🔍   - visible: {self.text_area.visible}")
            if hasattr(self.text_area, 'size'):
                debug_log(f"🔍   - size: {self.text_area.size}")
            if hasattr(self.text_area, 'region'):
                debug_log(f"🔍   - region: {self.text_area.region}")
            
            # AGGRESSIVE positioning: Force cursor to top MULTIPLE times with different approaches
            
            # Method 1: Force cursor to start at beginning
            self.text_area.cursor_location = (0, 0)
            debug_log(f"🔢   Set cursor_location to (0, 0)")
            
            # Method 2: Clear any existing selection that might affect positioning
            if hasattr(self.text_area, 'selection'):
                try:
                    self.text_area.selection = None
                    debug_log(f"🔢   Cleared selection")
                except:
                    pass
                    
            # Method 3: Force scroll to top using multiple methods
            # Method 4: Try to access internal scroll attributes if they exist
            # Method 5: For markdown files, be extra aggressive
            is_markdown = False
            if hasattr(self.text_area, 'file_path') and self.text_area.file_path:
                file_path_str = str(self.text_area.file_path).lower()
                is_markdown = file_path_str.endswith(('.md', '.markdown'))
                if is_markdown:
                    debug_log(f"🔢   MARKDOWN FILE detected: {self.text_area.file_path}")
                    # Triple-force for markdown files
                    self.text_area.cursor_location = (0, 0)
            # Method 6: Force cursor position using TextArea internal methods if available
            if hasattr(self.text_area, 'move_cursor'):
                try:
                    self.text_area.move_cursor((0, 0))
                    debug_log(f"🔢   Called move_cursor((0, 0))")
                except:
                    pass
                    
            # Focus the text area AFTER positioning
            self.text_area.focus()
            debug_log(f"🔢   Focused text area")
            
            # VERIFICATION: Log what actually happened after all our positioning attempts
            final_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            final_selection = getattr(self.text_area, 'selection', None)
            total_lines = len(self.text_area.text.split('\n'))
            
            debug_log(f"🔢 FINAL VERIFICATION AFTER POSITIONING:")
            debug_log(f"🔢   Final cursor_location: {final_cursor}")
            debug_log(f"🔢   Final selection: {final_selection}")
            debug_log(f"🔢   Total lines in content: {total_lines}")
            debug_log(f"🔢   Is markdown file: {is_markdown}")
            
            # Try to get scroll position if available
            if hasattr(self.text_area, 'scroll_offset'):
                debug_log(f"🔢   Final scroll_offset: {getattr(self.text_area, 'scroll_offset', 'N/A')}")
            if hasattr(self.text_area, 'scroll_x'):
                debug_log(f"🔢   Final scroll_x/y: ({getattr(self.text_area, 'scroll_x', 'N/A')}, {getattr(self.text_area, 'scroll_y', 'N/A')})")
            
            # Use cursor position for line numbers
            if hasattr(self.text_area, 'selection') and self.text_area.selection:
                current_line = self.text_area.selection.end[0]
                debug_log(f"🔢   Using selection.end[0] for line numbers: {current_line}")
            elif hasattr(self.text_area, 'cursor_location'):
                current_line = self.text_area.cursor_location[0]
                debug_log(f"🔢   Using cursor_location[0] for line numbers: {current_line}")
            else:
                current_line = 0
                debug_log(f"🔢   Fallback to 0 for line numbers")
            
            debug_log(f"🔢 VimEditor _initialize_editor completed successfully")
            
        except Exception as e:
            logger.error(f"Error initializing vim editor: {e}")
    
    def _delayed_positioning_check(self):
        """Delayed check to ensure positioning worked correctly."""
        try:
            debug_log(f"🔢 DELAYED POSITIONING CHECK starting")
            
            # Check if we're still at the top
            current_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            current_selection = getattr(self.text_area, 'selection', None)
            
            debug_log(f"🔢   Current cursor after delay: {current_cursor}")
            debug_log(f"🔢   Current selection after delay: {current_selection}")
            
            # If we're not at the top, force it again
            cursor_row = current_cursor[0] if current_cursor else 0
            selection_row = current_selection.end[0] if current_selection else 0
            
            if cursor_row != 0 or selection_row != 0:
                debug_log(f"🔢   NOT AT TOP! cursor_row={cursor_row}, selection_row={selection_row}")
                debug_log(f"🔢   Forcing position to top again...")
                
                # Force positioning again
                self.text_area.cursor_location = (0, 0)
                if hasattr(self.text_area, 'selection'):
                    self.text_area.selection = None
                debug_log(f"🔢   Forced positioning completed")
            else:
                debug_log(f"🔢   Position is correct, no adjustment needed")
                
        except Exception as e:
            logger.error(f"Error in delayed positioning check: {e}")
    
    @property
    def vim_mode(self):
        """Get current vim mode."""
        return self.text_area.vim_mode
    
    @property 
    def text(self):
        """Get/set text content (property interface)."""
        return self.text_area.text
    
    @text.setter
    def text(self, value):
        """Set text content."""
        self.text_area.text = value
