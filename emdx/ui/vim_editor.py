#!/usr/bin/env python3
"""
Unified vim editor component for EMDX TUI.
Provides consistent vim editing experience across main browser and file browser.
"""

import logging

from textual.containers import Horizontal, Vertical

from .text_areas import VimEditTextArea

logger = logging.getLogger(__name__)


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
        # Pass content as first positional argument (required by VimEditTextArea)
        self.text_area = VimEditTextArea(
            app_instance,
            content,  # First positional arg after app_instance
            read_only=False,
            id="vim-text-area"
        )
        
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
        # TEMPORARILY DISABLED: Line numbers causing layout issues
        # Just mount the text area directly without line numbers
        
        # Configure text area to take full space
        self.text_area.styles.width = "100%"
        self.text_area.styles.padding = (0, 1)  # Add horizontal padding
        
        # Mount only text area (no line numbers for now)
        self.edit_container.mount(self.text_area)
        
        
        # Ensure the entire vim editor container starts at top
        # TEMPORARILY DISABLED: This might be causing first line visibility issues
        # self.scroll_to(0, 0, animate=False)
        
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
            
            # DEBUG: Check TextArea state
            if hasattr(self.text_area, 'size'):
            if hasattr(self.text_area, 'region'):
            
            # AGGRESSIVE positioning: Force cursor to top MULTIPLE times with different approaches
            
            # Method 1: Force cursor to start at beginning
            self.text_area.cursor_location = (0, 0)
            
            # Method 2: Clear any existing selection that might affect positioning
            if hasattr(self.text_area, 'selection'):
                try:
                    self.text_area.selection = None
                except:
                    pass
                    
            # Method 3: Force scroll to top using multiple methods
            # TEMPORARILY DISABLED: This might be hiding the first line
            # if hasattr(self.text_area, 'scroll_to'):
            #     self.text_area.scroll_to(0, 0, animate=False)
            #     logger.debug(f"🔢   Called scroll_to(0, 0)")
            
            # Method 4: Try to access internal scroll attributes if they exist
            # TEMPORARILY DISABLED: This might be hiding the first line
            # if hasattr(self.text_area, 'scroll_offset'):
            #     try:
            #         self.text_area.scroll_offset = (0, 0)
            #         logger.debug(f"🔢   Set scroll_offset to (0, 0)")
            #     except:
            #         pass
                    
            # TEMPORARILY DISABLED: This might be hiding the first line
            # if hasattr(self.text_area, 'scroll_x'):
            #     try:
            #         self.text_area.scroll_x = 0
            #         self.text_area.scroll_y = 0
            #         logger.debug(f"🔢   Set scroll_x/y to 0")
            #     except:
            #         pass
            
            # Method 5: For markdown files, be extra aggressive
            is_markdown = False
            if hasattr(self.text_area, 'file_path') and self.text_area.file_path:
                file_path_str = str(self.text_area.file_path).lower()
                is_markdown = file_path_str.endswith(('.md', '.markdown'))
                if is_markdown:
                    # Triple-force for markdown files
                    self.text_area.cursor_location = (0, 0)
                    # TEMPORARILY DISABLED: scroll_to might be hiding first line
                    # if hasattr(self.text_area, 'scroll_to'):
                    #     self.text_area.scroll_to(0, 0, animate=False)
            
            # Method 6: Force cursor position using TextArea internal methods if available
            if hasattr(self.text_area, 'move_cursor'):
                try:
                    self.text_area.move_cursor((0, 0))
                except:
                    pass
                    
            # Focus the text area AFTER positioning
            self.text_area.focus()
            
            # VERIFICATION: Log what actually happened after all our positioning attempts
            final_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            final_selection = getattr(self.text_area, 'selection', None)
            total_lines = len(self.text_area.text.split('\n'))
            
            
            # Try to get scroll position if available
            if hasattr(self.text_area, 'scroll_offset'):
            if hasattr(self.text_area, 'scroll_x'):
            
            # Use cursor position for line numbers
            if hasattr(self.text_area, 'selection') and self.text_area.selection:
                current_line = self.text_area.selection.end[0]
            elif hasattr(self.text_area, 'cursor_location'):
                current_line = self.text_area.cursor_location[0]
            else:
                current_line = 0
            
            # TEMPORARILY DISABLED: Line numbers
            # self.line_numbers.set_line_numbers(current_line, total_lines, self.text_area)
            # self._update_line_number_width()
            # if hasattr(self.text_area, '_update_line_numbers'):
            #     logger.debug(f"🔢 Calling text area's _update_line_numbers()")
            #     self.text_area._update_line_numbers()
                
            
        except Exception as e:
            logger.error(f"Error initializing vim editor: {e}")
    
    def _delayed_positioning_check(self):
        """Delayed check to ensure positioning worked correctly."""
        try:
            
            # Check if we're still at the top
            current_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            current_selection = getattr(self.text_area, 'selection', None)
            
            
            # If we're not at the top, force it again
            cursor_row = current_cursor[0] if current_cursor else 0
            selection_row = current_selection.end[0] if current_selection else 0
            
            if cursor_row != 0 or selection_row != 0:
                
                # Force positioning again
                self.text_area.cursor_location = (0, 0)
                if hasattr(self.text_area, 'selection'):
                    self.text_area.selection = None
                # TEMPORARILY DISABLED: scroll_to might be hiding first line
                # if hasattr(self.text_area, 'scroll_to'):
                #     self.text_area.scroll_to(0, 0, animate=False)
                    
                # TEMPORARILY DISABLED: Line numbers
                # total_lines = len(self.text_area.text.split('\n'))
                # self.line_numbers.set_line_numbers(0, total_lines, self.text_area)
                
            else:
                
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
