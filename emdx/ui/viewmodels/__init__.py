"""
ViewModels for UI components (STUB MODULE).

This module was deleted in PR #300 but is still imported by document_browser.py.
These are stub classes that provide the interface without implementation.
The full presenter/viewmodel pattern was removed as dead code.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DocumentListItem:
    """ViewModel for a single document in the list (stub)."""

    id: int
    title: str
    tags: List[str]
    tags_display: str
    project: str
    access_count: int
    created_at: Optional[str] = None
    accessed_at: Optional[str] = None
    parent_id: Optional[int] = None
    has_children: bool = False
    depth: int = 0
    is_archived: bool = False
    relationship: Optional[str] = None


@dataclass
class DocumentDetailVM:
    """ViewModel for document detail view (stub)."""

    id: int
    title: str
    content: str
    project: str
    tags: List[str]
    tags_formatted: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    accessed_at: Optional[str] = None
    access_count: int = 0
    word_count: int = 0
    char_count: int = 0
    line_count: int = 0


@dataclass
class DocumentListVM:
    """ViewModel for the document list (stub)."""

    documents: List[DocumentListItem] = field(default_factory=list)
    filtered_documents: List[DocumentListItem] = field(default_factory=list)
    search_query: str = ""
    total_count: int = 0
    filtered_count: int = 0
    current_offset: int = 0
    has_more: bool = False
    status_text: str = ""


__all__ = [
    "DocumentListItem",
    "DocumentListVM",
    "DocumentDetailVM",
]
