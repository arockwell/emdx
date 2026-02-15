"""Tests for cascade command CLI interface.

This module tests the cascade commands in emdx/commands/cascade.py:
- cascade add: Add ideas to the cascade pipeline
- cascade status: Show cascade status and document counts
- cascade show: Show documents at a specific stage
- cascade process: Process documents through stages
- cascade run: Run cascade continuously or in auto mode
- cascade advance: Manually advance documents between stages
- cascade remove: Remove documents from cascade
- cascade synthesize: Combine documents at a stage
- cascade runs: Show cascade run history
"""

import re
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.commands.cascade import (
    NEXT_STAGE,
    STAGE_PROMPTS,
    STAGES,
    _create_cascade_run,
    _get_stages_between,
    _update_cascade_run,
    app,
)

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_db_path():
    """Create a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture(scope="function")
def setup_cascade_db(test_db_path, monkeypatch):
    """Set up a test database with cascade tables.

    This fixture patches all necessary modules to use a test database.
    """
    monkeypatch.setenv("EMDX_TEST_DB", str(test_db_path))

    from emdx.database.connection import DatabaseConnection
    from emdx.database.migrations import run_migrations

    run_migrations(test_db_path)

    conn_instance = DatabaseConnection(test_db_path)

    # Patch the global db_connection in all relevant modules
    import emdx.commands.cascade as cascade_cmd_module
    import emdx.database.cascade as cascade_module
    import emdx.database.connection as conn_module
    import emdx.database.documents as docs_module

    original_conn = conn_module.db_connection

    conn_module.db_connection = conn_instance
    docs_module.db_connection = conn_instance
    cascade_module.db_connection = conn_instance
    cascade_cmd_module.db_connection = conn_instance

    yield conn_instance

    # Restore original
    conn_module.db_connection = original_conn
    docs_module.db_connection = original_conn
    cascade_module.db_connection = original_conn
    cascade_cmd_module.db_connection = original_conn


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestStageConfiguration:
    """Test cascade stage configuration constants."""

    def test_stages_are_valid(self):
        """Test that STAGES contains expected stages."""
        assert STAGES == ["idea", "prompt", "analyzed", "planned", "done"]

    def test_next_stage_mapping(self):
        """Test NEXT_STAGE maps correctly."""
        assert NEXT_STAGE["idea"] == "prompt"
        assert NEXT_STAGE["prompt"] == "analyzed"
        assert NEXT_STAGE["analyzed"] == "planned"
        assert NEXT_STAGE["planned"] == "done"

    def test_stage_prompts_exist(self):
        """Test that prompts exist for processable stages."""
        # All stages except 'done' should have prompts
        for stage in STAGES[:-1]:
            assert stage in STAGE_PROMPTS
            assert "{content}" in STAGE_PROMPTS[stage]


class TestGetStagesBetween:
    """Tests for _get_stages_between helper function."""

    def test_idea_to_done(self):
        """Test getting all stages from idea to done."""
        stages = _get_stages_between("idea", "done")
        assert stages == ["idea", "prompt", "analyzed", "planned"]

    def test_idea_to_analyzed(self):
        """Test partial stage range."""
        stages = _get_stages_between("idea", "analyzed")
        assert stages == ["idea", "prompt"]

    def test_prompt_to_planned(self):
        """Test mid-range stages."""
        stages = _get_stages_between("prompt", "planned")
        assert stages == ["prompt", "analyzed"]

    def test_same_stage_returns_empty(self):
        """Test that same start/stop returns empty list."""
        stages = _get_stages_between("idea", "idea")
        assert stages == []

    def test_single_stage(self):
        """Test single stage transition."""
        stages = _get_stages_between("planned", "done")
        assert stages == ["planned"]


# =============================================================================
# Cascade Add Command Tests
# =============================================================================


class TestCascadeAdd:
    """Tests for cascade add command."""

    @patch("emdx.commands.cascade.cascade_db")
    def test_add_basic(self, mock_cascade_db):
        """Test basic cascade add."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "Build a REST API"])
        assert result.exit_code == 0
        out = _out(result)
        assert "#42" in out
        assert "stage 'idea'" in out
        mock_cascade_db.save_document_to_cascade.assert_called_once()

    @patch("emdx.commands.cascade.cascade_db")
    def test_add_with_title(self, mock_cascade_db):
        """Test cascade add with custom title."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "Build a REST API", "--title", "REST API Feature"])
        assert result.exit_code == 0
        call_args = mock_cascade_db.save_document_to_cascade.call_args
        assert call_args.kwargs["title"] == "REST API Feature"

    @patch("emdx.commands.cascade.cascade_db")
    def test_add_with_custom_stage(self, mock_cascade_db):
        """Test cascade add with custom starting stage."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "My gameplan", "--stage", "planned"])
        assert result.exit_code == 0
        call_args = mock_cascade_db.save_document_to_cascade.call_args
        assert call_args.kwargs["stage"] == "planned"

    def test_add_invalid_stage(self):
        """Test cascade add with invalid stage."""
        result = runner.invoke(app, ["add", "Test", "--stage", "invalid"])
        assert result.exit_code == 1
        assert "Invalid stage" in _out(result)

    def test_add_stop_before_start(self):
        """Test cascade add with stop stage before start stage."""
        result = runner.invoke(app, ["add", "Test", "--stage", "planned", "--stop", "idea"])
        assert result.exit_code == 1
        assert "must be after" in _out(result)

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_add_with_auto_runs_pipeline(self, mock_cascade_db, mock_run_auto):
        """Test cascade add --auto triggers auto-run."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "Build API", "--auto"])
        assert result.exit_code == 0
        mock_run_auto.assert_called_once_with(42, "idea", "done")

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_add_analyze_shortcut(self, mock_cascade_db, mock_run_auto):
        """Test --analyze shortcut sets auto and stop stage."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "Build API", "--analyze"])
        assert result.exit_code == 0
        mock_run_auto.assert_called_once_with(42, "idea", "analyzed")

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_add_plan_shortcut(self, mock_cascade_db, mock_run_auto):
        """Test --plan shortcut sets auto and stop stage."""
        mock_cascade_db.save_document_to_cascade.return_value = 42
        result = runner.invoke(app, ["add", "Build API", "--plan"])
        assert result.exit_code == 0
        mock_run_auto.assert_called_once_with(42, "idea", "planned")


