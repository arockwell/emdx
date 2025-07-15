#!/usr/bin/env python3
"""Edit mode mixin for browser widgets."""

import logging
from typing import Optional, Dict, Any
from textual.binding import Binding

logger = logging.getLogger(__name__)


class EditMixin:
    """Mixin that provides vim edit mode functionality."""
    
    EDIT_BINDINGS: list[Binding] = [
        Binding("e", "edit_document", "Edit", key_display="e"),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'edit_mode'):
            self.edit_mode = False
            self.editing_doc_id: Optional[int] = None
    
    def get_current_document_for_edit(self) -> Optional[Dict[str, Any]]:
        """Get current document for editing. Override in subclass."""
        return None
    
    async def action_edit_document(self) -> None:
        """Edit the current document."""
        doc = self.get_current_document_for_edit()
        if not doc:
            return
            
        self.editing_doc_id = doc["id"]
        self.edit_mode = True
        
        container = self.query_one("#preview")
        container.remove_children()
        
        from .text_areas import VimEditTextArea
        edit_area = VimEditTextArea(
            self, 
            content=doc["content"], 
            id="edit-area"
        )
        container.mount(edit_area)
        edit_area.focus()
    
    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode."""
        if self.edit_mode:
            self.call_after_refresh(self._async_exit_edit_mode)
    
    def _async_exit_edit_mode(self) -> None:
        """Async wrapper for exit_edit_mode."""
        import asyncio
        asyncio.create_task(self.exit_edit_mode())
    
    async def exit_edit_mode(self) -> None:
        """Exit edit mode and restore preview."""
        if not self.edit_mode:
            return
            
        container = self.query_one("#preview")
        container.remove_children()
        
        from textual.widgets import RichLog
        richlog = RichLog(
            id="preview-content", 
            wrap=True, 
            highlight=True, 
            markup=True
        )
        container.mount(richlog)
        
        self.edit_mode = False
        self.editing_doc_id = None
        await self._restore_edit_preview()
    
    async def _restore_edit_preview(self) -> None:
        """Restore preview content after exiting edit mode. Override in subclass."""
        pass
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode information. Override in subclass."""
        pass