"""Activity item types for the activity view.

Simple dataclasses for documents and agent executions shown in the
flat activity table. No hierarchy, no expand/collapse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from emdx.ui.types import AgentExecutionDict

if TYPE_CHECKING:
    from emdx.models.types import TaskDict


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

    @property
    def item_type(self) -> str:
        return "document"

    @property
    def type_icon(self) -> str:
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


@dataclass
class AgentExecutionItem(ActivityItem):
    """An agent execution (from `emdx delegate` command)."""

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


# Task status icons (plain text, no emoji)
TASK_STATUS_ICONS = {
    "done": "v",
    "active": ">",
    "open": ".",
    "failed": "x",
    "blocked": "-",
}


@dataclass
class TaskItem(ActivityItem):
    """A task in the activity stream."""

    task_data: TaskDict | None = None

    @property
    def item_type(self) -> str:
        return "task"

    @property
    def type_icon(self) -> str:
        return TASK_STATUS_ICONS.get(self.status, "?")

    @property
    def status_icon(self) -> str:
        return TASK_STATUS_ICONS.get(self.status, "?")

    def get_context_lines(self) -> list[str]:
        """Return status, epic, and category info."""
        lines: list[str] = []
        if not self.task_data:
            return lines
        lines.append(f"Status: {self.status}")
        epic_key = self.task_data.get("epic_key")
        if epic_key:
            epic_seq = self.task_data.get("epic_seq")
            if epic_seq:
                lines.append(f"Epic: {epic_key}-{epic_seq}")
            else:
                lines.append(f"Epic: {epic_key}")
        priority = self.task_data.get("priority")
        if priority is not None:
            lines.append(f"Priority: {priority}")
        return lines

    async def get_preview_content(self, doc_db: Any) -> tuple[str, str]:
        """Show task description and dependencies in preview."""
        parts: list[str] = []

        if self.task_data:
            parts.append(f"# {self.task_data['title']}")
            parts.append("")

            # Context info
            context = self.get_context_lines()
            if context:
                parts.append("  ".join(context))
                parts.append("")

            # Description
            desc = self.task_data.get("description")
            if desc:
                parts.append(desc)
                parts.append("")

            # Dependencies
            try:
                from emdx.models.tasks import get_dependencies, get_dependents

                deps = get_dependencies(self.task_data["id"])
                if deps:
                    parts.append("**Depends on:**")
                    for dep in deps:
                        icon = TASK_STATUS_ICONS.get(dep["status"], "?")
                        parts.append(f"  {icon} #{dep['id']} {dep['title'][:60]} [{dep['status']}]")
                    parts.append("")

                dependents = get_dependents(self.task_data["id"])
                if dependents:
                    parts.append("**Blocks:**")
                    for dep in dependents:
                        icon = TASK_STATUS_ICONS.get(dep["status"], "?")
                        parts.append(f"  {icon} #{dep['id']} {dep['title'][:60]} [{dep['status']}]")
            except Exception:
                pass

        content = "\n".join(parts)
        task_id = self.task_data["id"] if self.task_data else self.item_id
        return content, f"{self.type_icon} Task #{task_id}"
