"""Tests for emdx.services.lifecycle_tracker module.

Focuses on the pure logic in _get_stage_from_tags and STAGES/TRANSITIONS constants.
DB-dependent methods are tested against the session-scoped test database.
"""

import pytest
from unittest.mock import patch, MagicMock

from emdx.services.lifecycle_tracker import LifecycleTracker


# ---------------------------------------------------------------------------
# STAGES / TRANSITIONS constants
# ---------------------------------------------------------------------------

class TestStageConstants:
    def test_all_stages_have_emoji_lists(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        for stage, emojis in tracker.STAGES.items():
            assert isinstance(emojis, list)
            assert len(emojis) >= 1, f"Stage '{stage}' has no emojis"

    def test_all_transition_keys_are_valid_stages(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        for source in tracker.TRANSITIONS:
            assert source in tracker.STAGES, f"Transition source '{source}' is not a valid stage"

    def test_all_transition_targets_are_valid_stages(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        for source, targets in tracker.TRANSITIONS.items():
            for target in targets:
                assert target in tracker.STAGES, \
                    f"Transition target '{target}' from '{source}' is not a valid stage"

    def test_archived_is_terminal(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        assert tracker.TRANSITIONS["archived"] == []

    def test_expected_stages_present(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        expected = {"planning", "active", "blocked", "completed", "success", "failed", "archived"}
        assert set(tracker.STAGES.keys()) == expected


# ---------------------------------------------------------------------------
# _get_stage_from_tags  (pure logic, no DB)
# ---------------------------------------------------------------------------

class TestGetStageFromTags:
    def setup_method(self):
        self.tracker = LifecycleTracker.__new__(LifecycleTracker)

    def test_planning_stage_with_target_emoji(self):
        assert self.tracker._get_stage_from_tags({"\U0001F3AF"}) == "planning"

    def test_planning_stage_with_notepad_emoji(self):
        assert self.tracker._get_stage_from_tags({"\U0001F4DD"}) == "planning"

    def test_active_stage(self):
        assert self.tracker._get_stage_from_tags({"\U0001F680"}) == "active"

    def test_blocked_stage(self):
        assert self.tracker._get_stage_from_tags({"\U0001F6A7"}) == "blocked"

    def test_completed_stage(self):
        assert self.tracker._get_stage_from_tags({"\u2705"}) == "completed"

    def test_success_stage(self):
        assert self.tracker._get_stage_from_tags({"\U0001F389"}) == "success"

    def test_failed_stage(self):
        assert self.tracker._get_stage_from_tags({"\u274C"}) == "failed"

    def test_archived_stage(self):
        assert self.tracker._get_stage_from_tags({"\U0001F4E6"}) == "archived"

    def test_empty_tags_returns_none(self):
        assert self.tracker._get_stage_from_tags(set()) is None

    def test_unrelated_tags_returns_none(self):
        assert self.tracker._get_stage_from_tags({"python", "docs"}) is None

    def test_later_stage_takes_precedence(self):
        """When multiple stage emojis present, later-defined stage wins (reversed iteration)."""
        # reversed order: archived, failed, success, completed, blocked, active, planning
        # archived is checked first so it wins over planning
        tags = {"\U0001F3AF", "\U0001F4E6"}  # planning + archived
        assert self.tracker._get_stage_from_tags(tags) == "archived"

    def test_completed_and_success_resolves_correctly(self):
        """If both completed and success tags present, later stage (success) wins."""
        tags = {"\u2705", "\U0001F389"}  # completed + success
        result = self.tracker._get_stage_from_tags(tags)
        # success comes after completed in reversed order, so success is checked first
        assert result == "success"

    def test_active_and_blocked_resolves(self):
        tags = {"\U0001F680", "\U0001F6A7"}  # active + blocked
        result = self.tracker._get_stage_from_tags(tags)
        # blocked comes after active in reversed order
        assert result == "blocked"


# ---------------------------------------------------------------------------
# TRANSITIONS validation (pure logic)
# ---------------------------------------------------------------------------

class TestTransitions:
    def setup_method(self):
        self.tracker = LifecycleTracker.__new__(LifecycleTracker)

    def test_planning_can_go_active(self):
        assert "active" in self.tracker.TRANSITIONS["planning"]

    def test_planning_can_go_blocked(self):
        assert "blocked" in self.tracker.TRANSITIONS["planning"]

    def test_active_can_go_completed(self):
        assert "completed" in self.tracker.TRANSITIONS["active"]

    def test_blocked_can_go_active(self):
        assert "active" in self.tracker.TRANSITIONS["blocked"]

    def test_completed_can_go_success(self):
        assert "success" in self.tracker.TRANSITIONS["completed"]

    def test_completed_can_go_failed(self):
        assert "failed" in self.tracker.TRANSITIONS["completed"]

    def test_success_only_to_archived(self):
        assert self.tracker.TRANSITIONS["success"] == ["archived"]

    def test_failed_only_to_archived(self):
        assert self.tracker.TRANSITIONS["failed"] == ["archived"]

    def test_no_cycles_to_self(self):
        for stage, targets in self.tracker.TRANSITIONS.items():
            assert stage not in targets, f"Stage '{stage}' transitions to itself"


# ---------------------------------------------------------------------------
# suggest_transitions (mocked DB)
# ---------------------------------------------------------------------------

class TestSuggestTransitions:
    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    @patch("emdx.services.lifecycle_tracker.get_document")
    def test_no_stage_suggests_planning(self, mock_get_doc, mock_get_tags):
        mock_get_tags.return_value = []
        mock_get_doc.return_value = {"title": "test"}
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        suggestions = tracker.suggest_transitions(1)
        assert len(suggestions) == 1
        assert suggestions[0][0] == "planning"

    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    @patch("emdx.services.lifecycle_tracker.get_document")
    def test_planning_stage_suggests_valid_transitions(self, mock_get_doc, mock_get_tags):
        mock_get_tags.return_value = ["\U0001F3AF"]
        mock_get_doc.return_value = {"title": "test"}
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        suggestions = tracker.suggest_transitions(1)
        stages = [s[0] for s in suggestions]
        assert "active" in stages
        assert "blocked" in stages
        assert "archived" in stages

    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    @patch("emdx.services.lifecycle_tracker.get_document")
    def test_archived_no_suggestions(self, mock_get_doc, mock_get_tags):
        mock_get_tags.return_value = ["\U0001F4E6"]
        mock_get_doc.return_value = {"title": "test"}
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        suggestions = tracker.suggest_transitions(1)
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# transition_document (mocked DB)
# ---------------------------------------------------------------------------

class TestTransitionDocument:
    @patch("emdx.services.lifecycle_tracker.update_document")
    @patch("emdx.services.lifecycle_tracker.get_document")
    @patch("emdx.services.lifecycle_tracker.add_tags_to_document")
    @patch("emdx.services.lifecycle_tracker.remove_tags_from_document")
    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    def test_valid_transition_returns_true(
        self, mock_get_tags, mock_remove, mock_add, mock_get_doc, mock_update
    ):
        mock_get_tags.return_value = ["\U0001F3AF"]  # planning
        mock_get_doc.return_value = {"title": "test", "content": "content"}
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        result = tracker.transition_document(1, "active")
        assert result is True
        mock_add.assert_called_once()

    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    def test_invalid_transition_returns_false(self, mock_get_tags):
        mock_get_tags.return_value = ["\U0001F3AF"]  # planning
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        # planning -> success is not a valid transition
        result = tracker.transition_document(1, "success")
        assert result is False

    @patch("emdx.services.lifecycle_tracker.update_document")
    @patch("emdx.services.lifecycle_tracker.get_document")
    @patch("emdx.services.lifecycle_tracker.add_tags_to_document")
    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    def test_transition_from_none_always_valid(
        self, mock_get_tags, mock_add, mock_get_doc, mock_update
    ):
        mock_get_tags.return_value = []  # no stage
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        result = tracker.transition_document(1, "planning")
        assert result is True

    @patch("emdx.services.lifecycle_tracker.update_document")
    @patch("emdx.services.lifecycle_tracker.get_document")
    @patch("emdx.services.lifecycle_tracker.add_tags_to_document")
    @patch("emdx.services.lifecycle_tracker.remove_tags_from_document")
    @patch("emdx.services.lifecycle_tracker.get_document_tags")
    def test_transition_with_notes_appends_to_content(
        self, mock_get_tags, mock_remove, mock_add, mock_get_doc, mock_update
    ):
        mock_get_tags.return_value = ["\U0001F3AF"]  # planning
        mock_get_doc.return_value = {"title": "test", "content": "existing content"}
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        tracker.transition_document(1, "active", notes="Starting work")
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        new_content = call_args[0][2]
        assert "Starting work" in new_content
        assert "planning" in new_content
        assert "active" in new_content


# ---------------------------------------------------------------------------
# get_stage_duration_stats (placeholder data)
# ---------------------------------------------------------------------------

class TestStageDurationStats:
    def test_returns_dict_with_expected_stages(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        stats = tracker.get_stage_duration_stats()
        assert "planning" in stats
        assert "active" in stats
        assert "blocked" in stats
        assert "completed" in stats

    def test_each_stage_has_duration_keys(self):
        tracker = LifecycleTracker.__new__(LifecycleTracker)
        stats = tracker.get_stage_duration_stats()
        for stage, data in stats.items():
            assert "avg_days" in data
            assert "min_days" in data
            assert "max_days" in data
