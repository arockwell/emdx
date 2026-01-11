#!/usr/bin/env python3
"""
Document selection stage for agent execution overlay.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, ListView, ListItem, Label
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from ...database.documents import get_recent_documents, search_documents
from .base import OverlayStage

logger = get_logger(__name__)


def format_document_display(doc: Dict[str, Any]) -> str:
    """Format document for display in ListView."""
    # Format the accessed time
    accessed_str = "Never"
    if doc.get('accessed_at'):
        if isinstance(doc['accessed_at'], datetime):
            accessed_str = doc['accessed_at'].strftime('%Y-%m-%d %H:%M')
        else:
            accessed_str = str(doc['accessed_at'])[:16]
    
    # Format project display
    project_str = doc.get('project', 'Default')
    if len(project_str) > 15:
        project_str = project_str[:12] + "..."
    
    title = doc.get('title', 'Untitled')
    # Truncate title if needed
    if len(title) > 50:
        title = title[:47] + "..."
    
    return f"[{doc['id']:3}] {title:<50} [{project_str:<15}] ({accessed_str})"


class DocumentSelectionStage(OverlayStage):
    """Document selection stage with recent documents and search."""
    
    BINDINGS = [
        Binding("enter", "select_document", "Select Document"),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear Search"),
    ]
    
    DEFAULT_CSS = """
    DocumentSelectionStage {
        height: 1fr;
        layout: vertical;
    }
    
    #doc-search-input {
        height: 3;
        margin: 0 0 1 0;
        border: solid $primary;
    }
    
    #doc-list-view {
        height: 1fr;
        border: solid $primary;
    }
    
    #doc-help {
        height: 2;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }
    
    .doc-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 1 1;
    }
    """
    
    class DocumentSelected(Message):
        """Message sent when a document is selected."""
        def __init__(self, document_id: int, document_data: Dict[str, Any]) -> None:
            self.document_id = document_id
            self.document_data = document_data
            super().__init__()
    
    def __init__(self, host, **kwargs):
        super().__init__(host, "document", **kwargs)
        self.documents: List[Dict[str, Any]] = []
        self.filtered_documents: List[Dict[str, Any]] = []
        self.selected_document: Optional[Dict[str, Any]] = None
        self.search_query = ""
    
    def compose(self) -> ComposeResult:
        """Create the document selection UI."""
        yield Static("[bold yellow]📄 Document Selection[/bold yellow]", classes="doc-header")
        yield Input(placeholder="Type to search documents... (Press / to focus)", id="doc-search-input")
        yield ListView(id="doc-list-view")
        yield Static("↑↓/jk: Navigate | Enter: Select | Tab: Next Stage | /: Search", id="doc-help")
    
    async def on_mount(self) -> None:
        """Load stage when mounted."""
        await super().on_mount()
    
    async def load_stage_data(self) -> None:
        """Load recent documents data."""
        try:
            logger.info("Loading recent documents")
            self.documents = get_recent_documents(limit=20)
            self.filtered_documents = self.documents.copy()
            logger.info(f"Loaded {len(self.documents)} documents")
            
            # Ensure the UI is fully mounted before updating the list
            # Small delay to allow ListView to be properly initialized
            await asyncio.sleep(0.1)
            await self.update_document_list()
        except Exception as e:
            logger.error(f"Failed to load documents: {e}")
            await self.show_error(f"Failed to load documents: {e}")
    
    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the search input."""
        search_input = self.query_one("#doc-search-input", Input)
        search_input.focus()
    
    def validate_selection(self) -> bool:
        """Check if a document is selected."""
        return self.selected_document is not None
    
    def get_selection_data(self) -> Dict[str, Any]:
        """Return selected document data."""
        if self.selected_document:
            return {
                "document_id": self.selected_document["id"],
                "document_title": self.selected_document.get("title", "Untitled"),
                "document_project": self.selected_document.get("project", "Default")
            }
        return {}
    
    async def update_document_list(self) -> None:
        """Update the document list display."""
        try:
            # Check if the ListView exists and is properly mounted
            list_view_query = self.query("#doc-list-view")
            if not list_view_query:
                logger.warning("ListView not found, waiting for UI to be ready")
                await asyncio.sleep(0.2)
                
            list_view = self.query_one("#doc-list-view", ListView)
            
            # Clear existing content
            list_view.clear()
            
            if not self.filtered_documents:
                if self.search_query:
                    list_view.append(ListItem(Static(f"No documents found for '{self.search_query}'")))
                else:
                    list_view.append(ListItem(Static("No documents available")))
                return
            
            # Add document items
            for doc in self.filtered_documents:
                display_text = format_document_display(doc)
                list_view.append(ListItem(Static(display_text)))
                
        except Exception as e:
            logger.error(f"Failed to update document list: {e}")
            # Fallback: try to show error without ListView if it's not available
            try:
                await self.show_error(f"UI Error: {e}")
            except Exception:
                logger.error(f"Could not show error in UI: {e}")
    
    async def show_error(self, message: str) -> None:
        """Show error message."""
        try:
            list_view = self.query_one("#doc-list-view", ListView)
            list_view.clear()
            list_view.append(ListItem(Static(f"[red]Error: {message}[/red]")))
        except Exception as e:
            logger.error(f"Could not show error in ListView: {e}")
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search input - select first filtered document."""
        if event.input.id == "doc-search-input" and self.filtered_documents:
            # Get the currently highlighted item from ListView
            try:
                list_view = self.query_one("#doc-list-view", ListView)
                selected_index = list_view.index if list_view.index is not None else 0

                if 0 <= selected_index < len(self.filtered_documents):
                    document = self.filtered_documents[selected_index]
                    self.selected_document = document

                    logger.info(f"Document selected via search input Enter: {document['id']}")

                    # Update host selection
                    self.host.set_document_selection(document["id"])

                    # Update selection data and mark as valid
                    self.update_selection(self.get_selection_data())
                    self._is_valid = True

                    # Post selection message
                    self.post_message(self.DocumentSelected(document["id"], document))

                    # Request navigation to next stage
                    self.request_navigation("next")
            except Exception as e:
                logger.error(f"Error selecting document from search: {e}")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle ListView selection (when user presses Enter on an item)."""
        if not self.filtered_documents:
            return

        # Get the selected index from the event
        selected_index = event.list_view.index

        if selected_index is not None and 0 <= selected_index < len(self.filtered_documents):
            document = self.filtered_documents[selected_index]
            self.selected_document = document

            logger.info(f"Document selected via ListView: {document['id']} - {document.get('title', 'Untitled')}")

            # Update host selection
            self.host.set_document_selection(document["id"])

            # Update selection data and mark as valid
            self.update_selection(self.get_selection_data())
            self._is_valid = True
            
            # Post selection message
            self.post_message(self.DocumentSelected(document["id"], document))
            
            # Request navigation to next stage
            self.request_navigation("next")
    
    def action_select_document(self) -> None:
        """Select the current document (backup method for Enter key)."""
        logger.info("action_select_document called")
        if not self.filtered_documents:
            logger.warning("No filtered documents available")
            return
        
        # Get currently highlighted item from ListView
        try:
            list_view = self.query_one("#doc-list-view", ListView)
            selected_index = list_view.index
            logger.info(f"ListView index: {selected_index}, filtered_docs count: {len(self.filtered_documents)}")
            
            if selected_index is not None and 0 <= selected_index < len(self.filtered_documents):
                document = self.filtered_documents[selected_index]
                self.selected_document = document
                
                logger.info(f"Document selected via action: {document['id']} - {document.get('title', 'Untitled')}")
                
                # Update host selection
                self.host.set_document_selection(document["id"])
                
                # Update selection data and mark as valid
                self.update_selection(self.get_selection_data())
                self._is_valid = True
                
                # Post selection message
                self.post_message(self.DocumentSelected(document["id"], document))
                
                # Request navigation to next stage
                self.request_navigation("next")
            else:
                logger.warning(f"Invalid selection index: {selected_index}")
        except Exception as e:
            logger.error(f"Error in action_select_document: {e}", exc_info=True)
    
    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        # Validate we have a selection before advancing
        if not self.validate_selection():
            logger.warning("Cannot advance: no document selected")
            return
        self.request_navigation("next")
    
    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        self.request_navigation("prev")
    
    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#doc-search-input", Input)
        search_input.focus()
    
    def action_clear_search(self) -> None:
        """Clear search if there's a query, otherwise cancel the overlay."""
        # If there's a search query, clear it
        if self.search_query:
            search_input = self.query_one("#doc-search-input", Input)
            search_input.value = ""
            self.search_query = ""
            self.filtered_documents = self.documents.copy()
            self.call_after_refresh(self.update_document_list)
        else:
            # No search query - cancel the overlay
            # Try to call parent's cancel action
            try:
                if hasattr(self.host, 'action_cancel'):
                    self.host.action_cancel()
            except Exception as e:
                logger.error(f"Failed to cancel overlay: {e}")
    
    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "doc-search-input":
            self.search_query = event.value.strip()
            await self.perform_search()
    
    async def perform_search(self) -> None:
        """Perform document search."""
        try:
            if not self.search_query:
                # Show all documents if search is empty
                self.filtered_documents = self.documents.copy()
            else:
                logger.info(f"Searching documents for: {self.search_query}")
                # Use EMDX search functionality
                search_results = search_documents(
                    query=self.search_query,
                    limit=50,
                    project=None  # Search all projects
                )
                self.filtered_documents = search_results
                logger.info(f"Found {len(search_results)} documents")
            
            await self.update_document_list()
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            await self.show_error(f"Search failed: {e}")
    
    def get_help_text(self) -> str:
        """Get help text for this stage."""
        return "Select a document to execute the agent on. Use ↑↓ or j/k to navigate, Enter to select, / to search."