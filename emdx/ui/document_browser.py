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
from textual.containers import Horizontal, ScrollableContainer, Vertical, Container
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, RichLog, Static
from textual.widget import Widget
from textual.binding import Binding
from datetime import datetime

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.ui.formatting import format_tags, truncate_emoji_safe
from emdx.utils.emoji_aliases import expand_aliases, EMOJI_ALIASES

from .document_viewer import FullScreenView
from .modals import DeleteConfirmScreen
from .text_areas import EditTextArea, SelectionTextArea, VimEditTextArea

logger = logging.getLogger(__name__)


class DetailsPanel(Static):
    """Document details panel with reactive updates"""
    
    DEFAULT_CSS = """
    DetailsPanel {
        height: 100%;
        width: 100%;
    }
    """
    
    current_doc = reactive(None)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update("[dim]Loading document details...[/dim]")
    
    def get_project_color(self, project):
        """Get consistent color for project"""
        colors = ['cyan', 'magenta', 'yellow', 'green', 'blue', 'red']
        if project:
            # Simple hash to get consistent color
            index = sum(ord(c) for c in project) % len(colors)
            return colors[index]
        return 'dim'
    
    def get_relative_time(self, dt):
        """Convert datetime to relative time string"""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        
        now = datetime.now()
        # Ensure both datetimes are naive (no timezone) for comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        delta = now - dt
        
        if delta.days == 0:
            if delta.seconds < 3600:
                mins = delta.seconds // 60
                return f"{mins} minutes ago" if mins > 1 else "just now"
            else:
                hours = delta.seconds // 3600
                return f"{hours} hours ago" if hours > 1 else "1 hour ago"
        elif delta.days == 1:
            return "yesterday"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        elif delta.days < 30:
            weeks = delta.days // 7
            return f"{weeks} weeks ago" if weeks > 1 else "1 week ago"
        else:
            return dt.strftime("%Y-%m-%d")
    
    def create_progress_bar(self, value, max_value, width=10):
        """Create a visual progress bar"""
        if max_value == 0:
            return "[dim]" + "░" * width + "[/dim]"
        filled = int((value / max_value) * width)
        empty = width - filled
        return f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim]"
    
    def get_tag_emoji(self, tag):
        """Get emoji for tag using emoji_aliases.py logic"""
        # Reverse lookup - find emoji for tag
        for emoji, aliases in EMOJI_ALIASES.items():
            if tag in aliases:
                return emoji
        return "🏷️"  # Default tag emoji
    
    def get_tag_color(self, tag):
        """Get color styling for tag type"""
        # Status tags
        if tag in ['active', 'rocket', 'current', 'working', 'inprogress']:
            return 'on green'
        elif tag in ['done', 'complete', 'finished', 'success', 'check']:
            return 'on blue'
        elif tag in ['blocked', 'stuck', 'waiting', 'construction', 'wip']:
            return 'on red'
        # Document type tags
        elif tag in ['gameplan', 'plan', 'strategy', 'target']:
            return 'on magenta'
        elif tag in ['analysis', 'investigate', 'research', 'explore']:
            return 'on cyan'
        elif tag in ['notes', 'note', 'memo', 'thoughts']:
            return 'on dim white'
        # Technical tags
        elif tag in ['bug', 'issue', 'problem', 'defect', 'error']:
            return 'on red'
        elif tag in ['feature', 'new', 'enhancement', 'sparkle', 'magic']:
            return 'on yellow'
        elif tag in ['refactor', 'improvement', 'tool', 'fix', 'maintenance']:
            return 'on blue'
        # Priority tags
        elif tag in ['urgent', 'critical', 'important', 'alarm', 'emergency']:
            return 'on bright_red'
        return ''  # No background for unknown tags
    
    def format_tag_badges(self, tags):
        """Format tags as colored badges with emojis"""
        badges = []
        for tag in tags:
            emoji = self.get_tag_emoji(tag)
            color = self.get_tag_color(tag)
            if color:
                badges.append(f"[{color}] {emoji} {tag} [/{color.replace('on ', '')}]")
            else:
                badges.append(f"{emoji} {tag}")
        return " ".join(badges)
    
    def watch_current_doc(self, doc):
        """React to document selection changes"""
        if doc:
            self.update_content(doc)
        else:
            self.update("[dim]No document selected[/dim]")
    
    def update_content(self, doc):
        """Update panel with rich formatted document information"""
        # Get tags for the document
        tags = get_document_tags(doc["id"])
        
        # Get full document for word count
        full_doc = get_document(str(doc["id"]))
        
        # Build sections
        sections = []
        
        # Header with emoji
        sections.append(f"[bold blue]📄 Document #{doc['id']}[/bold blue]")
        sections.append("")
        
        # Project with color
        project = doc["project"] if doc["project"] else 'default'
        project_color = self.get_project_color(project)
        sections.append(f"[bold]📁 Project:[/bold] [{project_color}]{project}[/{project_color}]")
        sections.append("")
        
        # Tags with emoji formatting and colored badges
        if tags:
            sections.append("[bold]🏷️  Tags:[/bold]")
            sections.append(self.format_tag_badges(tags))
            sections.append("")
        
        # Timeline section
        sections.append("[bold]📅 Timeline:[/bold]")
        created = doc["created_at"]
        if created:
            relative_time = self.get_relative_time(created)
            sections.append(f"Created: {relative_time}")
        
        # Access info with progress bar
        access_count = doc["access_count"] if doc["access_count"] else 0
        if access_count > 0:
            bar = self.create_progress_bar(min(access_count, 20), 20)
            sections.append(f"Views: {bar} {access_count}")
        else:
            sections.append("Views: [dim]Not viewed yet[/dim]")
        
        # Stats section with word count
        if full_doc and full_doc.get("content"):
            sections.append("")
            sections.append("[bold]📊 Stats:[/bold]")
            words = len(full_doc["content"].split())
            read_time = max(1, words // 200)  # Average 200 wpm
            sections.append(f"{words:,} words • {read_time} min read")
        
        # Update the widget
        self.update("\n".join(sections))


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


class DocumentBrowser(Widget):
    """Document browser widget that can host text areas."""
    
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("e", "edit_document", "Edit"),
        Binding("/", "search", "Search"),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags"),
        Binding("s", "selection_mode", "Select"),
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
        layout: vertical;
        height: 100%;
    }
    
    .table-area {
        height: 2fr;
        min-height: 15;
        overflow-y: auto;
    }
    
    .details-area {
        height: 1fr;
        min-height: 10;
        border-top: thick $primary;
        background: $surface;
        padding: 1;
        overflow-y: auto;
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
    }
    
    #preview {
        height: 1fr;
        border: solid $primary;
    }
    
    #preview-content {
        height: 1fr;
        padding: 1;
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
                yield DataTable(id="doc-table", classes="table-area")
                yield DetailsPanel(id="doc-details", classes="details-area")
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
        table.add_columns("ID", "Title")
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
        
        # Select first document if available
        if self.filtered_docs:
            details = self.query_one("#doc-details", DetailsPanel)
            details.current_doc = self.filtered_docs[0]
        
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
            # Format row data
            title = truncate_emoji_safe(doc["title"], 60)  # More space for titles now
            
            table.add_row(
                str(doc["id"]),
                title
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
            
        # Store original preview for restoration
        self.original_preview_content = full_doc["content"]
        
        # Replace preview with edit area
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
        
        # Create edit area with proper app instance (self implements TextAreaHost)
        edit_area: VimEditTextArea = VimEditTextArea(self, full_doc["content"], id="edit-area")
        await preview_container.mount(edit_area)
        edit_area.focus()
        
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
            # Update vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            if message:
                vim_indicator.update(f"VIM: {message}")
            else:
                vim_indicator.update("VIM: NORMAL | ESC=exit")
                
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
        if not table.cursor_row or table.cursor_row >= len(self.filtered_docs):
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
        
        # Remove all children except vim indicator
        for child in list(preview_container.children):
            if child.id not in ["vim-mode-indicator"]:
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
                status_text += " | e=edit | /=search | t=tag | q=quit"
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
        
        # Update details panel
        try:
            details = self.query_one("#doc-details", DetailsPanel)
            details.current_doc = doc
        except Exception as e:
            logger.error(f"Error updating details panel: {e}")
        
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