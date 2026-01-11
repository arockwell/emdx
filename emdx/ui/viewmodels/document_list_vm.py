"""
ViewModels for document list and detail views.

These are lightweight data transfer objects that contain all the data
needed to render the UI, with display formatting already applied.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DocumentListItem:
    """ViewModel for a single document in the list."""

    id: int
    title: str
    tags: List[str]
    tags_display: str  # Pre-formatted for display (e.g., "🎯 🚀 📝")
    project: str
    access_count: int
    created_at: Optional[str] = None
    accessed_at: Optional[str] = None


@dataclass
class DocumentDetailVM:
    """ViewModel for document detail view."""

    id: int
    title: str
    content: str
    project: str
    tags: List[str]
    tags_formatted: str  # Pre-formatted tags for display
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    accessed_at: Optional[str] = None
    access_count: int = 0
    word_count: int = 0
    char_count: int = 0
    line_count: int = 0


@dataclass
class DocumentListVM:
    """ViewModel for the document list."""

    documents: List[DocumentListItem] = field(default_factory=list)
    filtered_documents: List[DocumentListItem] = field(default_factory=list)
    search_query: str = ""
    total_count: int = 0
    filtered_count: int = 0
    current_offset: int = 0
    has_more: bool = False
    status_text: str = ""
