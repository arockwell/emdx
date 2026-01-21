"""Tests for WorkService business logic."""

import time
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from emdx.work.service import WorkService, generate_work_id
from emdx.work.models import Cascade, WorkItem, WorkDep, WorkTransition


class TestGenerateWorkId:
    """Tests for the generate_work_id function."""

    def test_generates_valid_format(self):
        work_id = generate_work_id("Test title")
        assert work_id.startswith("emdx-")
        assert len(work_id) == 11  # "emdx-" + 6 hex chars

    def test_generates_hex_suffix(self):
        work_id = generate_work_id("Test title")
        hex_part = work_id.split("-")[1]
        # Should be valid hex
        int(hex_part, 16)

    def test_different_titles_produce_different_ids(self):
        id1 = generate_work_id("Title A")
        id2 = generate_work_id("Title B")
        assert id1 != id2

    def test_same_title_same_timestamp_produces_same_id(self):
        ts = datetime(2024, 1, 1, 12, 0, 0)
        id1 = generate_work_id("Same title", ts)
        id2 = generate_work_id("Same title", ts)
        assert id1 == id2


class TestWorkServiceCascadeOperations:
    """Tests for cascade-related WorkService methods."""

    def test_create_cascade(self, work_service):
        cascade = work_service.create_cascade(
            name="test-custom",
            stages=["start", "middle", "end"],
            processors={"start": "Begin processing"},
            description="Custom cascade",
        )
        assert cascade.name == "test-custom"
        assert cascade.stages == ["start", "middle", "end"]
        assert cascade.processors == {"start": "Begin processing"}
        assert cascade.description == "Custom cascade"

    def test_get_cascade(self, work_service, default_cascade):
        cascade = work_service.get_cascade("default")
        assert cascade is not None
        assert cascade.name == "default"
        assert "idea" in cascade.stages

    def test_get_cascade_not_found(self, work_service):
        cascade = work_service.get_cascade("nonexistent")
        assert cascade is None

    def test_list_cascades(self, work_service, default_cascade, review_cascade):
        cascades = work_service.list_cascades()
        names = [c.name for c in cascades]
        assert "default" in names
        assert "review" in names

    def test_cascade_cache_is_used(self, work_service, default_cascade):
        """Verify that cascade cache prevents redundant DB queries."""
        # First call populates cache
        cascade1 = work_service.get_cascade("default")

        # Second call should return cached value (same object)
        cascade2 = work_service.get_cascade("default")

        assert cascade1 is cascade2

    def test_cascade_cache_invalidation(self, work_service, default_cascade):
        """Verify that cache invalidation clears the cache."""
        # Populate cache
        work_service.get_cascade("default")
        assert "default" in work_service._cascade_cache

        # Invalidate
        work_service._invalidate_cascade_cache()
        assert len(work_service._cascade_cache) == 0

    def test_cascade_cache_ttl_expiry(self, work_service, default_cascade):
        """Verify that cache expires after TTL."""
        # Set a very short TTL
        work_service._cascade_cache_ttl = 0.01

        # Populate cache
        work_service.get_cascade("default")

        # Wait for TTL to expire
        time.sleep(0.02)

        # Cache should be invalid
        assert not work_service._is_cascade_cache_valid()


class TestWorkServiceAddItem:
    """Tests for adding work items."""

    def test_add_basic_item(self, work_service, default_cascade):
        item = work_service.add(title="Test item")
        assert item.id.startswith("emdx-")
        assert item.title == "Test item"
        assert item.cascade == "default"
        assert item.stage == "idea"  # First stage
        assert item.priority == 3

    def test_add_item_with_all_options(self, work_service, default_cascade):
        item = work_service.add(
            title="Full item",
            cascade="default",
            stage="planned",
            content="Detailed content",
            priority=1,
            type_="feature",
        )
        assert item.title == "Full item"
        assert item.stage == "planned"
        assert item.content == "Detailed content"
        assert item.priority == 1
        assert item.type == "feature"

    def test_add_item_unknown_cascade_raises(self, work_service):
        with pytest.raises(ValueError, match="Unknown cascade"):
            work_service.add(title="Test", cascade="nonexistent")

    def test_add_item_invalid_stage_raises(self, work_service, default_cascade):
        with pytest.raises(ValueError, match="Invalid stage"):
            work_service.add(title="Test", cascade="default", stage="invalid")

    def test_add_item_creates_initial_transition(self, work_service, default_cascade):
        item = work_service.add(title="Test item")
        transitions = work_service.get_transitions(item.id)
        assert len(transitions) == 1
        assert transitions[0].from_stage is None
        assert transitions[0].to_stage == "idea"
        assert transitions[0].transitioned_by == "created"

    def test_add_item_with_dependencies(self, work_service, default_cascade):
        # Create prerequisite
        prereq = work_service.add(title="Prerequisite")

        # Create item with dependency
        item = work_service.add(title="Dependent", depends_on=[prereq.id])

        # Verify dependency was created
        deps = work_service.get_dependencies(item.id)
        assert len(deps) == 1
        assert deps[0][0].depends_on == prereq.id
        assert deps[0][0].dep_type == "blocks"


