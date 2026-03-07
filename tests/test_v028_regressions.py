"""Regression tests for v0.28 bug fixes.

Each test validates that a specific v0.28 fix remains correct.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.main import app
from emdx.models.document import Document

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# 1. maintain --auto --dry-run doesn't mutate
# ---------------------------------------------------------------------------
class TestMaintainAutoDryRun:
    """Verify that maintain --auto with dry_run=True passes dry_run to all sub-functions."""

    @patch("emdx.commands.maintain._garbage_collect")
    @patch("emdx.commands.maintain._merge_documents")
    @patch("emdx.commands.maintain._auto_tag_documents")
    @patch("emdx.commands.maintain._clean_documents")
    def test_auto_dry_run_passes_dry_run_true(
        self,
        mock_clean: MagicMock,
        mock_tag: MagicMock,
        mock_merge: MagicMock,
        mock_gc: MagicMock,
    ) -> None:
        """--auto without --execute should pass dry_run=True to every sub-function."""
        mock_clean.return_value = None
        mock_tag.return_value = None
        mock_merge.return_value = None
        mock_gc.return_value = None

        # Default is dry_run=True (--dry-run); --auto enables all operations
        result = runner.invoke(app, ["maintain", "--auto"])
        assert result.exit_code == 0

        mock_clean.assert_called_once_with(True)
        mock_tag.assert_called_once_with(True)
        mock_merge.assert_called_once()
        # _merge_documents receives (dry_run, threshold)
        assert mock_merge.call_args[0][0] is True
        mock_gc.assert_called_once_with(True)


# ---------------------------------------------------------------------------
# 2. briefing --json produces valid JSON
# ---------------------------------------------------------------------------
class TestBriefingJsonOutput:
    """Verify that briefing --json outputs valid JSON, not Rich markup."""

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_json_is_valid(
        self,
        mock_docs: MagicMock,
        mock_completed: MagicMock,
        mock_added: MagicMock,
        mock_blocked: MagicMock,
    ) -> None:
        """--json flag must produce parseable JSON with no Rich markup."""
        mock_docs.return_value = [
            {
                "id": 1,
                "title": "Test Doc",
                "project": "proj",
                "created_at": "2026-01-15T10:00:00",
                "tags": "notes,active",
            }
        ]
        mock_completed.return_value = [
            {"id": 5, "title": "Done task", "completed_at": "2026-01-15T12:00:00"}
        ]
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(app, ["briefing", "--json"])
        assert result.exit_code == 0

        # Must be valid JSON
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "documents_created" in data
        assert data["summary"]["documents_created"] == 1
        assert data["summary"]["tasks_completed"] == 1

        # Tags should be a list, not a raw string
        assert isinstance(data["documents_created"][0]["tags"], list)

        # Output must not contain Rich markup
        assert "[bold" not in result.stdout
        assert "[red" not in result.stdout
        assert "[cyan" not in result.stdout


# ---------------------------------------------------------------------------
# 3. find --all --no-tags filters correctly
# ---------------------------------------------------------------------------
class TestFindNoTagsFilter:
    """Verify that --no-tags excludes documents with the specified tags."""

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_no_tags_excludes_matching_docs(
        self,
        mock_search: MagicMock,
        mock_tags_map: MagicMock,
    ) -> None:
        """--no-tags should remove docs that have any of the excluded tags."""
        # Simulate 3 search results with all required fields
        mock_search.return_value = [
            {
                "id": 1,
                "title": "Keep me",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
            {
                "id": 2,
                "title": "Exclude me",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
            {
                "id": 3,
                "title": "Also keep",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
        ]
        # Doc 2 has the excluded tag "draft"
        mock_tags_map.return_value = {
            1: ["notes"],
            2: ["draft", "wip"],
            3: ["notes", "active"],
        }

        # Use --mode keyword to avoid hybrid search path
        result = runner.invoke(
            app,
            ["find", "test query", "--no-tags", "draft", "--mode", "keyword"],
        )
        assert result.exit_code == 0
        out = _out(result)

        # Doc 1 and 3 should appear; doc 2 should be filtered out
        assert "Keep me" in out
        assert "Also keep" in out
        assert "Exclude me" not in out

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_no_tags_multiple_excluded(
        self,
        mock_search: MagicMock,
        mock_tags_map: MagicMock,
    ) -> None:
        """--no-tags with comma-separated tags excludes docs with ANY of them."""
        mock_search.return_value = [
            {
                "id": 1,
                "title": "Keep me",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
            {
                "id": 2,
                "title": "Has draft",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
            {
                "id": 3,
                "title": "Has wip",
                "project": "p",
                "content": "c",
                "created_at": "2026-01-15",
            },
        ]
        mock_tags_map.return_value = {
            1: ["notes"],
            2: ["draft"],
            3: ["wip"],
        }

        # Use --mode keyword to avoid hybrid search path
        result = runner.invoke(
            app,
            [
                "find",
                "test query",
                "--no-tags",
                "draft,wip",
                "--mode",
                "keyword",
            ],
        )
        assert result.exit_code == 0
        out = _out(result)

        assert "Keep me" in out
        assert "Has draft" not in out
        assert "Has wip" not in out


# ---------------------------------------------------------------------------
# 4. history --json returns proper JSON
# ---------------------------------------------------------------------------
class TestHistoryJsonOutput:
    """Verify that history --json returns valid JSON output."""

    @patch("emdx.commands.history.db_connection")
    @patch("emdx.commands.history.get_document")
    def test_history_json_valid(
        self,
        mock_get_doc: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """history --json should produce parseable JSON with version info."""
        mock_get_doc.return_value = Document.from_row(
            {"id": 42, "title": "Test Document", "content": "body"}
        )

        # Simulate version rows from the database
        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, "Test Document", "abc123", 100, "manual", "2026-01-15T10:00:00"),
            (2, "Test Document v2", "def456", 50, "edit", "2026-01-16T11:00:00"),
        ]

        result = runner.invoke(app, ["history", "42", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["doc_id"] == 42
        assert data["title"] == "Test Document"
        assert len(data["versions"]) == 2
        assert data["versions"][0]["version"] == 1
        assert data["versions"][1]["change_source"] == "edit"

    @patch("emdx.commands.history.db_connection")
    @patch("emdx.commands.history.get_document")
    def test_history_json_no_versions(
        self,
        mock_get_doc: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """history --json with no versions should output a JSON error message."""
        mock_get_doc.return_value = Document.from_row(
            {"id": 42, "title": "Test", "content": "body"}
        )

        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = []

        result = runner.invoke(app, ["history", "42", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert "error" in data


# ---------------------------------------------------------------------------
# 5. wiki generate --dry-run defaults to all topics
# ---------------------------------------------------------------------------
class TestWikiGenerateDryRunDefault:
    """Verify that wiki generate --dry-run without --all defaults to all topics."""

    @patch("emdx.services.wiki_synthesis_service.complete_wiki_run")
    @patch("emdx.services.wiki_synthesis_service.generate_article")
    @patch("emdx.services.wiki_synthesis_service.create_wiki_run")
    @patch("emdx.services.wiki_clustering_service.get_topics")
    def test_dry_run_without_all_defaults_to_all(
        self,
        mock_get_topics: MagicMock,
        mock_create_run: MagicMock,
        mock_generate: MagicMock,
        mock_complete: MagicMock,
    ) -> None:
        """--dry-run alone (without --all or topic_id) should process all topics."""
        mock_get_topics.return_value = [
            {"id": 1, "label": "Topic A"},
            {"id": 2, "label": "Topic B"},
        ]
        mock_create_run.return_value = 1

        # Simulate dry-run article results
        article_result = MagicMock()
        article_result.skipped = False
        article_result.topic_label = "Topic A"
        article_result.cost_usd = 0.01
        article_result.input_tokens = 100
        article_result.output_tokens = 50
        mock_generate.return_value = article_result

        result = runner.invoke(app, ["wiki", "generate", "--dry-run"])
        assert result.exit_code == 0

        # Should have called generate_article for both topics
        assert mock_generate.call_count == 2

        # Each call should have dry_run=True
        for call in mock_generate.call_args_list:
            assert call.kwargs.get("dry_run") is True


# ---------------------------------------------------------------------------
# 6. wiki view doesn't crash (no doc_id column error)
# ---------------------------------------------------------------------------
class TestWikiViewNoCrash:
    """Verify that wiki view works without crashing on doc_id column access."""

    @patch("emdx.models.documents.get_document")
    @patch("emdx.database.db")
    def test_wiki_view_returns_content(
        self,
        mock_db_obj: MagicMock,
        mock_get_doc: MagicMock,
    ) -> None:
        """wiki view <topic_id> should display the article without error."""
        mock_conn = MagicMock()
        mock_db_obj.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_obj.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=99)
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        mock_get_doc.return_value = Document.from_row(
            {
                "id": 99,
                "title": "Wiki Article Title",
                "content": "# Article\n\nSome content here.",
            }
        )

        result = runner.invoke(app, ["wiki", "view", "5", "--raw"])
        assert result.exit_code == 0
        assert "Article" in result.stdout
        assert "Some content here" in result.stdout

    @patch("emdx.database.db")
    def test_wiki_view_missing_topic(
        self,
        mock_db_obj: MagicMock,
    ) -> None:
        """wiki view with nonexistent topic_id should exit 1, not crash."""
        mock_conn = MagicMock()
        mock_db_obj.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_obj.get_connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None

        result = runner.invoke(app, ["wiki", "view", "9999"])
        assert result.exit_code == 1
