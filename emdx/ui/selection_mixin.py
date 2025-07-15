#!/usr/bin/env python3
"""Selection mode mixin for browser widgets."""

import logging
from textual.binding import Binding
from .widget_ids import PREVIEW_CONTAINER, PREVIEW_CONTENT

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
    
    async def action_toggle_selection_mode(self) -> None:
        """Toggle between formatted view and text selection mode."""
        try:
            container = self.query_one(f"#{PREVIEW_CONTAINER}")
            self.selection_mode = not self.selection_mode
            
            # Remove all children to ensure clean state
            logger.info(f"SelectionMixin: Container has {len(container.children)} children before removal")
            
            # Remove all children one by one
            removed_count = 0
            while container.children:
                try:
                    child = container.children[0]
                    child_type = type(child).__name__
                    child_id = getattr(child, 'id', 'no-id')
                    child.remove()
                    removed_count += 1
                    logger.info(f"SelectionMixin: Removed child {removed_count}: {child_type} with id={child_id}")
                except Exception as e:
                    logger.error(f"SelectionMixin: Failed to remove child: {e}")
                    break
            
            logger.info(f"SelectionMixin: Container has {len(container.children)} children after removal")
            
            if self.selection_mode:
                from .text_areas import SelectionTextArea
                content = self.get_current_document_content()
                logger.info(f"SelectionMixin: Creating SelectionTextArea with {len(content)} chars")
                text_area = SelectionTextArea(
                    self, 
                    text=content, 
                    id=PREVIEW_CONTENT
                )
                text_area.read_only = True
                text_area.can_focus = True
                # Use await to ensure proper mounting
                await container.mount(text_area)
                text_area.focus()
                logger.info("SelectionMixin: SelectionTextArea mounted and focused")
                
                # Force refresh to ensure content is displayed
                self.call_after_refresh(lambda: text_area.refresh())
            else:
                from textual.widgets import RichLog
                richlog = RichLog(
                    id=PREVIEW_CONTENT, 
                    wrap=True, 
                    highlight=True, 
                    markup=True
                )
                await container.mount(richlog)
                self._restore_preview_content()
                
        except Exception as e:
            logger.error(f"Error in selection mode toggle: {e}")
    
    def _restore_preview_content(self) -> None:
        """Restore preview content. Override in subclass."""
        pass