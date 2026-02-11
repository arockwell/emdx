"""Activity item type hierarchy for the activity view.

This module provides typed classes for different activity stream items,
replacing the stringly-typed item_type field with proper polymorphism.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


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
    doc_id: Optional[int] = None  # Document ID if this item has associated content
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
    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Load child items from database."""
        ...

    @abstractmethod
    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Get content and header for preview pane.

        Returns:
            Tuple of (content_markdown, header_text)
        """
        ...


@dataclass
class WorkflowItem(ActivityItem):
    """A workflow execution in the activity stream."""

    workflow_run: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    cost: float = 0.0
    tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    progress_completed: int = 0
    progress_total: int = 0
    progress_stage: str = ""
    output_count: int = 0
    doc_id: Optional[int] = None
    has_workflow_outputs: bool = False

    @property
    def item_type(self) -> str:
        return "workflow"

    @property
    def type_icon(self) -> str:
        return "⚡"

    @property
    def status_icon(self) -> str:
        icons = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "queued": "⏸️",
            "pending": "⏳",
        }
        return icons.get(self.status, "⚪")

    def can_expand(self) -> bool:
        return (
            self.status == "running"
            or self.has_workflow_outputs
            or self.output_count > 0
        )

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Load workflow children (individual runs or synthesis + explorations)."""
        children = []

        if not self.workflow_run or not wf_db:
            return children

        run = self.workflow_run
        stage_runs = wf_db.list_stage_runs(run["id"])

        for sr in stage_runs:
            stage_status = sr.get("status", "pending")
            target_runs = sr.get("target_runs", 1)
            ind_runs = wf_db.list_individual_runs(sr["id"])

            # For running/pending workflows, show individual runs
            if stage_status in ("running", "pending") or self.status == "running":
                for ir in ind_runs:
                    ir_status = ir.get("status", "pending")
                    run_num = ir.get("run_number", 0)

                    # Build title based on status
                    if ir_status == "completed" and ir.get("output_doc_id"):
                        doc = (
                            doc_db.get_document(ir["output_doc_id"]) if doc_db else None
                        )
                        title = (
                            doc.get("title", f"Run {run_num}")
                            if doc
                            else f"Run {run_num}"
                        )
                    elif ir_status == "running":
                        title = f"Run {run_num} (running...)"
                    elif ir_status == "pending":
                        title = f"Run {run_num} (pending)"
                    elif ir_status == "failed":
                        title = f"Run {run_num} (failed)"
                    else:
                        title = f"Run {run_num}"

                    children.append(
                        IndividualRunItem(
                            item_id=ir.get("id") or 0,
                            title=title,
                            timestamp=self.timestamp,
                            doc_id=ir.get("output_doc_id"),
                            status=ir_status,
                            cost=ir.get("cost_usd") or 0,
                            run_number=run_num,
                            depth=self.depth + 1,
                        )
                    )

                # Add placeholders for pending runs
                if len(ind_runs) < target_runs:
                    for i in range(len(ind_runs) + 1, target_runs + 1):
                        children.append(
                            IndividualRunItem(
                                item_id=0,
                                title=f"Run {i} (pending)",
                                timestamp=self.timestamp,
                                status="pending",
                                run_number=i,
                                depth=self.depth + 1,
                            )
                        )

            # For completed workflows, show synthesis + explorations
            else:
                if sr.get("synthesis_doc_id"):
                    doc = (
                        doc_db.get_document(sr["synthesis_doc_id"]) if doc_db else None
                    )
                    title = doc.get("title", "Synthesis") if doc else "Synthesis"

                    children.append(
                        SynthesisItem(
                            item_id=sr["synthesis_doc_id"],
                            title=title,
                            timestamp=self.timestamp,
                            doc_id=sr["synthesis_doc_id"],
                            depth=self.depth + 1,
                        )
                    )

                    # Add individual outputs as explorations
                    for ir in ind_runs:
                        if ir.get("output_doc_id") and ir["output_doc_id"] != sr.get(
                            "synthesis_doc_id"
                        ):
                            out_doc = (
                                doc_db.get_document(ir["output_doc_id"])
                                if doc_db
                                else None
                            )
                            out_title = (
                                out_doc.get("title", f"Output #{ir['run_number']}")
                                if out_doc
                                else f"Output #{ir['run_number']}"
                            )

                            children.append(
                                ExplorationItem(
                                    item_id=ir["output_doc_id"],
                                    title=out_title,
                                    timestamp=self.timestamp,
                                    doc_id=ir["output_doc_id"],
                                    status=ir.get("status", "completed"),
                                    cost=ir.get("cost_usd") or 0,
                                    depth=self.depth + 1,
                                )
                            )

                # No synthesis - show outputs directly
                elif not sr.get("synthesis_doc_id"):
                    for ir in ind_runs:
                        if ir.get("output_doc_id"):
                            doc = (
                                doc_db.get_document(ir["output_doc_id"])
                                if doc_db
                                else None
                            )
                            title = (
                                doc.get("title", f"Output #{ir['run_number']}")
                                if doc
                                else f"Output #{ir['run_number']}"
                            )

                            children.append(
                                ExplorationItem(
                                    item_id=ir["output_doc_id"],
                                    title=title,
                                    timestamp=self.timestamp,
                                    doc_id=ir["output_doc_id"],
                                    status=ir.get("status", "completed"),
                                    cost=ir.get("cost_usd") or 0,
                                    depth=self.depth + 1,
                                )
                            )

        return children

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Get workflow preview - live log for running, output for completed."""
        if self.status == "running":
            return "", f"[green]● LIVE[/green] {self.title}"

        if self.doc_id and doc_db:
            doc = doc_db.get_document(self.doc_id)
            if doc:
                return doc.get("content", ""), f"📄 #{self.doc_id}"

        return f"[italic]{self.title}[/italic]", "PREVIEW"


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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Load child documents."""
        children = []

        if not doc_db:
            return children

        child_docs = doc_db.get_children(self.doc_id, include_archived=False)

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

            grandchildren = doc_db.get_children(child_doc["id"], include_archived=False)

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

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
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
class SynthesisItem(ActivityItem):
    """A synthesis document from a workflow stage."""

    doc_id: int = 0
    individual_outputs: List[int] = field(default_factory=list)

    @property
    def item_type(self) -> str:
        return "synthesis"

    @property
    def type_icon(self) -> str:
        return "📝"

    @property
    def status_icon(self) -> str:
        return "✅"

    def can_expand(self) -> bool:
        return len(self.individual_outputs) > 0 or len(self.children) > 0

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Synthesis items don't load children dynamically - they're set by parent."""
        return self.children

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Get synthesis document content."""
        if not doc_db:
            return "", "PREVIEW"

        doc = doc_db.get_document(self.doc_id)
        if doc:
            return doc.get("content", ""), f"📝 #{self.doc_id}"

        return "", "PREVIEW"


