"""Activity item type hierarchy for the activity view.

This module provides typed classes for different activity stream items,
replacing the stringly-typed item_type field with proper polymorphism.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from emdx.ui.types import AgentExecutionDict


@dataclass
class ActivityItem(ABC):
    """Base class for all activity stream items."""

    item_id: int
    title: str
    timestamp: datetime
    depth: int = 0
    expanded: bool = False
    children: list["ActivityItem"] = field(default_factory=list)
    status: str = "completed"  # Default status for items that don't track status
    doc_id: int | None = None  # Document ID if this item has associated content
    cost: float = 0.0  # Cost in USD if tracked

    @property
    @abstractmethod
    def item_type(self) -> str:
        """String type for backwards compatibility during transition."""
        ...

    @property
    @abstractmethod
    def type_icon(self) -> str:
        """Icon representing the item type."""
        ...

    @property
    @abstractmethod
    def status_icon(self) -> str:
        """Icon representing the item status."""
        ...

    @abstractmethod
    def can_expand(self) -> bool:
        """Whether this item can be expanded to show children."""
        ...

    @abstractmethod
    async def load_children(self, doc_db: Any) -> list["ActivityItem"]:
        """Load child items from database."""
        ...

    @abstractmethod
    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Get content and header for preview pane.

        Returns:
            Tuple of (content_markdown, header_text)
        """
        ...


@dataclass
class DocumentItem(ActivityItem):
    """A standalone document in the activity stream."""

    doc_id: int = 0
    has_children: bool = False

    @property
    def item_type(self) -> str:
        return "document"

    @property
    def type_icon(self) -> str:
        return "📄"

    @property
    def status_icon(self) -> str:
        return "✅"

    def can_expand(self) -> bool:
        return self.has_children

    async def load_children(self, doc_db: Any) -> list["ActivityItem"]:
        """Load child documents."""
        children: list[ActivityItem] = []

        if not doc_db:
            return children

        child_docs = doc_db.get_children(self.doc_id)

        for child_doc in child_docs:
            relationship = child_doc.get("relationship", "")
            rel_icon = {
                "supersedes": "↑",
                "exploration": "◇",
                "variant": "≈",
            }.get(relationship, "")

            title = child_doc.get("title", "")
            if rel_icon:
                title = f"{rel_icon} {title}"

            grandchildren = doc_db.get_children(child_doc["id"])

            children.append(
                DocumentItem(
                    item_id=child_doc["id"],
                    title=title,
                    timestamp=self.timestamp,
                    doc_id=child_doc["id"],
                    has_children=len(grandchildren) > 0,
                    depth=self.depth + 1,
                )
            )

        return children

    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Get document content for preview."""
        if not doc_db:
            return "", "PREVIEW"

        doc = doc_db.get_document(self.doc_id)
        if doc:
            content = doc.get("content", "")
            title = doc.get("title", "Untitled")

            # Check if content already has title header
            content_stripped = content.lstrip()
            if not (content_stripped.startswith(f"# {title}") or content_stripped.startswith("# ")):
                content = f"# {title}\n\n{content}"

            return content, f"📄 #{self.doc_id}"

        return "", "PREVIEW"


@dataclass
class AgentExecutionItem(ActivityItem):
    """A standalone agent execution (from `emdx delegate` command)."""

    execution: AgentExecutionDict = field(default_factory=dict)  # type: ignore[assignment]
    status: str = "running"
    doc_id: int | None = None
    log_file: str = ""
    cli_tool: str = "claude"

    @property
    def item_type(self) -> str:
        return "agent_execution"

    @property
    def type_icon(self) -> str:
        return "🤖"

    @property
    def status_icon(self) -> str:
        icons = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        return icons.get(self.status, "⚪")

    def can_expand(self) -> bool:
        return False

    async def load_children(self, doc_db: Any) -> list["ActivityItem"]:
        """Agent executions don't have children."""
        return []

    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Show execution log content in preview."""
        from pathlib import Path

        # If we have an output doc, show it
        if self.doc_id and doc_db:
            doc = doc_db.get_document(self.doc_id)
            if doc:
                return doc.get("content", ""), f"{self.type_icon} #{self.doc_id}"

        # If execution has persisted output text, show as markdown
        output_text = self.execution.get("output_text") or ""
        if output_text:
            return output_text, f"{self.type_icon} Answer"

        # Fallback: show filtered log file
        if self.log_file:
            log_path = Path(self.log_file)
            if log_path.exists():
                try:
                    content = log_path.read_text()
                    lines = [
                        line
                        for line in content.split("\n")
                        if not line.startswith("__RAW_RESULT_JSON__:")
                    ]
                    if len(lines) > 100:
                        lines = lines[-100:]
                    content = "\n".join(lines)
                    return f"```\n{content}\n```", f"{self.type_icon} Log"
                except Exception:
                    pass

        return f"[italic]{self.title}[/italic]", "PREVIEW"
