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
                            doc.get("title", f"Run {run_num}")[:25]
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
                            title=title[:30],
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
                                out_doc.get("title", f"Output #{ir['run_number']}")[:25]
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
                                doc.get("title", f"Output #{ir['run_number']}")[:25]
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

            title = child_doc.get("title", "")[:30]
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
