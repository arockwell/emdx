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


# Import the line numbers from main browser to avoid duplication
try:
    from .main_browser import SimpleVimLineNumbers
except ImportError:
    # Fallback in case of circular imports
    class SimpleVimLineNumbers(Static):
        """Dead simple vim-style line numbers widget."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.add_class("vim-line-numbers")
            self.text_area = None  # Reference to associated text area

        def set_line_numbers(self, current_line, total_lines, text_area=None):
            """Set line numbers given current line (0-based) and total lines."""
            logger.debug(f"🔢 set_line_numbers called: current={current_line}, total={total_lines}")
            
            # Store text area reference if provided
            if text_area:
                self.text_area = text_area
            
            # Clamp values to safe ranges
            current_line = max(0, min(current_line, total_lines - 1)) if total_lines > 0 else 0
            total_lines = max(1, total_lines)
            
            logger.debug(f"🔢 After clamping: current={current_line}, total={total_lines}")
            
            # Generate relative line numbers
            lines = []
            for i in range(total_lines):
                if i == current_line:
                    # Current line shows absolute number
                    lines.append(f"{i + 1:>3}")
                else:
                    # Other lines show relative distance
                    relative = abs(i - current_line)
                    lines.append(f"{relative:>3}")
            
            # Update display with newlines
            self.update("\n".join(lines))
            logger.debug(f"🔢 Line numbers updated successfully")


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
        
        # Focus the text area
        self.text_area.can_focus = True
        self.call_after_refresh(lambda: self.text_area.focus())
    
    def get_text(self):
        """Get the current text content."""
        return self.text_area.text
    
    def set_text(self, content):
        """Set the text content."""
        self.text_area.text = content
    
    def focus_editor(self):
        """Focus the text editor."""
        self.text_area.focus()
    
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