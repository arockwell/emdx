"""
Browser State Management for EMDX.

This module extracts state management from the main browser to reduce complexity.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Any
from pathlib import Path


@dataclass
class DocumentSelection:
    """Track document selection state."""
    selected_ids: Set[int] = field(default_factory=set)
    last_selected_index: Optional[int] = None
    
    def toggle(self, doc_id: int, index: int):
        """Toggle selection of a document."""
        if doc_id in self.selected_ids:
            self.selected_ids.remove(doc_id)
        else:
            self.selected_ids.add(doc_id)
        self.last_selected_index = index
    
    def clear(self):
        """Clear all selections."""
        self.selected_ids.clear()
        self.last_selected_index = None
    
    def select_all(self, doc_ids: List[int]):
        """Select all documents."""
        self.selected_ids = set(doc_ids)
    
    @property
    def count(self) -> int:
        """Get number of selected documents."""
        return len(self.selected_ids)


@dataclass
class SearchState:
    """Track search state."""
    query: str = ""
    tag_filter: Optional[str] = None
    tag_filter_mode: str = "all"  # "all" or "any"
    results_count: int = 0
    
    def clear(self):
        """Clear search state."""
        self.query = ""
        self.tag_filter = None
        self.results_count = 0
    
    def is_active(self) -> bool:
        """Check if search is active."""
        return bool(self.query or self.tag_filter)


@dataclass
class EditState:
    """Track edit mode state."""
    editing_doc_id: Optional[int] = None
    original_content: Optional[str] = None
    cursor_position: tuple[int, int] = (0, 0)
    
    def start_edit(self, doc_id: int, content: str):
        """Start editing a document."""
        self.editing_doc_id = doc_id
        self.original_content = content
    
    def end_edit(self):
        """End editing."""
        self.editing_doc_id = None
        self.original_content = None
        self.cursor_position = (0, 0)
    
    def is_editing(self) -> bool:
        """Check if currently editing."""
        return self.editing_doc_id is not None


@dataclass
class GitState:
    """Track git browser state."""
    current_worktree_path: Optional[Path] = None
    worktree_index: int = 0
    selected_file_index: int = 0
    git_files: List[Dict[str, Any]] = field(default_factory=list)
    
    def clear(self):
        """Clear git state."""
        self.git_files.clear()
        self.selected_file_index = 0


@dataclass
class LogBrowserState:
    """Track log browser state."""
    executions: List[Any] = field(default_factory=list)
    current_execution_index: int = 0
    current_log_file: Optional[Path] = None
    monitoring_active: bool = False
    
    def clear(self):
        """Clear log browser state."""
        self.executions.clear()
        self.current_execution_index = 0
        self.current_log_file = None
        self.monitoring_active = False


class BrowserStateManager:
    """
    Centralized state management for the EMDX browser.
    
    This reduces the number of instance variables in the main browser
    and provides a cleaner interface for state management.
    """
    
    def __init__(self):
        # Document state
        self.documents: List[Dict[str, Any]] = []
        self.filtered_docs: List[Dict[str, Any]] = []
        self.current_doc_id: Optional[int] = None
        
        # Feature states
        self.selection = DocumentSelection()
        self.search = SearchState()
        self.edit = EditState()
        self.git = GitState()
        self.log = LogBrowserState()
        
        # UI state
        self.table_cursor_position: int = 0
        self.preview_scroll_position: int = 0
        self.status_message: str = ""
        
        # Tag state
        self.tag_action: str = ""  # "add" or "remove"
        self.tag_input: str = ""
        self.available_tags: List[str] = []
        self.current_tag_completion: int = 0
    
    def reset(self):
        """Reset all state to defaults."""
        self.documents.clear()
        self.filtered_docs.clear()
        self.current_doc_id = None
        
        self.selection.clear()
        self.search.clear()
        self.edit.end_edit()
        self.git.clear()
        self.log.clear()
        
        self.table_cursor_position = 0
        self.preview_scroll_position = 0
        self.status_message = ""
        
        self.tag_action = ""
        self.tag_input = ""
        self.available_tags.clear()
        self.current_tag_completion = 0
    
    def save_table_position(self, cursor_row: int):
        """Save current table position."""
        self.table_cursor_position = cursor_row
    
    def restore_table_position(self) -> int:
        """Restore table position."""
        return self.table_cursor_position
    
    def get_current_document(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected document."""
        if not self.current_doc_id:
            return None
        
        for doc in self.filtered_docs:
            if doc.get("id") == self.current_doc_id:
                return doc
        
        return None
    
    def update_filtered_docs(self, docs: List[Dict[str, Any]]):
        """Update filtered documents list."""
        self.filtered_docs = docs
        self.search.results_count = len(docs)
        
        # Update current doc if it's no longer in filtered list
        if self.current_doc_id:
            doc_ids = {doc["id"] for doc in docs}
            if self.current_doc_id not in doc_ids:
                self.current_doc_id = docs[0]["id"] if docs else None