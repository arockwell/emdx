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
from .vim_editor import VimEditor

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


print("🔴🔴🔴 LOADING DOCUMENT BROWSER WITH BRIGHT COLORS 🔴🔴🔴")

BUILD_ID = "BUILD-1752897674-DIRECT-STYLES"

class DocumentBrowser(Widget):
    """Document browser widget that can host text areas."""
    
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("e", "edit_document", "Edit"),
        Binding("n", "new_document", "New"),
        Binding("/", "search", "Search"),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags"),
        Binding("s", "selection_mode", "Select"),
        Binding("x", "execute_document", "Execute"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    DEFAULT_CSS = """
    DocumentBrowser {
        layout: vertical;
        height: 100%;
        layers: base overlay;
        padding: 0;
        margin: 0;
    }
    
    /* Debug styles to make layout visible */
    /* DataTable {
        border: solid green;
    } */
    
    /* RichLog {
        border: solid yellow;
    } */
    
    #search-input, #tag-input {
        layer: overlay;
        display: none;
        height: 3;
        margin: 1;
        border: solid $primary;
        offset: 0 0;
    }
    
    #search-input.visible, #tag-input.visible {
        display: block;
    }
    
    .browser-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
        layer: base;
    }
    
    #tag-selector {
        layer: overlay;
        display: none;
        height: 1;
        margin: 0 1;
        offset: 0 0;
    }
    
    Horizontal {
        height: 1fr;
        layer: base;
    }
    
    #sidebar {
        width: 1fr;
        min-width: 40;
        height: 100%;
        layout: vertical;
        padding: 0;
        margin: 0;
    }
    
    #table-container {
        height: 2fr;
        min-height: 15;
    }
    
    #details-container {
        height: 1fr;
        min-height: 10;
    }
    
    #doc-table {
        height: 100%;
    }
    
    #details-panel {
        height: 100%;
        padding: 1;
    }
    
    .details-richlog {
    }
    
    #preview-container {
        width: 1fr;
        min-width: 40;
        padding: 0;
        margin: 0;
    }
    
    #vim-mode-indicator {
        layer: overlay;
        display: none;
        height: 1;
        background: $boost;
        text-align: center;
        offset: 0 0;
    }
    
    #vim-mode-indicator.active {
        display: block;
    }
    
    #preview {
        height: 1fr;
    }
    
    #preview-content {
        height: 1fr;
        padding: 1;
    }
    
    #edit-container {
        height: 100%;
        layout: vertical;
    }
    
    #title-input {
        height: 3;
        margin: 1;
        border: solid $primary;
    }
    
    #edit-area, #vim-editor-container {
        height: 1fr;
        width: 100%;
    }
    
    #doc-table {
        height: 1fr;
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
        # Docked inputs at the top (hidden by default)
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input",
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")
        yield Label("", id="vim-mode-indicator")
        
        with Horizontal():
            with Vertical(id="sidebar") as sidebar:
                # Remove debug background
                pass
                with Vertical(id="table-container", classes="table-section") as table_container:
                    # Apply direct styles - 2/3 of sidebar
                    table_container.styles.height = "66%"
                    table_container.styles.min_height = 10
                    table_container.styles.padding = (1, 0, 0, 0)  # Top padding for spacing
                    yield DataTable(id="doc-table")
                with Vertical(id="details-container", classes="details-section") as details_container:
                    # Apply direct styles - 1/3 of sidebar
                    details_container.styles.height = "34%"
                    details_container.styles.min_height = 8
                    details_container.styles.padding = 0
                    details_container.styles.border_top = ("heavy", "gray")
                    yield RichLog(
                        id="details-panel",
                        classes="details-richlog",
                        wrap=True, 
                        highlight=True, 
                        markup=True, 
                    auto_scroll=False
                )
            with Vertical(id="preview-container"):
                with ScrollableContainer(id="preview"):
                    yield RichLog(
                        id="preview-content",
                        classes="preview-richlog",
                        wrap=True, highlight=True, markup=True, auto_scroll=False
                    )
        
        # Status bar at the bottom
        yield Static("Ready", id="browser-status", classes="browser-status")
                    
    async def on_mount(self) -> None:
        """Initialize the document browser."""
        logger.info(f"DocumentBrowser mounted - LHS split implementation - {BUILD_ID}")
        logger.info("Details panel should be visible in bottom 1/3 of sidebar")
        print(f"🔴 MOUNTED WITH {BUILD_ID} 🔴")
        
        # Log CSS content to verify it's loaded
        logger.info(f"CSS contains 'background: green': {'background: green' in self.DEFAULT_CSS}")
        logger.info(f"First 200 chars of CSS: {self.DEFAULT_CSS[:200]}")
        
        # Setup table
        table = self.query_one("#doc-table", DataTable)
        table.add_column("ID", width=4)
        table.add_column("Tags", width=8)  
        table.add_column(" ", width=1)  # Padding column
        table.add_column("Title", width=74)
        table.cursor_type = "row"
        table.show_header = True  # Show built-in headers
        table.cell_padding = 0  # Remove cell padding for tight spacing
        
        # Disable focus on non-interactive widgets
        preview_content = self.query_one("#preview-content")
        preview_content.can_focus = False
        
        # Setup details panel
        try:
            details_panel = self.query_one("#details-panel")
            details_panel.can_focus = False
            
            # Add initial content to details panel
            details_panel.write("📋 **Document Details**")
            details_panel.write("")
            details_panel.write("[dim]Select a document to view details[/dim]")
        except Exception as e:
            logger.error(f"Error setting up details panel: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        search_input = self.query_one("#search-input")
        search_input.can_focus = False
        tag_input = self.query_one("#tag-input")
        tag_input.can_focus = False
        
        # Hide inputs initially
        search_input.display = False
        tag_input.display = False
        
        # Debug: Check sidebar children and their computed styles
        try:
            sidebar = self.query_one("#sidebar", Vertical)
            logger.info(f"SIDEBAR CHILDREN COUNT: {len(sidebar.children)}")
            for i, child in enumerate(sidebar.children):
                logger.info(f"SIDEBAR CHILD {i}: {child.__class__.__name__} with id={child.id}")
                # Log computed styles
                logger.info(f"  - Size: {child.size}")
                logger.info(f"  - Styles.height: {child.styles.height}")
                logger.info(f"  - Styles.min_height: {child.styles.min_height}")
                logger.info(f"  - Styles.max_height: {child.styles.max_height}")
                logger.info(f"  - Styles.background: {child.styles.background}")
        except Exception as e:
            logger.error(f"ERROR CHECKING SIDEBAR: {e}")
        
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
                    ORDER BY id DESC
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
            # Format row data - ID, Tags, and Title
            title, was_truncated = truncate_emoji_safe(doc["title"], 74)
            if was_truncated:
                title += "..."
            
            # Get first 3 tags as emojis with spaces between, pad to 5 chars
            doc_tags = get_document_tags(doc["id"])
            tags_display = " ".join(doc_tags[:3]).ljust(8)  # Pad to exactly 8 chars
            
            table.add_row(
                str(doc["id"]),
                tags_display,
                "",  # Empty padding column
                title,
            )
            
        # Update status using our own status bar
        try:
            status_text = f"{len(self.filtered_docs)}/{len(self.documents)} docs"
            if self.mode == "NORMAL":
                status_text += " | e=edit | n=new | /=search | t=tag | x=execute | r=refresh | q=quit"
            elif self.mode == "SEARCH":
                status_text += " | Enter=apply | ESC=cancel"
            self.update_status(status_text)
        except Exception as e:
            logger.error(f"Status update failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
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
                # For new document mode, just cancel without saving
                if getattr(self, 'new_document_mode', False):
                    self.new_document_mode = False
                await self.exit_edit_mode()
                event.stop()
            elif self.mode == "SEARCH":
                self.exit_search_mode()
                event.stop()
            elif self.mode == "TAG":
                self.exit_tag_mode()
                event.stop()
            # Note: SELECTION mode escape is handled by SelectionTextArea itself
                
    async def enter_edit_mode(self) -> None:
        """Enter edit mode for the selected document."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is None:
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
            
        # Store original preview for restoration
        self.original_preview_content = full_doc["content"]
        self.edit_mode = True
        
        # Replace preview with edit area
        from textual.containers import Vertical, ScrollableContainer
        preview_container = self.query_one("#preview-container", Vertical)
        try:
            preview = self.query_one("#preview", ScrollableContainer)
            await preview.remove()
        except Exception as e:
            logger.error(f"Error removing preview for edit mode: {e}")
            # Try removing all children instead
            for child in list(preview_container.children):
                if child.id in ["preview", "preview-content"]:
                    await child.remove()
        
        # Create a vertical container for title input and content editor (same as new document mode)
        edit_container = Vertical(id="edit-container")
        
        # Mount the container first
        await preview_container.mount(edit_container)
        
        # Create title input with existing title
        from .inputs import TitleInput
        title_input = TitleInput(self, value=full_doc["title"], placeholder="Enter document title...", id="title-input")
        
        # Extract content without unicode box if present
        content = self._extract_content_without_title_box(full_doc["content"], full_doc["title"])
        
        # Create vim editor with the content (without the title box)
        from .vim_editor import VimEditor
        vim_editor = VimEditor(self, content=content, id="vim-editor-container")
        
        # Mount both components to the already-mounted container
        await edit_container.mount(title_input)
        await edit_container.mount(vim_editor)
        
        # Focus on title input first
        self.call_after_refresh(lambda: title_input.focus())
        
        # Update status
        self._update_vim_status("EDIT DOCUMENT | Tab=switch fields | Ctrl+S=save | ESC=cancel")
        
    def action_save_and_exit_edit(self) -> None:
        """Save document and exit edit mode (called by VimEditTextArea)."""
        logger.info("action_save_and_exit_edit called")
        try:
            # Use call_after_refresh to avoid timing issues
            self.call_after_refresh(self._async_save_and_exit_edit_mode)
        except Exception as e:
            logger.error(f"Error in action_save_and_exit_edit: {e}")
            # Fallback - try direct call
            try:
                import asyncio
                asyncio.create_task(self.save_and_exit_edit_mode())
            except:
                pass
            
    def _async_exit_edit_mode(self) -> None:
        """Async wrapper for exit_edit_mode."""
        logger.info("_async_exit_edit_mode called")
        import asyncio
        asyncio.create_task(self.exit_edit_mode())
        
    def _async_save_and_exit_edit_mode(self) -> None:
        """Async wrapper for save_and_exit_edit_mode."""
        logger.info("_async_save_and_exit_edit_mode called")
        import asyncio
        asyncio.create_task(self.save_and_exit_edit_mode())
        
    async def save_and_exit_edit_mode(self) -> None:
        """Save the document and exit edit mode."""
        if not self.edit_mode:
            return
            
        try:
            if getattr(self, 'new_document_mode', False):
                # Save new document
                try:
                    title_input = self.query_one("#title-input", Input)
                    vim_editor = self.query_one("#vim-editor-container", VimEditor)
                    
                    title = title_input.value.strip()
                    content = vim_editor.text_area.text
                    
                    if not title:
                        # Update status to show error
                        self._update_vim_status("ERROR: Title required | Enter title and press Ctrl+S")
                        return
                    
                    # Save the new document
                    from emdx.models.documents import save_document
                    from emdx.utils.git import get_git_project
                    
                    # Add unicode box to content when saving
                    formatted_content = self._format_content_with_title_box(title, content)
                    
                    project = get_git_project() or "default"
                    doc_id = save_document(title=title, content=formatted_content, project=project)
                    
                    logger.info(f"Created new document with ID: {doc_id}")
                    
                    # Clean up new document mode flag
                    self.new_document_mode = False
                    
                except Exception as e:
                    logger.error(f"Error saving new document: {e}")
                    self._update_vim_status(f"ERROR: {str(e)}")
                    return
            else:
                # Update existing document
                if self.editing_doc_id:
                    try:
                        title_input = self.query_one("#title-input", Input)
                        vim_editor = self.query_one("#vim-editor-container", VimEditor)
                        
                        title = title_input.value.strip()
                        content = vim_editor.text_area.text
                        
                        if not title:
                            # Update status to show error
                            self._update_vim_status("ERROR: Title required | Enter title and press Ctrl+S")
                            return
                        
                        # Add unicode box to content when saving
                        formatted_content = self._format_content_with_title_box(title, content)
                        
                        from emdx.models.documents import update_document
                        update_document(str(self.editing_doc_id), title=title, content=formatted_content)
                        
                        logger.info(f"Updated document ID: {self.editing_doc_id}")
                    except Exception as e:
                        logger.error(f"Error updating document: {e}")
                        self._update_vim_status(f"ERROR: {str(e)}")
                        return
            
            # Exit edit mode and reload documents
            await self.exit_edit_mode()
            await self.load_documents()
            
        except Exception as e:
            logger.error(f"Error in save_and_exit_edit_mode: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
    def _format_content_with_title_box(self, title: str, content: str) -> str:
        """Format content with title as markdown header."""
        # Simply use markdown header - Rich will render it with the unicode box
        formatted = f"# {title}\n\n{content}"
        return formatted
    
    def _extract_content_without_title_box(self, content: str, title: str) -> str:
        """Extract content without the title header or unicode box if present."""
        lines = content.split('\n')
        
        # Check for markdown header first
        if lines and lines[0].strip() == f"# {title}":
            # Skip the header line and optional blank line
            start_idx = 1
            if len(lines) > 1 and not lines[1].strip():
                start_idx = 2
            return '\n'.join(lines[start_idx:])
        
        # Check if content starts with a unicode box (various styles)
        if len(lines) >= 3:
            # Check for double-line box (╔═╗)
            if lines[0].startswith('╔') and lines[2].startswith('╚'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
            
            # Check for heavy-line box (┏━┓)
            elif lines[0].startswith('┏') and lines[2].startswith('┗'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
            
            # Check for single-line box (┌─┐)
            elif lines[0].startswith('┌') and lines[2].startswith('└'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
        
        # No header or box found, return original content
        return content
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status bar with vim mode info (called by VimEditTextArea)."""
        try:
            # Update vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            if message:
                vim_indicator.update(f"VIM: {message}")
                vim_indicator.add_class("active")
            else:
                vim_indicator.update("VIM: NORMAL | ESC=exit")
                vim_indicator.add_class("active")
                
            # Also update main status
            app = self.app
            if hasattr(app, 'update_status'):
                if message:
                    app.update_status(f"Edit Mode | {message}")
                else:
                    app.update_status("Edit Mode | ESC=exit | Ctrl+S=save")
        except:
            pass
            
    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (called by SelectionTextArea)."""
        if self.mode == "SELECTION":
            # Exit selection mode
            try:
                self.call_after_refresh(self._async_exit_selection_mode)
            except:
                pass
        
    def _async_exit_selection_mode(self) -> None:
        """Async wrapper for exit_selection_mode."""
        import asyncio
        asyncio.create_task(self.exit_selection_mode())
        
    async def exit_edit_mode(self) -> None:
        """Exit edit mode and restore preview."""
        if not self.edit_mode:
            return
            
        # Clear preview container completely
        preview_container = self.query_one("#preview-container", Vertical)
        
        # Remove all children
        for child in list(preview_container.children):
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
        # Clean up new document mode flag if it was set
        if hasattr(self, 'new_document_mode'):
            self.new_document_mode = False
        
        # Clear vim mode indicator
        try:
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.update("")
            vim_indicator.remove_class("active")
        except:
            pass
        
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
        
    async def enter_new_document_mode(self) -> None:
        """Enter mode to create a new document."""
        # Store that we're creating a new document
        self.editing_doc_id = None  # No existing document
        self.edit_mode = True
        self.new_document_mode = True
        
        # Replace preview with edit area for new document
        from textual.containers import Vertical, ScrollableContainer
        preview_container = self.query_one("#preview-container", Vertical)
        try:
            preview = self.query_one("#preview", ScrollableContainer)
            await preview.remove()
        except Exception as e:
            logger.error(f"Error removing preview for new document mode: {e}")
            # Try removing all children instead
            for child in list(preview_container.children):
                if child.id in ["preview", "preview-content"]:
                    await child.remove()
        
        # Create a vertical container for title input and content editor
        from textual.containers import Vertical
        edit_container = Vertical(id="edit-container")
        
        # Create title input
        from .inputs import TitleInput
        title_input = TitleInput(self, placeholder="Enter document title...", id="title-input")
        
        # Create vim editor with empty content
        vim_editor = VimEditor(self, content="", id="vim-editor-container")
        
        # Mount the container and its children
        await preview_container.mount(edit_container)
        await edit_container.mount(title_input)
        await edit_container.mount(vim_editor)
        
        # Vim editor will start in NORMAL mode by default
        
        # Focus on title input first - use call_after_refresh to ensure it's ready
        self.call_after_refresh(lambda: title_input.focus())
        
        # Update status
        self._update_vim_status("NEW DOCUMENT | Enter title | Tab=switch to content | Ctrl+S=save | ESC=cancel")
        
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
            
    async def action_edit_document(self) -> None:
        """Edit the current document."""
        await self.enter_edit_mode()
    
    async def action_refresh(self) -> None:
        """Refresh the document list."""
        await self.load_documents()
        
    def update_status(self, message: str) -> None:
        """Update the document browser status bar."""
        try:
            status = self.query_one("#browser-status", Static)
            status.update(message)
        except Exception:
            # Fallback to app status if our status bar doesn't exist
            app = self.app
            if hasattr(app, 'update_status'):
                app.update_status(message)
    
    def action_execute_document(self) -> None:
        """Execute the current document with context-aware behavior based on tags."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row >= len(self.filtered_docs):
            self.update_status("No document selected for execution")
            return
            
        doc = self.filtered_docs[table.cursor_row]
        doc_id = int(doc["id"])
        
        try:
            import time
            from pathlib import Path
            from emdx.commands.claude_execute import get_execution_context
            from emdx.models.tags import get_document_tags
            from emdx.models.executions import create_execution
            
            # Get document tags
            doc_tags = get_document_tags(str(doc_id))
            
            # Get execution context to show what will happen
            context = get_execution_context(doc_tags)
            self.update_status(f"Executing {context['type'].value}: {context['description']}")
            
            # Create logs directory
            log_dir = Path.home() / ".config/emdx/logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Create the execution record and get numeric ID
            timestamp = int(time.time())
            log_filename = f"claude-{doc_id}-{timestamp}.log"
            log_path = log_dir / log_filename
            
            exec_id = create_execution(
                doc_id=doc_id,
                doc_title=doc['title'],
                log_file=str(log_path)
            )
            
            # Now execute in background using the wrapper script
            import subprocess
            import sys
            
            # Find the wrapper script
            wrapper_path = Path(__file__).parent.parent / "utils" / "claude_wrapper.py"
            
            # Build the claude command using emdx CLI
            # Use the emdx command instead of calling module directly
            import shutil
            emdx_path = shutil.which("emdx")
            if not emdx_path:
                # Fallback to python module if emdx not in PATH
                emdx_path = sys.executable
                claude_cmd = [
                    emdx_path,
                    "-m", "emdx",
                    "claude", "execute",
                    str(doc_id),
                    "--background",
                    "--exec-id", str(exec_id),
                    "--log-file", str(log_path)
                ]
            else:
                claude_cmd = [
                    emdx_path,
                    "claude", "execute", 
                    str(doc_id),
                    "--background",
                    "--exec-id", str(exec_id),
                    "--log-file", str(log_path)
                ]
            
            # For background execution, don't use wrapper here
            # The execute command with --background already uses a wrapper internally
            # to monitor the actual Claude process. Double-wrapping causes the outer
            # wrapper to mark execution as complete when execute command exits.
            
            # Start the process directly without wrapper
            subprocess.Popen(
                claude_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Show success message
            self.update_status(f"🚀 Claude executing: {doc['title'][:25]}... → #{exec_id} (Press 'l' for logs)")
            
        except Exception as e:
            logger.error(f"Error executing document: {e}", exc_info=True)
            self.update_status(f"Error: {str(e)}")
        
    async def action_new_document(self) -> None:
        """Create a new document."""
        # Don't allow new document in log browser mode
        if getattr(self, 'mode', 'NORMAL') == "LOG_BROWSER":
            return
        await self.enter_new_document_mode()
        
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
        
    async def action_selection_mode(self) -> None:
        """Enter selection mode for document content."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.filtered_docs):
            return
            
        doc = self.filtered_docs[table.cursor_row]
        
        # Load full document for selection
        full_doc = get_document(str(doc["id"]))
        if not full_doc:
            return
            
        # Replace preview with selection text area
        preview_container = self.query_one("#preview-container", Vertical)
        try:
            preview = self.query_one("#preview", ScrollableContainer)
            await preview.remove()
        except Exception as e:
            logger.error(f"Error removing preview for selection mode: {e}")
            # Try removing all children instead
            for child in list(preview_container.children):
                if child.id in ["preview", "preview-content"]:
                    await child.remove()
        
        # Create selection text area with proper app instance (self implements TextAreaHost)
        from .text_areas import SelectionTextArea
        selection_area: SelectionTextArea = SelectionTextArea(
            self,
            full_doc["content"], 
            id="selection-area",
            read_only=True
        )
        await preview_container.mount(selection_area)
        selection_area.focus()
        
        # Update mode
        self.mode = "SELECTION"
        
        # Update status
        try:
            app = self.app
            if hasattr(app, 'update_status'):
                app.update_status("Selection Mode | ESC=exit | Enter=copy selection")
        except:
            pass
            
    async def exit_selection_mode(self) -> None:
        """Exit selection mode and restore preview."""
        if self.mode != "SELECTION":
            return
            
        # Clear preview container completely
        preview_container = self.query_one("#preview-container", Vertical)
        
        # Remove all children
        for child in list(preview_container.children):
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
        
        self.mode = "NORMAL"
        
        # Refresh current document preview
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
        
        # Update status
        try:
            app = self.app
            if hasattr(app, 'update_status'):
                status_text = f"{len(self.filtered_docs)}/{len(self.documents)} docs"
                status_text += " | e=edit | n=new | /=search | t=tag | x=execute | r=refresh | q=quit"
                app.update_status(status_text)
        except:
            pass
    
    async def on_data_table_row_highlighted(self, event) -> None:
        """Update preview and details panel when row is highlighted."""
        if self.edit_mode:
            return
            
        row_idx = event.cursor_row
        
        if row_idx >= len(self.filtered_docs):
            return
            
        doc = self.filtered_docs[row_idx]
        
        # Load full document for preview
        full_doc = get_document(str(doc["id"]))
            
        if full_doc and not self.edit_mode:
            # Update main preview
            try:
                preview_container = self.query_one("#preview", ScrollableContainer)
                preview = preview_container.query_one("#preview-content", RichLog)
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
            
            # Update details panel
            await self.update_details_panel(full_doc)
    
    async def update_details_panel(self, doc: dict) -> None:
        """Update the details panel with rich document information."""
        try:
            details_panel = self.query_one("#details-panel", RichLog)
            details_panel.clear()
            
            # Get tags for this document
            tags = get_document_tags(doc["id"])
            
            # Format details with emoji and rich formatting
            from rich.text import Text
            from rich.panel import Panel
            from rich.columns import Columns
            from datetime import datetime
            
            # Document metadata
            details = []
            
            # ID and basic info
            details.append(f"📄 **ID:** {doc['id']}")
            details.append(f"📂 **Project:** {doc.get('project', 'default')}")
            
            # Tags with emoji formatting
            if tags:
                tags_formatted = format_tags(tags)
                details.append(f"🏷️  **Tags:** {tags_formatted}")
            else:
                details.append("🏷️  **Tags:** [dim]None[/dim]")
            
            # Dates
            if doc.get('created_at'):
                created = doc['created_at']
                if isinstance(created, str):
                    created = created[:16]  # Truncate to YYYY-MM-DD HH:MM
                details.append(f"📅 **Created:** {created}")
            
            if doc.get('updated_at'):
                updated = doc['updated_at']
                if isinstance(updated, str):
                    updated = updated[:16]  # Truncate to YYYY-MM-DD HH:MM
                details.append(f"✏️  **Updated:** {updated}")
            
            if doc.get('accessed_at'):
                accessed = doc['accessed_at']
                if isinstance(accessed, str):
                    accessed = accessed[:16]  # Truncate to YYYY-MM-DD HH:MM
                details.append(f"👁️  **Accessed:** {accessed}")
            
            # Access count
            access_count = doc.get('access_count', 0)
            details.append(f"📊 **Views:** {access_count}")
            
            # Content stats
            content = doc.get('content', '')
            word_count = len(content.split()) if content else 0
            char_count = len(content) if content else 0
            line_count = content.count('\n') + 1 if content else 0
            
            details.append(f"📝 **Words:** {word_count} | **Chars:** {char_count} | **Lines:** {line_count}")
            
            # Write each detail on a separate line
            for detail in details:
                details_panel.write(detail)
                
        except Exception as e:
            logger.error(f"Error updating details panel: {e}")
            # Fallback - just show basic info
            try:
                details_panel = self.query_one("#details-panel", RichLog)
                details_panel.clear()
                details_panel.write(f"📄 Document {doc['id']}: {doc['title']}")
            except:
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
