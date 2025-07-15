#!/usr/bin/env python3
"""
Type definitions for browser widgets and common patterns.

This module provides comprehensive type hints for the browser refactoring,
ensuring type safety and better developer experience.
"""

from typing import Protocol, TypedDict, Literal, Union, Optional, Any, Callable
from pathlib import Path
from datetime import datetime
from textual.widgets import DataTable
from textual import events


# Document types
class DocumentDict(TypedDict):
    """Type definition for document data from database."""
    id: int
    title: str
    content: str
    project: str
    created_at: datetime
    updated_at: datetime
    accessed_at: datetime
    access_count: int
    deleted_at: Optional[datetime]
    is_deleted: int


class DocumentRow(TypedDict):
    """Type definition for document table row data."""
    id: int
    project: str
    title: str
    tags: str
    created: str


# Browser mode types
BrowserMode = Literal[
    "NORMAL",
    "SEARCH", 
    "TAG",
    "SELECTION",
    "EDIT",
    "GIT_DIFF_BROWSER",
    "FILE_BROWSER"
]

# Browser state types
class BrowserState(TypedDict, total=False):
    """Type definition for browser state that can be saved/restored."""
    mode: BrowserMode
    current_search: str
    cursor_position: tuple[int, int]
    selected_index: int


# Navigation protocols
class NavigationProvider(Protocol):
    """Protocol for widgets that provide navigation functionality."""
    
    def get_primary_table(self) -> DataTable:
        """Return the primary DataTable widget for navigation."""
        ...
    
    def action_cursor_down(self) -> None:
        """Move cursor down."""
        ...
    
    def action_cursor_up(self) -> None:
        """Move cursor up."""
        ...
    
    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        ...
    
    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        ...


class SelectionProvider(Protocol):
    """Protocol for widgets that provide selection mode functionality."""
    
    selection_mode: bool
    
    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode."""
        ...


class EditProvider(Protocol):
    """Protocol for widgets that provide edit mode functionality."""
    
    edit_mode: bool
    
    def action_edit_document(self) -> None:
        """Enter edit mode."""
        ...
    
    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode."""
        ...


class StatefulBrowser(Protocol):
    """Protocol for browsers that can save/restore state."""
    
    def save_state(self) -> BrowserState:
        """Save current browser state."""
        ...
    
    def restore_state(self, state: BrowserState) -> None:
        """Restore browser state."""
        ...


# Event types for better type safety
class KeyEventHandler(Protocol):
    """Protocol for key event handlers."""
    
    def __call__(self, event: events.Key) -> None:
        """Handle key event."""
        ...


class DocumentSelectedEvent(Protocol):
    """Protocol for document selection events."""
    
    document_id: int
    document: DocumentDict


# File browser types
class FileInfo(TypedDict):
    """Type definition for file information."""
    path: Path
    name: str
    size: int
    modified: datetime
    is_directory: bool
    is_hidden: bool


# Git browser types
GitFileStatus = Literal["modified", "added", "deleted", "renamed", "untracked", "staged"]

class GitFileInfo(TypedDict):
    """Type definition for git file information."""
    path: Path
    status: GitFileStatus
    staged: bool
    diff_lines: int


# Status update callback type
StatusUpdateCallback = Callable[[str], None]

# Common browser widget interface
class BrowserWidget(NavigationProvider, StatefulBrowser, Protocol):
    """
    Complete protocol for browser widgets.
    
    This combines all the common functionality that browser widgets should provide.
    """
    
    mode: BrowserMode
    
    def get_primary_table(self) -> DataTable:
        """Return the primary table for navigation."""
        ...
    
    def save_state(self) -> BrowserState:
        """Save current state."""
        ...
    
    def restore_state(self, state: BrowserState) -> None:
        """Restore state."""
        ...
    
    async def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        ...


# Type aliases for common patterns
KeyHandler = Callable[[str], bool]
MountCallback = Callable[[], None]
DocumentFilter = Callable[[DocumentDict], bool]