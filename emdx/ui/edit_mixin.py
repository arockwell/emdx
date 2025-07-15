#!/usr/bin/env python3
"""
Edit mode mixin for browser widgets.

This mixin provides consistent vim-style editing functionality across browsers.
"""

import logging
from typing import Protocol, Callable, Optional, Any, Dict
from textual.containers import ScrollableContainer, Horizontal, Container, Vertical
from textual.widgets import RichLog, Label
from textual.binding import Binding

logger = logging.getLogger(__name__)


class EditHost(Protocol):
    """Protocol defining what EditMixin expects from its host widget."""
    
    edit_mode: bool
    editing_doc_id: Optional[int]
    app: Any  # Textual app instance
    
    def call_after_refresh(self, callback: Callable[[], None]) -> None:
        """Schedule callback to run after next refresh."""
        ...
    
    def query_one(self, selector: str, widget_type: type = None) -> Any:
        """Query for a single widget."""
        ...
    
    def get_current_document_for_edit(self) -> Optional[Dict[str, Any]]:
        """Get the current document for editing."""
        ...
    
    def get_primary_table(self) -> Any:
        """Get the primary table widget."""
        ...


class EditMixin:
    """
    Mixin that provides vim-style edit mode functionality.
    
    Classes using this mixin should implement EditHost protocol and TextAreaHost.
    """
    
    # Standard edit bindings
    EDIT_BINDINGS: list[Binding] = [
        Binding("e", "edit_document", "Edit", key_display="e"),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'edit_mode'):
            self.edit_mode: bool = False
        if not hasattr(self, 'editing_doc_id'):
            self.editing_doc_id: Optional[int] = None
    
    def get_current_document_for_edit(self) -> Optional[Dict[str, Any]]:
        """
        Get current document for editing.
        
        Subclasses should override this to provide the actual document.
        
        Returns:
            Dict[str, Any]: Document data with 'id' and 'content' keys
        """
        return None
    
    async def action_edit_document(self) -> None:
        """Edit the current document."""
        await self.enter_edit_mode()
    
    async def enter_edit_mode(self) -> None:
        """Enter edit mode for the selected document."""
        # Get document from host
        doc = self.get_current_document_for_edit()
        if not doc:
            return
            
        self.editing_doc_id = doc["id"]
        
        # Store original preview for restoration
        self.original_preview_content = doc["content"]
        
        # Get the preview container (like original working version)
        container = self.query_one("#preview", ScrollableContainer)
        
        # Clear container like original version  
        container.remove_children()
        container.refresh()
        
        # Create edit area with proper app instance (self implements TextAreaHost)
        from .text_areas import VimEditTextArea
        edit_area: VimEditTextArea = VimEditTextArea(self, doc["content"], id="edit-area")
        
        # Import line numbers class and containers
        from .main_browser import SimpleVimLineNumbers
        
        # Create wrapper container (like original)
        edit_wrapper = Container(id="edit-wrapper")
        
        # Mount wrapper in preview container
        container.mount(edit_wrapper)
        
        # Create line numbers widget
        line_numbers = SimpleVimLineNumbers(id="line-numbers")
        edit_area.line_numbers_widget = line_numbers
        
        # Create horizontal container for line numbers and text area
        edit_container = Horizontal(id="edit-container")
        
        # Mount edit container in wrapper
        edit_wrapper.mount(edit_container)
        
        # Mount line numbers and edit area in the container
        edit_container.mount(line_numbers)
        edit_container.mount(edit_area)
        
        edit_area.focus()
        
        # Initialize line numbers with current cursor position
        current_line = edit_area.cursor_location[0] if hasattr(edit_area, 'cursor_location') else 0
        total_lines = len(edit_area.text.split('\n'))
        
        # Force cursor to start at beginning if needed
        if current_line == 0:
            edit_area.cursor_location = (0, 0)
            
        line_numbers.set_line_numbers(current_line, total_lines, edit_area)
        
        self.edit_mode = True
        
        # Show vim mode indicator immediately - use call_after_refresh to ensure widget is ready
        self.call_after_refresh(lambda: self._update_vim_status(f"{edit_area.vim_mode} | ESC=exit"))
    
    def action_save_and_exit_edit(self) -> None:
        """Save document and exit edit mode (called by VimEditTextArea)."""
        # For now, just exit edit mode - saving would need to be implemented
        logger.info("action_save_and_exit_edit called")
        try:
            # Use call_after_refresh to avoid timing issues
            self.call_after_refresh(self._async_exit_edit_mode)
        except Exception as e:
            logger.error(f"Error in action_save_and_exit_edit: {e}")
            # Fallback - try direct call
            try:
                import asyncio
                asyncio.create_task(self.exit_edit_mode())
            except:
                pass
    
    def _async_exit_edit_mode(self) -> None:
        """Async wrapper for exit_edit_mode."""
        logger.info("_async_exit_edit_mode called")
        import asyncio
        asyncio.create_task(self.exit_edit_mode())
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status bar with vim mode info (called by VimEditTextArea)."""
        try:
            # Update vim mode indicator if it exists
            try:
                vim_indicator = self.query_one("#vim-mode-indicator", Label)
                if message:
                    vim_indicator.update(f"VIM: {message}")
                else:
                    vim_indicator.update("VIM: NORMAL | ESC=exit")
            except:
                pass  # Vim indicator doesn't exist
                
            # Also update main status
            app = self.app
            if hasattr(app, 'update_status'):
                if message:
                    app.update_status(f"Edit Mode | {message}")
                else:
                    app.update_status("Edit Mode | ESC=exit | Ctrl+S=save")
        except:
            pass
    
    async def exit_edit_mode(self) -> None:
        """Exit edit mode and restore preview."""
        if not self.edit_mode:
            return
            
        # Clear preview container completely
        preview_container = self.query_one("#preview-container", Vertical)
        
        # Remove all children except vim indicator
        for child in list(preview_container.children):
            if child.id not in ["vim-mode-indicator"]:  # Keep vim indicator
                await child.remove()
        
        # Restore original preview structure exactly
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog
        
        # Create preview container and mount directly to the attached container
        preview = ScrollableContainer(id="preview")
        await preview_container.mount(preview)
        
        # Now create and mount the content to the attached preview
        preview_content = RichLog(
            id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
        )
        preview_content.can_focus = False  # Disable focus like original
        await preview.mount(preview_content)
        
        self.edit_mode = False
        
        # Clear vim mode indicator
        try:
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.update("")
        except:
            pass
            
        # Reset main status bar to normal
        app = self.app
        if hasattr(app, 'update_status'):
            app.update_status("Document Browser | f=files | d=git | q=quit")
        
        # Refresh the current document's preview
        await self._restore_edit_preview()
        
        # Return focus to table
        try:
            table = self.get_primary_table()
            table.focus()
        except:
            pass
    
    async def _restore_edit_preview(self) -> None:
        """
        Restore preview content after exiting edit mode.
        
        Subclasses should override this to provide actual content restoration.
        """
        try:
            preview_content = self.query_one("#preview-content", RichLog)
            preview_content.clear()
            preview_content.write("[dim]Edit preview restoration not implemented[/dim]")
        except:
            pass