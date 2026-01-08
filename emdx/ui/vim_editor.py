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
        logger.debug(f"🔍 VimEditor.__init__: Creating VimEditTextArea with content length: {len(content)}")
        logger.debug(f"🔍 VimEditor.__init__: First 100 chars: {repr(content[:100])}")
        # Pass content as first positional argument (required by VimEditTextArea)
        self.text_area = VimEditTextArea(
            app_instance,
            content,  # First positional arg after app_instance
            read_only=False,
            id="vim-text-area"
        )
        logger.debug(f"🔍 VimEditor.__init__: VimEditTextArea created")
        
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
        # Note: Line numbers are disabled due to Textual TextArea layout conflicts
        # Just mount the text area directly
        
        # Configure text area to take full space
        self.text_area.styles.width = "100%"
        self.text_area.styles.padding = (0, 1)  # Add horizontal padding
        
        # Mount only text area (no line numbers for now)
        self.edit_container.mount(self.text_area)
        
        logger.debug(f"🔍 VimEditor.on_mount: Components mounted")
        logger.debug(f"🔍 VimEditor.on_mount: TextArea text length: {len(self.text_area.text)}")
        logger.debug(f"🔍 VimEditor.on_mount: First 50 chars of text: {repr(self.text_area.text[:50])}")
        
        # Note: Explicit scroll_to(0, 0) disabled - causes first line visibility issues
        
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
        logger.debug(f"🔢 Line number width calculation: total_lines={total_lines}, max_digits={max_digits}, width={width}")
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
            logger.debug(f"🔢 VimEditor _initialize_editor starting")
            
            # DEBUG: Check TextArea state
            logger.debug(f"🔍 DEBUG TextArea state:")
            logger.debug(f"🔍   - text length: {len(self.text_area.text)}")
            logger.debug(f"🔍   - text first 50: {repr(self.text_area.text[:50])}")
            logger.debug(f"🔍   - has_focus: {self.text_area.has_focus}")
            logger.debug(f"🔍   - display: {self.text_area.display}")
            logger.debug(f"🔍   - visible: {self.text_area.visible}")
            if hasattr(self.text_area, 'size'):
                logger.debug(f"🔍   - size: {self.text_area.size}")
            if hasattr(self.text_area, 'region'):
                logger.debug(f"🔍   - region: {self.text_area.region}")
            
            # AGGRESSIVE positioning: Force cursor to top MULTIPLE times with different approaches
            
            # Method 1: Force cursor to start at beginning
            self.text_area.cursor_location = (0, 0)
            logger.debug(f"🔢   Set cursor_location to (0, 0)")
            
            # Method 2: Clear any existing selection that might affect positioning
            if hasattr(self.text_area, 'selection'):
                try:
                    self.text_area.selection = None
                    logger.debug(f"🔢   Cleared selection")
                except Exception:
                    pass
                    
            # Note: scroll_to, scroll_offset, scroll_x/y methods disabled due to
            # first-line visibility issues in Textual TextArea

            # Method 3: For markdown files, be extra aggressive
            is_markdown = False
            if hasattr(self.text_area, 'file_path') and self.text_area.file_path:
                file_path_str = str(self.text_area.file_path).lower()
                is_markdown = file_path_str.endswith(('.md', '.markdown'))
                if is_markdown:
                    logger.debug(f"🔢   MARKDOWN FILE detected: {self.text_area.file_path}")
                    # Force cursor to top for markdown files
                    self.text_area.cursor_location = (0, 0)
                    logger.debug(f"🔢   Applied markdown-specific positioning")
            
            # Method 6: Force cursor position using TextArea internal methods if available
            if hasattr(self.text_area, 'move_cursor'):
                try:
                    self.text_area.move_cursor((0, 0))
                    logger.debug(f"🔢   Called move_cursor((0, 0))")
                except Exception:
                    pass
                    
            # Focus the text area AFTER positioning
            self.text_area.focus()
            logger.debug(f"🔢   Focused text area")
            
            # VERIFICATION: Log what actually happened after all our positioning attempts
            final_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            final_selection = getattr(self.text_area, 'selection', None)
            total_lines = len(self.text_area.text.split('\n'))
            
            logger.debug(f"🔢 FINAL VERIFICATION AFTER POSITIONING:")
            logger.debug(f"🔢   Final cursor_location: {final_cursor}")
            logger.debug(f"🔢   Final selection: {final_selection}")
            logger.debug(f"🔢   Total lines in content: {total_lines}")
            logger.debug(f"🔢   Is markdown file: {is_markdown}")
            
            # Try to get scroll position if available
            if hasattr(self.text_area, 'scroll_offset'):
                logger.debug(f"🔢   Final scroll_offset: {getattr(self.text_area, 'scroll_offset', 'N/A')}")
            if hasattr(self.text_area, 'scroll_x'):
                logger.debug(f"🔢   Final scroll_x/y: ({getattr(self.text_area, 'scroll_x', 'N/A')}, {getattr(self.text_area, 'scroll_y', 'N/A')})")
            
            # Use cursor position for line numbers
            if hasattr(self.text_area, 'selection') and self.text_area.selection:
                current_line = self.text_area.selection.end[0]
                logger.debug(f"🔢   Using selection.end[0] for line numbers: {current_line}")
            elif hasattr(self.text_area, 'cursor_location'):
                current_line = self.text_area.cursor_location[0]
                logger.debug(f"🔢   Using cursor_location[0] for line numbers: {current_line}")
            else:
                current_line = 0
                logger.debug(f"🔢   Fallback to 0 for line numbers")
            
            # Note: Line number widget disabled due to Textual layout conflicts

            logger.debug(f"🔢 VimEditor _initialize_editor completed successfully")
            
        except Exception as e:
            logger.error(f"Error initializing vim editor: {e}")
    
    def _delayed_positioning_check(self):
        """Delayed check to ensure positioning worked correctly."""
        try:
            logger.debug(f"🔢 DELAYED POSITIONING CHECK starting")
            
            # Check if we're still at the top
            current_cursor = getattr(self.text_area, 'cursor_location', (0, 0))
            current_selection = getattr(self.text_area, 'selection', None)
            
            logger.debug(f"🔢   Current cursor after delay: {current_cursor}")
            logger.debug(f"🔢   Current selection after delay: {current_selection}")
            
            # If we're not at the top, force it again
            cursor_row = current_cursor[0] if current_cursor else 0
            selection_row = current_selection.end[0] if current_selection else 0
            
            if cursor_row != 0 or selection_row != 0:
                logger.debug(f"🔢   NOT AT TOP! cursor_row={cursor_row}, selection_row={selection_row}")
                logger.debug(f"🔢   Forcing position to top again...")
                
                # Force positioning again
                self.text_area.cursor_location = (0, 0)
                if hasattr(self.text_area, 'selection'):
                    self.text_area.selection = None
                # Note: scroll_to and line numbers disabled due to layout issues

                logger.debug(f"🔢   Forced positioning completed")
            else:
                logger.debug(f"🔢   Position is correct, no adjustment needed")
                
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
