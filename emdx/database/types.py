"""TypedDict definitions for the database layer."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class DocumentRow(TypedDict):
    """Full document row from the documents table.

    Datetime fields are parsed from SQLite strings to datetime objects
    by ``_parse_doc_datetimes`` before being returned to callers.
    """

    id: int
    title: str
    content: str
    project: str | None
    created_at: datetime | None
    updated_at: datetime | None
    accessed_at: datetime | None
    access_count: int
    deleted_at: datetime | None
    is_deleted: int
    parent_id: int | None
    relationship: str | None
    archived_at: datetime | None
    stage: str | None


class DocumentListItem(TypedDict):
    """Document item returned by list_documents."""

    id: int
    title: str
    project: str | None
    created_at: datetime | None
    access_count: int
    parent_id: int | None
    relationship: str | None
    archived_at: datetime | None
    accessed_at: datetime | None


class RecentDocumentItem(TypedDict):
    """Document item returned by get_recent_documents."""

    id: int
    title: str
    project: str | None
    accessed_at: datetime | None
    access_count: int


class DeletedDocumentItem(TypedDict):
    """Document item returned by list_deleted_documents."""

    id: int
    title: str
    project: str | None
    deleted_at: datetime | None
    access_count: int


class ChildDocumentItem(TypedDict):
    """Document item returned by get_children."""

    id: int
    title: str
    project: str | None
    created_at: datetime | None
    parent_id: int | None
    relationship: str | None
    archived_at: datetime | None


class SupersedeCandidate(TypedDict):
    """Candidate document for supersede matching."""

    id: int
    title: str
    content: str
    project: str | None
    created_at: datetime | None
    parent_id: int | None


class SearchResult(TypedDict):
    """Search result from FTS5 queries."""

    id: int
    title: str
    project: str | None
    created_at: datetime | None
    updated_at: datetime | None
    snippet: str | None
    rank: float


class MostViewedDoc(TypedDict):
    """Most viewed document summary."""

    id: int
    title: str
    access_count: int


class DatabaseStats(TypedDict, total=False):
    """Statistics returned by get_stats."""

    total_documents: int
    total_projects: int
    total_views: int
    avg_views: float
    newest_doc: str | None
    last_accessed: str | None
    table_size: str
    most_viewed: MostViewedDoc
