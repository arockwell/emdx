#!/usr/bin/env python3
"""Essential type definitions for browser widgets."""

from typing import TypedDict, Literal, Optional, Tuple
from datetime import datetime


# Document types
class DocumentDict(TypedDict):
    """Document data from database."""
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
    """Document table row data."""
    id: int
    project: str
    title: str
    tags: str
    created: str


# Browser modes
BrowserMode = Literal["NORMAL", "SEARCH", "TAG", "SELECTION", "EDIT", "GIT_DIFF_BROWSER", "FILE_BROWSER"]


# Browser state
class BrowserState(TypedDict, total=False):
    """Browser state for save/restore."""
    mode: BrowserMode
    cursor_position: Optional[Tuple[int, int]]
    current_search: Optional[str]


# Git file info
class GitFileInfo(TypedDict):
    """Git file information."""
    path: str
    status: str
    lines_added: int
    lines_removed: int