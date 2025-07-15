#!/usr/bin/env python3
"""
Selection mode mixin for browser widgets.

This mixin provides consistent text selection functionality across browsers.
"""

import logging
from typing import Protocol, Callable, Optional, Any
from textual.containers import ScrollableContainer
from textual.widgets import RichLog
from textual.binding import Binding

logger = logging.getLogger(__name__)


class SelectionHost(Protocol):
    """Protocol defining what SelectionMixin expects from its host widget."""
    
    selection_mode: bool
    app: Any  # Textual app instance
    
    def call_after_refresh(self, callback: Callable[[], None]) -> None:
        """Schedule callback to run after next refresh."""
        ...
    
    def query_one(self, selector: str, widget_type: type = None) -> Any:
        """Query for a single widget."""
        ...
    
    def get_current_document_content(self) -> str:
        """Get the current document content for selection mode."""
        ...


class SelectionMixin:
    """
    Mixin that provides text selection mode functionality.
    
    Classes using this mixin should implement SelectionHost protocol.
    """
    
    # Standard selection bindings
    SELECTION_BINDINGS: list[Binding] = [
        Binding("s", "toggle_selection_mode", "Select", key_display="s"),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'selection_mode'):
            self.selection_mode: bool = False
    
    def get_current_document_content(self) -> str:
        """
        Get current document content for selection mode.
        
        Subclasses should override this to provide the actual content.
        
        Returns:
            str: The content to display in selection mode
        """
        return "No content available for selection"
    
    def action_toggle_selection_mode(self) -> None:
        """Toggle between formatted view and text selection mode."""
        try:
            # Check if we're in the right screen/context
            try:
                container: ScrollableContainer = self.query_one("#preview", ScrollableContainer)
                app = self.app
            except Exception:
                # We're not in the main browser screen - selection mode not available
                return

            if not self.selection_mode:
                # Switch to selection mode
                self.selection_mode = True
                self._enter_selection_mode(container, app)
            else:
                # Switch back to formatted view
                self.selection_mode = False
                self._exit_selection_mode(container, app)

        except Exception as e:
            # Recovery: ensure we have a working widget
            logger.error(f"Error in action_toggle_selection_mode: {e}", exc_info=True)
            try:
                app = self.app
                if hasattr(app, 'update_status'):
                    app.update_status(f"Toggle failed: {e} - try refreshing")
            except:
                pass
    
    def _enter_selection_mode(self, container: ScrollableContainer, app: Any) -> None:
        """Enter selection mode with a text area for copying."""
        # Get content from the host
        plain_content = self.get_current_document_content()

        # Remove old widgets explicitly and safely
        try:
            existing_widget = container.query_one("#preview-content")
            if existing_widget:
                existing_widget.remove()
        except Exception:
            pass

        # Then remove all children as backup
        container.remove_children()
        container.refresh(layout=True)

        # Create and mount TextArea for selection
        def mount_text_area():
            try:
                from .text_areas import SelectionTextArea
                text_area = SelectionTextArea(
                    self,  # Pass host instance
                    plain_content,
                    id="preview-content"
                )
                text_area.read_only = True
                text_area.disabled = False
                text_area.can_focus = True
                text_area.add_class("constrained-textarea")

                if hasattr(text_area, 'word_wrap'):
                    text_area.word_wrap = True

                container.mount(text_area)
                text_area.focus()

                if hasattr(app, 'update_status'):
                    app.update_status("SELECTION MODE: Select text with mouse, Ctrl+C to copy, ESC or 's' to exit")
            except Exception as mount_error:
                if hasattr(app, 'update_status'):
                    app.update_status(f"Failed to create selection widget: {mount_error}")

        # Use call_after_refresh to ensure DOM is clean before mounting
        self.call_after_refresh(mount_text_area)
    
    def _exit_selection_mode(self, container: ScrollableContainer, app: Any) -> None:
        """Exit selection mode and restore formatted view."""
        # Remove old widgets
        try:
            existing_widget = container.query_one("#preview-content")
            if existing_widget:
                existing_widget.remove()
        except Exception:
            pass

        container.remove_children()
        container.refresh(layout=True)

        # Restore RichLog
        def mount_richlog():
            richlog = RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False
            )
            richlog.can_focus = False
            container.mount(richlog)
            
            # Restore current document preview
            self.call_after_refresh(self._restore_preview_content)

        self.call_after_refresh(mount_richlog)

        if hasattr(app, 'update_status'):
            app.update_status("Document Browser | f=files | d=git | q=quit")
    
    def _restore_preview_content(self) -> None:
        """
        Restore preview content after exiting selection mode.
        
        Subclasses should override this to provide actual content restoration.
        """
        try:
            preview = self.query_one("#preview-content", RichLog)
            preview.clear()
            preview.write("[dim]Preview content restoration not implemented[/dim]")
        except:
            pass
    
    async def exit_selection_mode(self) -> None:
        """
        Async version of selection mode exit.
        
        This method can be called from async contexts and will handle
        the selection mode exit properly.
        """
        if not self.selection_mode:
            return
            
        # Get preview container
        try:
            preview_container = self.query_one("#preview-container")
        except:
            # Fallback to preview if preview-container doesn't exist
            try:
                preview_container = self.query_one("#preview")
            except:
                return
        
        # Remove all children except vim indicator (if it exists)
        for child in list(preview_container.children):
            if getattr(child, 'id', None) not in ["vim-mode-indicator"]:
                await child.remove()
        
        # Restore preview structure
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog
        
        preview = ScrollableContainer(id="preview")
        preview_content = RichLog(
            id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
        )
        preview_content.can_focus = False
        
        await preview_container.mount(preview)
        await preview.mount(preview_content)
        
        self.selection_mode = False
        
        # Restore preview content
        self._restore_preview_content()
        
        # Update status
        try:
            app = self.app
            if hasattr(app, 'update_status'):
                app.update_status("Document Browser | f=files | d=git | q=quit")
        except:
            pass