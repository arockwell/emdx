#!/usr/bin/env python3
"""
Unified vim editor component for EMDX TUI.
Provides consistent vim editing experience across main browser and file browser.
"""

import logging
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from .text_areas import VimEditTextArea
from ..config.vim_settings import vim_settings

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
        # Check if line numbers are enabled
        if vim_settings.line_numbers_enabled:
            # Configure line numbers widget
            width = vim_settings.line_numbers_width
            self.line_numbers.styles.width = width
            self.line_numbers.styles.min_width = width
            self.line_numbers.styles.max_width = width
            self.line_numbers.styles.background = vim_settings.settings["colors"]["line_numbers"]["background"]
            self.line_numbers.styles.color = vim_settings.settings["colors"]["line_numbers"]["foreground"]
            self.line_numbers.styles.padding = (1, 1, 0, 0)
            self.line_numbers.styles.dock = "left"
            
            # Configure text area to take remaining space
            self.text_area.styles.width = "100%"
            self.text_area.styles.padding = (0, 1)  # Add horizontal padding
            
            # Mount line numbers and text area in proper order
            self.edit_container.mount(self.line_numbers, self.text_area)
        else:
            # No line numbers, just mount text area
            self.text_area.styles.width = "100%"
            self.text_area.styles.padding = (0, 1)
            self.edit_container.mount(self.text_area)
        
        logger.debug(f"🔍 VimEditor.on_mount: Components mounted")
        logger.debug(f"🔍 VimEditor.on_mount: TextArea text length: {len(self.text_area.text)}")
        logger.debug(f"🔍 VimEditor.on_mount: First 50 chars of text: {repr(self.text_area.text[:50])}")
        
        # Ensure the entire vim editor container starts at top
        # TEMPORARILY DISABLED: This might be causing first line visibility issues
        # self.scroll_to(0, 0, animate=False)
        
        # Focus the text area and initialize line numbers
        self.text_area.can_focus = True
        
        # Initialize line numbers immediately on mount
        self._initialize_editor()
        
        # Update line numbers on every cursor move if enabled
        if vim_settings.line_numbers_enabled:
            self.set_interval(0.05, self._update_line_numbers_periodically)
    
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
    
    def _update_line_numbers_periodically(self):
        """Periodically update line numbers to ensure they stay in sync."""
        try:
            if not self.text_area.has_focus:
                return
                
            # Get current cursor position
            if hasattr(self.text_area, 'selection') and self.text_area.selection:
                current_line = self.text_area.selection.end[0]
            elif hasattr(self.text_area, 'cursor_location'):
                current_line = self.text_area.cursor_location[0]
            else:
                current_line = 0
                
            total_lines = len(self.text_area.text.split('\n'))
            
            # Update line numbers
            self.line_numbers.set_line_numbers(current_line, total_lines, self.text_area)
            self._update_line_number_width()
            
        except Exception as e:
            logger.debug(f"Error in periodic line number update: {e}")
    
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
                    logger.debug(f"🔢   MARKDOWN FILE detected: {self.text_area.file_path}")
                    # Triple-force for markdown files
                    self.text_area.cursor_location = (0, 0)
                    # TEMPORARILY DISABLED: scroll_to might be hiding first line
                    # if hasattr(self.text_area, 'scroll_to'):
                    #     self.text_area.scroll_to(0, 0, animate=False)
                    logger.debug(f"🔢   Applied markdown-specific positioning (scroll disabled)")
            
            # Method 6: Force cursor position using TextArea internal methods if available
            if hasattr(self.text_area, 'move_cursor'):
                try:
                    self.text_area.move_cursor((0, 0))
                    logger.debug(f"🔢   Called move_cursor((0, 0))")
                except:
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
            
            # Initialize line numbers if enabled
            if vim_settings.line_numbers_enabled:
                self.line_numbers.set_line_numbers(current_line, total_lines, self.text_area)
                self._update_line_number_width()
                if hasattr(self.text_area, '_update_line_numbers'):
                    logger.debug(f"🔢 Calling text area's _update_line_numbers()")
                    self.text_area._update_line_numbers()
                
            logger.debug(f"🔢 VimEditor _initialize_editor completed successfully")
            
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