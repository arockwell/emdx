"""Activity item type hierarchy for the activity view.

This module provides typed classes for different activity stream items,
replacing the stringly-typed item_type field with proper polymorphism.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class ActivityItem(ABC):
    """Base class for all activity stream items."""

    item_id: int
    title: str
    timestamp: datetime
    depth: int = 0
    expanded: bool = False
    children: List["ActivityItem"] = field(default_factory=list)
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
    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Load child items from database."""
        ...

    @abstractmethod
    async def get_preview_content(self, doc_db) -> tuple[str, str]:
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

    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Load child documents."""
        children = []

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

    async def get_preview_content(self, doc_db) -> tuple[str, str]:
        """Get document content for preview."""
        if not doc_db:
            return "", "PREVIEW"

        doc = doc_db.get_document(self.doc_id)
        if doc:
            content = doc.get("content", "")
            title = doc.get("title", "Untitled")

            # Check if content already has title header
            content_stripped = content.lstrip()
            if not (
                content_stripped.startswith(f"# {title}")
                or content_stripped.startswith("# ")
            ):
                content = f"# {title}\n\n{content}"

            return content, f"📄 #{self.doc_id}"

        return "", "PREVIEW"


@dataclass
class CascadeRunItem(ActivityItem):
    """A cascade run in the activity stream.

    Represents an end-to-end cascade execution (idea → prompt → analyzed → planned → done)
    with all associated stage transitions shown as children.
    """

    cascade_run: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    pipeline_name: str = "default"
    current_stage: str = ""
    execution_count: int = 0

    @property
    def item_type(self) -> str:
        return "cascade_run"

    @property
    def type_icon(self) -> str:
        return "🌊"  # Cascade wave emoji

    @property
    def status_icon(self) -> str:
        icons = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "⏹️",
        }
        return icons.get(self.status, "⚪")

    def can_expand(self) -> bool:
        return self.execution_count > 0 or len(self.children) > 0

    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Load cascade stage executions as children."""
        from emdx.services.cascade_service import get_cascade_run_executions

        children = []

        if not self.cascade_run:
            return children

        run_id = self.cascade_run.get("id")
        if not run_id:
            return children

        try:
            executions = get_cascade_run_executions(run_id)

            for exec_data in executions:
                exec_status = exec_data.get("status", "pending")
                doc_stage = exec_data.get("doc_stage", "")

                # Build title showing stage transition
                title = exec_data.get("doc_title", "Stage execution")
                if doc_stage:
                    title = f"{doc_stage}: {title}"

                children.append(
                    CascadeStageItem(
                        item_id=exec_data.get("id", 0),
                        title=title,
                        timestamp=self.timestamp,
                        doc_id=exec_data.get("doc_id"),
                        status=exec_status,
                        stage=doc_stage,
                        depth=self.depth + 1,
                    )
                )

        except Exception:
            pass

        return children

    async def get_preview_content(self, doc_db) -> tuple[str, str]:
        """Get cascade run preview - status and stage info."""
        run = self.cascade_run

        content_parts = [f"# Cascade Run #{run.get('id', '?')}\n"]
        content_parts.append(f"\n**Pipeline:** {run.get('pipeline_display_name', run.get('pipeline_name', 'default'))}")
        content_parts.append(f"\n**Status:** {self.status}")

        if self.current_stage:
            content_parts.append(f"\n**Current Stage:** {self.current_stage}")

        if run.get("initial_doc_title"):
            content_parts.append(f"\n**Initial Document:** {run['initial_doc_title']}")

        if run.get("started_at"):
            content_parts.append(f"\n**Started:** {run['started_at']}")

        if run.get("completed_at"):
            content_parts.append(f"\n**Completed:** {run['completed_at']}")

        if run.get("error_message"):
            content_parts.append(f"\n\n**Error:** {run['error_message']}")

        content = "".join(content_parts)
        return content, f"🌊 Cascade #{run.get('id', '?')}"


@dataclass
class CascadeStageItem(ActivityItem):
    """A single stage execution within a cascade run."""

    doc_id: int | None = None
    status: str = "pending"
    stage: str = ""

    @property
    def item_type(self) -> str:
        return "cascade_stage"

    @property
    def type_icon(self) -> str:
        # Stage-specific emojis
        stage_icons = {
            "idea": "💡",
            "prompt": "📝",
            "analyzed": "🔍",
            "reviewed": "🔬",
            "planned": "📋",
            "done": "✅",
        }
        return stage_icons.get(self.stage, "⚙️")

    @property
    def status_icon(self) -> str:
        icons = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "pending": "⏳",
        }
        return icons.get(self.status, "⚪")

    def can_expand(self) -> bool:
        return False

    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Stage items don't have children."""
        return []

    async def get_preview_content(self, doc_db) -> tuple[str, str]:
        """Get stage execution output."""
        if self.doc_id and doc_db:
            doc = doc_db.get_document(self.doc_id)
            if doc:
                return doc.get("content", ""), f"{self.type_icon} #{self.doc_id}"

        return f"[italic]{self.title}[/italic]", "PREVIEW"


