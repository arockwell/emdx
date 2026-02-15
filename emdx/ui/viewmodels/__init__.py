"""
ViewModels for UI components (STUB MODULE).

This module was deleted in PR #300 but is still imported by document_browser.py.
These are stub classes that provide the interface without implementation.
The full presenter/viewmodel pattern was removed as dead code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DocumentListItem:
    """ViewModel for a single document in the list (stub)."""

    id: int
    title: str
    tags: list[str]
    tags_display: str
    project: str
    access_count: int
    created_at: datetime | None = None
    accessed_at: datetime | None = None
    parent_id: int | None = None
    has_children: bool = False
    depth: int = 0
    relationship: str | None = None

@dataclass
class DocumentDetailVM:
    """ViewModel for document detail view (stub)."""

    id: int
    title: str
    content: str
    project: str
    tags: list[str]
    tags_formatted: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    accessed_at: datetime | None = None
    access_count: int = 0
    word_count: int = 0
    char_count: int = 0
    line_count: int = 0

@dataclass
class DocumentListVM:
    """ViewModel for the document list (stub)."""

    documents: list[DocumentListItem] = field(default_factory=list)
    filtered_documents: list[DocumentListItem] = field(default_factory=list)
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
