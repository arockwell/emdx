#!/usr/bin/env python3
"""
Unified vim editor component for EMDX TUI.
Provides consistent vim editing experience across main browser and file browser.
"""

import logging
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from .text_areas import VimEditTextArea

logger = logging.getLogger(__name__)


# Import the exact same line numbers implementation from main browser
from .main_browser import SimpleVimLineNumbers


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
        
        # Create the vim text area
        self.text_area = VimEditTextArea(
            app_instance,
            text=content,
            read_only=False,
            id="vim-text-area"
        )
        
        # Apply styling
        self.text_area.add_class("constrained-textarea")
        self.text_area.word_wrap = True
        self.text_area.show_line_numbers = False  # Using custom vim relative numbers
        
        # Try setting max line length if available
        if hasattr(self.text_area, 'max_line_length'):
            self.text_area.max_line_length = 80
        
        # Create line numbers widget
        self.line_numbers = SimpleVimLineNumbers(id="vim-line-numbers")
        self.text_area.line_numbers_widget = self.line_numbers
        
        # Create horizontal container for line numbers and text area
        self.edit_container = Horizontal(id="vim-edit-container")
    
    def compose(self):
        """Compose the vim editor layout."""
        yield self.edit_container
    
    def on_mount(self):
        """Set up the vim editor after mounting."""
        # Mount line numbers and text area in horizontal layout
        self.edit_container.mount(self.line_numbers)
        self.edit_container.mount(self.text_area)
        
        # Focus the text area and initialize line numbers
        self.text_area.can_focus = True
        self.call_after_refresh(lambda: self._initialize_editor())
    
    def get_text(self):
        """Get the current text content."""
        return self.text_area.text
    
    def set_text(self, content):
        """Set the text content."""
        self.text_area.text = content
    
    def focus_editor(self):
        """Focus the text editor."""
        self.text_area.focus()
    
    def _initialize_editor(self):
        """Initialize editor after mounting - focus and set up line numbers."""
        try:
            # Focus the text area first
            self.text_area.focus()
            
            # Force cursor to start at beginning (files should start at top)
            self.text_area.cursor_location = (0, 0)
            
            # Use the same cursor detection logic as VimEditTextArea._update_line_numbers
            if hasattr(self.text_area, 'selection') and self.text_area.selection:
                current_line = self.text_area.selection.end[0]
                logger.debug(f"🔢   Using selection.end[0]: {current_line}")
            elif hasattr(self.text_area, 'cursor_location'):
                current_line = self.text_area.cursor_location[0]
                logger.debug(f"🔢   Using cursor_location[0]: {current_line}")
            else:
                current_line = 0
                logger.debug(f"🔢   Fallback to 0")
            
            # Get actual cursor position for logging
            actual_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            actual_selection = getattr(self.text_area, 'selection', None)
            total_lines = len(self.text_area.text.split('\n'))
            
            logger.debug(f"🔢 VimEditor INITIAL SETUP:")
            logger.debug(f"🔢   Set cursor to: (0, 0)")
            logger.debug(f"🔢   Actual cursor: {actual_cursor}")
            logger.debug(f"🔢   Actual selection: {actual_selection}")
            logger.debug(f"🔢   current_line={current_line}, total_lines={total_lines}")
            
            # Set initial line numbers
            self.line_numbers.set_line_numbers(current_line, total_lines, self.text_area)
            
            # Double-check by calling text area's update method if it exists
            if hasattr(self.text_area, '_update_line_numbers'):
                logger.debug(f"🔢 Calling text area's _update_line_numbers()")
                self.text_area._update_line_numbers()
            
        except Exception as e:
            logger.error(f"Error initializing vim editor: {e}")
    
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