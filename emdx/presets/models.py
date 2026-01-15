"""Preset data models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Preset:
    """A saved configuration for emdx run."""

    id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    discover_command: Optional[str]
    task_template: Optional[str]
    synthesize: bool
    max_jobs: Optional[int]
    created_at: datetime
    updated_at: datetime
    usage_count: int
    last_used_at: Optional[datetime]
    is_active: bool

    @classmethod
    def from_row(cls, row: dict) -> "Preset":
        """Create Preset from database row."""
        return cls(
            id=row["id"],
            name=row["name"],
            display_name=row.get("display_name"),
            description=row.get("description"),
            discover_command=row.get("discover_command"),
            task_template=row.get("task_template"),
            synthesize=bool(row.get("synthesize", False)),
            max_jobs=row.get("max_jobs"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            usage_count=row.get("usage_count", 0),
            last_used_at=row.get("last_used_at"),
            is_active=bool(row.get("is_active", True)),
        )

    @property
    def has_discovery(self) -> bool:
        """Check if preset has discovery command."""
        return bool(self.discover_command)

    @property
    def has_template(self) -> bool:
        """Check if preset has task template."""
        return bool(self.task_template)