# =============================================================================
# Cascade Status Command Tests
# =============================================================================


class TestCascadeStatus:
    """Tests for cascade status command."""

    @patch("emdx.commands.cascade.db_connection")
    @patch("emdx.commands.cascade.cascade_db")
    def test_status_empty_cascade(self, mock_cascade_db, mock_db_conn):
        """Test status when cascade is empty."""
        mock_cascade_db.get_cascade_stats.return_value = {
            "idea": 0,
            "prompt": 0,
            "analyzed": 0,
            "planned": 0,
            "done": 0,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Cascade is empty" in out

    @patch("emdx.commands.cascade.db_connection")
    @patch("emdx.commands.cascade.cascade_db")
    def test_status_with_documents(self, mock_cascade_db, mock_db_conn):
        """Test status with documents at various stages."""
        mock_cascade_db.get_cascade_stats.return_value = {
            "idea": 3,
            "prompt": 2,
            "analyzed": 1,
            "planned": 0,
            "done": 5,
        }
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Total documents in cascade: 11" in out

    @patch("emdx.commands.cascade.db_connection")
    @patch("emdx.commands.cascade.cascade_db")
    def test_status_shows_active_runs(self, mock_cascade_db, mock_db_conn):
        """Test status shows active cascade runs."""
        mock_cascade_db.get_cascade_stats.return_value = {"idea": 1, "prompt": 0, "analyzed": 0, "planned": 0, "done": 0}
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, "idea", "done", "prompt", "running"),
        ]
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Active Cascade Runs" in out


# =============================================================================
# Cascade Show Command Tests
# =============================================================================


