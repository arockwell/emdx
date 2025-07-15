#!/usr/bin/env python3
"""
Document browser - extracted from the monolith.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Any, Protocol

from .navigation_mixin import NavigationMixin
from .selection_mixin import SelectionMixin
from .edit_mixin import EditMixin
from .browser_types import BrowserState, BrowserMode, DocumentDict, DocumentRow

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, RichLog, Static
from textual.widget import Widget
from textual.binding import Binding

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.ui.formatting import format_tags, truncate_emoji_safe
from emdx.utils.emoji_aliases import expand_aliases

from .document_viewer import FullScreenView
from .modals import DeleteConfirmScreen
from .text_areas import EditTextArea, SelectionTextArea, VimEditTextArea

logger = logging.getLogger(__name__)


class TextAreaHost(Protocol):
    """Protocol defining what VimEditTextArea and SelectionTextArea expect from their host."""
    
    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode."""
        ...
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode information."""
        ...
        
    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (for SelectionTextArea)."""
        ...


class DocumentBrowser(Widget, NavigationMixin, SelectionMixin, EditMixin):
    """Document browser widget that can host text areas."""
    
    BINDINGS = [
        *NavigationMixin.NAVIGATION_BINDINGS,  # Include navigation bindings from mixin
        *SelectionMixin.SELECTION_BINDINGS,    # Include selection bindings from mixin
        *EditMixin.EDIT_BINDINGS,              # Include edit bindings from mixin
        Binding("/", "search", "Search"),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags"),
    ]
    
    CSS = """
    DocumentBrowser {
        layout: vertical;
        height: 100%;
    }
    
    #search-input, #tag-input {
        display: none;
        height: 3;
        margin: 1;
        border: solid $primary;
    }
    
    #search-input.visible, #tag-input.visible {
        display: block;
    }
    
    #tag-selector {
        display: none;
        height: 1;
        margin: 0 1;
    }
    
    Horizontal {
        height: 1fr;
    }
    
    #sidebar {
        width: 40%;
        min-width: 40;
    }
    
    #doc-table {
        height: 1fr;
        min-height: 10;
    }
    
    #preview-container {
        width: 60%;
        min-width: 40;
        padding: 0 1;
    }
    
    #vim-mode-indicator {
        height: 1;
        background: $boost;
        text-align: center;
        display: none;
    }
    
    #vim-mode-indicator.visible {
        display: block;
    }
    
    #preview {
        height: 1fr;
        border: solid $primary;
    }
    
    #preview-content {
        height: 1fr;
        padding: 1;
    }
    
    /* Edit mode layout */
    #edit-container {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0;
        margin: 0;
        background: $background;
    }
    
    #edit-container > * {
        padding: 0;
        margin: 0;
    }
    
    #edit-container TextArea {
        margin: 0;
        padding-left: 0;
        border-left: none;
        background: $background;
        color: $text;  /* Fix: Set text color to be visible */
        width: 1fr;
    }
    
    #line-numbers {
        border: none;
        scrollbar-size: 0 0;
        overflow: hidden;
        padding-top: 0;
        padding-left: 0;
        padding-right: 1;
        padding-bottom: 0;
        margin-top: 0;
        margin-left: 0;
        margin-right: 0;
    }
    
    /* Vim relative line numbers */
    .vim-line-numbers {
        width: 4;
        background: $background;
        color: $text-muted;
        text-align: right;
        padding-right: 1;
        padding-top: 1;
        margin: 0;
        border: none;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    """
    
    # Reactive properties
    mode = reactive("NORMAL")
    selection_mode = reactive(False)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.documents: List[Dict[str, Any]] = []
        self.filtered_docs: List[Dict[str, Any]] = []
        self.current_search: str = ""
        self.edit_mode: bool = False
        self.editing_doc_id: Optional[int] = None
        self.tag_action: Optional[str] = None
    
    def get_primary_table(self) -> DataTable:
        """Return the document table for navigation."""
        return self.query_one("#doc-table", DataTable)
    
    def get_current_document_content(self) -> str:
        """Get current document content for selection mode."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            full_doc = get_document(str(doc["id"]))
            if full_doc:
                content = full_doc["content"].strip()
                if not content.startswith(f"# {full_doc['title']}"):
                    return f"# {full_doc['title']}\n\n{content}"
                else:
                    return content
        return "Select and copy text here..."
    
    def get_current_document_for_edit(self) -> Optional[Dict[str, Any]]:
        """Get current document for editing."""
        table = self.query_one("#doc-table", DataTable)
        if not table.cursor_row:
            return None
            
        row_idx = table.cursor_row
        if row_idx >= len(self.filtered_docs):
            return None
            
        doc = self.filtered_docs[row_idx]
        
        # Load full document
        full_doc = get_document(str(doc["id"]))
        return full_doc
    
    def _restore_preview_content(self) -> None:
        """Restore preview content after exiting selection mode."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            full_doc = get_document(str(doc["id"]))
            
            if full_doc:
                from rich.markdown import Markdown
                try:
                    preview_content = self.query_one("#preview-content", RichLog)
                    content = full_doc["content"]
                    if content.strip():
                        markdown = Markdown(content)
                        preview_content.write(markdown)
                    else:
                        preview_content.write("[dim]Empty document[/dim]")
                except Exception as e:
                    preview_content.write(full_doc["content"])
    
    async def _restore_edit_preview(self) -> None:
        """Restore preview content after exiting edit mode."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            full_doc = get_document(str(doc["id"]))
            
            if full_doc:
                from rich.markdown import Markdown
                try:
                    preview_content = self.query_one("#preview-content", RichLog)
                    content = full_doc["content"]
                    if content.strip():
                        markdown = Markdown(content)
                        preview_content.write(markdown)
                    else:
                        preview_content.write("[dim]Empty document[/dim]")
                except Exception as e:
                    preview_content.write(full_doc["content"])
        
    def compose(self) -> ComposeResult:
        """Compose the document browser UI."""
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input",
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")
        
        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with Vertical(id="preview-container"):
                yield Label("", id="vim-mode-indicator")
                with ScrollableContainer(id="preview"):
                    yield RichLog(
                        id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
                    )
                    
    async def on_mount(self) -> None:
        """Initialize the document browser."""
        logger.info("DocumentBrowser mounted")
        
        # Setup table
        table = self.query_one("#doc-table", DataTable)
        table.add_columns("ID", "Project", "Title", "Tags", "Created")
        table.cursor_type = "row"
        table.show_header = True
        
        # Disable focus on non-interactive widgets
        preview_content = self.query_one("#preview-content")
        preview_content.can_focus = False
        
        search_input = self.query_one("#search-input")
        search_input.can_focus = False
        tag_input = self.query_one("#tag-input")
        tag_input.can_focus = False
        
        # Hide inputs initially
        search_input.display = False
        tag_input.display = False
        
        # Set focus to table so keys work immediately
        table.focus()
        
        # Load documents
        await self.load_documents()
        
    async def load_documents(self) -> None:
        """Load documents from database."""
        try:
            with db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, title, project, created_at, accessed_at, access_count
                    FROM documents
                    WHERE is_deleted = 0
                    ORDER BY accessed_at DESC
                """)
                self.documents = cursor.fetchall()
                self.filtered_docs = self.documents
                logger.info(f"Loaded {len(self.documents)} documents")
                await self.update_table()
        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def update_table(self) -> None:
        """Update the table with filtered documents."""
        table = self.query_one("#doc-table", DataTable)
        table.clear()
        
        for doc in self.filtered_docs:
            # Get tags for document
            tags = get_document_tags(doc["id"])
            
            # Format row data
            tags_str = format_tags(tags) if tags else ""
            title = truncate_emoji_safe(doc["title"], 40)
            project = doc["project"] or "default"
            
            table.add_row(
                str(doc["id"]),
                project,
                title,
                tags_str,
                str(doc["created_at"])[:10],
            )
            
        # Update status - need to find the app instance
        try:
            app = self.app
            if hasattr(app, 'update_status'):
                status_text = f"{len(self.filtered_docs)}/{len(self.documents)} docs"
                if self.mode == "NORMAL":
                    status_text += " | e=edit | /=search | t=tag | q=quit"
                elif self.mode == "SEARCH":
                    status_text += " | Enter=apply | ESC=cancel"
                app.update_status(status_text)
        except:
            pass  # Status update failed, continue
            
    def save_state(self) -> Dict[str, Any]:
        """Save current state for restoration."""
        state: Dict[str, Any] = {
            "mode": self.mode,
            "current_search": self.current_search,
        }
        
        # Save cursor position
        try:
            table = self.query_one("#doc-table", DataTable)
            state["cursor_position"] = table.cursor_coordinate
        except:
            pass
            
        return state
        
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore saved state."""
        self.mode = state.get("mode", "NORMAL")
        self.current_search = state.get("current_search", "")
        
        # Restore cursor position
        if "cursor_position" in state:
            try:
                table = self.query_one("#doc-table", DataTable)
                table.cursor_coordinate = state["cursor_position"]
            except:
                pass
                
    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        
        # Handle escape key to exit modes
        # Don't handle escape for SELECTION mode here - let SelectionTextArea handle it
        if key == "escape":
            if self.edit_mode:
                await self.exit_edit_mode()
                event.stop()
            elif self.mode == "SEARCH":
                self.exit_search_mode()
                event.stop()
            elif self.mode == "TAG":
                self.exit_tag_mode()
                event.stop()
            # Note: SELECTION mode escape is handled by SelectionTextArea itself
                
        
            
        
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
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            full_doc = get_document(str(doc["id"]))
            
            if full_doc:
                from rich.markdown import Markdown
                try:
                    content = full_doc["content"]
                    if content.strip():
                        markdown = Markdown(content)
                        preview_content.write(markdown)
                    else:
                        preview_content.write("[dim]Empty document[/dim]")
                except Exception as e:
                    preview_content.write(full_doc["content"])
        
        # Return focus to table
        table.focus()
        
    # Navigation methods provided by NavigationMixin
            
    # Edit document action provided by EditMixin
        
    def action_search(self) -> None:
        """Enter search mode."""
        self.mode = "SEARCH"
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.can_focus = True
        search_input.focus()
        
    def action_add_tags(self) -> None:
        """Enter tag adding mode."""
        self.mode = "TAG"
        self.tag_action = "add"
        tag_input = self.query_one("#tag-input", Input)
        tag_input.display = True
        tag_input.can_focus = True
        tag_input.focus()
        
    def action_remove_tags(self) -> None:
        """Enter tag removal mode."""
        self.mode = "TAG"
        self.tag_action = "remove"
        # Show tag selector with existing tags
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row >= len(self.filtered_docs):
            return
        doc = self.filtered_docs[table.cursor_row]
        tags = get_document_tags(doc["id"])
        
        if not tags:
            return  # No tags to remove
            
        # For now, just use input - proper selector later
        tag_input = self.query_one("#tag-input", Input)
        tag_input.placeholder = f"Remove tags: {', '.join(tags)}"
        tag_input.display = True
        tag_input.can_focus = True
        tag_input.focus()
        
    # Selection mode provided by SelectionMixin
            
    # Exit selection mode provided by SelectionMixin
    
    async def on_data_table_row_highlighted(self, event) -> None:
        """Update preview when row is highlighted."""
        if self.edit_mode:
            return
            
        row_idx = event.cursor_row
        if row_idx >= len(self.filtered_docs):
            return
            
        doc = self.filtered_docs[row_idx]
        
        # Load full document for preview
        full_doc = get_document(str(doc["id"]))
            
        if full_doc and not self.edit_mode:
            try:
                preview = self.query_one("#preview-content", RichLog)
                preview.clear()
                
                # Render content as markdown
                from rich.markdown import Markdown
                try:
                    content = full_doc["content"]
                    if content.strip():
                        markdown = Markdown(content)
                        preview.write(markdown)
                    else:
                        preview.write("[dim]Empty document[/dim]")
                except Exception as e:
                    # Fallback to plain text if markdown fails
                    preview.write(full_doc["content"])
            except Exception as e:
                # Preview widget not found or not ready - ignore
                pass
                
    async def on_input_submitted(self, event) -> None:
        """Handle input submission."""
        if event.input.id == "search-input":
            # Handle search
            query = event.input.value.strip()
            if query:
                self.current_search = query
                await self.apply_search()
            self.exit_search_mode()
            
        elif event.input.id == "tag-input":
            # Handle tag operations
            if self.tag_action == "add":
                await self.add_tags_to_current_doc(event.input.value)
            elif self.tag_action == "remove":
                await self.remove_tags_from_current_doc(event.input.value)
            self.exit_tag_mode()
            
    def exit_search_mode(self) -> None:
        """Exit search mode."""
        self.mode = "NORMAL"
        search_input = self.query_one("#search-input", Input)
        search_input.display = False
        search_input.can_focus = False
        search_input.value = ""
        table = self.query_one("#doc-table", DataTable)
        table.focus()
        
    def exit_tag_mode(self) -> None:
        """Exit tag mode."""
        self.mode = "NORMAL"
        tag_input = self.query_one("#tag-input", Input)
        tag_input.display = False
        tag_input.can_focus = False
        tag_input.value = ""
        tag_input.placeholder = "Enter tags separated by spaces..."
        table = self.query_one("#doc-table", DataTable)
        table.focus()
        
    async def apply_search(self) -> None:
        """Apply current search filter."""
        if not self.current_search:
            self.filtered_docs = self.documents
        else:
            # Simple title search for now
            self.filtered_docs = [
                doc for doc in self.documents
                if self.current_search.lower() in doc["title"].lower()
            ]
        await self.update_table()
        
    async def add_tags_to_current_doc(self, tag_text: str) -> None:
        """Add tags to current document."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row >= len(self.filtered_docs):
            return
        doc = self.filtered_docs[table.cursor_row]
        
        tags = [tag.strip() for tag in tag_text.split() if tag.strip()]
        if tags:
            add_tags_to_document(doc["id"], tags)
            await self.update_table()
            
    async def remove_tags_from_current_doc(self, tag_text: str) -> None:
        """Remove tags from current document."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row >= len(self.filtered_docs):
            return
        doc = self.filtered_docs[table.cursor_row]
        
        tags = [tag.strip() for tag in tag_text.split() if tag.strip()]
        if tags:
            remove_tags_from_document(doc["id"], tags)
            await self.update_table()