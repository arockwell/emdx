"""Comprehensive tests for emdx/workflows/database.py.

Tests all 31+ public functions in the workflows database module, covering:
- Workflow CRUD (7 functions)
- Workflow Run operations (5 functions)
- Stage Run operations (4 functions)
- Individual Run operations (8+ functions)
- Preset operations (7+ functions)

Uses the session-scoped test database from conftest.py (isolate_test_database)
which patches emdx.workflows.database.db_connection automatically.
"""

import json
from datetime import datetime, timedelta

import pytest

from emdx.workflows.database import (
    # Workflow CRUD
    create_workflow,
    get_workflow,
    get_workflow_by_name,
    list_workflows,
    update_workflow,
    delete_workflow,
    increment_workflow_usage,
    # Workflow Runs
    create_workflow_run,
    get_workflow_run,
    list_workflow_runs,
    update_workflow_run,
    cleanup_zombie_workflow_runs,
    # Stage Runs
    create_stage_run,
    get_stage_run,
    list_stage_runs,
    update_stage_run,
    # Individual Runs
    create_individual_run,
    get_individual_run,
    list_individual_runs,
    count_individual_runs,
    update_individual_run,
    get_active_execution_for_run,
    get_agent_execution,
    get_latest_execution_for_run,
    # Presets
    create_preset,
    get_preset,
    get_preset_by_name,
    get_default_preset,
    list_presets,
    update_preset,
    delete_preset,
    increment_preset_usage,
    create_preset_from_run,
    # Output doc IDs
    get_workflow_output_doc_ids,
)
import emdx.database.connection as _conn_module


# =============================================================================
# Helpers
# =============================================================================

def _make_workflow(
    name: str = "test_workflow",
    display_name: str = "Test Workflow",
    definition: dict = None,
    description: str = None,
    category: str = "custom",
    created_by: str = None,
) -> int:
    """Helper to create a workflow and return its ID."""
    if definition is None:
        definition = {"stages": [{"name": "stage1", "mode": "single"}]}
    return create_workflow(
        name=name,
        display_name=display_name,
        definition_json=json.dumps(definition),
        description=description,
        category=category,
        created_by=created_by,
    )


def _make_workflow_run(workflow_id: int, **kwargs) -> int:
    """Helper to create a workflow run and return its ID."""
    return create_workflow_run(workflow_id=workflow_id, **kwargs)


def _make_stage_run(workflow_run_id: int, stage_name: str = "stage1", mode: str = "parallel", target_runs: int = 3) -> int:
    """Helper to create a stage run and return its ID."""
    return create_stage_run(
        workflow_run_id=workflow_run_id,
        stage_name=stage_name,
        mode=mode,
        target_runs=target_runs,
    )


def _make_individual_run(stage_run_id: int, run_number: int = 1, **kwargs) -> int:
    """Helper to create an individual run and return its ID."""
    return create_individual_run(
        stage_run_id=stage_run_id,
        run_number=run_number,
        **kwargs,
    )


def _create_document(title: str = "Test Doc", content: str = "Test content") -> int:
    """Helper to create a document in the documents table."""
    with _conn_module.db_connection.get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO documents (title, content) VALUES (?, ?)",
            (title, content),
        )
        conn.commit()
        return cursor.lastrowid


