"""Shared fixtures for work system tests."""

import json
import pytest
from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock, patch

from emdx.work.models import Cascade, WorkItem, WorkDep, WorkTransition
from emdx.work.service import WorkService, generate_work_id


# =============================================================================
# WORK SERVICE FIXTURES
# =============================================================================

@pytest.fixture
def work_service():
    """Create a fresh WorkService instance for testing.

    The service will use the test database from conftest.py's
    isolate_test_database fixture.
    """
    service = WorkService()
    # Clear cascade cache to ensure fresh state
    service._invalidate_cascade_cache()
    return service


@pytest.fixture
def default_cascade(work_service):
    """Ensure the default cascade exists and return it."""
    cascade = work_service.get_cascade("default")
    if not cascade:
        # Create default cascade if it doesn't exist
        cascade = work_service.create_cascade(
            name="default",
            stages=["idea", "prompt", "analyzed", "planned", "implementing", "done"],
            processors={
                "idea": "Transform this idea into a well-formed prompt.",
                "prompt": "Analyze this prompt for implementation.",
                "analyzed": "Create a detailed plan for implementation.",
                "planned": "Implement the planned changes.",
            },
            description="Default cascade for general work items",
        )
    return cascade


@pytest.fixture
def review_cascade(work_service):
    """Ensure the review cascade exists and return it."""
    cascade = work_service.get_cascade("review")
    if not cascade:
        cascade = work_service.create_cascade(
            name="review",
            stages=["draft", "reviewed", "revised", "approved", "merged"],
            processors={
                "draft": "Review this draft for quality.",
                "reviewed": "Make revisions based on feedback.",
            },
            description="Review workflow cascade",
        )
    return cascade


@pytest.fixture
def sample_work_item(work_service, default_cascade):
    """Create a sample work item for testing."""
    item = work_service.add(
        title="Test Work Item",
        cascade="default",
        content="This is test content for the work item.",
        priority=2,
        type_="task",
    )
    return item


@pytest.fixture
def sample_work_items(work_service, default_cascade):
    """Create multiple work items with varying properties."""
    items = []

    # Item 1: High priority, idea stage
    items.append(work_service.add(
        title="Critical bug fix",
        cascade="default",
        priority=0,
        type_="bug",
        content="Fix the critical null pointer exception",
    ))

    # Item 2: Medium priority, planned stage
    item = work_service.add(
        title="New feature implementation",
        cascade="default",
        priority=2,
        type_="feature",
        content="Implement user authentication",
    )
    # Advance to planned
    work_service.set_stage(item.id, "planned", "test")
    items.append(work_service.get(item.id))

    # Item 3: Low priority
    items.append(work_service.add(
        title="Documentation update",
        cascade="default",
        priority=3,
        type_="task",
        content="Update the README",
    ))

    return items


@pytest.fixture
def blocked_work_item(work_service, default_cascade):
    """Create a work item that is blocked by another."""
    # Create the blocker item
    blocker = work_service.add(
        title="Prerequisite task",
        cascade="default",
        content="This must be done first",
    )

    # Create the blocked item with dependency
    blocked = work_service.add(
        title="Dependent task",
        cascade="default",
        content="This depends on the prerequisite",
        depends_on=[blocker.id],
    )

    return blocked, blocker


@pytest.fixture
def claimed_work_item(work_service, default_cascade):
    """Create a work item that is claimed by an agent."""
    item = work_service.add(
        title="Claimed work item",
        cascade="default",
        content="This item is claimed",
    )
    work_service.claim(item.id, "patrol:test")
    return work_service.get(item.id)


# =============================================================================
# MODEL FIXTURES
# =============================================================================

@pytest.fixture
def cascade_row():
    """Sample database row for Cascade.from_row()."""
    return (
        "test-cascade",
        '["stage1", "stage2", "stage3"]',
        '{"stage1": "Process stage 1", "stage2": "Process stage 2"}',
        "Test cascade description",
        "2024-01-01T12:00:00",
    )


