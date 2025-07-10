#!/usr/bin/env python3
"""
True modal browser for emdx using Textual with mouse support.

This provides:
- NORMAL mode: j/k navigation, e/d/v trigger actions  
- SEARCH mode: all keys including e/d/v just type characters for search
- Full mouse support for clicking and scrolling
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Input, Label, Static, TextArea, RichLog, Button
from textual.containers import Horizontal, Vertical, Container, ScrollableContainer, Grid
from textual.binding import Binding
from textual.reactive import reactive
from textual import events
from textual.screen import Screen, ModalScreen
import subprocess
import sys
from datetime import datetime
from typing import Optional
import asyncio
from rich.markdown import Markdown
from rich.console import Console
import io

from emdx.database import db


class SearchInput(Input):
    """Custom search input that captures all keys in search mode."""
    pass


# TODO: Add modal dialog for delete confirmation


class DocumentBrowser(App):
    """Modal document browser with vim-style navigation."""
    
    CSS = """
    #sidebar {
        width: 50%;
        border-right: solid $primary;
    }
    
    #preview {
        width: 50%;
        padding: 1;
    }
    
    RichLog {
        padding: 0 1;
        background: $background;
    }
    
    DataTable {
        height: 100%;
    }
    
    #mode-indicator {
        background: $success;
        color: $background;
        padding: 0 2;
        dock: top;
        height: 1;
    }
    
    #mode-indicator.search-mode {
        background: $warning;
    }
    
    SearchInput {
        dock: top;
        margin: 0 1;
        display: none;
    }
    
    SearchInput.visible {
        display: block;
    }
    
    #status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("shift+g", "cursor_bottom", "Bottom", show=False),
        Binding("/", "search_mode", "Search", key_display="/"),
        Binding("e", "edit", "Edit", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("v", "view", "View", show=False),
        Binding("enter", "view", "View", show=False),
        Binding("ctrl+d", "preview_down", "Preview down", show=False),
        Binding("ctrl+u", "preview_up", "Preview up", show=False),
    ]
    
    mode = reactive("NORMAL")
    search_query = reactive("")
    
    def __init__(self):
        super().__init__()
        self.documents = []
        self.filtered_docs = []
        self.current_doc_id = None
        
    def compose(self) -> ComposeResult:
        """Create the UI structure."""
        yield Label("NORMAL", id="mode-indicator")
        yield SearchInput(placeholder="Type to search...", id="search-input")
        
        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with ScrollableContainer(id="preview"):
                yield RichLog(id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False)
        
        yield Label("", id="status")
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the app when mounted."""
        self.load_documents()
        self.setup_table()
        self.update_status()
        # Select first document if available
        if self.filtered_docs:
            self.on_row_selected()
        
    def load_documents(self):
        """Load documents from database."""
        try:
            db.ensure_schema()
            docs = db.list_documents(limit=1000)
            self.documents = docs
            self.filtered_docs = docs
        except Exception as e:
            self.exit(message=f"Error loading documents: {e}")
    
    def setup_table(self):
        """Setup the document table."""
        table = self.query_one("#doc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        
        # Add columns
        table.add_columns("ID", "Title", "Project", "Created", "Views")
        
        # Add rows
        for doc in self.filtered_docs:
            created = doc['created_at'].strftime('%Y-%m-%d')
            table.add_row(
                str(doc['id']),
                doc['title'][:40] + "..." if len(doc['title']) > 40 else doc['title'],
                doc['project'] or 'None',
                created,
                str(doc['access_count'])
            )
        
        # Focus the table
        table.focus()
    
    def on_row_selected(self):
        """Handle row selection to update preview."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            self.current_doc_id = doc['id']
            self.update_preview(doc['id'])
    
    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        """Handle row highlighting (cursor movement)."""
        if message.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[message.cursor_row]
            self.current_doc_id = doc['id']
            self.update_preview(doc['id'])
    
    def update_preview(self, doc_id: int):
        """Update the preview pane with document content."""
        try:
            doc = db.get_document(str(doc_id))
            if doc:
                preview_log = self.query_one("#preview-content", RichLog)
                preview_log.clear()
                
                # Format content with title and metadata
                created = doc['created_at'].strftime('%Y-%m-%d %H:%M')
                markdown_content = f"""# {doc['title']}

**Project:** {doc['project'] or 'None'}  
**Created:** {created}  
**Views:** {doc['access_count']}

---

{doc['content']}"""
                
                # Clear and render markdown using Rich
                preview_log.clear()
                md = Markdown(markdown_content, code_theme="monokai")
                preview_log.write(md)
                # Force immediate scroll to top
                preview_log.scroll_to(0, 0, animate=False)
        except Exception as e:
            preview_log = self.query_one("#preview-content", RichLog)
            preview_log.clear()
            preview_log.write(f"[red]Error loading preview: {e}[/red]")
    
    def update_status(self):
        """Update the status bar."""
        status = self.query_one("#status", Label)
        status.update(f"{len(self.filtered_docs)}/{len(self.documents)} documents")
    
    def watch_mode(self, old_mode: str, new_mode: str):
        """React to mode changes."""
        mode_label = self.query_one("#mode-indicator", Label)
        mode_label.update(new_mode)
        
        if new_mode == "SEARCH":
            mode_label.add_class("search-mode")
            search = self.query_one("#search-input", SearchInput)
            search.add_class("visible")
            search.focus()
        else:
            mode_label.remove_class("search-mode")
            search = self.query_one("#search-input", SearchInput)
            search.remove_class("visible")
            search.value = ""
            table = self.query_one("#doc-table", DataTable)
            table.focus()
    
    def action_search_mode(self):
        """Enter search mode."""
        self.mode = "SEARCH"
    
    def on_input_changed(self, event: Input.Changed):
        """Handle live search as user types."""
        if event.input.id == "search-input":
            self.search_query = event.value
            self.filter_documents(event.value)
    
    def on_input_submitted(self, event: Input.Submitted):
        """Handle search input submission."""
        if event.input.id == "search-input":
            self.mode = "NORMAL"
    
    def on_key(self, event: events.Key):
        """Handle key presses based on mode."""
        if self.mode == "SEARCH":
            if event.key == "escape":
                self.mode = "NORMAL"
                self.search_query = ""
                self.filter_documents("")
                event.prevent_default()
        elif self.mode == "NORMAL":
            # In normal mode, keys trigger actions
            if event.character and self.current_doc_id:
                if event.character == "e":
                    event.prevent_default()
                    event.stop()
                    self.action_edit()
                elif event.character == "d":
                    event.prevent_default()
                    event.stop()
                    self.action_delete()
                elif event.character == "v":
                    event.prevent_default()
                    event.stop()
                    self.action_view()
    
    def filter_documents(self, query: str):
        """Filter documents based on search query."""
        if not query:
            self.filtered_docs = self.documents
        else:
            query_lower = query.lower()
            self.filtered_docs = [
                doc for doc in self.documents
                if query_lower in doc['title'].lower() or
                   query_lower in (doc['project'] or '').lower()
            ]
        
        # Rebuild table
        table = self.query_one("#doc-table", DataTable)
        table.clear()
        
        for doc in self.filtered_docs:
            created = doc['created_at'].strftime('%Y-%m-%d')
            table.add_row(
                str(doc['id']),
                doc['title'][:40] + "..." if len(doc['title']) > 40 else doc['title'],
                doc['project'] or 'None',
                created,
                str(doc['access_count'])
            )
        
        self.update_status()
        
        # Re-highlight first row if we have documents
        if self.filtered_docs and table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()
    
    def action_cursor_down(self):
        """Move cursor down."""
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_down()
    
    def action_cursor_up(self):
        """Move cursor up."""
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_up()
    
    def action_cursor_top(self):
        """Move cursor to top."""
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()
    
    def action_cursor_bottom(self):
        """Move cursor to bottom."""
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            if table.row_count > 0:
                table.cursor_coordinate = (table.row_count - 1, 0)
                self.on_row_selected()
    
    def action_preview_down(self):
        """Scroll preview down."""
        preview = self.query_one("#preview", ScrollableContainer)
        preview.scroll_relative(y=5)
    
    def action_preview_up(self):
        """Scroll preview up."""
        preview = self.query_one("#preview", ScrollableContainer)
        preview.scroll_relative(y=-5)
    
    def action_edit(self):
        """Edit the current document.""" 
        if self.mode == "SEARCH":
            return  # Don't trigger in search mode
        if self.current_doc_id:
            # Simply exit - we'll handle the rest outside
            self.exit()
            subprocess.run([sys.executable, '-m', 'emdx.cli', 'edit', str(self.current_doc_id)])
    
    def action_delete(self):
        """Delete the current document."""
        if self.mode == "SEARCH":
            return  # Don't trigger in search mode
        if self.current_doc_id:
            # Exit and let the CLI handle confirmation
            self.exit()
            subprocess.run([sys.executable, '-m', 'emdx.cli', 'delete', str(self.current_doc_id)])
    
    def action_view(self):
        """View the current document."""
        if self.mode == "SEARCH":
            return  # Don't trigger in search mode
        if self.current_doc_id:
            # Don't exit - just update the preview to be full screen or show a message
            # For now, let's just show a message that they should use Enter for full view
            pass  # TODO: Implement full-screen view
    
    def action_quit(self):
        """Quit the application."""
        self.exit()


def run():
    """Run the textual browser."""
    try:
        # Check if we have documents
        db.ensure_schema()
        docs = db.list_documents(limit=1)
        if not docs:
            print("No documents found in knowledge base.")
            print("\nGet started with:")
            print("  emdx save <file>         - Save a markdown file")
            print("  emdx direct <title>      - Create a document directly") 
            print("  emdx note 'quick note'   - Save a quick note")
            return
        
        app = DocumentBrowser()
        app.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()