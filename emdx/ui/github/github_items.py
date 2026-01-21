"""GitHub PR dataclasses and view models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from rich.markup import escape

# Re-export from service for convenience
from emdx.services.github_service import (
    FilterMode,
    PRItem,
    PRDetailVM,
    ReviewDecision,
    ChecksStatus,
    MergeableState,
)


@dataclass
class PRStateVM:
    """State view model for the GitHub PR presenter."""

    prs: List[PRItem] = field(default_factory=list)
    filtered_prs: List[PRItem] = field(default_factory=list)
    selected_index: int = 0
    filter_mode: FilterMode = FilterMode.ALL
    loading: bool = False
    error: Optional[str] = None
    gh_available: bool = True
    gh_error: Optional[str] = None

    # Filter counts
    filter_counts: dict = field(default_factory=dict)

    @property
    def selected_pr(self) -> Optional[PRItem]:
        """Get the currently selected PR."""
        if 0 <= self.selected_index < len(self.filtered_prs):
            return self.filtered_prs[self.selected_index]
        return None

    @property
    def status_text(self) -> str:
        """Get status bar text."""
        if not self.gh_available:
            return escape(self.gh_error) if self.gh_error else "GitHub CLI not available"
        if self.loading:
            return "Loading PRs..."
        if self.error:
            return f"Error: {escape(self.error)}"

        total = len(self.prs)
        filtered = len(self.filtered_prs)

        if self.filter_mode == FilterMode.ALL:
            return f"{total} PRs"

        return f"{filtered}/{total} PRs ({self.filter_mode.value})"

    @property
    def counts_text(self) -> str:
        """Get filter counts summary."""
        if not self.filter_counts:
            return ""

        parts = []
        needs_review = self.filter_counts.get(FilterMode.NEEDS_REVIEW, 0)
        conflicts = self.filter_counts.get(FilterMode.CONFLICTS, 0)
        ready = self.filter_counts.get(FilterMode.READY, 0)

        if needs_review:
            parts.append(f"{needs_review} need review")
        if conflicts:
            parts.append(f"{conflicts} conflicts")
        if ready:
            parts.append(f"{ready} ready")

        return " | ".join(parts)


__all__ = [
    "FilterMode",
    "PRItem",
    "PRDetailVM",
    "PRStateVM",
    "ReviewDecision",
    "ChecksStatus",
    "MergeableState",
]
