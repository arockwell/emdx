"""Activity item types for the activity view.

Simple dataclasses for documents shown in the flat activity table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ActivityItem:
    """Base for all activity stream items."""

    item_id: int
    title: str
    timestamp: datetime
    status: str = "completed"
    doc_id: int | None = None
    cost: float = 0.0

    @property
    def item_type(self) -> str:
        raise NotImplementedError

    @property
    def type_icon(self) -> str:
        raise NotImplementedError

    @property
    def status_icon(self) -> str:
        raise NotImplementedError

    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Get content and header for preview pane.

        Returns:
            Tuple of (content_markdown, header_text)
        """
        return "", "PREVIEW"


@dataclass
class DocumentItem(ActivityItem):
    """A document in the activity stream."""

    doc_id: int = 0
    doc_type: str = "user"
    project: str = ""
    tags: list[str] | None = None
    access_count: int = 0
    word_count: int = 0
    updated_at: datetime | None = None
    accessed_at: datetime | None = None
    parent_id: int | None = None

    @property
    def item_type(self) -> str:
        return "document"

    @property
    def type_icon(self) -> str:
        if self.doc_type == "wiki":
            return "📚"
        return "📄"

    @property
    def status_icon(self) -> str:
        return "✅"

    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Get document content for preview."""
        if not doc_db:
            return "", "PREVIEW"

        doc = doc_db.get_document(self.doc_id)
        if doc:
            content = doc.get("content", "")
            title = doc.get("title", "Untitled")

            content_stripped = content.lstrip()
            if not (content_stripped.startswith(f"# {title}") or content_stripped.startswith("# ")):
                content = f"# {title}\n\n{content}"

            return content, f"📄 #{self.doc_id}"

        return "", "PREVIEW"
