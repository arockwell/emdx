"""
Document Table Manager for EMDX Browser.

This module extracts all DataTable-related functionality from the main browser.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from textual.widgets import DataTable
from rich.text import Text

from emdx.ui.formatting import format_tags, truncate_emoji_safe

logger = logging.getLogger(__name__)


class DocumentTableManager:
    """
    Manages the document DataTable widget.
    
    This extracts all the table setup, population, and manipulation code
    from the main browser, significantly reducing its size.
    """
    
    def __init__(self, table: DataTable):
        self.table = table
        self.setup_table()
    
    def setup_table(self):
        """Initial table setup with columns and styling."""
        self.table.add_column("", width=3)  # Selection column
        self.table.add_column("ID", width=8)
        self.table.add_column("Title", width=50)
        self.table.add_column("Tags", width=25)
        self.table.add_column("Modified", width=16)
        self.table.cursor_type = "row"
        self.table.zebra_stripes = True
    
    def populate_table(self, documents: List[Dict[str, Any]], 
                      selected_ids: Optional[set] = None,
                      search_query: Optional[str] = None) -> int:
        """
        Populate the table with documents.
        
        Returns the number of documents added.
        """
        selected_ids = selected_ids or set()
        
        # Clear existing rows
        self.table.clear()
        
        # Store original indices for selection tracking
        row_count = 0
        
        for idx, doc in enumerate(documents):
            try:
                # Selection indicator
                selection_mark = "●" if doc["id"] in selected_ids else " "
                
                # Format the row data
                doc_id = str(doc["id"])
                title = self._format_title(doc.get("title", "Untitled"), search_query)
                tags = self._format_tags(doc.get("tags", []))
                modified = self._format_date(doc.get("updated_at"))
                
                # Add the row
                self.table.add_row(
                    selection_mark,
                    doc_id,
                    title,
                    tags,
                    modified,
                    key=str(doc["id"])
                )
                row_count += 1
                
            except Exception as e:
                logger.error(f"Error adding document {doc.get('id')} to table: {e}")
        
        return row_count
    
    def update_selection(self, doc_id: int, selected: bool):
        """Update selection indicator for a specific document."""
        try:
            row_key = str(doc_id)
            if self.table.is_valid_row_index(self._get_row_index_by_key(row_key)):
                # Update the selection column (column 0)
                self.table.update_cell(
                    row_key, 
                    column_key=self.table.columns[0].key,
                    value="●" if selected else " "
                )
        except Exception as e:
            logger.error(f"Error updating selection for doc {doc_id}: {e}")
    
    def get_current_doc_id(self) -> Optional[int]:
        """Get the document ID of the currently highlighted row."""
        try:
            cursor_row = self.table.cursor_coordinate.row
            if cursor_row >= 0:
                row_key = self.table.get_row_at(cursor_row)[0]
                return int(row_key)
        except Exception as e:
            logger.error(f"Error getting current doc ID: {e}")
        return None
    
    def restore_cursor_position(self, position: int):
        """Restore cursor to a specific row position."""
        try:
            max_row = len(self.table.rows) - 1
            safe_position = min(position, max_row)
            if safe_position >= 0:
                self.table.cursor_coordinate = (safe_position, 0)
        except Exception as e:
            logger.error(f"Error restoring cursor position: {e}")
    
    def get_cursor_position(self) -> int:
        """Get current cursor row position."""
        return self.table.cursor_coordinate.row
    
    def move_cursor(self, direction: str, amount: int = 1):
        """Move cursor up or down by the specified amount."""
        current_row = self.table.cursor_coordinate.row
        
        if direction == "up":
            new_row = max(0, current_row - amount)
        elif direction == "down":
            max_row = len(self.table.rows) - 1
            new_row = min(max_row, current_row + amount)
        elif direction == "top":
            new_row = 0
        elif direction == "bottom":
            new_row = len(self.table.rows) - 1
        else:
            return
        
        self.table.cursor_coordinate = (new_row, 0)
    
    def highlight_search_results(self, search_query: str):
        """Highlight search query in visible titles."""
        if not search_query:
            return
            
        # This would require access to the table's rendering system
        # For now, we format titles with highlighting during population
        pass
    
    def _format_title(self, title: str, search_query: Optional[str] = None) -> Text:
        """Format title with optional search highlighting."""
        # Truncate title if needed
        truncated = truncate_emoji_safe(title, 50)
        
        if search_query and search_query.lower() in title.lower():
            # Create Rich Text with highlighting
            text = Text(truncated)
            # Find all occurrences and highlight them
            query_lower = search_query.lower()
            title_lower = truncated.lower()
            start = 0
            while True:
                pos = title_lower.find(query_lower, start)
                if pos == -1:
                    break
                text.stylize("bold yellow", pos, pos + len(search_query))
                start = pos + 1
            return text
        
        return Text(truncated)
    
    def _format_tags(self, tags: List[str]) -> str:
        """Format tags for display."""
        return format_tags(tags) if tags else ""
    
    def _format_date(self, date_str: Optional[str]) -> str:
        """Format date for display."""
        if not date_str:
            return ""
            
        try:
            # Parse the date string
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Format as "YYYY-MM-DD HH:MM"
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return date_str[:16] if len(date_str) > 16 else date_str
    
    def _get_row_index_by_key(self, row_key: str) -> int:
        """Get row index by key."""
        for idx, row in enumerate(self.table.rows):
            if row.key == row_key:
                return idx
        return -1
    
    def clear(self):
        """Clear all rows from the table."""
        self.table.clear()
    
    def focus(self):
        """Focus the table widget."""
        self.table.focus()
    
    @property
    def row_count(self) -> int:
        """Get the number of rows in the table."""
        return len(self.table.rows)