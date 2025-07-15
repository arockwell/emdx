#!/usr/bin/env python3
"""Selection mode mixin for browser widgets."""

import logging
from textual.binding import Binding

logger = logging.getLogger(__name__)


class SelectionMixin:
    """Mixin that provides text selection mode functionality."""
    
    SELECTION_BINDINGS: list[Binding] = [
        Binding("s", "toggle_selection_mode", "Select", key_display="s"),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'selection_mode'):
            self.selection_mode = False
    
    def get_current_document_content(self) -> str:
        """Get current document content. Override in subclass."""
        return "Select and copy text here..."
    
    def action_toggle_selection_mode(self) -> None:
        """Toggle between formatted view and text selection mode."""
        try:
            container = self.query_one("#preview")
            self.selection_mode = not self.selection_mode
            
            # Remove all children to ensure clean state
            # Make a copy of children list to avoid modification during iteration
            children_to_remove = list(container.children)
            for child in children_to_remove:
                child.remove()
            
            if self.selection_mode:
                from .text_areas import SelectionTextArea
                text_area = SelectionTextArea(
                    self, 
                    text=self.get_current_document_content(), 
                    id="preview-content"
                )
                text_area.read_only = True
                text_area.can_focus = True
                container.mount(text_area)
                text_area.focus()
            else:
                from textual.widgets import RichLog
                richlog = RichLog(
                    id="preview-content", 
                    wrap=True, 
                    highlight=True, 
                    markup=True
                )
                container.mount(richlog)
                self._restore_preview_content()
                
        except Exception as e:
            logger.error(f"Error in selection mode toggle: {e}")
    
    def _restore_preview_content(self) -> None:
        """Restore preview content. Override in subclass."""
        pass