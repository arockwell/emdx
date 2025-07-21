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
        
        # Apply styling - use file-browser specific class for proper alignment
        self.text_area.add_class("file-browser-vim-textarea")
        self.text_area.word_wrap = True
        self.text_area.show_line_numbers = False  # Using custom vim relative numbers
        
        # DEBUG: Add visible border and background to text area
        self.text_area.styles.border = ("solid", "red")
        self.text_area.styles.background = "#1a1a1a"  # Dark gray background
        self.text_area.styles.width = "1fr"  # Take remaining space
        
        # Try setting max line length if available
        if hasattr(self.text_area, 'max_line_length'):
            self.text_area.max_line_length = 80
        
        # Create line numbers widget
        self.line_numbers = SimpleVimLineNumbers(id="vim-line-numbers")
        self.text_area.line_numbers_widget = self.line_numbers
        
        # DEBUG: Add visible border to line numbers
        self.line_numbers.styles.border = ("solid", "green")
        self.line_numbers.styles.width = 4  # Fixed width for line numbers (matching CSS)
        self.line_numbers.styles.max_width = 4
        self.line_numbers.styles.min_width = 4
        
        # Create horizontal container for line numbers and text area
        self.edit_container = Horizontal(id="vim-edit-container")
        
        # DEBUG: Ensure container takes full width
        self.edit_container.styles.width = "100%"
    
    def compose(self):
        """Compose the vim editor layout."""
        yield self.edit_container
    
    def on_mount(self):
        """Set up the vim editor after mounting."""
        # Mount line numbers and text area in horizontal layout
        self.edit_container.mount(self.line_numbers)
        self.edit_container.mount(self.text_area)
        
        logger.debug(f"🔍 VimEditor.on_mount: Components mounted")
        logger.debug(f"🔍 VimEditor.on_mount: TextArea text length: {len(self.text_area.text)}")
        logger.debug(f"🔍 VimEditor.on_mount: First 50 chars of text: {repr(self.text_area.text[:50])}")
        
        # DEBUG: Log widget sizes after mounting
        self.call_after_refresh(lambda: self._log_widget_sizes())
        
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
    
    def _log_widget_sizes(self):
        """DEBUG: Log widget sizes and visibility."""
        try:
            logger.debug(f"🔍 DEBUG WIDGET SIZES:")
            logger.debug(f"🔍   VimEditor size: {self.size}")
            logger.debug(f"🔍   VimEditor region: {self.region}")
            logger.debug(f"🔍   Edit container size: {self.edit_container.size}")
            logger.debug(f"🔍   Line numbers size: {self.line_numbers.size}")
            logger.debug(f"🔍   Line numbers visible: {self.line_numbers.visible}")
            logger.debug(f"🔍   TextArea size: {self.text_area.size}")
            logger.debug(f"🔍   TextArea visible: {self.text_area.visible}")
            logger.debug(f"🔍   TextArea display: {self.text_area.display}")
            logger.debug(f"🔍   TextArea has content: {len(self.text_area.text) > 0}")
            logger.debug(f"🔍   TextArea content preview: {repr(self.text_area.text[:100])}")
        except Exception as e:
            logger.debug(f"🔍 Error logging widget sizes: {e}")
    
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
            
            # Set initial line numbers
            self.line_numbers.set_line_numbers(current_line, total_lines, self.text_area)
            
            # Double-check by calling text area's update method if it exists
            if hasattr(self.text_area, '_update_line_numbers'):
                logger.debug(f"🔢 Calling text area's _update_line_numbers()")
                self.text_area._update_line_numbers()
                
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
                # TEMPORARILY DISABLED: scroll_to might be hiding first line
                # if hasattr(self.text_area, 'scroll_to'):
                #     self.text_area.scroll_to(0, 0, animate=False)
                    
                # Update line numbers
                total_lines = len(self.text_area.text.split('\n'))
                self.line_numbers.set_line_numbers(0, total_lines, self.text_area)
                
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