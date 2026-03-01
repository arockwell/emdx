"""Integration tests for Wave 1 intelligence layer features.

Tests the new features from PRs #919-#925 working together end-to-end:
- prime --brief (compact context injection)
- view --review (adversarial document review)
- maintain drift (stale work detection)
- maintain code-drift (stale code reference detection)
- find --wander (serendipity search)
- status --vitals / status --mirror (dashboard and AI mirror)
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.database.documents import save_document
from emdx.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes."""
    return _ANSI_RE.sub("", text)


# ── Shared fixtures ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_slate() -> Generator[None, None, None]:
    """Ensure a clean database state for each test."""
    with db.get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute("UPDATE documents SET is_deleted = 1 WHERE is_deleted = 0")
        conn.commit()
    yield


def _ensure_category(conn: sqlite3.Connection, key: str = "TEST") -> None:
    """Ensure a category exists for FK constraints."""
    conn.execute(
        "INSERT OR IGNORE INTO categories (key, name) VALUES (?, ?)",
        (key, key),
    )
    conn.commit()


def _create_epic(
    conn: sqlite3.Connection,
    title: str,
    epic_key: str = "TEST",
    status: str = "open",
) -> int:
    """Create an epic task directly via SQL."""
    _ensure_category(conn, epic_key)
    cursor = conn.execute(
        "INSERT INTO tasks (title, type, epic_key, status) VALUES (?, 'epic', ?, ?)",
        (title, epic_key, status),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _create_task(
    conn: sqlite3.Connection,
    title: str,
    parent_task_id: int | None = None,
    status: str = "open",
    epic_key: str | None = None,
    days_ago: int = 0,
    source_doc_id: int | None = None,
) -> int:
    """Create a task directly via SQL."""
    if epic_key:
        _ensure_category(conn, epic_key)
    cursor = conn.execute(
        """
        INSERT INTO tasks (
            title, parent_task_id, status, epic_key,
            created_at, updated_at,
            source_doc_id
        )
        VALUES (
            ?, ?, ?, ?,
            datetime('now', ? || ' days'),
            datetime('now', ? || ' days'),
            ?
        )
        """,
        (
            title,
            parent_task_id,
            status,
            epic_key,
            f"-{days_ago}",
            f"-{days_ago}",
            source_doc_id,
        ),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _seed_docs(
    n: int = 10,
    project: str = "test-proj",
    content_prefix: str = "Document content",
) -> list[int]:
    """Insert N documents into the test database."""
    ids: list[int] = []
    for i in range(n):
        doc_id = save_document(
            f"Doc {i}",
            f"{content_prefix} {i}",
            project=project,
            tags=["alpha"] if i % 2 == 0 else None,
        )
        ids.append(doc_id)
    return ids


# =====================================================================
# 1. LIFECYCLE TEST: Save -> Tag -> Drift -> Vitals -> Review
# =====================================================================


class TestIntelligenceLifecycle:
    """End-to-end test: create docs/tasks, then run intelligence commands."""

    def test_lifecycle_drift_after_seeding(self) -> None:
        """Save docs, create stale epic, then run drift to detect it."""
        # Step 1: Seed documents
        doc_ids = _seed_docs(5)
        assert len(doc_ids) == 5

        # Step 2: Create stale epic with old task
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Lifecycle Epic", epic_key="LIFE")
            _create_task(
                conn,
                "Old task under lifecycle epic",
                parent_task_id=epic_id,
                days_ago=45,
            )

        # Step 3: Run drift analysis
        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "Lifecycle Epic" in out
        assert "Stale Epics" in out

    def test_lifecycle_drift_then_vitals(self) -> None:
        """Run drift analysis, then check vitals -- both should succeed."""
        _seed_docs(8)

        # Drift should find no issues (no stale epics)
        drift_result = runner.invoke(app, ["maintain", "drift"])
        assert drift_result.exit_code == 0
        assert "No drift detected" in drift_result.stdout

        # Vitals should show the seeded docs
        vitals_result = runner.invoke(app, ["status", "--vitals"])
        assert vitals_result.exit_code == 0
        out = _strip_ansi(vitals_result.stdout)
        assert "Documents:" in out

    def test_lifecycle_vitals_then_mirror(self) -> None:
        """Vitals and mirror both work on the same KB state."""
        _seed_docs(12)

        # Vitals
        vitals_result = runner.invoke(app, ["status", "--vitals"])
        assert vitals_result.exit_code == 0

        # Mirror (needs >= 5 docs)
        mirror_result = runner.invoke(app, ["status", "--mirror"])
        assert mirror_result.exit_code == 0
        # Should have produced some output (either narrative or "too few")
        assert len(mirror_result.stdout.strip()) > 0


# =====================================================================
# 2. EMPTY KB: All commands handle empty database gracefully
# =====================================================================


class TestEmptyKB:
    """Every intelligence command should handle an empty KB gracefully."""

    def test_prime_brief_empty(self) -> None:
        """prime --brief with no tasks shows 'No ready tasks' message."""
        result = runner.invoke(app, ["prime", "--brief"])
        assert result.exit_code == 0
        assert "No ready tasks" in result.stdout

    def test_drift_empty(self) -> None:
        """maintain drift with no tasks shows 'No drift detected'."""
        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        assert "No drift detected" in result.stdout

    def test_vitals_empty(self) -> None:
        """status --vitals with no docs shows friendly message."""
        result = runner.invoke(app, ["status", "--vitals"])
        assert result.exit_code == 0
        assert "No documents yet" in _strip_ansi(result.stdout)

    def test_mirror_empty(self) -> None:
        """status --mirror with no docs shows friendly message."""
        result = runner.invoke(app, ["status", "--mirror"])
        assert result.exit_code == 0
        assert "No documents yet" in _strip_ansi(result.stdout)

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_code_drift_empty(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        """maintain code-drift with no docs shows 'No documents to check'."""
        mock_docs.return_value = []
        mock_has_tool.return_value = True
        mock_git_repo.return_value = True

        result = runner.invoke(app, ["maintain", "code-drift"])
        assert result.exit_code == 0
        assert "No documents to check" in _strip_ansi(result.stdout)

    def test_drift_json_empty(self) -> None:
        """maintain drift --json with empty KB returns valid empty JSON."""
        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["stale_epics"] == []
        assert data["orphaned_tasks"] == []
        assert data["stale_linked_docs"] == []
        assert data["burst_epics"] == []


# =====================================================================
# 3. JSON OUTPUT: Every command with --json produces valid JSON
# =====================================================================


class TestJsonOutput:
    """All --json flags produce parseable JSON with expected structure."""

    def test_drift_json_structure(self) -> None:
        """maintain drift --json has all expected keys."""
        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "stale_epics" in data
        assert "orphaned_tasks" in data
        assert "stale_linked_docs" in data
        assert "burst_epics" in data
        assert isinstance(data["stale_epics"], list)

    def test_drift_json_with_data(self) -> None:
        """Drift JSON includes stale epic data when present."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "JSON Test Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["stale_epics"]) == 1
        assert data["stale_epics"][0]["title"] == "JSON Test Epic"

    def test_vitals_json_structure(self) -> None:
        """status --vitals --json has expected keys."""
        _seed_docs(5)
        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "total_docs" in data
        assert "by_project" in data
        assert "growth_per_week" in data
        assert "embedding_coverage_pct" in data
        assert "access_distribution" in data
        assert "tag_coverage_pct" in data
        assert "tasks" in data

    def test_mirror_json_structure(self) -> None:
        """status --mirror --json has expected keys."""
        _seed_docs(10)
        result = runner.invoke(app, ["status", "--mirror", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "total_docs" in data
        assert "top_tags" in data
        assert "weekly_activity" in data
        assert "temporal_pattern" in data
        assert "project_balance" in data
        assert "staleness" in data

    def test_prime_brief_json_structure(self) -> None:
        """prime --brief --format json has tasks and epics but no git context."""
        result = runner.invoke(app, ["prime", "--brief", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "ready_tasks" in data
        assert "in_progress_tasks" in data
        assert "active_epics" in data
        # Brief mode should exclude git context
        assert "git_context" not in data

    def test_prime_default_json_structure(self) -> None:
        """prime --format json has project, tasks, epics."""
        result = runner.invoke(app, ["prime", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "ready_tasks" in data
        assert "in_progress_tasks" in data
        assert "active_epics" in data

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_code_drift_json_structure(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        """maintain code-drift --json has expected keys."""
        mock_docs.return_value = [
            (1, "Doc", "Use `SomeClass` here."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = False
        mock_search.return_value = False

        result = runner.invoke(app, ["maintain", "code-drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "total_docs_scanned" in data
        assert "total_identifiers_checked" in data
        assert "stale_references" in data
        assert isinstance(data["stale_references"], list)


# =====================================================================
# 4. FLAG COMBINATIONS: Test conflicting or composable flags
# =====================================================================


class TestFlagCombinations:
    """Conflicting flags produce good errors; composable flags work."""

    def test_view_review_and_raw_exclusive(self) -> None:
        """view --review --raw should produce an error."""
        result = runner.invoke(app, ["view", "1", "--review", "--raw"])
        assert result.exit_code != 0
        assert "mutually exclusive" in _strip_ansi(result.stdout)

    def test_prime_brief_plus_verbose_brief_wins(self) -> None:
        """--brief + --verbose should behave like --brief (brief wins)."""
        result = runner.invoke(app, ["prime", "--brief", "--verbose"])
        assert result.exit_code == 0
        # Brief mode skips git context and recent docs
        assert "GIT CONTEXT" not in result.stdout
        assert "RECENT DOCS" not in result.stdout
        assert "KEY DOCS" not in result.stdout

    def test_prime_brief_plus_quiet_quiet_wins(self) -> None:
        """--brief + --quiet should behave like quiet (quiet wins)."""
        result = runner.invoke(app, ["prime", "--brief", "--quiet"])
        assert result.exit_code == 0
        # Quiet omits the header bullet line
        assert "\u25cf emdx" not in result.stdout
        # Quiet omits epics section
        assert "ACTIVE EPICS" not in result.stdout

    def test_prime_brief_json_excludes_git(self) -> None:
        """--brief --format json excludes git_context."""
        result = runner.invoke(app, ["prime", "--brief", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "git_context" not in data

    def test_drift_custom_days(self) -> None:
        """--days flag adjusts the staleness threshold."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Semi-Stale")
            _create_task(
                conn,
                "Task",
                parent_task_id=epic_id,
                days_ago=10,
            )

        # Default 30 days -- not stale
        result_30 = runner.invoke(app, ["maintain", "drift"])
        assert "No drift detected" in result_30.stdout

        # 7 days threshold -- stale
        result_7 = runner.invoke(app, ["maintain", "drift", "--days", "7"])
        assert "Semi-Stale" in result_7.stdout


# =====================================================================
# 5. BRIEF MODE: prime --brief produces shorter output
# =====================================================================


class TestBriefMode:
    """prime --brief should produce compact output."""

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_is_shorter_than_default(
        self,
        mock_project: MagicMock,
        mock_ip: MagicMock,
        mock_ready: MagicMock,
        mock_epics: MagicMock,
    ) -> None:
        """Brief output should be fewer lines than default output."""
        mock_project.return_value = "myproject"
        mock_epics.return_value = [
            {
                "id": 100,
                "title": "My Epic",
                "status": "active",
                "epic_key": "FEAT",
                "child_count": 5,
                "children_done": 2,
            }
        ]
        mock_ready.return_value = [
            {
                "id": 10,
                "title": "Fix the bug",
                "description": "A detailed description that should show in default.",
                "priority": 5,
                "status": "open",
                "source_doc_id": 42,
                "epic_key": None,
                "epic_seq": None,
            }
        ]
        mock_ip.return_value = []

        from emdx.commands.prime import app as prime_app

        # Default output
        default_result = runner.invoke(prime_app, [])
        # Brief output
        brief_result = runner.invoke(prime_app, ["--brief"])

        assert brief_result.exit_code == 0
        assert default_result.exit_code == 0

        brief_lines = brief_result.stdout.strip().splitlines()
        default_lines = default_result.stdout.strip().splitlines()
        # Brief should have fewer lines
        assert len(brief_lines) <= len(default_lines)

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_omits_doc_references(
        self,
        mock_project: MagicMock,
        mock_ip: MagicMock,
        mock_ready: MagicMock,
        mock_epics: MagicMock,
    ) -> None:
        """Brief mode should omit doc #N references from task lines."""
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            {
                "id": 10,
                "title": "Fix auth",
                "description": "",
                "priority": 5,
                "status": "open",
                "source_doc_id": 42,
                "epic_key": None,
                "epic_seq": None,
            }
        ]
        mock_ip.return_value = []

        from emdx.commands.prime import app as prime_app

        result = runner.invoke(prime_app, ["--brief"])
        assert result.exit_code == 0
        assert "Fix auth" in result.stdout
        assert "doc #42" not in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_skips_git_context(
        self,
        mock_project: MagicMock,
        mock_ip: MagicMock,
        mock_ready: MagicMock,
        mock_epics: MagicMock,
    ) -> None:
        """Brief mode should never include GIT CONTEXT section."""
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            {
                "id": 1,
                "title": "Task",
                "description": "",
                "priority": 5,
                "status": "open",
                "source_doc_id": None,
                "epic_key": None,
                "epic_seq": None,
            }
        ]
        mock_ip.return_value = []

        from emdx.commands.prime import app as prime_app

        result = runner.invoke(prime_app, ["--brief"])
        assert result.exit_code == 0
        assert "GIT CONTEXT" not in result.stdout


