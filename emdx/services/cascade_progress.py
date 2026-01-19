"""Cascade progress tracking via log file parsing.

Parses Claude output logs in real-time to estimate progress through stages.
Uses pattern matching to detect work phases (discovery, implementation, etc.).
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class WorkPhase(Enum):
    """Phases of work detected from Claude output."""
    STARTING = "starting"
    DISCOVERY = "discovery"
    ANALYZING = "analyzing"
    IMPLEMENTATION = "implementation"
    COMMITTING = "committing"
    CREATING_PR = "creating_pr"
    COMPLETE = "complete"


@dataclass
class ProgressEstimate:
    """Estimated progress through a stage."""
    phase: WorkPhase
    percentage: int  # 0-100
    description: str
    is_running: bool = True


# Progress patterns: (regex, percentage, phase, description)
PROGRESS_PATTERNS = [
    # Completion indicators
    (r"PR_URL:\s*https://", 100, WorkPhase.COMPLETE, "Complete"),
    (r"successfully created|PR created|Pull request created", 95, WorkPhase.COMPLETE, "PR created"),

    # PR creation phase
    (r"gh pr create|Creating pull request", 90, WorkPhase.CREATING_PR, "Creating PR"),
    (r"git push|Pushing to remote", 85, WorkPhase.CREATING_PR, "Pushing changes"),

    # Committing phase
    (r"git commit|Committing changes", 80, WorkPhase.COMMITTING, "Committing"),
    (r"git add|Staging files", 75, WorkPhase.COMMITTING, "Staging changes"),

    # Implementation phase
    (r"Writing:|Write tool|creating file", 60, WorkPhase.IMPLEMENTATION, "Writing files"),
    (r"Editing:|Edit tool|modifying", 55, WorkPhase.IMPLEMENTATION, "Editing files"),
    (r"Tests pass|All tests|test.*pass", 70, WorkPhase.IMPLEMENTATION, "Tests passing"),
    (r"Running tests|pytest|npm test", 65, WorkPhase.IMPLEMENTATION, "Running tests"),

    # Analysis phase
    (r"Planning|Creating plan|analyzing", 40, WorkPhase.ANALYZING, "Planning"),
    (r"Thinking|Considering|evaluating", 35, WorkPhase.ANALYZING, "Analyzing"),

    # Discovery phase
    (r"Reading file:|Read tool", 20, WorkPhase.DISCOVERY, "Reading files"),
    (r"Searching:|Grep tool|grep", 18, WorkPhase.DISCOVERY, "Searching"),
    (r"Glob tool|Finding files", 15, WorkPhase.DISCOVERY, "Finding files"),
    (r"Understanding|examining|looking at", 12, WorkPhase.DISCOVERY, "Exploring"),

    # Starting phase
    (r"Starting|Beginning|Let me", 5, WorkPhase.STARTING, "Starting"),
]


class CascadeProgressTracker:
    """Tracks cascade progress by parsing log output.

    Uses pattern matching on Claude's log output to estimate how far
    through a task it has progressed. Designed for UI display.
    """

    def __init__(self):
        # Compile patterns for efficiency
        self._patterns = [
            (re.compile(pattern, re.IGNORECASE), pct, phase, desc)
            for pattern, pct, phase, desc in PROGRESS_PATTERNS
        ]

    def estimate_progress(
        self,
        log_content: str,
        stage: str,
    ) -> ProgressEstimate:
        """Estimate progress from log content.

        Args:
            log_content: The log file content to analyze
            stage: Current cascade stage (idea, prompt, analyzed, planned)

        Returns:
            ProgressEstimate with phase, percentage, and description
        """
        if not log_content:
            return ProgressEstimate(
                phase=WorkPhase.STARTING,
                percentage=0,
                description="Waiting...",
                is_running=True,
            )

        # Check for completion first
        if "PR_URL:" in log_content and "https://github.com" in log_content:
            return ProgressEstimate(
                phase=WorkPhase.COMPLETE,
                percentage=100,
                description="Complete",
                is_running=False,
            )

        # Find the highest-percentage pattern that matches
        # Search from the end of log to find most recent activity
        last_lines = log_content[-5000:]  # Last ~5000 chars for efficiency

        best_match = None
        best_pct = 0

        for pattern, pct, phase, desc in self._patterns:
            if pattern.search(last_lines):
                if pct > best_pct:
                    best_pct = pct
                    best_match = (phase, pct, desc)

        if best_match:
            phase, pct, desc = best_match
            return ProgressEstimate(
                phase=phase,
                percentage=pct,
                description=desc,
                is_running=pct < 100,
            )

        # Default: processing without specific phase detected
        return ProgressEstimate(
            phase=WorkPhase.STARTING,
            percentage=5,
            description="Processing...",
            is_running=True,
        )

    def estimate_from_file(
        self,
        log_path: Path,
        stage: str,
    ) -> Optional[ProgressEstimate]:
        """Estimate progress from a log file path.

        Args:
            log_path: Path to the log file
            stage: Current cascade stage

        Returns:
            ProgressEstimate or None if file doesn't exist
        """
        if not log_path.exists():
            return None

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.estimate_progress(content, stage)
        except Exception:
            return None


def format_progress(estimate: ProgressEstimate) -> str:
    """Format progress estimate for display.

    Args:
        estimate: The progress estimate to format

    Returns:
        Formatted string like "⟳ 45% - Implementing..."
    """
    if not estimate.is_running:
        return f"✓ {estimate.description}"

    return f"⟳ {estimate.percentage}% - {estimate.description}"


def format_progress_bar(estimate: ProgressEstimate, width: int = 10) -> str:
    """Format progress as a visual bar.

    Args:
        estimate: The progress estimate
        width: Width of the bar in characters

    Returns:
        Progress bar like "[████░░░░░░]"
    """
    if not estimate.is_running:
        return "✓ done"

    filled = int(estimate.percentage / 100 * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"