@dataclass
class GroupItem(ActivityItem):
    """A document group (batch, round, initiative) in the activity stream."""

    group: Dict[str, Any] = field(default_factory=dict)
    doc_count: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    child_group_count: int = 0

    @property
    def item_type(self) -> str:
        return "group"

    @property
    def type_icon(self) -> str:
        icons = {
            "initiative": "📋",
            "round": "🔄",
            "batch": "📦",
            "session": "💾",
            "custom": "🏷️",
        }
        return icons.get(self.group.get("group_type", ""), "📁")

    @property
    def status_icon(self) -> str:
        return "📊"

    def can_expand(self) -> bool:
        return self.doc_count > 0 or self.child_group_count > 0 or len(self.children) > 0

    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Load child groups and member documents."""
        from emdx.services import group_service as groups

        children = []

        if not self.group:
            return children

        group_id = self.group.get("id")
        if not group_id:
            return children

        # Load child groups first
        child_groups = groups.get_child_groups(group_id)
        for cg in child_groups:
            if not cg.get("is_active", True):
                continue

            # Count grandchildren for expansion indicator
            grandchildren = groups.get_child_groups(cg["id"])

            children.append(
                GroupItem(
                    item_id=cg["id"],
                    title=cg["name"],
                    timestamp=self.timestamp,
                    group=cg,
                    doc_count=cg.get("doc_count", 0),
                    total_cost=cg.get("total_cost_usd", 0),
                    total_tokens=cg.get("total_tokens", 0),
                    child_group_count=len(grandchildren),
                    depth=self.depth + 1,
                )
            )

        # Load member documents
        members = groups.get_group_members(group_id)
        for m in members:
            role_icons = {
                "primary": "★",
                "synthesis": "📝",
                "exploration": "◇",
                "variant": "≈",
            }
            role_icon = role_icons.get(m.get("role", ""), "")
            title = m.get("title", "Untitled")
            if role_icon:
                title = f"{role_icon} {title}"

            children.append(
                DocumentItem(
                    item_id=m["id"],
                    title=title,
                    timestamp=self.timestamp,
                    doc_id=m["id"],
                    has_children=False,
                    depth=self.depth + 1,
                )
            )

        return children

    async def get_preview_content(self, doc_db) -> tuple[str, str]:
        """Show group summary in preview."""
        from emdx.services import group_service as groups

        if not self.group:
            return "", "PREVIEW"

        content_parts = [f"# {self.group.get('name', 'Untitled Group')}\n"]

        if self.group.get("description"):
            content_parts.append(f"\n{self.group['description']}\n")

        content_parts.append(f"\n**Type:** {self.group.get('group_type', 'batch')}")
        content_parts.append(f"\n**Documents:** {self.doc_count}")

        if self.total_tokens:
            content_parts.append(f"\n**Total tokens:** {self.total_tokens:,}")
        if self.total_cost:
            content_parts.append(f"\n**Total cost:** ${self.total_cost:.4f}")

        # Show member list
        group_id = self.group.get("id")
        if group_id:
            members = groups.get_group_members(group_id)
            if members:
                content_parts.append("\n\n## Documents\n")
                for m in members[:10]:
                    role = m.get("role", "member")
                    content_parts.append(f"- #{m['id']} {m['title'][:40]} ({role})\n")
                if len(members) > 10:
                    content_parts.append(f"\n*... and {len(members) - 10} more*\n")

        content = "".join(content_parts)
        return content, f"{self.type_icon} Group #{self.group.get('id', '?')}"


@dataclass
class AgentExecutionItem(ActivityItem):
    """A standalone agent execution (from `emdx delegate` command).

    These are direct CLI delegate runs not part of any workflow or cascade.
    """

    execution: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    doc_id: int | None = None
    log_file: str = ""
    cli_tool: str = "claude"

    @property
    def item_type(self) -> str:
        return "agent_execution"

    @property
    def type_icon(self) -> str:
        # Show different icon based on CLI tool
        if self.cli_tool == "cursor":
            return "🖱️"  # Cursor icon
        return "🤖"  # Claude icon

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

    async def load_children(self, doc_db) -> List["ActivityItem"]:
        """Agent executions don't have children."""
        return []

    async def get_preview_content(self, doc_db) -> tuple[str, str]:
        """Show execution log content in preview."""
        from pathlib import Path

        # If we have an output doc, show it
        if self.doc_id and doc_db:
            doc = doc_db.get_document(self.doc_id)
            if doc:
                return doc.get("content", ""), f"{self.type_icon} #{self.doc_id}"

        # Otherwise show the log file
        if self.log_file:
            log_path = Path(self.log_file)
            if log_path.exists():
                try:
                    content = log_path.read_text()
                    # Show last 100 lines max
                    lines = content.split('\n')
                    if len(lines) > 100:
                        content = '\n'.join(lines[-100:])
                    return f"```\n{content}\n```", f"{self.type_icon} Log"
                except Exception:
                    pass

        return f"[italic]{self.title}[/italic]", "PREVIEW"


