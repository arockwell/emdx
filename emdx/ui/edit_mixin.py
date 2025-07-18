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
        try:
            doc = self.get_current_document_for_edit()
            if not doc:
                return
                
            self.editing_doc_id = doc["id"]
            self.edit_mode = True
            
            # Remove the preview container first
            preview_container = self.query_one("#preview-container")
            
            # Remove all children except vim mode indicator
            for child in list(preview_container.children):
                if child.id not in ["vim-mode-indicator"]:
                    child.remove()
            
            # Use the same VimEditor that works in file browser
            from .vim_editor import VimEditor
            
            content = doc.get("content", "")
            logger.info(f"EditMixin: Creating VimEditor with {len(content)} chars of content")
            
            # Create a mock app instance for vim callbacks
            class EditMixinVimApp:
                def __init__(self, parent):
                    self.parent = parent
                
                def action_save_and_exit_edit(self):
                    self.parent.action_save_and_exit_edit()
                
                def _update_vim_status(self, message=""):
                    self.parent._update_vim_status(message)
            
            vim_app = EditMixinVimApp(self)
            
            # Create vim editor - mount directly to preview container like file browser
            vim_editor = VimEditor(
                vim_app,
                content=content,
                id="vim-editor-widget"
            )
            
            # Store reference for save/exit
            self.vim_editor = vim_editor
            
            logger.info(f"EditMixin: About to mount VimEditor with {len(content)} chars of content")
            preview_container.mount(vim_editor)
            
            # Debug: Check if text area actually has content after mounting
            def debug_check():
                try:
                    if hasattr(vim_editor, 'text_area'):
                        actual_text = vim_editor.text_area.text
                        logger.info(f"EditMixin: After mount - text_area has {len(actual_text)} chars")
                        logger.info(f"EditMixin: Text area content starts with: {actual_text[:50]}")
                    else:
                        logger.error("EditMixin: No text_area found in vim_editor!")
                    vim_editor.focus_editor()
                except Exception as e:
                    logger.error(f"EditMixin: Error in debug_check: {e}")
            
            # Focus after mounting
            self.call_after_refresh(debug_check)
            
            logger.info(f"EditMixin: VimEditor mounted")
        except Exception as e:
            logger.error(f"EditMixin: Error in action_edit_document: {e}")
            self.edit_mode = False
            self.editing_doc_id = None
    
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
            
        preview_container = self.query_one("#preview-container")
        
        # Remove vim editor if it exists
        if hasattr(self, 'vim_editor'):
            self.vim_editor.remove()
            delattr(self, 'vim_editor')
        
        # Remove all children except vim mode indicator
        for child in list(preview_container.children):
            if child.id not in ["vim-mode-indicator"]:
                child.remove()
        
        # Restore original preview structure
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog
        
        # Create preview container
        preview = ScrollableContainer(id="preview")
        preview_container.mount(preview)
        
        # Create content widget
        richlog = RichLog(
            id="preview-content", 
            wrap=True, 
            highlight=True, 
            markup=True
        )
        preview.mount(richlog)
        
        self.edit_mode = False
        self.editing_doc_id = None
        await self._restore_edit_preview()
    
    async def _restore_edit_preview(self) -> None:
        """Restore preview content after exiting edit mode. Override in subclass."""
        pass
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode information. Override in subclass."""
        pass