class TestWorkServiceGetItem:
    """Tests for getting work items."""

    def test_get_item(self, work_service, sample_work_item):
        item = work_service.get(sample_work_item.id)
        assert item is not None
        assert item.id == sample_work_item.id
        assert item.title == sample_work_item.title

    def test_get_item_not_found(self, work_service):
        item = work_service.get("nonexistent-id")
        assert item is None

    def test_get_item_with_blocking_dependency(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item
        item = work_service.get(blocked.id)
        assert item.is_blocked is True
        assert blocker.id in item.blocked_by

    def test_get_item_unblocked_when_blocker_done(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item

        # Complete the blocker
        work_service.done(blocker.id)

        # Blocked item should now be unblocked
        item = work_service.get(blocked.id)
        assert item.is_blocked is False


class TestWorkServiceListItems:
    """Tests for listing work items."""

    def test_list_items_default(self, work_service, sample_work_items):
        items = work_service.list()
        assert len(items) >= 3

    def test_list_items_filter_by_cascade(self, work_service, sample_work_items, review_cascade):
        # Add a review item
        work_service.add(title="Review item", cascade="review")

        # List only default cascade
        items = work_service.list(cascade="default")
        for item in items:
            assert item.cascade == "default"

    def test_list_items_filter_by_stage(self, work_service, sample_work_items):
        items = work_service.list(stage="planned")
        for item in items:
            assert item.stage == "planned"

    def test_list_items_exclude_done_by_default(self, work_service, sample_work_items):
        # Complete one item
        work_service.done(sample_work_items[0].id)

        items = work_service.list(include_done=False)
        for item in items:
            assert item.is_done is False

    def test_list_items_include_done(self, work_service, sample_work_items):
        # Complete one item
        work_service.done(sample_work_items[0].id)

        items = work_service.list(include_done=True)
        done_items = [i for i in items if i.is_done]
        assert len(done_items) >= 1

    def test_list_items_with_limit(self, work_service, sample_work_items):
        items = work_service.list(limit=2)
        assert len(items) <= 2

    def test_list_items_ordered_by_priority(self, work_service, sample_work_items):
        items = work_service.list()
        priorities = [i.priority for i in items]
        assert priorities == sorted(priorities)


class TestWorkServiceReadyItems:
    """Tests for the ready() query - critical for patrol system."""

    def test_ready_returns_unblocked_items(self, work_service, sample_work_items):
        ready = work_service.ready()
        for item in ready:
            assert item.is_blocked is False

    def test_ready_excludes_blocked_items(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item
        ready = work_service.ready()
        ready_ids = [i.id for i in ready]
        assert blocked.id not in ready_ids

    def test_ready_excludes_claimed_items(self, work_service, claimed_work_item):
        ready = work_service.ready()
        ready_ids = [i.id for i in ready]
        assert claimed_work_item.id not in ready_ids

    def test_ready_excludes_terminal_stages(self, work_service, sample_work_items):
        # Complete an item
        work_service.done(sample_work_items[0].id)

        ready = work_service.ready()
        for item in ready:
            assert item.is_done is False

    def test_ready_filter_by_cascade(self, work_service, sample_work_items, review_cascade):
        # Add a review item
        work_service.add(title="Review item", cascade="review")

        ready = work_service.ready(cascade="default")
        for item in ready:
            assert item.cascade == "default"

    def test_ready_filter_by_stage(self, work_service, sample_work_items):
        ready = work_service.ready(stage="idea")
        for item in ready:
            assert item.stage == "idea"

    def test_ready_ordered_by_priority(self, work_service, sample_work_items):
        ready = work_service.ready()
        priorities = [i.priority for i in ready]
        assert priorities == sorted(priorities)

    def test_ready_with_limit(self, work_service, sample_work_items):
        ready = work_service.ready(limit=1)
        assert len(ready) <= 1


class TestWorkServiceAdvance:
    """Tests for advancing work items through stages."""

    def test_advance_moves_to_next_stage(self, work_service, sample_work_item):
        old_stage = sample_work_item.stage
        item = work_service.advance(sample_work_item.id)

        cascade = work_service.get_cascade(item.cascade)
        expected_stage = cascade.get_next_stage(old_stage)
        assert item.stage == expected_stage

    def test_advance_creates_transition(self, work_service, sample_work_item):
        old_stage = sample_work_item.stage
        item = work_service.advance(sample_work_item.id, transitioned_by="test")

        transitions = work_service.get_transitions(item.id)
        last_trans = transitions[-1]
        assert last_trans.from_stage == old_stage
        assert last_trans.to_stage == item.stage
        assert last_trans.transitioned_by == "test"

    def test_advance_at_terminal_stage_raises(self, work_service, sample_work_item):
        # Move to terminal stage
        work_service.done(sample_work_item.id)

        with pytest.raises(ValueError, match="already at final stage"):
            work_service.advance(sample_work_item.id)

    def test_advance_not_found_raises(self, work_service):
        with pytest.raises(ValueError, match="not found"):
            work_service.advance("nonexistent")

    def test_advance_with_content_update(self, work_service, sample_work_item):
        new_content = "Updated content after advancement"
        item = work_service.advance(sample_work_item.id, new_content=new_content)
        assert item.content == new_content


class TestWorkServiceSetStage:
    """Tests for setting a specific stage."""

    def test_set_stage_to_valid_stage(self, work_service, sample_work_item):
        item = work_service.set_stage(sample_work_item.id, "planned")
        assert item.stage == "planned"

    def test_set_stage_invalid_stage_raises(self, work_service, sample_work_item):
        with pytest.raises(ValueError, match="Invalid stage"):
            work_service.set_stage(sample_work_item.id, "invalid")

    def test_set_stage_implementing_sets_started_at(self, work_service, sample_work_item):
        item = work_service.set_stage(sample_work_item.id, "implementing")
        assert item.started_at is not None

    def test_set_stage_terminal_sets_completed_at(self, work_service, sample_work_item):
        item = work_service.set_stage(sample_work_item.id, "done")
        assert item.completed_at is not None

    def test_set_stage_terminal_clears_claim(self, work_service, claimed_work_item):
        # Claim the item first
        assert claimed_work_item.claimed_by is not None

        # Move to terminal stage
        item = work_service.set_stage(claimed_work_item.id, "done")
        assert item.claimed_by is None
        assert item.claimed_at is None


class TestWorkServiceClaim:
    """Tests for claiming work items."""

    def test_claim_item(self, work_service, sample_work_item):
        item = work_service.claim(sample_work_item.id, "patrol:test")
        assert item.claimed_by == "patrol:test"
        assert item.claimed_at is not None

    def test_claim_already_claimed_by_same_raises(self, work_service, sample_work_item):
        work_service.claim(sample_work_item.id, "patrol:test")
        # Same claimer should work
        item = work_service.claim(sample_work_item.id, "patrol:test")
        assert item.claimed_by == "patrol:test"

    def test_claim_already_claimed_by_other_raises(self, work_service, sample_work_item):
        work_service.claim(sample_work_item.id, "patrol:first")
        with pytest.raises(ValueError, match="already claimed"):
            work_service.claim(sample_work_item.id, "patrol:second")

    def test_claim_not_found_raises(self, work_service):
        with pytest.raises(ValueError, match="not found"):
            work_service.claim("nonexistent", "patrol:test")


class TestWorkServiceRelease:
    """Tests for releasing claimed work items."""

    def test_release_claimed_item(self, work_service, claimed_work_item):
        item = work_service.release(claimed_work_item.id)
        assert item.claimed_by is None
        assert item.claimed_at is None

    def test_release_unclaimed_item(self, work_service, sample_work_item):
        # Should work without error
        item = work_service.release(sample_work_item.id)
        assert item.claimed_by is None


class TestWorkServiceDone:
    """Tests for marking work items as done."""

    def test_done_moves_to_terminal_stage(self, work_service, sample_work_item):
        item = work_service.done(sample_work_item.id)
        assert item.is_done is True

    def test_done_sets_completed_at(self, work_service, sample_work_item):
        item = work_service.done(sample_work_item.id)
        assert item.completed_at is not None

    def test_done_with_pr_number(self, work_service, sample_work_item):
        item = work_service.done(sample_work_item.id, pr_number=123)
        assert item.pr_number == 123

    def test_done_without_output_doc_id(self, work_service, sample_work_item):
        # Note: output_doc_id requires a valid document (foreign key)
        # Just test done() without output_doc_id since test DB may not have documents
        item = work_service.done(sample_work_item.id)
        assert item.output_doc_id is None

    def test_done_clears_claim(self, work_service, claimed_work_item):
        item = work_service.done(claimed_work_item.id)
        assert item.claimed_by is None

    def test_done_creates_transition(self, work_service, sample_work_item):
        old_stage = sample_work_item.stage
        work_service.done(sample_work_item.id)

        transitions = work_service.get_transitions(sample_work_item.id)
        last_trans = transitions[-1]
        assert last_trans.from_stage == old_stage
        assert last_trans.transitioned_by == "done"


class TestWorkServiceUpdate:
    """Tests for updating work item fields."""

    def test_update_title(self, work_service, sample_work_item):
        item = work_service.update(sample_work_item.id, title="New title")
        assert item.title == "New title"

    def test_update_content(self, work_service, sample_work_item):
        item = work_service.update(sample_work_item.id, content="New content")
        assert item.content == "New content"

    def test_update_priority(self, work_service, sample_work_item):
        item = work_service.update(sample_work_item.id, priority=0)
        assert item.priority == 0

    def test_update_type(self, work_service, sample_work_item):
        item = work_service.update(sample_work_item.id, type_="bug")
        assert item.type == "bug"

    def test_update_multiple_fields(self, work_service, sample_work_item):
        item = work_service.update(
            sample_work_item.id,
            title="New title",
            content="New content",
            priority=1,
        )
        assert item.title == "New title"
        assert item.content == "New content"
        assert item.priority == 1

    def test_update_no_changes(self, work_service, sample_work_item):
        item = work_service.update(sample_work_item.id)
        assert item.title == sample_work_item.title


class TestWorkServiceDelete:
    """Tests for deleting work items."""

    def test_delete_item(self, work_service, sample_work_item):
        result = work_service.delete(sample_work_item.id)
        assert result is True
        assert work_service.get(sample_work_item.id) is None

    def test_delete_nonexistent(self, work_service):
        result = work_service.delete("nonexistent")
        assert result is False


class TestWorkServiceDependencies:
    """Tests for dependency management."""

    def test_add_dependency(self, work_service, sample_work_items):
        item1, item2 = sample_work_items[:2]
        dep = work_service.add_dependency(item1.id, item2.id)
        assert dep.work_id == item1.id
        assert dep.depends_on == item2.id
        assert dep.dep_type == "blocks"

    def test_add_dependency_with_type(self, work_service, sample_work_items):
        item1, item2 = sample_work_items[:2]
        dep = work_service.add_dependency(item1.id, item2.id, dep_type="related")
        assert dep.dep_type == "related"

    def test_add_dependency_invalid_type_raises(self, work_service, sample_work_items):
        item1, item2 = sample_work_items[:2]
        with pytest.raises(ValueError, match="Invalid dependency type"):
            work_service.add_dependency(item1.id, item2.id, dep_type="invalid")

    def test_remove_dependency(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item
        result = work_service.remove_dependency(blocked.id, blocker.id)
        assert result is True

        # Item should no longer be blocked
        item = work_service.get(blocked.id)
        assert item.is_blocked is False

    def test_remove_nonexistent_dependency(self, work_service, sample_work_items):
        result = work_service.remove_dependency(sample_work_items[0].id, "nonexistent")
        assert result is False

    def test_get_dependencies(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item
        deps = work_service.get_dependencies(blocked.id)
        assert len(deps) == 1
        dep, dep_item = deps[0]
        assert dep.depends_on == blocker.id
        assert dep_item.id == blocker.id

    def test_get_dependents(self, work_service, blocked_work_item):
        blocked, blocker = blocked_work_item
        dependents = work_service.get_dependents(blocker.id)
        assert len(dependents) == 1
        dep, dep_item = dependents[0]
        assert dep.work_id == blocked.id
        assert dep_item.id == blocked.id


class TestWorkServiceStatistics:
    """Tests for statistics and query methods."""

    def test_get_stage_counts(self, work_service, sample_work_items):
        counts = work_service.get_stage_counts()
        assert "default" in counts
        assert isinstance(counts["default"], dict)

    def test_get_stage_counts_filter_cascade(self, work_service, sample_work_items, review_cascade):
        # Add a review item
        work_service.add(title="Review item", cascade="review")

        counts = work_service.get_stage_counts(cascade="default")
        assert "default" in counts
        assert "review" not in counts

    def test_get_transitions(self, work_service, sample_work_item):
        # Advance item to create more transitions
        work_service.advance(sample_work_item.id)
        work_service.advance(sample_work_item.id)

        transitions = work_service.get_transitions(sample_work_item.id)
        assert len(transitions) >= 3  # Initial + 2 advances

    def test_get_recent_transitions(self, work_service, sample_work_items):
        # Create some transitions
        work_service.advance(sample_work_items[0].id)
        work_service.advance(sample_work_items[1].id)

        transitions = work_service.get_recent_transitions(limit=5)
        assert len(transitions) <= 5
        # Should be ordered by created_at DESC
        if len(transitions) >= 2:
            assert transitions[0].created_at >= transitions[1].created_at