@pytest.fixture
def work_item_row():
    """Sample database row for WorkItem.from_row()."""
    return (
        "emdx-abc123",  # id
        "Test Item",  # title
        "Test content",  # content
        "default",  # cascade
        "idea",  # stage
        2,  # priority
        "task",  # type
        None,  # parent_id
        "test-project",  # project
        None,  # pr_number
        None,  # output_doc_id
        "2024-01-01T12:00:00",  # created_at
        "2024-01-01T12:00:00",  # updated_at
        None,  # started_at
        None,  # completed_at
        None,  # claimed_by
        None,  # claimed_at
    )


@pytest.fixture
def work_dep_row():
    """Sample database row for WorkDep.from_row()."""
    return (
        "emdx-abc123",  # work_id
        "emdx-def456",  # depends_on
        "blocks",  # dep_type
        "2024-01-01T12:00:00",  # created_at
    )


@pytest.fixture
def work_transition_row():
    """Sample database row for WorkTransition.from_row()."""
    return (
        1,  # id
        "emdx-abc123",  # work_id
        "idea",  # from_stage
        "prompt",  # to_stage
        "patrol:test",  # transitioned_by
        "Transition content snapshot",  # content_snapshot
        "2024-01-01T12:00:00",  # created_at
    )


# =============================================================================
# PATROL FIXTURES
# =============================================================================

@pytest.fixture
def patrol_config():
    """Create a test PatrolConfig."""
    from emdx.services.patrol import PatrolConfig
    return PatrolConfig(
        name="patrol:test",
        cascade=None,
        stage=None,
        poll_interval=1,  # Fast polling for tests
        max_items=1,
        timeout=30,
        dry_run=False,
    )


@pytest.fixture
def patrol_runner(patrol_config):
    """Create a PatrolRunner instance."""
    from emdx.services.patrol import PatrolRunner
    return PatrolRunner(patrol_config)


@pytest.fixture
def mock_execute_claude_sync():
    """Mock the execute_claude_sync function."""
    with patch('emdx.services.patrol.execute_claude_sync') as mock:
        mock.return_value = {
            "success": True,
            "output": "Claude output from processing",
        }
        yield mock


@pytest.fixture
def mock_create_execution():
    """Mock the create_execution function."""
    with patch('emdx.services.patrol.create_execution') as mock:
        mock.return_value = 1  # Return execution ID
        yield mock


@pytest.fixture
def mock_update_execution_status():
    """Mock the update_execution_status function."""
    with patch('emdx.services.patrol.update_execution_status') as mock:
        yield mock


# =============================================================================
# CLI FIXTURES
# =============================================================================

@pytest.fixture
def cli_runner():
    """Create a Typer CLI test runner."""
    from typer.testing import CliRunner
    return CliRunner()


@pytest.fixture
def work_app():
    """Get the work command Typer app."""
    from emdx.commands.work import app
    return app


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def make_work_item(
    id: str = "emdx-test01",
    title: str = "Test Item",
    stage: str = "idea",
    cascade: str = "default",
    content: Optional[str] = None,
    priority: int = 3,
    type_: str = "task",
    is_blocked: bool = False,
    blocked_by: Optional[List[str]] = None,
    claimed_by: Optional[str] = None,
) -> WorkItem:
    """Factory function to create WorkItem instances for testing."""
    return WorkItem(
        id=id,
        title=title,
        stage=stage,
        cascade=cascade,
        content=content,
        priority=priority,
        type=type_,
        is_blocked=is_blocked,
        blocked_by=blocked_by or [],
        claimed_by=claimed_by,
    )


def make_cascade(
    name: str = "test-cascade",
    stages: Optional[List[str]] = None,
    processors: Optional[dict] = None,
) -> Cascade:
    """Factory function to create Cascade instances for testing."""
    return Cascade(
        name=name,
        stages=stages or ["stage1", "stage2", "stage3"],
        processors=processors or {},
    )
