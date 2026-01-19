"""
Data models for the Unified Work System.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


def _parse_datetime(value) -> Optional[datetime]:
    """Parse a datetime value that may be str or datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


@dataclass
class Cascade:
    """A cascade defines a pipeline of stages that work items flow through."""

    name: str
    stages: List[str]
    processors: Dict[str, str]  # stage -> processor prompt
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: tuple) -> "Cascade":
        """Create from database row."""
        name, stages_json, processors_json, description, created_at = row
        return cls(
            name=name,
            stages=json.loads(stages_json) if stages_json else [],
            processors=json.loads(processors_json) if processors_json else {},
            description=description,
            created_at=_parse_datetime(created_at),
        )

    def get_next_stage(self, current_stage: str) -> Optional[str]:
        """Get the next stage after the current one, or None if at end."""
        try:
            idx = self.stages.index(current_stage)
            if idx < len(self.stages) - 1:
                return self.stages[idx + 1]
        except ValueError:
            pass
        return None

    def get_processor(self, stage: str) -> Optional[str]:
        """Get the processor prompt for a stage."""
        return self.processors.get(stage)

    def is_terminal_stage(self, stage: str) -> bool:
        """Check if this is the last stage in the cascade."""
        return self.stages and self.stages[-1] == stage


@dataclass
class WorkItem:
    """A work item that flows through cascade stages."""

    id: str  # Hash ID like "emdx-a3f2dd"
    title: str
    stage: str
    cascade: str = "default"
    content: Optional[str] = None
    priority: int = 3  # 0=critical, 1=high, 2=medium, 3=low, 4=backlog
    type: str = "task"  # task, bug, feature, epic, research, review
    parent_id: Optional[str] = None
    project: Optional[str] = None
    pr_number: Optional[int] = None
    output_doc_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None

    # Runtime fields (not persisted)
    is_blocked: bool = field(default=False, repr=False)
    blocked_by: List[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_row(cls, row: tuple) -> "WorkItem":
        """Create from database row."""
        (
            id, title, content, cascade, stage, priority, type_,
            parent_id, project, pr_number, output_doc_id,
            created_at, updated_at, started_at, completed_at,
            claimed_by, claimed_at
        ) = row

        return cls(
            id=id,
            title=title,
            content=content,
            cascade=cascade,
            stage=stage,
            priority=priority,
            type=type_,
            parent_id=parent_id,
            project=project,
            pr_number=pr_number,
            output_doc_id=output_doc_id,
            created_at=_parse_datetime(created_at),
            updated_at=_parse_datetime(updated_at),
            started_at=_parse_datetime(started_at),
            completed_at=_parse_datetime(completed_at),
            claimed_by=claimed_by,
            claimed_at=_parse_datetime(claimed_at),
        )

    @property
    def priority_label(self) -> str:
        """Get human-readable priority label."""
        labels = ["P0-CRITICAL", "P1-HIGH", "P2-MEDIUM", "P3-LOW", "P4-BACKLOG"]
        return labels[min(self.priority, 4)]

    @property
    def is_done(self) -> bool:
        """Check if work item is in a terminal/done state."""
        # Common terminal stages across cascades
        return self.stage in ("done", "merged", "conclusion", "deployed", "completed")


@dataclass
class WorkDep:
    """A dependency between two work items."""

    work_id: str
    depends_on: str
    dep_type: str = "blocks"  # blocks, related, discovered-from
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: tuple) -> "WorkDep":
        """Create from database row."""
        work_id, depends_on, dep_type, created_at = row
        return cls(
            work_id=work_id,
            depends_on=depends_on,
            dep_type=dep_type,
            created_at=_parse_datetime(created_at),
        )


@dataclass
class WorkTransition:
    """A record of a work item moving between stages."""

    id: int
    work_id: str
    from_stage: Optional[str]
    to_stage: str
    transitioned_by: Optional[str] = None
    content_snapshot: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: tuple) -> "WorkTransition":
        """Create from database row."""
        id_, work_id, from_stage, to_stage, transitioned_by, content_snapshot, created_at = row
        return cls(
            id=id_,
            work_id=work_id,
            from_stage=from_stage,
            to_stage=to_stage,
            transitioned_by=transitioned_by,
            content_snapshot=content_snapshot,
            created_at=_parse_datetime(created_at),
        )
