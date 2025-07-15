#!/usr/bin/env python3
"""
Document browser - extracted from the monolith.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Any

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


class DocumentBrowser(Widget):
    """Document browser widget."""
    
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
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
    }
    
    #search-input.visible, #tag-input.visible {
        display: block;
    }
    
    #doc-table {
        width: 45%;
        margin: 0;
    }
    
    #preview-container {
        width: 55%;
        padding: 0 1;
    }
    
    #sidebar {
        width: 45%;
    }
    """
    
    # Reactive properties
    mode = reactive("NORMAL")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.documents: List[Dict[str, Any]] = []
        self.filtered_docs: List[Dict[str, Any]] = []
        self.current_search: str = ""
        self.edit_mode: bool = False
        self.editing_doc_id: Optional[int] = None
        self.tag_action: Optional[str] = None
        
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
        
        if self.mode == "NORMAL":
            if key == "/":
                # Enter search mode
                self.mode = "SEARCH"
                search_input = self.query_one("#search-input", Input)
                search_input.display = True
                search_input.can_focus = True
                search_input.focus()
                event.stop()
            elif key == "t":
                # Tag mode
                self.mode = "TAG"
                self.tag_action = "add"
                tag_input = self.query_one("#tag-input", Input)
                tag_input.display = True
                tag_input.can_focus = True
                tag_input.focus()
                event.stop()
            elif key == "e":
                # Edit mode
                await self.enter_edit_mode()
                event.stop()
        elif self.mode == "SEARCH":
            if key == "escape":
                # Exit search
                self.mode = "NORMAL"
                search_input = self.query_one("#search-input", Input)
                search_input.display = False
                search_input.can_focus = False
                table = self.query_one("#doc-table", DataTable)
                table.focus()
                event.stop()
        elif self.mode == "TAG":
            if key == "escape":
                # Exit tag mode
                self.mode = "NORMAL"
                tag_input = self.query_one("#tag-input", Input)
                tag_input.display = False
                tag_input.can_focus = False
                table = self.query_one("#doc-table", DataTable)
                table.focus()
                event.stop()
                
    async def enter_edit_mode(self) -> None:
        """Enter edit mode for the selected document."""
        table = self.query_one("#doc-table", DataTable)
        if not table.cursor_row:
            return
            
        row_idx = table.cursor_row
        if row_idx >= len(self.filtered_docs):
            return
            
        doc = self.filtered_docs[row_idx]
        self.editing_doc_id = doc["id"]
        
        # Load full document
        full_doc = get_document(str(doc["id"]))
            
        if not full_doc:
            return
            
        # Replace preview with edit area
        preview_container = self.query_one("#preview-container", Vertical)
        preview = self.query_one("#preview", ScrollableContainer)
        preview.remove()
        
        # Create edit area
        edit_area = VimEditTextArea(full_doc["content"], id="edit-area")
        preview_container.mount(edit_area)
        edit_area.focus()
        
        self.edit_mode = True
        
    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#doc-table", DataTable)
        table.action_cursor_down()
        
    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#doc-table", DataTable)
        table.action_cursor_up()
        
    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            
    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0:
            table.cursor_coordinate = (table.row_count - 1, 0)
    
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
            
        if full_doc:
            preview = self.query_one("#preview-content", RichLog)
            preview.clear()
            preview.write(full_doc["content"])