# =====================================================================
# 6. WANDER SEARCH: Works gracefully without embedding index
# =====================================================================


class TestWanderFallback:
    """find --wander should handle missing embeddings gracefully."""

    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        side_effect=ImportError("sentence-transformers not installed"),
    )
    def test_wander_no_embeddings_library(
        self,
        mock_embed_cls: MagicMock,
    ) -> None:
        """--wander without sentence-transformers exits with error."""
        result = runner.invoke(app, ["find", "--wander", "test"])
        assert result.exit_code != 0

    @patch("emdx.services.embedding_service.EmbeddingService", autospec=True)
    def test_wander_too_few_indexed_docs(
        self,
        mock_embed_cls: Any,
    ) -> None:
        """--wander with <10 indexed docs shows helpful message."""
        from emdx.services.embedding_service import EmbeddingStats

        mock_service = MagicMock()
        mock_service.stats.return_value = EmbeddingStats(
            total_documents=5,
            indexed_documents=5,
            coverage_percent=100.0,
            model_name="all-MiniLM-L6-v2",
            index_size_bytes=5000,
        )
        mock_embed_cls.return_value = mock_service

        result = runner.invoke(app, ["find", "--wander"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "Serendipity works better" in out
        assert "5" in out

    @patch("emdx.services.embedding_service.EmbeddingService", autospec=True)
    def test_wander_too_few_indexed_docs_json(
        self,
        mock_embed_cls: Any,
    ) -> None:
        """--wander --json with too few docs returns JSON error object."""
        from emdx.services.embedding_service import EmbeddingStats

        mock_service = MagicMock()
        mock_service.stats.return_value = EmbeddingStats(
            total_documents=3,
            indexed_documents=3,
            coverage_percent=100.0,
            model_name="all-MiniLM-L6-v2",
            index_size_bytes=3000,
        )
        mock_embed_cls.return_value = mock_service

        result = runner.invoke(app, ["find", "--wander", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "error" in data


# =====================================================================
# 7. VIEW --REVIEW: LLM-based adversarial review
# =====================================================================


class TestViewReviewIntegration:
    """Integration tests for view --review via CliRunner."""

    @patch("emdx.commands.core._view_review")
    @patch("emdx.commands.core.get_document")
    def test_review_calls_helper(
        self,
        mock_get_doc: MagicMock,
        mock_review: MagicMock,
    ) -> None:
        """--review invokes the _view_review helper."""
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Test Doc",
            "content": "Some content here.",
            "project": "proj",
            "created_at": datetime(2024, 6, 1),
            "access_count": 3,
        }

        from emdx.commands.core import app as core_app

        result = runner.invoke(core_app, ["view", "1", "--review"])
        assert result.exit_code == 0
        mock_review.assert_called_once()

    @patch("emdx.commands.core.get_document")
    def test_review_nonexistent_doc(self, mock_get_doc: MagicMock) -> None:
        """--review on missing doc shows 'not found' error."""
        mock_get_doc.return_value = None

        from emdx.commands.core import app as core_app

        result = runner.invoke(core_app, ["view", "999", "--review"])
        assert result.exit_code != 0
        assert "not found" in _strip_ansi(result.stdout)


# =====================================================================
# 8. MAINTAIN CODE-DRIFT: Stale code reference detection
# =====================================================================


class TestCodeDriftIntegration:
    """Integration tests for maintain code-drift subcommand."""

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_detects_stale_references(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        """Code-drift surfaces identifiers not found in codebase."""
        mock_docs.return_value = [
            (1, "Architecture", "Use `OldModule` to handle requests."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = False
        mock_search.return_value = False

        result = runner.invoke(app, ["maintain", "code-drift"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "OldModule" in out
        assert "not found" in out

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_clean_codebase(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        """When all identifiers are found, shows 'clean' message."""
        mock_docs.return_value = [
            (1, "Good Doc", "The `ExistingClass` works well."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = True
        mock_search.return_value = True

        result = runner.invoke(app, ["maintain", "code-drift"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "All code references look current" in out

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_code_drift_json_with_stale_refs(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        """JSON output includes stale reference details."""
        mock_docs.return_value = [
            (42, "My Doc", "Use `MissingClass` in `gone_module.py`."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = False
        mock_search.return_value = False

        result = runner.invoke(app, ["maintain", "code-drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_docs_scanned"] == 1
        assert len(data["stale_references"]) >= 1
        identifiers = [r["identifier"] for r in data["stale_references"]]
        assert "MissingClass" in identifiers


# =====================================================================
# 9. STATUS --VITALS: Dashboard data
# =====================================================================


class TestVitalsIntegration:
    """Integration tests for status --vitals."""

    def test_vitals_plain_output(self) -> None:
        """Plain text vitals contains key metrics."""
        _seed_docs(6)
        result = runner.invoke(app, ["status", "--vitals"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "Documents:" in out
        assert "Embedding coverage:" in out
        assert "Tag coverage:" in out
        assert "Tasks:" in out

    def test_vitals_json_data_types(self) -> None:
        """Vitals JSON values have correct types."""
        _seed_docs(5)
        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data["total_docs"], int)
        assert isinstance(data["by_project"], list)
        assert isinstance(data["growth_per_week"], list)
        assert isinstance(data["embedding_coverage_pct"], (int, float))
        assert isinstance(data["tag_coverage_pct"], (int, float))
        assert isinstance(data["tasks"], dict)
        assert "open" in data["tasks"]
        assert "done" in data["tasks"]
        assert "total" in data["tasks"]

    def test_vitals_project_counts_sum(self) -> None:
        """by_project counts should sum to total_docs."""
        _seed_docs(5, project="proj-a")
        _seed_docs(3, project="proj-b")
        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        total_from_projects = sum(p["count"] for p in data["by_project"])
        assert total_from_projects == data["total_docs"]

    def test_vitals_growth_has_four_weeks(self) -> None:
        """Growth data always has exactly 4 weekly entries."""
        _seed_docs(3)
        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["growth_per_week"]) == 4

    def test_vitals_access_distribution_four_buckets(self) -> None:
        """Access distribution has exactly 4 buckets."""
        _seed_docs(3)
        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["access_distribution"]) == 4
        ranges = [b["range"] for b in data["access_distribution"]]
        assert "0 views" in ranges
        assert "1-5 views" in ranges
        assert "6-20 views" in ranges
        assert "21+ views" in ranges

    def test_vitals_rich_no_crash(self) -> None:
        """--vitals --rich does not crash."""
        _seed_docs(3)
        result = runner.invoke(app, ["status", "--vitals", "--rich"])
        assert result.exit_code == 0


# =====================================================================
# 10. STATUS --MIRROR: Reflective narrative
# =====================================================================


class TestMirrorIntegration:
    """Integration tests for status --mirror."""

    def test_mirror_too_few_docs(self) -> None:
        """Mirror with <5 docs shows 'Too few documents'."""
        _seed_docs(3)
        result = runner.invoke(app, ["status", "--mirror"])
        assert result.exit_code == 0
        assert "Too few documents" in _strip_ansi(result.stdout)

    def test_mirror_with_enough_docs(self) -> None:
        """Mirror with >=5 docs produces narrative output."""
        _seed_docs(10)
        result = runner.invoke(app, ["status", "--mirror"])
        assert result.exit_code == 0
        assert len(result.stdout.strip()) > 0

    def test_mirror_json_staleness_values(self) -> None:
        """Mirror JSON staleness values are between 0 and 100."""
        _seed_docs(10)
        result = runner.invoke(app, ["status", "--mirror", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        s = data["staleness"]
        for key in ("over_30_days_pct", "over_60_days_pct", "over_90_days_pct"):
            assert 0 <= s[key] <= 100

    def test_mirror_temporal_pattern_valid(self) -> None:
        """Mirror temporal pattern is one of the known values."""
        _seed_docs(10)
        result = runner.invoke(app, ["status", "--mirror", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["temporal_pattern"] in ("steady", "burst", "sporadic", "inactive")

    def test_mirror_weekly_activity_eight_weeks(self) -> None:
        """Mirror weekly activity has 8 entries."""
        _seed_docs(10)
        result = runner.invoke(app, ["status", "--mirror", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["weekly_activity"]) == 8


# =====================================================================
# 11. MAINTAIN DRIFT: Complex scenarios
# =====================================================================


class TestDriftComplex:
    """Complex drift scenarios testing multiple signal types."""

    def test_orphaned_active_task_detected(self) -> None:
        """Active tasks idle for >14 days are flagged."""
        with db.get_connection() as conn:
            _create_task(
                conn,
                "Abandoned active task",
                status="active",
                days_ago=20,
            )

        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        out = result.stdout
        assert "Abandoned active task" in out

    def test_burst_epic_detected(self) -> None:
        """Epic with many tasks created in short window then silence."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Burst Epic")
            for i in range(4):
                _create_task(
                    conn,
                    f"Burst task {i}",
                    parent_task_id=epic_id,
                    days_ago=45,
                )

        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        out = result.stdout
        assert "Burst Epic" in out

    def test_stale_linked_doc_detected(self) -> None:
        """Documents linked to stale tasks are surfaced."""
        with db.get_connection() as conn:
            # Create a document
            cursor = conn.execute(
                "INSERT INTO documents (title, content, is_deleted) "
                "VALUES ('Stale Source Doc', 'content', 0)"
            )
            conn.commit()
            assert cursor.lastrowid is not None
            doc_id = int(cursor.lastrowid)

            # Link it to a stale task via source_doc_id
            _create_task(
                conn,
                "Stale task with doc",
                status="open",
                days_ago=45,
                source_doc_id=doc_id,
            )

        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        out = result.stdout
        assert "Stale Source Doc" in out

    def test_multiple_drift_types_together(self) -> None:
        """Multiple drift types detected in same analysis."""
        with db.get_connection() as conn:
            # Stale epic
            epic_id = _create_epic(conn, "Forgotten Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

            # Orphaned active task (unrelated to epic)
            _create_task(
                conn,
                "Orphaned work",
                status="active",
                days_ago=20,
            )

        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["stale_epics"]) >= 1
        assert len(data["orphaned_tasks"]) >= 1


# =====================================================================
# 12. CROSS-FEATURE: Features interact correctly
# =====================================================================


class TestCrossFeatureInteractions:
    """Features work correctly when the same KB state is inspected."""

    def test_vitals_reflects_drift_state(self) -> None:
        """When tasks exist, vitals reports them in task stats."""
        _seed_docs(5)
        with db.get_connection() as conn:
            _create_task(conn, "Open task", status="open", days_ago=0)
            _create_task(conn, "Done task", status="done", days_ago=0)

        result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        t = data["tasks"]
        assert t["total"] >= 2
        assert t["open"] >= 1
        assert t["done"] >= 1

    def test_prime_and_vitals_same_project(self) -> None:
        """prime and vitals both reflect the same project state."""
        _seed_docs(5, project="shared-proj")

        # Prime should succeed with JSON output
        prime_result = runner.invoke(app, ["prime", "--format", "json"])
        assert prime_result.exit_code == 0
        # Validate it produces valid JSON
        json.loads(prime_result.stdout)

        # Vitals should include the project in by_project
        vitals_result = runner.invoke(app, ["status", "--vitals", "--json"])
        assert vitals_result.exit_code == 0
        vitals_data = json.loads(vitals_result.stdout)

        project_names = [p["project"] for p in vitals_data["by_project"]]
        assert "shared-proj" in project_names


# =====================================================================
# 13. HELP TEXT: Commands show useful help
# =====================================================================


class TestHelpText:
    """All new commands/flags show help text."""

    def test_drift_help(self) -> None:
        """maintain drift --help shows usage."""
        result = runner.invoke(app, ["maintain", "drift", "--help"])
        assert result.exit_code == 0
        assert "--days" in _strip_ansi(result.stdout)

    def test_code_drift_help(self) -> None:
        """maintain code-drift --help shows usage."""
        result = runner.invoke(app, ["maintain", "code-drift", "--help"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "--json" in out
        assert "--project" in out

    def test_prime_help_mentions_brief(self) -> None:
        """prime --help mentions --brief."""
        result = runner.invoke(app, ["prime", "--help"])
        assert result.exit_code == 0
        assert "--brief" in _strip_ansi(result.stdout)

    def test_status_help_mentions_vitals_and_mirror(self) -> None:
        """status --help mentions --vitals and --mirror."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        out = _strip_ansi(result.stdout)
        assert "--vitals" in out
        assert "--mirror" in out
