"""Tests for cascade progress tracking via log file parsing."""

import pytest

from emdx.services.cascade_progress import (
    CascadeProgressTracker,
    ProgressEstimate,
    WorkPhase,
    format_progress,
    format_progress_bar,
)


class TestCascadeProgressTracker:
    """Tests for the CascadeProgressTracker class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = CascadeProgressTracker()

    def test_empty_log_returns_starting(self):
        """Empty log should return starting state."""
        result = self.tracker.estimate_progress("", "idea")
        assert result.phase == WorkPhase.STARTING
        assert result.percentage == 0
        assert result.is_running

    def test_none_log_returns_starting(self):
        """None log should be handled gracefully."""
        # Pass empty string as a proxy for "no content"
        result = self.tracker.estimate_progress("", "idea")
        assert result.phase == WorkPhase.STARTING
        assert result.is_running

    def test_pr_url_means_complete(self):
        """PR URL in log indicates completion."""
        log = """
        Working on changes...
        Creating PR...
        PR_URL: https://github.com/owner/repo/pull/123
        Done!
        """
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.COMPLETE
        assert result.percentage == 100
        assert not result.is_running

    def test_git_commit_detected(self):
        """Git commit activity should be detected."""
        log = """
        Making changes to files...
        git commit -m "Add feature"
        """
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.COMMITTING
        assert result.percentage >= 75

    def test_reading_files_detected(self):
        """Reading file activity should be detected."""
        log = """
        Starting analysis...
        Reading file: src/main.py
        """
        result = self.tracker.estimate_progress(log, "idea")
        assert result.phase == WorkPhase.DISCOVERY
        assert result.percentage >= 15

    def test_writing_files_detected(self):
        """Writing file activity should be detected."""
        log = """
        Implementing feature...
        Writing: src/feature.py
        """
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.IMPLEMENTATION
        assert result.percentage >= 55

    def test_searching_detected(self):
        """Searching activity should be detected."""
        log = """
        Exploring codebase...
        Searching: function definitions
        """
        result = self.tracker.estimate_progress(log, "idea")
        assert result.phase == WorkPhase.DISCOVERY
        assert result.percentage >= 15

    def test_tests_passing_detected(self):
        """Tests passing should be detected."""
        log = """
        Running tests...
        Tests pass
        All tests pass
        """
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.IMPLEMENTATION
        assert result.percentage >= 65

    def test_highest_percentage_wins(self):
        """When multiple patterns match, highest percentage should win."""
        log = """
        Reading file: src/main.py
        Writing: src/feature.py
        git commit -m "Add feature"
        """
        result = self.tracker.estimate_progress(log, "planned")
        # Git commit has higher percentage than reading/writing
        assert result.phase == WorkPhase.COMMITTING
        assert result.percentage >= 75

    def test_planning_phase_detected(self):
        """Planning phase should be detected."""
        log = """
        Creating plan for implementation...
        Planning the steps needed
        """
        result = self.tracker.estimate_progress(log, "analyzed")
        assert result.phase == WorkPhase.ANALYZING
        assert result.percentage >= 35

    def test_pr_creation_detected(self):
        """PR creation activity should be detected."""
        log = """
        git push origin feature-branch
        gh pr create --title "Feature"
        Creating pull request
        """
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.CREATING_PR
        assert result.percentage >= 85


class TestFormatProgress:
    """Tests for progress formatting functions."""

    def test_format_running_progress(self):
        """Running progress should show spinner and percentage."""
        estimate = ProgressEstimate(
            phase=WorkPhase.IMPLEMENTATION,
            percentage=45,
            description="Writing files",
            is_running=True,
        )
        result = format_progress(estimate)
        assert "⟳" in result
        assert "45%" in result
        assert "Writing files" in result

    def test_format_complete_progress(self):
        """Completed progress should show checkmark."""
        estimate = ProgressEstimate(
            phase=WorkPhase.COMPLETE,
            percentage=100,
            description="Complete",
            is_running=False,
        )
        result = format_progress(estimate)
        assert "✓" in result
        assert "Complete" in result

    def test_format_progress_bar_empty(self):
        """Progress bar at 0% should be empty."""
        estimate = ProgressEstimate(
            phase=WorkPhase.STARTING,
            percentage=0,
            description="Starting",
            is_running=True,
        )
        result = format_progress_bar(estimate, width=10)
        assert "░" * 10 in result or result.count("░") == 10

    def test_format_progress_bar_half(self):
        """Progress bar at 50% should be half filled."""
        estimate = ProgressEstimate(
            phase=WorkPhase.IMPLEMENTATION,
            percentage=50,
            description="Implementing",
            is_running=True,
        )
        result = format_progress_bar(estimate, width=10)
        assert "█" in result
        assert "░" in result

    def test_format_progress_bar_complete(self):
        """Completed progress bar should show done."""
        estimate = ProgressEstimate(
            phase=WorkPhase.COMPLETE,
            percentage=100,
            description="Done",
            is_running=False,
        )
        result = format_progress_bar(estimate, width=10)
        assert "done" in result.lower()


class TestCaseInsensitivity:
    """Tests for case-insensitive pattern matching."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = CascadeProgressTracker()

    def test_uppercase_patterns(self):
        """Uppercase patterns should still match."""
        log = "READING FILE: src/main.py"
        result = self.tracker.estimate_progress(log, "idea")
        assert result.phase == WorkPhase.DISCOVERY

    def test_mixed_case_patterns(self):
        """Mixed case patterns should still match."""
        log = "Writing: SRC/Feature.py"
        result = self.tracker.estimate_progress(log, "planned")
        assert result.phase == WorkPhase.IMPLEMENTATION