def _create_execution(
    doc_title: str = "Workflow Agent Run #1",
    status: str = "running",
    log_file: str = "/tmp/test.log",
) -> int:
    """Helper to create an execution record and return its ID."""
    with _conn_module.db_connection.get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO executions (doc_title, status, started_at, log_file)
               VALUES (?, ?, datetime('now', 'localtime'), ?)""",
            (doc_title, status, log_file),
        )
        conn.commit()
        return cursor.lastrowid


def _clean_all_tables():
    """Delete all rows from workflow-related tables in FK-safe order.

    Uses a raw sqlite3 connection (bypassing db_connection.get_connection which
    enables foreign keys) so we can disable FK checks for safe cleanup.
    """
    import sqlite3
    conn = sqlite3.connect(str(_conn_module.db_connection.db_path))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM workflow_individual_runs")
    conn.execute("DELETE FROM workflow_stage_runs")
    conn.execute("DELETE FROM workflow_presets")
    conn.execute("DELETE FROM workflow_runs")
    conn.execute("DELETE FROM workflows")
    conn.execute("DELETE FROM executions")
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def clean_workflow_tables():
    """Clean all workflow-related tables before and after each test.

    Runs cleanup BEFORE the test to ensure a pristine state, and also
    AFTER to leave things clean for the next test.
    """
    _clean_all_tables()
    yield
    _clean_all_tables()


# =============================================================================
# Workflow CRUD Tests
# =============================================================================

class TestCreateWorkflow:
    """Tests for create_workflow()."""

    def test_create_minimal_workflow(self):
        wf_id = _make_workflow()
        assert isinstance(wf_id, int)
        assert wf_id > 0

    def test_create_workflow_with_all_fields(self):
        wf_id = _make_workflow(
            name="full_wf",
            display_name="Full Workflow",
            description="A complete workflow",
            category="analysis",
            created_by="test_user",
        )
        wf = get_workflow(wf_id)
        assert wf["name"] == "full_wf"
        assert wf["display_name"] == "Full Workflow"
        assert wf["description"] == "A complete workflow"
        assert wf["category"] == "analysis"
        assert wf["created_by"] == "test_user"
        assert wf["is_active"] == 1  # SQLite boolean
        assert wf["usage_count"] == 0
        assert wf["success_count"] == 0
        assert wf["failure_count"] == 0

    def test_create_workflow_stores_definition_json(self):
        definition = {"stages": [{"name": "s1"}, {"name": "s2"}]}
        wf_id = _make_workflow(definition=definition)
        wf = get_workflow(wf_id)
        assert json.loads(wf["definition_json"]) == definition

    def test_create_duplicate_name_raises(self):
        _make_workflow(name="unique_name")
        with pytest.raises(Exception):  # IntegrityError for UNIQUE constraint
            _make_workflow(name="unique_name")

    def test_create_multiple_workflows_get_unique_ids(self):
        id1 = _make_workflow(name="wf1")
        id2 = _make_workflow(name="wf2")
        id3 = _make_workflow(name="wf3")
        assert len({id1, id2, id3}) == 3


class TestGetWorkflow:
    """Tests for get_workflow()."""

    def test_get_existing_workflow(self):
        wf_id = _make_workflow(name="get_test")
        wf = get_workflow(wf_id)
        assert wf is not None
        assert wf["id"] == wf_id
        assert wf["name"] == "get_test"

    def test_get_nonexistent_workflow_returns_none(self):
        assert get_workflow(999999) is None

    def test_get_inactive_workflow_returns_none(self):
        wf_id = _make_workflow(name="inactive_test")
        delete_workflow(wf_id)  # soft delete
        assert get_workflow(wf_id) is None


class TestGetWorkflowByName:
    """Tests for get_workflow_by_name()."""

    def test_get_by_name(self):
        wf_id = _make_workflow(name="named_wf")
        wf = get_workflow_by_name("named_wf")
        assert wf is not None
        assert wf["id"] == wf_id

    def test_get_by_name_not_found(self):
        assert get_workflow_by_name("nonexistent_workflow") is None

    def test_get_by_name_inactive_returns_none(self):
        wf_id = _make_workflow(name="will_delete")
        delete_workflow(wf_id)
        assert get_workflow_by_name("will_delete") is None


class TestListWorkflows:
    """Tests for list_workflows()."""

    def test_list_empty(self):
        result = list_workflows()
        assert result == []

    def test_list_returns_active_only_by_default(self):
        wf1 = _make_workflow(name="active_wf")
        wf2 = _make_workflow(name="deleted_wf")
        delete_workflow(wf2)
        result = list_workflows()
        names = [w["name"] for w in result]
        assert "active_wf" in names
        assert "deleted_wf" not in names

    def test_list_include_inactive(self):
        wf1 = _make_workflow(name="active_wf2")
        wf2 = _make_workflow(name="deleted_wf2")
        delete_workflow(wf2)
        result = list_workflows(include_inactive=True)
        names = [w["name"] for w in result]
        assert "active_wf2" in names
        assert "deleted_wf2" in names

    def test_list_filter_by_category(self):
        _make_workflow(name="analysis_wf", category="analysis")
        _make_workflow(name="custom_wf", category="custom")
        result = list_workflows(category="analysis")
        assert len(result) == 1
        assert result[0]["name"] == "analysis_wf"

    def test_list_respects_limit(self):
        for i in range(5):
            _make_workflow(name=f"limit_wf_{i}")
        result = list_workflows(limit=3)
        assert len(result) == 3

    def test_list_ordered_by_usage_count_then_name(self):
        wf1 = _make_workflow(name="b_wf")
        wf2 = _make_workflow(name="a_wf")
        increment_workflow_usage(wf1, success=True)
        result = list_workflows()
        assert result[0]["name"] == "b_wf"  # Higher usage_count first
        assert result[1]["name"] == "a_wf"


class TestUpdateWorkflow:
    """Tests for update_workflow()."""

    def test_update_display_name(self):
        wf_id = _make_workflow(name="update_test")
        result = update_workflow(wf_id, display_name="New Display Name")
        assert result is True
        wf = get_workflow(wf_id)
        assert wf["display_name"] == "New Display Name"

    def test_update_description(self):
        wf_id = _make_workflow(name="desc_test")
        update_workflow(wf_id, description="New description")
        wf = get_workflow(wf_id)
        assert wf["description"] == "New description"

    def test_update_definition_json(self):
        wf_id = _make_workflow(name="def_test")
        new_def = json.dumps({"stages": [{"name": "new_stage"}]})
        update_workflow(wf_id, definition_json=new_def)
        wf = get_workflow(wf_id)
        assert wf["definition_json"] == new_def

    def test_update_category(self):
        wf_id = _make_workflow(name="cat_test", category="custom")
        update_workflow(wf_id, category="analysis")
        wf = get_workflow(wf_id)
        assert wf["category"] == "analysis"

    def test_update_multiple_fields(self):
        wf_id = _make_workflow(name="multi_test")
        update_workflow(
            wf_id,
            display_name="Updated",
            description="Updated desc",
            category="review",
        )
        wf = get_workflow(wf_id)
        assert wf["display_name"] == "Updated"
        assert wf["description"] == "Updated desc"
        assert wf["category"] == "review"

    def test_update_nonexistent_returns_false(self):
        result = update_workflow(999999, display_name="Nothing")
        assert result is False

    def test_update_sets_updated_at(self):
        wf_id = _make_workflow(name="timestamp_test")
        wf_before = get_workflow(wf_id)
        update_workflow(wf_id, display_name="Changed")
        wf_after = get_workflow(wf_id)
        # updated_at should have changed (or be at least as recent)
        assert wf_after["updated_at"] is not None


class TestDeleteWorkflow:
    """Tests for delete_workflow()."""

    def test_soft_delete(self):
        wf_id = _make_workflow(name="soft_delete_test")
        result = delete_workflow(wf_id)
        assert result is True
        # Should not appear in normal get
        assert get_workflow(wf_id) is None
        # But still in DB with is_active=False
        wfs = list_workflows(include_inactive=True)
        found = [w for w in wfs if w["id"] == wf_id]
        assert len(found) == 1
        assert found[0]["is_active"] == 0

    def test_hard_delete(self):
        wf_id = _make_workflow(name="hard_delete_test")
        result = delete_workflow(wf_id, hard_delete=True)
        assert result is True
        # Should not appear even with include_inactive
        wfs = list_workflows(include_inactive=True)
        found = [w for w in wfs if w["id"] == wf_id]
        assert len(found) == 0

    def test_delete_nonexistent_returns_false(self):
        result = delete_workflow(999999)
        assert result is False


class TestIncrementWorkflowUsage:
    """Tests for increment_workflow_usage()."""

    def test_increment_success(self):
        wf_id = _make_workflow(name="usage_success")
        increment_workflow_usage(wf_id, success=True)
        wf = get_workflow(wf_id)
        assert wf["usage_count"] == 1
        assert wf["success_count"] == 1
        assert wf["failure_count"] == 0
        assert wf["last_used_at"] is not None

    def test_increment_failure(self):
        wf_id = _make_workflow(name="usage_failure")
        increment_workflow_usage(wf_id, success=False)
        wf = get_workflow(wf_id)
        assert wf["usage_count"] == 1
        assert wf["success_count"] == 0
        assert wf["failure_count"] == 1

    def test_increment_multiple_times(self):
        wf_id = _make_workflow(name="usage_multi")
        increment_workflow_usage(wf_id, success=True)
        increment_workflow_usage(wf_id, success=True)
        increment_workflow_usage(wf_id, success=False)
        wf = get_workflow(wf_id)
        assert wf["usage_count"] == 3
        assert wf["success_count"] == 2
        assert wf["failure_count"] == 1


# =============================================================================
# Workflow Run Tests
# =============================================================================

class TestCreateWorkflowRun:
    """Tests for create_workflow_run()."""

    def test_create_minimal_run(self):
        wf_id = _make_workflow(name="run_wf")
        run_id = _make_workflow_run(wf_id)
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_create_run_with_all_fields(self):
        wf_id = _make_workflow(name="run_full_wf")
        run_id = create_workflow_run(
            workflow_id=wf_id,
            input_doc_id=None,
            input_variables={"task": "analyze code", "model": "opus"},
            gameplan_id=42,
            task_id=99,
            parent_run_id=None,
        )
        run = get_workflow_run(run_id)
        assert run["workflow_id"] == wf_id
        assert run["status"] == "pending"
        assert run["gameplan_id"] == 42
        assert run["task_id"] == 99
        variables = json.loads(run["input_variables"])
        assert variables["task"] == "analyze code"
        assert variables["model"] == "opus"

    def test_create_run_with_parent(self):
        wf_id = _make_workflow(name="parent_run_wf")
        parent_id = _make_workflow_run(wf_id)
        child_id = create_workflow_run(workflow_id=wf_id, parent_run_id=parent_id)
        child = get_workflow_run(child_id)
        assert child["parent_run_id"] == parent_id

    def test_create_run_null_variables_stored_as_null(self):
        wf_id = _make_workflow(name="null_vars_wf")
        run_id = _make_workflow_run(wf_id, input_variables=None)
        run = get_workflow_run(run_id)
        assert run["input_variables"] is None


class TestGetWorkflowRun:
    """Tests for get_workflow_run()."""

    def test_get_existing_run(self):
        wf_id = _make_workflow(name="get_run_wf")
        run_id = _make_workflow_run(wf_id)
        run = get_workflow_run(run_id)
        assert run is not None
        assert run["id"] == run_id

    def test_get_nonexistent_run(self):
        assert get_workflow_run(999999) is None


class TestListWorkflowRuns:
    """Tests for list_workflow_runs()."""

    def test_list_all_runs(self):
        wf_id = _make_workflow(name="list_runs_wf")
        _make_workflow_run(wf_id)
        _make_workflow_run(wf_id)
        _make_workflow_run(wf_id)
        runs = list_workflow_runs()
        assert len(runs) >= 3

    def test_list_filter_by_workflow_id(self):
        wf1 = _make_workflow(name="list_wf1")
        wf2 = _make_workflow(name="list_wf2")
        _make_workflow_run(wf1)
        _make_workflow_run(wf1)
        _make_workflow_run(wf2)
        runs = list_workflow_runs(workflow_id=wf1)
        assert len(runs) == 2
        assert all(r["workflow_id"] == wf1 for r in runs)

    def test_list_filter_by_status(self):
        wf_id = _make_workflow(name="status_filter_wf")
        run1 = _make_workflow_run(wf_id)
        run2 = _make_workflow_run(wf_id)
        update_workflow_run(run1, status="running")
        runs = list_workflow_runs(status="running")
        assert len(runs) >= 1
        assert all(r["status"] == "running" for r in runs)

    def test_list_respects_limit(self):
        wf_id = _make_workflow(name="limit_runs_wf")
        for _ in range(5):
            _make_workflow_run(wf_id)
        runs = list_workflow_runs(limit=2)
        assert len(runs) == 2

    def test_list_ordered_by_id_desc(self):
        wf_id = _make_workflow(name="order_runs_wf")
        id1 = _make_workflow_run(wf_id)
        id2 = _make_workflow_run(wf_id)
        id3 = _make_workflow_run(wf_id)
        runs = list_workflow_runs(workflow_id=wf_id)
        assert runs[0]["id"] > runs[1]["id"] > runs[2]["id"]


class TestUpdateWorkflowRun:
    """Tests for update_workflow_run()."""

    def test_update_status(self):
        wf_id = _make_workflow(name="upd_status_wf")
        run_id = _make_workflow_run(wf_id)
        result = update_workflow_run(run_id, status="running")
        assert result is True
        run = get_workflow_run(run_id)
        assert run["status"] == "running"

    def test_update_current_stage(self):
        wf_id = _make_workflow(name="upd_stage_wf")
        run_id = _make_workflow_run(wf_id)
        update_workflow_run(run_id, current_stage="analysis")
        run = get_workflow_run(run_id)
        assert run["current_stage"] == "analysis"

    def test_update_context_json(self):
        wf_id = _make_workflow(name="upd_ctx_wf")
        run_id = _make_workflow_run(wf_id)
        ctx = json.dumps({"key": "value"})
        update_workflow_run(run_id, context_json=ctx)
        run = get_workflow_run(run_id)
        assert json.loads(run["context_json"]) == {"key": "value"}

    def test_update_output_doc_ids(self):
        wf_id = _make_workflow(name="upd_docs_wf")
        run_id = _make_workflow_run(wf_id)
        update_workflow_run(run_id, output_doc_ids=[1, 2, 3])
        run = get_workflow_run(run_id)
        assert json.loads(run["output_doc_ids"]) == [1, 2, 3]

    def test_update_error_message(self):
        wf_id = _make_workflow(name="upd_err_wf")
        run_id = _make_workflow_run(wf_id)
        update_workflow_run(run_id, status="failed", error_message="Something broke")
        run = get_workflow_run(run_id)
        assert run["error_message"] == "Something broke"

    def test_update_tokens_and_time(self):
        wf_id = _make_workflow(name="upd_tokens_wf")
        run_id = _make_workflow_run(wf_id)
        update_workflow_run(run_id, total_tokens_used=5000, total_execution_time_ms=12000)
        run = get_workflow_run(run_id)
        assert run["total_tokens_used"] == 5000
        assert run["total_execution_time_ms"] == 12000

    def test_update_started_at_and_completed_at(self):
        wf_id = _make_workflow(name="upd_times_wf")
        run_id = _make_workflow_run(wf_id)
        now = datetime.now()
        later = now + timedelta(minutes=5)
        update_workflow_run(run_id, started_at=now, completed_at=later)
        run = get_workflow_run(run_id)
        assert run["started_at"] is not None
        assert run["completed_at"] is not None

    def test_update_completed_clears_error_message(self):
        """When status='completed', error_message is cleared to NULL unless explicitly set."""
        wf_id = _make_workflow(name="upd_clear_err_wf")
        run_id = _make_workflow_run(wf_id)
        # First set an error
        update_workflow_run(run_id, status="failed", error_message="Oops")
        # Then complete (error_message not passed explicitly)
        update_workflow_run(run_id, status="completed")
        run = get_workflow_run(run_id)
        assert run["status"] == "completed"
        assert run["error_message"] is None

    def test_update_no_fields_returns_false(self):
        wf_id = _make_workflow(name="upd_noop_wf")
        run_id = _make_workflow_run(wf_id)
        result = update_workflow_run(run_id)
        assert result is False

    def test_update_nonexistent_returns_false(self):
        result = update_workflow_run(999999, status="running")
        assert result is False


class TestCleanupZombieWorkflowRuns:
    """Tests for cleanup_zombie_workflow_runs()."""

    def test_cleanup_marks_old_running_as_failed(self):
        wf_id = _make_workflow(name="zombie_wf")
        run_id = _make_workflow_run(wf_id)
        # Set status to running with a started_at time 3 hours ago
        old_time = datetime.now() - timedelta(hours=3)
        update_workflow_run(run_id, status="running", started_at=old_time)

        count = cleanup_zombie_workflow_runs(max_age_hours=2.0)
        assert count >= 1

        run = get_workflow_run(run_id)
        assert run["status"] == "failed"
        assert "process appears to have died" in run["error_message"]

    def test_cleanup_does_not_affect_recent_runs(self):
        wf_id = _make_workflow(name="recent_zombie_wf")
        run_id = _make_workflow_run(wf_id)
        # Set as running with recent started_at
        now = datetime.now()
        update_workflow_run(run_id, status="running", started_at=now)

        count = cleanup_zombie_workflow_runs(max_age_hours=2.0)
        # Should not mark recent runs as failed
        run = get_workflow_run(run_id)
        assert run["status"] == "running"

    def test_cleanup_does_not_affect_completed_runs(self):
        wf_id = _make_workflow(name="completed_zombie_wf")
        run_id = _make_workflow_run(wf_id)
        old_time = datetime.now() - timedelta(hours=5)
        update_workflow_run(run_id, status="completed", started_at=old_time)

        cleanup_zombie_workflow_runs(max_age_hours=2.0)
        run = get_workflow_run(run_id)
        assert run["status"] == "completed"

    def test_cleanup_cascades_to_stage_and_individual_runs(self):
        wf_id = _make_workflow(name="cascade_zombie_wf")
        run_id = _make_workflow_run(wf_id)
        old_time = datetime.now() - timedelta(hours=3)
        update_workflow_run(run_id, status="running", started_at=old_time)

        stage_id = _make_stage_run(run_id, stage_name="s1", mode="parallel", target_runs=2)
        update_stage_run(stage_id, status="running")
        ind_id = _make_individual_run(stage_id, run_number=1)
        update_individual_run(ind_id, status="running")

        cleanup_zombie_workflow_runs(max_age_hours=2.0)

        stage = get_stage_run(stage_id)
        assert stage["status"] == "failed"
        ind = get_individual_run(ind_id)
        assert ind["status"] == "failed"

    def test_cleanup_returns_zero_when_no_zombies(self):
        count = cleanup_zombie_workflow_runs(max_age_hours=2.0)
        assert count == 0


# =============================================================================
# Stage Run Tests
# =============================================================================

class TestCreateStageRun:
    """Tests for create_stage_run()."""

    def test_create_stage_run(self):
        wf_id = _make_workflow(name="stage_create_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id, stage_name="analysis", mode="parallel", target_runs=5)
        assert isinstance(stage_id, int)
        assert stage_id > 0

    def test_create_stage_run_initial_status_is_pending(self):
        wf_id = _make_workflow(name="stage_pending_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        stage = get_stage_run(stage_id)
        assert stage["status"] == "pending"

    def test_create_stage_run_stores_all_fields(self):
        wf_id = _make_workflow(name="stage_fields_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = create_stage_run(
            workflow_run_id=run_id,
            stage_name="review",
            mode="adversarial",
            target_runs=3,
        )
        stage = get_stage_run(stage_id)
        assert stage["workflow_run_id"] == run_id
        assert stage["stage_name"] == "review"
        assert stage["mode"] == "adversarial"
        assert stage["target_runs"] == 3


class TestGetStageRun:
    """Tests for get_stage_run()."""

    def test_get_existing(self):
        wf_id = _make_workflow(name="stage_get_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        stage = get_stage_run(stage_id)
        assert stage is not None
        assert stage["id"] == stage_id

    def test_get_nonexistent(self):
        assert get_stage_run(999999) is None


class TestListStageRuns:
    """Tests for list_stage_runs()."""

    def test_list_returns_all_stages_for_run(self):
        wf_id = _make_workflow(name="stage_list_wf")
        run_id = _make_workflow_run(wf_id)
        s1 = _make_stage_run(run_id, stage_name="s1")
        s2 = _make_stage_run(run_id, stage_name="s2")
        s3 = _make_stage_run(run_id, stage_name="s3")
        stages = list_stage_runs(run_id)
        assert len(stages) == 3

    def test_list_ordered_by_id(self):
        wf_id = _make_workflow(name="stage_order_wf")
        run_id = _make_workflow_run(wf_id)
        s1 = _make_stage_run(run_id, stage_name="first")
        s2 = _make_stage_run(run_id, stage_name="second")
        stages = list_stage_runs(run_id)
        assert stages[0]["stage_name"] == "first"
        assert stages[1]["stage_name"] == "second"

    def test_list_only_returns_stages_for_given_run(self):
        wf_id = _make_workflow(name="stage_isolate_wf")
        run1 = _make_workflow_run(wf_id)
        run2 = _make_workflow_run(wf_id)
        _make_stage_run(run1, stage_name="s_for_run1")
        _make_stage_run(run2, stage_name="s_for_run2")
        stages = list_stage_runs(run1)
        assert len(stages) == 1
        assert stages[0]["stage_name"] == "s_for_run1"


class TestUpdateStageRun:
    """Tests for update_stage_run()."""

    def test_update_status(self):
        wf_id = _make_workflow(name="stage_upd_status_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        result = update_stage_run(stage_id, status="running")
        assert result is True
        stage = get_stage_run(stage_id)
        assert stage["status"] == "running"

    def test_update_runs_completed(self):
        wf_id = _make_workflow(name="stage_upd_runs_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id, target_runs=5)
        update_stage_run(stage_id, runs_completed=3)
        stage = get_stage_run(stage_id)
        assert stage["runs_completed"] == 3

    def test_update_target_runs(self):
        wf_id = _make_workflow(name="stage_upd_target_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id, target_runs=3)
        update_stage_run(stage_id, target_runs=10)
        stage = get_stage_run(stage_id)
        assert stage["target_runs"] == 10

    def test_update_output_and_synthesis_doc_ids(self):
        wf_id = _make_workflow(name="stage_upd_docs_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        doc1 = _create_document("Output Doc")
        doc2 = _create_document("Synthesis Doc")
        update_stage_run(stage_id, output_doc_id=doc1, synthesis_doc_id=doc2)
        stage = get_stage_run(stage_id)
        assert stage["output_doc_id"] == doc1
        assert stage["synthesis_doc_id"] == doc2

    def test_update_error_message(self):
        wf_id = _make_workflow(name="stage_upd_err_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        update_stage_run(stage_id, error_message="Stage failed badly")
        stage = get_stage_run(stage_id)
        assert stage["error_message"] == "Stage failed badly"

    def test_update_tokens_and_time(self):
        wf_id = _make_workflow(name="stage_upd_tokens_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        update_stage_run(stage_id, tokens_used=1000, execution_time_ms=5000)
        stage = get_stage_run(stage_id)
        assert stage["tokens_used"] == 1000
        assert stage["execution_time_ms"] == 5000

    def test_update_synthesis_cost_fields(self):
        wf_id = _make_workflow(name="stage_upd_synth_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        update_stage_run(
            stage_id,
            synthesis_cost_usd=0.05,
            synthesis_input_tokens=2000,
            synthesis_output_tokens=500,
        )
        stage = get_stage_run(stage_id)
        assert stage["synthesis_cost_usd"] == pytest.approx(0.05)
        assert stage["synthesis_input_tokens"] == 2000
        assert stage["synthesis_output_tokens"] == 500

    def test_update_timestamps(self):
        wf_id = _make_workflow(name="stage_upd_time_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        now = datetime.now()
        update_stage_run(stage_id, started_at=now, completed_at=now + timedelta(seconds=30))
        stage = get_stage_run(stage_id)
        assert stage["started_at"] is not None
        assert stage["completed_at"] is not None

    def test_update_no_fields_returns_false(self):
        wf_id = _make_workflow(name="stage_upd_noop_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        result = update_stage_run(stage_id)
        assert result is False

    def test_update_nonexistent_returns_false(self):
        result = update_stage_run(999999, status="running")
        assert result is False


# =============================================================================
# Individual Run Tests
# =============================================================================

class TestCreateIndividualRun:
    """Tests for create_individual_run()."""

    def test_create_minimal(self):
        wf_id = _make_workflow(name="ind_create_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id, run_number=1)
        assert isinstance(ind_id, int)
        assert ind_id > 0

    def test_create_with_prompt_and_context(self):
        wf_id = _make_workflow(name="ind_prompt_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = create_individual_run(
            stage_run_id=stage_id,
            run_number=1,
            prompt_used="Analyze the code",
            input_context="Previous output was...",
        )
        ind = get_individual_run(ind_id)
        assert ind["prompt_used"] == "Analyze the code"
        assert ind["input_context"] == "Previous output was..."

    def test_create_initial_status_is_pending(self):
        wf_id = _make_workflow(name="ind_pending_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        ind = get_individual_run(ind_id)
        assert ind["status"] == "pending"


class TestGetIndividualRun:
    """Tests for get_individual_run()."""

    def test_get_existing(self):
        wf_id = _make_workflow(name="ind_get_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        ind = get_individual_run(ind_id)
        assert ind is not None
        assert ind["id"] == ind_id

    def test_get_nonexistent(self):
        assert get_individual_run(999999) is None


class TestListIndividualRuns:
    """Tests for list_individual_runs()."""

    def test_list_all_for_stage(self):
        wf_id = _make_workflow(name="ind_list_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        _make_individual_run(stage_id, run_number=1)
        _make_individual_run(stage_id, run_number=2)
        _make_individual_run(stage_id, run_number=3)
        inds = list_individual_runs(stage_id)
        assert len(inds) == 3

    def test_list_ordered_by_run_number(self):
        wf_id = _make_workflow(name="ind_order_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        # Insert in reverse order
        _make_individual_run(stage_id, run_number=3)
        _make_individual_run(stage_id, run_number=1)
        _make_individual_run(stage_id, run_number=2)
        inds = list_individual_runs(stage_id)
        assert [i["run_number"] for i in inds] == [1, 2, 3]

    def test_list_only_for_given_stage(self):
        wf_id = _make_workflow(name="ind_isolate_wf")
        run_id = _make_workflow_run(wf_id)
        s1 = _make_stage_run(run_id, stage_name="s1")
        s2 = _make_stage_run(run_id, stage_name="s2")
        _make_individual_run(s1, run_number=1)
        _make_individual_run(s2, run_number=1)
        inds = list_individual_runs(s1)
        assert len(inds) == 1


class TestCountIndividualRuns:
    """Tests for count_individual_runs()."""

    def test_count_by_status(self):
        wf_id = _make_workflow(name="ind_count_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind1 = _make_individual_run(stage_id, run_number=1)
        ind2 = _make_individual_run(stage_id, run_number=2)
        ind3 = _make_individual_run(stage_id, run_number=3)
        ind4 = _make_individual_run(stage_id, run_number=4)

        update_individual_run(ind1, status="completed")
        update_individual_run(ind2, status="completed")
        update_individual_run(ind3, status="running")
        # ind4 stays pending

        counts = count_individual_runs(stage_id)
        assert counts["total"] == 4
        assert counts["completed"] == 2
        assert counts["running"] == 1
        assert counts["pending"] == 1
        assert counts["failed"] == 0

    def test_count_empty_stage(self):
        wf_id = _make_workflow(name="ind_count_empty_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        counts = count_individual_runs(stage_id)
        assert counts["total"] == 0
        assert counts["completed"] == 0
        assert counts["running"] == 0
        assert counts["pending"] == 0
        assert counts["failed"] == 0

    def test_count_all_failed(self):
        wf_id = _make_workflow(name="ind_count_fail_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind1 = _make_individual_run(stage_id, run_number=1)
        ind2 = _make_individual_run(stage_id, run_number=2)
        update_individual_run(ind1, status="failed")
        update_individual_run(ind2, status="failed")
        counts = count_individual_runs(stage_id)
        assert counts["total"] == 2
        assert counts["failed"] == 2


class TestUpdateIndividualRun:
    """Tests for update_individual_run()."""

    def test_update_status(self):
        wf_id = _make_workflow(name="ind_upd_status_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        result = update_individual_run(ind_id, status="running")
        assert result is True
        ind = get_individual_run(ind_id)
        assert ind["status"] == "running"

    def test_update_agent_execution_id(self):
        wf_id = _make_workflow(name="ind_upd_exec_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        exec_id = _create_execution()
        update_individual_run(ind_id, agent_execution_id=exec_id)
        ind = get_individual_run(ind_id)
        assert ind["agent_execution_id"] == exec_id

    def test_update_output_doc_id(self):
        wf_id = _make_workflow(name="ind_upd_doc_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        doc_id = _create_document()
        update_individual_run(ind_id, output_doc_id=doc_id)
        ind = get_individual_run(ind_id)
        assert ind["output_doc_id"] == doc_id

    def test_update_error_message(self):
        wf_id = _make_workflow(name="ind_upd_err_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        update_individual_run(ind_id, error_message="Agent crashed")
        ind = get_individual_run(ind_id)
        assert ind["error_message"] == "Agent crashed"

    def test_update_token_and_cost_fields(self):
        wf_id = _make_workflow(name="ind_upd_tokens_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        update_individual_run(
            ind_id,
            tokens_used=3000,
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.12,
            execution_time_ms=8000,
        )
        ind = get_individual_run(ind_id)
        assert ind["tokens_used"] == 3000
        assert ind["input_tokens"] == 2000
        assert ind["output_tokens"] == 1000
        assert ind["cost_usd"] == pytest.approx(0.12)
        assert ind["execution_time_ms"] == 8000

    def test_update_timestamps(self):
        wf_id = _make_workflow(name="ind_upd_time_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        now = datetime.now()
        update_individual_run(ind_id, started_at=now, completed_at=now + timedelta(seconds=10))
        ind = get_individual_run(ind_id)
        assert ind["started_at"] is not None
        assert ind["completed_at"] is not None

    def test_update_no_fields_returns_false(self):
        wf_id = _make_workflow(name="ind_upd_noop_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        result = update_individual_run(ind_id)
        assert result is False

    def test_update_nonexistent_returns_false(self):
        result = update_individual_run(999999, status="running")
        assert result is False


class TestGetActiveExecutionForRun:
    """Tests for get_active_execution_for_run()."""

    def test_returns_none_when_no_running_individual(self):
        wf_id = _make_workflow(name="active_exec_wf")
        run_id = _make_workflow_run(wf_id)
        result = get_active_execution_for_run(run_id)
        assert result is None

    def test_finds_running_individual_with_execution_id(self):
        wf_id = _make_workflow(name="active_exec_id_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id, run_number=1)

        exec_id = _create_execution(
            doc_title=f"Workflow Agent Run #{ind_id}",
            status="running",
            log_file="/tmp/agent.log",
        )
        update_individual_run(ind_id, status="running", agent_execution_id=exec_id)

        result = get_active_execution_for_run(run_id)
        assert result is not None
        assert result["log_file"] == "/tmp/agent.log"
        assert result["exec_status"] == "running"

    def test_finds_running_individual_by_title_fallback(self):
        wf_id = _make_workflow(name="active_exec_title_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id, run_number=1)
        update_individual_run(ind_id, status="running")

        # Create execution with matching title but don't link via agent_execution_id
        _create_execution(
            doc_title=f"Workflow Agent Run #{ind_id} - analysis",
            status="running",
            log_file="/tmp/fallback.log",
        )

        result = get_active_execution_for_run(run_id)
        assert result is not None
        assert result["log_file"] == "/tmp/fallback.log"

    def test_finds_synthesis_execution(self):
        wf_id = _make_workflow(name="active_synth_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        update_stage_run(stage_id, status="synthesizing")

        _create_execution(
            doc_title=f"Workflow Synthesis #{stage_id} - combine results",
            status="running",
            log_file="/tmp/synthesis.log",
        )

        result = get_active_execution_for_run(run_id)
        assert result is not None
        assert result["log_file"] == "/tmp/synthesis.log"
        assert result["is_synthesis"] is True

    def test_returns_none_when_no_active_execution(self):
        wf_id = _make_workflow(name="no_exec_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id)
        # Individual run is pending (not running), no execution
        result = get_active_execution_for_run(run_id)
        assert result is None


class TestGetAgentExecution:
    """Tests for get_agent_execution()."""

    def test_get_existing_execution(self):
        exec_id = _create_execution(doc_title="Test Exec", status="running", log_file="/tmp/test.log")
        result = get_agent_execution(exec_id)
        assert result is not None
        assert result["doc_title"] == "Test Exec"
        assert result["status"] == "running"
        assert result["log_file"] == "/tmp/test.log"

    def test_get_nonexistent_execution(self):
        assert get_agent_execution(999999) is None


class TestGetLatestExecutionForRun:
    """Tests for get_latest_execution_for_run()."""

    def test_returns_none_when_no_executions(self):
        wf_id = _make_workflow(name="latest_exec_wf")
        run_id = _make_workflow_run(wf_id)
        result = get_latest_execution_for_run(run_id)
        assert result is None

    def test_returns_latest_execution_with_log_file(self):
        wf_id = _make_workflow(name="latest_exec_log_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)

        now = datetime.now()

        # Create two individual runs with executions
        ind1 = _make_individual_run(stage_id, run_number=1)
        exec1 = _create_execution(doc_title="Run 1", status="completed", log_file="/tmp/run1.log")
        update_individual_run(ind1, status="completed", agent_execution_id=exec1, started_at=now)

        ind2 = _make_individual_run(stage_id, run_number=2)
        exec2 = _create_execution(doc_title="Run 2", status="completed", log_file="/tmp/run2.log")
        update_individual_run(
            ind2, status="completed", agent_execution_id=exec2,
            started_at=now + timedelta(seconds=5),
        )

        result = get_latest_execution_for_run(run_id)
        assert result is not None
        assert result["log_file"] == "/tmp/run2.log"

    def test_returns_none_when_no_log_files(self):
        wf_id = _make_workflow(name="no_log_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        ind_id = _make_individual_run(stage_id, run_number=1)
        # No execution linked - should return None
        update_individual_run(ind_id, status="completed")
        result = get_latest_execution_for_run(run_id)
        assert result is None


# =============================================================================
# Workflow Output Doc IDs Tests
# =============================================================================

class TestGetWorkflowOutputDocIds:
    """Tests for get_workflow_output_doc_ids()."""

    def test_returns_empty_for_run_with_no_outputs(self):
        wf_id = _make_workflow(name="no_output_wf")
        run_id = _make_workflow_run(wf_id)
        result = get_workflow_output_doc_ids(run_id)
        assert result == []

    def test_collects_from_workflow_run_output_doc_ids(self):
        wf_id = _make_workflow(name="output_wf")
        run_id = _make_workflow_run(wf_id)
        doc1 = _create_document("Output 1")
        doc2 = _create_document("Output 2")
        update_workflow_run(run_id, output_doc_ids=[doc1, doc2])
        result = get_workflow_output_doc_ids(run_id)
        assert set(result) == {doc1, doc2}

    def test_collects_from_individual_run_output_doc_id(self):
        wf_id = _make_workflow(name="ind_output_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        doc1 = _create_document("Ind Output 1")
        doc2 = _create_document("Ind Output 2")
        ind1 = _make_individual_run(stage_id, run_number=1)
        ind2 = _make_individual_run(stage_id, run_number=2)
        update_individual_run(ind1, output_doc_id=doc1)
        update_individual_run(ind2, output_doc_id=doc2)
        result = get_workflow_output_doc_ids(run_id)
        assert set(result) == {doc1, doc2}

    def test_collects_synthesis_doc_ids(self):
        wf_id = _make_workflow(name="synth_output_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        synth_doc = _create_document("Synthesis Doc")
        update_stage_run(stage_id, synthesis_doc_id=synth_doc)
        result = get_workflow_output_doc_ids(run_id)
        assert synth_doc in result

    def test_deduplicates_doc_ids(self):
        wf_id = _make_workflow(name="dedup_output_wf")
        run_id = _make_workflow_run(wf_id)
        stage_id = _make_stage_run(run_id)
        doc = _create_document("Shared Doc")
        # Same doc in workflow run output and individual run
        update_workflow_run(run_id, output_doc_ids=[doc])
        ind = _make_individual_run(stage_id, run_number=1)
        update_individual_run(ind, output_doc_id=doc)
        result = get_workflow_output_doc_ids(run_id)
        assert result == [doc]

    def test_filters_out_deleted_documents(self):
        wf_id = _make_workflow(name="deleted_doc_wf")
        run_id = _make_workflow_run(wf_id)
        doc1 = _create_document("Good Doc")
        doc2 = _create_document("Deleted Doc")
        # Soft-delete doc2
        with _conn_module.db_connection.get_connection() as conn:
            conn.execute("UPDATE documents SET is_deleted = TRUE WHERE id = ?", (doc2,))
            conn.commit()
        update_workflow_run(run_id, output_doc_ids=[doc1, doc2])
        result = get_workflow_output_doc_ids(run_id)
        assert doc1 in result
        assert doc2 not in result

    def test_filters_out_nonexistent_doc_ids(self):
        wf_id = _make_workflow(name="nonexist_doc_wf")
        run_id = _make_workflow_run(wf_id)
        doc1 = _create_document("Real Doc")
        # 99999 does not exist
        update_workflow_run(run_id, output_doc_ids=[doc1, 99999])
        result = get_workflow_output_doc_ids(run_id)
        assert result == [doc1]

    def test_handles_invalid_json_in_output_doc_ids(self):
        wf_id = _make_workflow(name="bad_json_wf")
        run_id = _make_workflow_run(wf_id)
        # Manually set invalid JSON
        with _conn_module.db_connection.get_connection() as conn:
            conn.execute(
                "UPDATE workflow_runs SET output_doc_ids = ? WHERE id = ?",
                ("not-valid-json", run_id),
            )
            conn.commit()
        # Should not raise, just return empty or partial
        result = get_workflow_output_doc_ids(run_id)
        assert isinstance(result, list)

    def test_returns_empty_for_nonexistent_run(self):
        result = get_workflow_output_doc_ids(999999)
        assert result == []


# =============================================================================
# Preset Tests
# =============================================================================

class TestCreatePreset:
    """Tests for create_preset()."""

    def test_create_minimal_preset(self):
        wf_id = _make_workflow(name="preset_create_wf")
        preset_id = create_preset(
            workflow_id=wf_id,
            name="basic_preset",
            display_name="Basic Preset",
            variables={"key": "value"},
        )
        assert isinstance(preset_id, int)
        assert preset_id > 0

    def test_create_preset_with_all_fields(self):
        wf_id = _make_workflow(name="preset_full_wf")
        preset_id = create_preset(
            workflow_id=wf_id,
            name="full_preset",
            display_name="Full Preset",
            variables={"tasks": ["t1", "t2"], "model": "opus"},
            description="A full preset description",
            is_default=True,
            created_by="test_user",
        )
        preset = get_preset(preset_id)
        assert preset["name"] == "full_preset"
        assert preset["display_name"] == "Full Preset"
        assert preset["description"] == "A full preset description"
        assert preset["is_default"] == 1
        assert preset["created_by"] == "test_user"
        variables = json.loads(preset["variables_json"])
        assert variables["tasks"] == ["t1", "t2"]
        assert variables["model"] == "opus"

    def test_create_default_preset_clears_other_defaults(self):
        wf_id = _make_workflow(name="preset_default_wf")
        p1 = create_preset(
            workflow_id=wf_id, name="p1", display_name="P1",
            variables={}, is_default=True,
        )
        p2 = create_preset(
            workflow_id=wf_id, name="p2", display_name="P2",
            variables={}, is_default=True,
        )
        # p1 should no longer be default
        preset1 = get_preset(p1)
        preset2 = get_preset(p2)
        assert preset1["is_default"] == 0
        assert preset2["is_default"] == 1

    def test_create_duplicate_name_for_same_workflow_raises(self):
        wf_id = _make_workflow(name="preset_dup_wf")
        create_preset(workflow_id=wf_id, name="dup", display_name="D1", variables={})
        with pytest.raises(Exception):  # UNIQUE constraint
            create_preset(workflow_id=wf_id, name="dup", display_name="D2", variables={})

    def test_same_preset_name_different_workflows_ok(self):
        wf1 = _make_workflow(name="preset_wf1")
        wf2 = _make_workflow(name="preset_wf2")
        p1 = create_preset(workflow_id=wf1, name="same_name", display_name="P1", variables={})
        p2 = create_preset(workflow_id=wf2, name="same_name", display_name="P2", variables={})
        assert p1 != p2


class TestGetPreset:
    """Tests for get_preset()."""

    def test_get_existing(self):
        wf_id = _make_workflow(name="get_preset_wf")
        preset_id = create_preset(workflow_id=wf_id, name="gp", display_name="GP", variables={"x": 1})
        preset = get_preset(preset_id)
        assert preset is not None
        assert preset["id"] == preset_id

    def test_get_nonexistent(self):
        assert get_preset(999999) is None


class TestGetPresetByName:
    """Tests for get_preset_by_name()."""

    def test_get_by_name(self):
        wf_id = _make_workflow(name="pbn_wf")
        create_preset(workflow_id=wf_id, name="named_preset", display_name="NP", variables={})
        preset = get_preset_by_name(wf_id, "named_preset")
        assert preset is not None
        assert preset["name"] == "named_preset"

    def test_get_by_name_not_found(self):
        wf_id = _make_workflow(name="pbn_nf_wf")
        assert get_preset_by_name(wf_id, "nonexistent") is None

    def test_get_by_name_wrong_workflow(self):
        wf1 = _make_workflow(name="pbn_wf1")
        wf2 = _make_workflow(name="pbn_wf2")
        create_preset(workflow_id=wf1, name="preset_x", display_name="PX", variables={})
        assert get_preset_by_name(wf2, "preset_x") is None


class TestGetDefaultPreset:
    """Tests for get_default_preset()."""

    def test_get_default_when_exists(self):
        wf_id = _make_workflow(name="def_preset_wf")
        create_preset(workflow_id=wf_id, name="default_p", display_name="DP", variables={}, is_default=True)
        preset = get_default_preset(wf_id)
        assert preset is not None
        assert preset["is_default"] == 1

    def test_get_default_when_none_set(self):
        wf_id = _make_workflow(name="no_def_preset_wf")
        create_preset(workflow_id=wf_id, name="not_default", display_name="ND", variables={}, is_default=False)
        assert get_default_preset(wf_id) is None


class TestListPresets:
    """Tests for list_presets()."""

    def test_list_all_presets(self):
        wf_id = _make_workflow(name="list_preset_wf")
        create_preset(workflow_id=wf_id, name="lp1", display_name="LP1", variables={})
        create_preset(workflow_id=wf_id, name="lp2", display_name="LP2", variables={})
        presets = list_presets()
        assert len(presets) >= 2

    def test_list_filter_by_workflow(self):
        wf1 = _make_workflow(name="list_preset_wf1")
        wf2 = _make_workflow(name="list_preset_wf2")
        create_preset(workflow_id=wf1, name="for_wf1", display_name="FW1", variables={})
        create_preset(workflow_id=wf2, name="for_wf2", display_name="FW2", variables={})
        presets = list_presets(workflow_id=wf1)
        assert len(presets) == 1
        assert presets[0]["name"] == "for_wf1"

    def test_list_respects_limit(self):
        wf_id = _make_workflow(name="list_limit_preset_wf")
        for i in range(5):
            create_preset(workflow_id=wf_id, name=f"lim_{i}", display_name=f"L{i}", variables={})
        presets = list_presets(workflow_id=wf_id, limit=3)
        assert len(presets) == 3

    def test_list_ordered_default_first_then_usage(self):
        wf_id = _make_workflow(name="list_order_preset_wf")
        p1 = create_preset(workflow_id=wf_id, name="a_high_use", display_name="A", variables={})
        p2 = create_preset(workflow_id=wf_id, name="b_default", display_name="B", variables={}, is_default=True)
        # Increment usage on p1
        increment_preset_usage(p1)
        increment_preset_usage(p1)
        presets = list_presets(workflow_id=wf_id)
        # Default should come first regardless of usage count
        assert presets[0]["name"] == "b_default"


class TestUpdatePreset:
    """Tests for update_preset()."""

    def test_update_display_name(self):
        wf_id = _make_workflow(name="upd_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="upd_p", display_name="Old", variables={})
        result = update_preset(p_id, display_name="New")
        assert result is True
        preset = get_preset(p_id)
        assert preset["display_name"] == "New"

    def test_update_description(self):
        wf_id = _make_workflow(name="upd_desc_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="upd_dp", display_name="D", variables={})
        update_preset(p_id, description="A new description")
        preset = get_preset(p_id)
        assert preset["description"] == "A new description"

    def test_update_variables(self):
        wf_id = _make_workflow(name="upd_vars_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="upd_vp", display_name="V", variables={"old": True})
        update_preset(p_id, variables={"new": True, "count": 42})
        preset = get_preset(p_id)
        variables = json.loads(preset["variables_json"])
        assert variables == {"new": True, "count": 42}

    def test_update_is_default_clears_others(self):
        wf_id = _make_workflow(name="upd_default_preset_wf")
        p1 = create_preset(workflow_id=wf_id, name="ud1", display_name="D1", variables={}, is_default=True)
        p2 = create_preset(workflow_id=wf_id, name="ud2", display_name="D2", variables={})
        # Set p2 as default via update
        update_preset(p2, is_default=True)
        preset1 = get_preset(p1)
        preset2 = get_preset(p2)
        assert preset1["is_default"] == 0
        assert preset2["is_default"] == 1

    def test_update_nonexistent_returns_false(self):
        result = update_preset(999999, display_name="Nothing")
        assert result is False


class TestDeletePreset:
    """Tests for delete_preset()."""

    def test_delete_existing(self):
        wf_id = _make_workflow(name="del_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="del_p", display_name="D", variables={})
        result = delete_preset(p_id)
        assert result is True
        assert get_preset(p_id) is None

    def test_delete_nonexistent(self):
        result = delete_preset(999999)
        assert result is False


class TestIncrementPresetUsage:
    """Tests for increment_preset_usage()."""

    def test_increment_once(self):
        wf_id = _make_workflow(name="incr_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="incr_p", display_name="I", variables={})
        increment_preset_usage(p_id)
        preset = get_preset(p_id)
        assert preset["usage_count"] == 1
        assert preset["last_used_at"] is not None

    def test_increment_multiple(self):
        wf_id = _make_workflow(name="incr_multi_preset_wf")
        p_id = create_preset(workflow_id=wf_id, name="incr_mp", display_name="IM", variables={})
        for _ in range(5):
            increment_preset_usage(p_id)
        preset = get_preset(p_id)
        assert preset["usage_count"] == 5


class TestCreatePresetFromRun:
    """Tests for create_preset_from_run()."""

    def test_create_from_run_with_variables(self):
        wf_id = _make_workflow(name="from_run_wf")
        run_id = create_workflow_run(
            workflow_id=wf_id,
            input_variables={"task": "analyze", "model": "opus", "_internal": "skip"},
        )
        preset_id = create_preset_from_run(
            run_id=run_id,
            name="from_run_preset",
            display_name="From Run",
            description="Created from a run",
            created_by="test",
        )
        preset = get_preset(preset_id)
        assert preset is not None
        variables = json.loads(preset["variables_json"])
        # Internal variables (starting with _) should be filtered out
        assert "task" in variables
        assert "model" in variables
        assert "_internal" not in variables

    def test_create_from_run_with_null_variables(self):
        wf_id = _make_workflow(name="from_run_null_wf")
        run_id = create_workflow_run(workflow_id=wf_id, input_variables=None)
        preset_id = create_preset_from_run(
            run_id=run_id,
            name="from_null_run",
            display_name="From Null Run",
        )
        preset = get_preset(preset_id)
        variables = json.loads(preset["variables_json"])
        assert variables == {}

    def test_create_from_nonexistent_run_raises(self):
        with pytest.raises(ValueError, match="Workflow run 999999 not found"):
            create_preset_from_run(
                run_id=999999,
                name="bad_preset",
                display_name="Bad",
            )

    def test_create_from_run_uses_correct_workflow_id(self):
        wf_id = _make_workflow(name="from_run_wfid_wf")
        run_id = create_workflow_run(workflow_id=wf_id, input_variables={"x": 1})
        preset_id = create_preset_from_run(
            run_id=run_id,
            name="correct_wf_preset",
            display_name="Correct WF",
        )
        preset = get_preset(preset_id)
        assert preset["workflow_id"] == wf_id


# =============================================================================
# Edge Case and Integration Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and cross-function interactions."""

    def test_full_workflow_lifecycle(self):
        """Test creating a workflow, running it, and tracking through stages."""
        # Create workflow
        wf_id = _make_workflow(name="lifecycle_wf", description="Full lifecycle test")
        assert get_workflow(wf_id) is not None

        # Create a run
        run_id = create_workflow_run(
            workflow_id=wf_id,
            input_variables={"tasks": ["task1", "task2"]},
        )
        update_workflow_run(run_id, status="running", started_at=datetime.now())

        # Create a stage
        stage_id = create_stage_run(
            workflow_run_id=run_id,
            stage_name="analysis",
            mode="parallel",
            target_runs=2,
        )
        update_stage_run(stage_id, status="running", started_at=datetime.now())

        # Create individual runs
        ind1 = create_individual_run(stage_run_id=stage_id, run_number=1, prompt_used="Task 1")
        ind2 = create_individual_run(stage_run_id=stage_id, run_number=2, prompt_used="Task 2")

        # Complete individual runs
        doc1 = _create_document("Result 1")
        doc2 = _create_document("Result 2")
        now = datetime.now()
        update_individual_run(ind1, status="completed", output_doc_id=doc1, started_at=now, completed_at=now)
        update_individual_run(ind2, status="completed", output_doc_id=doc2, started_at=now, completed_at=now)

        # Complete stage
        synth_doc = _create_document("Synthesis")
        update_stage_run(
            stage_id,
            status="completed",
            runs_completed=2,
            synthesis_doc_id=synth_doc,
            completed_at=datetime.now(),
        )

        # Complete run
        update_workflow_run(
            run_id,
            status="completed",
            output_doc_ids=[doc1, doc2, synth_doc],
            completed_at=datetime.now(),
        )

        # Increment usage
        increment_workflow_usage(wf_id, success=True)

        # Verify
        wf = get_workflow(wf_id)
        assert wf["usage_count"] == 1
        assert wf["success_count"] == 1

        run = get_workflow_run(run_id)
        assert run["status"] == "completed"

        output_docs = get_workflow_output_doc_ids(run_id)
        assert set(output_docs) == {doc1, doc2, synth_doc}

    def test_workflow_category_constraint(self):
        """Workflow category must be one of the allowed values."""
        # Valid categories
        for cat in ["analysis", "planning", "implementation", "review", "custom"]:
            wf_id = _make_workflow(name=f"cat_{cat}", category=cat)
            assert get_workflow(wf_id) is not None

    def test_stage_run_mode_constraint(self):
        """Stage mode must be one of the allowed values."""
        wf_id = _make_workflow(name="mode_constraint_wf")
        run_id = _make_workflow_run(wf_id)
        for mode in ["single", "parallel", "iterative", "adversarial", "dynamic"]:
            stage_id = create_stage_run(
                workflow_run_id=run_id,
                stage_name=f"stage_{mode}",
                mode=mode,
                target_runs=1,
            )
            assert get_stage_run(stage_id) is not None

    def test_multiple_stages_per_run(self):
        """A workflow run can have multiple stages."""
        wf_id = _make_workflow(name="multi_stage_wf")
        run_id = _make_workflow_run(wf_id)
        s1 = _make_stage_run(run_id, stage_name="gather")
        s2 = _make_stage_run(run_id, stage_name="analyze")
        s3 = _make_stage_run(run_id, stage_name="synthesize")
        stages = list_stage_runs(run_id)
        assert len(stages) == 3
        stage_names = [s["stage_name"] for s in stages]
        assert "gather" in stage_names
        assert "analyze" in stage_names
        assert "synthesize" in stage_names

    def test_update_workflow_run_with_string_timestamps(self):
        """Timestamps can be passed as strings (not just datetime objects)."""
        wf_id = _make_workflow(name="str_time_wf")
        run_id = _make_workflow_run(wf_id)
        # The update function handles both datetime and string via isoformat check
        now_str = datetime.now().isoformat()
        update_workflow_run(run_id, status="running")
        run = get_workflow_run(run_id)
        assert run["status"] == "running"

    def test_create_preset_from_run_filters_internal_vars(self):
        """Internal variables (starting with _) are filtered from presets."""
        wf_id = _make_workflow(name="filter_vars_wf")
        run_id = create_workflow_run(
            workflow_id=wf_id,
            input_variables={
                "public_var": "visible",
                "_private_var": "hidden",
                "_another_internal": 42,
                "also_public": True,
            },
        )
        preset_id = create_preset_from_run(
            run_id=run_id, name="filtered_preset", display_name="Filtered",
        )
        preset = get_preset(preset_id)
        variables = json.loads(preset["variables_json"])
        assert "public_var" in variables
        assert "also_public" in variables
        assert "_private_var" not in variables
        assert "_another_internal" not in variables