class TestCascadeShow:
    """Tests for cascade show command."""

    def test_show_invalid_stage(self):
        """Test show with invalid stage."""
        result = runner.invoke(app, ["show", "invalid"])
        assert result.exit_code == 1
        assert "Invalid stage" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    def test_show_empty_stage(self, mock_cascade_db):
        """Test show when stage has no documents."""
        mock_cascade_db.list_documents_at_stage.return_value = []
        result = runner.invoke(app, ["show", "idea"])
        assert result.exit_code == 0
        assert "No documents at stage 'idea'" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    def test_show_documents_at_stage(self, mock_cascade_db):
        """Test show displays documents at stage."""
        mock_cascade_db.list_documents_at_stage.return_value = [
            {"id": 1, "title": "Build REST API", "created_at": datetime.now()},
            {"id": 2, "title": "Add dark mode", "created_at": datetime.now()},
        ]
        result = runner.invoke(app, ["show", "idea"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Build REST API" in out
        assert "Add dark mode" in out

    @patch("emdx.commands.cascade.cascade_db")
    def test_show_with_limit(self, mock_cascade_db):
        """Test show respects limit parameter."""
        mock_cascade_db.list_documents_at_stage.return_value = []
        result = runner.invoke(app, ["show", "idea", "--limit", "5"])
        assert result.exit_code == 0
        mock_cascade_db.list_documents_at_stage.assert_called_with("idea", limit=5)


# =============================================================================
# Cascade Process Command Tests
# =============================================================================


class TestCascadeProcess:
    """Tests for cascade process command."""

    def test_process_done_stage_fails(self):
        """Test processing 'done' stage fails."""
        result = runner.invoke(app, ["process", "done"])
        assert result.exit_code == 1
        assert "terminal stage" in _out(result)

    def test_process_invalid_stage(self):
        """Test process with invalid stage."""
        result = runner.invoke(app, ["process", "invalid"])
        assert result.exit_code == 1
        assert "Invalid stage" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    def test_process_no_documents(self, mock_cascade_db):
        """Test process when no documents at stage."""
        mock_cascade_db.get_oldest_at_stage.return_value = None
        result = runner.invoke(app, ["process", "idea"])
        assert result.exit_code == 0
        assert "No documents waiting at stage" in _out(result)

    @patch("emdx.commands.cascade.get_document")
    def test_process_specific_doc_not_found(self, mock_get_doc):
        """Test process specific doc that doesn't exist."""
        mock_get_doc.return_value = None
        result = runner.invoke(app, ["process", "idea", "--doc", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    @patch("emdx.commands.cascade.get_document")
    def test_process_doc_wrong_stage(self, mock_get_doc):
        """Test process doc at wrong stage."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "prompt"}
        result = runner.invoke(app, ["process", "idea", "--doc", "42"])
        assert result.exit_code == 1
        assert "not 'idea'" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    def test_process_dry_run(self, mock_cascade_db):
        """Test process dry-run mode."""
        mock_cascade_db.get_oldest_at_stage.return_value = {
            "id": 42,
            "title": "Build REST API",
            "content": "...",
            "stage": "idea",
        }
        result = runner.invoke(app, ["process", "idea", "--dry-run"])
        assert result.exit_code == 0
        assert "Would process" in _out(result)
        assert "#42" in _out(result)

    @patch("emdx.commands.cascade._process_stage")
    @patch("emdx.commands.cascade.cascade_db")
    def test_process_sync_mode(self, mock_cascade_db, mock_process):
        """Test process in sync mode calls _process_stage."""
        mock_cascade_db.get_oldest_at_stage.return_value = {
            "id": 42,
            "title": "Build REST API",
            "content": "...",
            "stage": "idea",
        }
        mock_process.return_value = (True, 43, None)
        result = runner.invoke(app, ["process", "idea"])
        assert result.exit_code == 0
        mock_process.assert_called_once()

    @patch("emdx.commands.cascade.execute_claude_detached")
    @patch("emdx.commands.cascade.db_connection")
    @patch("emdx.commands.cascade.cascade_db")
    def test_process_async_mode(self, mock_cascade_db, mock_db_conn, mock_execute):
        """Test process in async mode starts detached process."""
        mock_cascade_db.get_oldest_at_stage.return_value = {
            "id": 42,
            "title": "Build REST API",
            "content": "...",
            "stage": "idea",
        }
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1
        mock_conn.execute.return_value = mock_cursor
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_execute.return_value = 12345  # PID

        result = runner.invoke(app, ["process", "idea", "--async"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Started processing" in out
        assert "PID: 12345" in out


# =============================================================================
# Cascade Advance Command Tests
# =============================================================================


class TestCascadeAdvance:
    """Tests for cascade advance command."""

    @patch("emdx.commands.cascade.get_document")
    def test_advance_doc_not_found(self, mock_get_doc):
        """Test advance for non-existent document."""
        mock_get_doc.return_value = None
        result = runner.invoke(app, ["advance", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    @patch("emdx.commands.cascade.get_document")
    def test_advance_doc_not_in_cascade(self, mock_get_doc):
        """Test advance for document not in cascade."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": None}
        result = runner.invoke(app, ["advance", "42"])
        assert result.exit_code == 1
        assert "not in the cascade" in _out(result)

    @patch("emdx.commands.cascade.get_document")
    def test_advance_doc_already_done(self, mock_get_doc):
        """Test advance for document already at done stage."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "done"}
        result = runner.invoke(app, ["advance", "42"])
        assert result.exit_code == 0
        assert "already at 'done'" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_advance_to_next_stage(self, mock_get_doc, mock_cascade_db):
        """Test advance moves to next stage."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "idea"}
        result = runner.invoke(app, ["advance", "42"])
        assert result.exit_code == 0
        out = _out(result)
        assert "idea → prompt" in out
        mock_cascade_db.update_cascade_stage.assert_called_with(42, "prompt")

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_advance_to_specific_stage(self, mock_get_doc, mock_cascade_db):
        """Test advance to specific stage with --to."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "idea"}
        result = runner.invoke(app, ["advance", "42", "--to", "done"])
        assert result.exit_code == 0
        out = _out(result)
        assert "idea → done" in out
        mock_cascade_db.update_cascade_stage.assert_called_with(42, "done")

    @patch("emdx.commands.cascade.get_document")
    def test_advance_invalid_target_stage(self, mock_get_doc):
        """Test advance with invalid target stage."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "idea"}
        result = runner.invoke(app, ["advance", "42", "--to", "invalid"])
        assert result.exit_code == 1
        assert "Invalid stage" in _out(result)


# =============================================================================
# Cascade Remove Command Tests
# =============================================================================


class TestCascadeRemove:
    """Tests for cascade remove command."""

    @patch("emdx.commands.cascade.get_document")
    def test_remove_doc_not_found(self, mock_get_doc):
        """Test remove for non-existent document."""
        mock_get_doc.return_value = None
        result = runner.invoke(app, ["remove", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    @patch("emdx.commands.cascade.get_document")
    def test_remove_doc_not_in_cascade(self, mock_get_doc):
        """Test remove for document not in cascade."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": None}
        result = runner.invoke(app, ["remove", "42"])
        assert result.exit_code == 0
        assert "not in the cascade" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_remove_success(self, mock_get_doc, mock_cascade_db):
        """Test successful removal from cascade."""
        mock_get_doc.return_value = {"id": 42, "title": "Test", "stage": "idea"}
        result = runner.invoke(app, ["remove", "42"])
        assert result.exit_code == 0
        assert "Removed document #42" in _out(result)
        mock_cascade_db.remove_from_cascade.assert_called_with(42)


# =============================================================================
# Cascade Run Command Tests
# =============================================================================


class TestCascadeRun:
    """Tests for cascade run command."""

    @patch("emdx.commands.cascade._process_stage")
    @patch("emdx.commands.cascade.cascade_db")
    def test_run_once_no_documents(self, mock_cascade_db, mock_process):
        """Test run --once with no documents."""
        mock_cascade_db.get_oldest_at_stage.return_value = None
        result = runner.invoke(app, ["run", "--once"])
        assert result.exit_code == 0
        assert "No documents to process" in _out(result)

    @patch("emdx.commands.cascade._process_stage")
    @patch("emdx.commands.cascade.cascade_db")
    def test_run_once_processes_one(self, mock_cascade_db, mock_process):
        """Test run --once processes exactly one document."""
        mock_cascade_db.get_oldest_at_stage.side_effect = [
            {"id": 42, "title": "Test", "content": "...", "stage": "idea"},
            None,  # After first iteration
        ]
        mock_process.return_value = (True, 43, None)
        result = runner.invoke(app, ["run", "--once"])
        assert result.exit_code == 0
        assert mock_process.call_count == 1

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_run_auto_once_no_ideas(self, mock_cascade_db, mock_run_auto):
        """Test run --auto --once with no ideas."""
        mock_cascade_db.get_oldest_at_stage.return_value = None
        result = runner.invoke(app, ["run", "--auto", "--once"])
        assert result.exit_code == 0
        assert "No ideas to process" in _out(result)
        mock_run_auto.assert_not_called()

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_run_auto_once_processes_idea(self, mock_cascade_db, mock_run_auto):
        """Test run --auto --once processes one idea."""
        mock_cascade_db.get_oldest_at_stage.return_value = {
            "id": 42,
            "title": "Build API",
            "content": "...",
            "stage": "idea",
        }
        result = runner.invoke(app, ["run", "--auto", "--once"])
        assert result.exit_code == 0
        mock_run_auto.assert_called_once_with(42, "idea", "done")

    @patch("emdx.commands.cascade._run_auto")
    @patch("emdx.commands.cascade.cascade_db")
    def test_run_auto_with_stop(self, mock_cascade_db, mock_run_auto):
        """Test run --auto with custom stop stage."""
        mock_cascade_db.get_oldest_at_stage.return_value = {
            "id": 42,
            "title": "Build API",
            "content": "...",
            "stage": "idea",
        }
        result = runner.invoke(app, ["run", "--auto", "--once", "--stop", "planned"])
        assert result.exit_code == 0
        mock_run_auto.assert_called_once_with(42, "idea", "planned")


# =============================================================================
# Cascade Synthesize Command Tests
# =============================================================================


class TestCascadeSynthesize:
    """Tests for cascade synthesize command."""

    @patch("emdx.commands.cascade.cascade_db")
    def test_synthesize_no_documents(self, mock_cascade_db):
        """Test synthesize with no documents at stage."""
        mock_cascade_db.list_documents_at_stage.return_value = []
        result = runner.invoke(app, ["synthesize", "analyzed"])
        assert result.exit_code == 0
        assert "No documents at stage" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    def test_synthesize_single_document(self, mock_cascade_db):
        """Test synthesize with only one document."""
        mock_cascade_db.list_documents_at_stage.return_value = [
            {"id": 42, "title": "Single Doc"},
        ]
        result = runner.invoke(app, ["synthesize", "analyzed"])
        assert result.exit_code == 0
        assert "Only 1 document" in _out(result)

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_synthesize_creates_combined(self, mock_get_doc, mock_cascade_db):
        """Test synthesize creates combined document."""
        mock_cascade_db.list_documents_at_stage.return_value = [
            {"id": 1, "title": "Analysis 1"},
            {"id": 2, "title": "Analysis 2"},
        ]
        mock_get_doc.side_effect = [
            {"id": 1, "title": "Analysis 1", "content": "Content 1"},
            {"id": 2, "title": "Analysis 2", "content": "Content 2"},
        ]
        mock_cascade_db.save_document_to_cascade.return_value = 10

        result = runner.invoke(app, ["synthesize", "analyzed"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Created synthesized document #10" in out
        # Verify source docs were moved to done
        assert mock_cascade_db.update_cascade_stage.call_count == 2

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_synthesize_with_keep(self, mock_get_doc, mock_cascade_db):
        """Test synthesize with --keep doesn't move source docs."""
        mock_cascade_db.list_documents_at_stage.return_value = [
            {"id": 1, "title": "Analysis 1"},
            {"id": 2, "title": "Analysis 2"},
        ]
        mock_get_doc.side_effect = [
            {"id": 1, "title": "Analysis 1", "content": "Content 1"},
            {"id": 2, "title": "Analysis 2", "content": "Content 2"},
        ]
        mock_cascade_db.save_document_to_cascade.return_value = 10

        result = runner.invoke(app, ["synthesize", "analyzed", "--keep"])
        assert result.exit_code == 0
        # Source docs should NOT be moved to done
        mock_cascade_db.update_cascade_stage.assert_not_called()

    @patch("emdx.commands.cascade.cascade_db")
    @patch("emdx.commands.cascade.get_document")
    def test_synthesize_custom_next_stage(self, mock_get_doc, mock_cascade_db):
        """Test synthesize with custom next stage."""
        mock_cascade_db.list_documents_at_stage.return_value = [
            {"id": 1, "title": "A1"},
            {"id": 2, "title": "A2"},
        ]
        mock_get_doc.side_effect = [
            {"id": 1, "title": "A1", "content": "C1"},
            {"id": 2, "title": "A2", "content": "C2"},
        ]
        mock_cascade_db.save_document_to_cascade.return_value = 10

        result = runner.invoke(app, ["synthesize", "analyzed", "--next", "done"])
        assert result.exit_code == 0
        call_args = mock_cascade_db.save_document_to_cascade.call_args
        assert call_args.kwargs["stage"] == "done"


# =============================================================================
# Cascade Runs Command Tests
# =============================================================================


class TestCascadeRuns:
    """Tests for cascade runs command."""

    @patch("emdx.commands.cascade.db_connection")
    def test_runs_empty(self, mock_db_conn):
        """Test runs when no cascade runs exist."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["runs"])
        assert result.exit_code == 0
        assert "No cascade runs found" in _out(result)

    @patch("emdx.commands.cascade.db_connection")
    def test_runs_shows_history(self, mock_db_conn):
        """Test runs displays run history."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, 42, "idea", "done", "done", "completed", "https://github.com/test/repo/pull/1", datetime.now(), datetime.now()),
            (2, 43, "idea", "planned", "analyzed", "running", None, datetime.now(), None),
        ]
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["runs"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Cascade Runs" in out

    @patch("emdx.commands.cascade.db_connection")
    def test_runs_with_limit(self, mock_db_conn):
        """Test runs respects limit parameter."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["runs", "--limit", "5"])
        assert result.exit_code == 0
        # Verify the query includes the limit
        call_args = mock_conn.execute.call_args
        assert 5 in call_args[0][1]

    @patch("emdx.commands.cascade.db_connection")
    def test_runs_with_status_filter(self, mock_db_conn):
        """Test runs with status filter."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(app, ["runs", "--status", "running"])
        assert result.exit_code == 0
        # Verify the query includes status filter
        call_args = mock_conn.execute.call_args
        assert "running" in call_args[0][1]


# =============================================================================
# Cascade Run Helper Function Tests
# =============================================================================


class TestCascadeRunHelpers:
    """Tests for cascade run helper functions."""

    @patch("emdx.commands.cascade.db_connection")
    def test_create_cascade_run(self, mock_db_conn):
        """Test _create_cascade_run creates a run record."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 99
        mock_conn.execute.return_value = mock_cursor
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        run_id = _create_cascade_run(42, "idea", "done")
        assert run_id == 99
        mock_conn.commit.assert_called_once()

    @patch("emdx.commands.cascade.db_connection")
    def test_update_cascade_run_status(self, mock_db_conn):
        """Test _update_cascade_run updates status."""
        mock_conn = MagicMock()
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        _update_cascade_run(99, status="completed")
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("emdx.commands.cascade.db_connection")
    def test_update_cascade_run_multiple_fields(self, mock_db_conn):
        """Test _update_cascade_run with multiple fields."""
        mock_conn = MagicMock()
        mock_db_conn.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_conn.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        _update_cascade_run(
            99,
            current_doc_id=50,
            current_stage="planned",
            pr_url="https://github.com/test/repo/pull/1",
        )
        call_args = mock_conn.execute.call_args
        query = call_args[0][0]
        assert "current_doc_id" in query
        assert "current_stage" in query
        assert "pr_url" in query


# =============================================================================
# Integration Tests with Real Database
# =============================================================================


class TestCascadeIntegration:
    """Integration tests using real database operations."""

    def test_add_and_show_integration(self, setup_cascade_db):
        """Test adding and showing cascade documents."""

        # Add a document
        result = runner.invoke(app, ["add", "Build a REST API"])
        assert result.exit_code == 0

        # Should be visible in show
        result = runner.invoke(app, ["show", "idea"])
        assert result.exit_code == 0
        assert "REST API" in _out(result)

    def test_add_and_advance_integration(self, setup_cascade_db):
        """Test adding and advancing cascade documents."""
        from emdx.database import cascade as cascade_db

        # Add a document
        result = runner.invoke(app, ["add", "Test idea"])
        assert result.exit_code == 0
        # Extract doc ID from output
        out = _out(result)
        doc_id = int(re.search(r"#(\d+)", out).group(1))

        # Advance it
        result = runner.invoke(app, ["advance", str(doc_id)])
        assert result.exit_code == 0
        assert "idea → prompt" in _out(result)

        # Verify it moved
        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata["stage"] == "prompt"

    def test_add_and_remove_integration(self, setup_cascade_db):
        """Test adding and removing cascade documents."""
        from emdx.database import cascade as cascade_db

        # Add a document
        result = runner.invoke(app, ["add", "Temporary idea"])
        assert result.exit_code == 0
        out = _out(result)
        doc_id = int(re.search(r"#(\d+)", out).group(1))

        # Remove it from cascade
        result = runner.invoke(app, ["remove", str(doc_id)])
        assert result.exit_code == 0

        # Verify it's removed from cascade but document still exists
        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is None

    def test_status_reflects_counts(self, setup_cascade_db):
        """Test status correctly shows document counts."""
        # Add multiple documents
        runner.invoke(app, ["add", "Idea 1"])
        runner.invoke(app, ["add", "Idea 2"])
        runner.invoke(app, ["add", "Idea 3"])

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Total documents in cascade: 3" in out