@dataclass
class IndividualRunItem(ActivityItem):
    """An individual run within a workflow stage."""

    doc_id: Optional[int] = None
    status: str = "pending"
    cost: float = 0.0
    run_number: int = 0

    @property
    def item_type(self) -> str:
        return "individual_run"

    @property
    def type_icon(self) -> str:
        return "🤖"

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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Individual runs don't have children."""
        return []

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Get run output or indicate running."""
        if self.status == "running":
            return "", f"[green]● LIVE[/green] {self.title}"

        if self.doc_id and doc_db:
            doc = doc_db.get_document(self.doc_id)
            if doc:
                return doc.get("content", ""), f"🤖 #{self.doc_id}"

        return f"[italic]{self.title}[/italic]", "PREVIEW"


@dataclass
class ExplorationItem(ActivityItem):
    """An exploration output from a workflow (child of synthesis)."""

    doc_id: int = 0
    status: str = "completed"
    cost: float = 0.0

    @property
    def item_type(self) -> str:
        return "exploration"

    @property
    def type_icon(self) -> str:
        return "◇"

    @property
    def status_icon(self) -> str:
        return "✅"

    def can_expand(self) -> bool:
        return False

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Exploration items don't have children."""
        return []

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Get exploration document content."""
        if not doc_db:
            return "", "PREVIEW"

        doc = doc_db.get_document(self.doc_id)
        if doc:
            return doc.get("content", ""), f"◇ #{self.doc_id}"

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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
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

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
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

    doc_id: Optional[int] = None
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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Stage items don't have children."""
        return []

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
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

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
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
    """A standalone agent execution (from `emdx agent` command).

    These are direct CLI agent runs not part of any workflow or cascade.
    """

    execution: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    doc_id: Optional[int] = None
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

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Agent executions don't have children."""
        return []

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
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


@dataclass
class MailItem(ActivityItem):
    """A mail message in the activity stream."""

    mail_message: Dict[str, Any] = field(default_factory=dict)
    sender: str = ""
    recipient: str = ""
    is_read: bool = False
    comment_count: int = 0
    url: str = ""

    @property
    def item_type(self) -> str:
        return "mail"

    @property
    def type_icon(self) -> str:
        return "📧"

    @property
    def status_icon(self) -> str:
        return "○" if self.is_read else "●"

    def can_expand(self) -> bool:
        return self.comment_count > 0

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        """Load replies as children."""
        import asyncio
        from emdx.services.mail_service import get_mail_service

        children = []
        service = get_mail_service()
        thread = await asyncio.to_thread(service.get_thread, self.item_id)

        if thread and thread.comments:
            for i, comment in enumerate(thread.comments):
                created_at = comment.get("created_at", "")
                if isinstance(created_at, str) and created_at:
                    try:
                        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        # Strip timezone to match naive datetimes used elsewhere
                        ts = parsed.replace(tzinfo=None)
                    except ValueError:
                        ts = self.timestamp
                else:
                    ts = self.timestamp

                children.append(
                    MailReplyItem(
                        item_id=self.item_id * 1000 + i,
                        title=f"@{comment.get('author', '?')}",
                        timestamp=ts,
                        body=comment.get("body", ""),
                        author=comment.get("author", ""),
                        depth=self.depth + 1,
                    )
                )
        return children

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        """Show message body in preview."""
        body = self.mail_message.get("body", "")
        header = f"📧 #{self.item_id} from @{self.sender}"

        content = f"# {self.title}\n\n"
        content += f"**From:** @{self.sender} → @{self.recipient}\n\n"
        content += f"---\n\n{body}"

        return content, header


@dataclass
class MailReplyItem(ActivityItem):
    """A reply within a mail thread (child of MailItem)."""

    body: str = ""
    author: str = ""

    @property
    def item_type(self) -> str:
        return "mail_reply"

    @property
    def type_icon(self) -> str:
        return "↩"

    @property
    def status_icon(self) -> str:
        return "○"

    def can_expand(self) -> bool:
        return False

    async def load_children(self, wf_db, doc_db) -> List["ActivityItem"]:
        return []

    async def get_preview_content(self, wf_db, doc_db) -> tuple[str, str]:
        return self.body, f"↩ @{self.author}"
