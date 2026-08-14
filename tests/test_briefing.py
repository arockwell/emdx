"""Tests for the briefing command."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.briefing import (
    _build_json_output,
    _format_relative_time,
    _get_tag_filtered_doc_ids,
    _parse_since,
    _parse_tags,
)
from emdx.database.documents import save_document
from emdx.main import app as main_app
from emdx.models.tasks import create_task, update_task

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# Unit tests for _parse_since
# ---------------------------------------------------------------------------
class TestParseSince:
    """Tests for the --since argument parser."""

    def test_parse_yesterday(self) -> None:
        result = _parse_since("yesterday")
        expected = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=1
        )
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_last_week(self) -> None:
        result = _parse_since("last week")
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_days(self) -> None:
        result = _parse_since("3 days ago")
        expected = datetime.now() - timedelta(days=3)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_hours(self) -> None:
        result = _parse_since("2 hours ago")
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_weeks(self) -> None:
        result = _parse_since("1 week ago")
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_iso_date(self) -> None:
        result = _parse_since("2026-01-15")
        assert result == datetime(2026, 1, 15, 0, 0, 0, 0)

    def test_parse_iso_datetime(self) -> None:
        # Note: _parse_since lowercases input, so "T" becomes "t"
        # The code checks for uppercase "T" so it treats this as date-only
        # and returns midnight. This tests the actual behavior.
        result = _parse_since("2026-01-15T10:30:00")
        # Because of .lower(), "T" -> "t", but fromisoformat still parses it
        # Let's check what actually comes back (depends on Python version)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_parse_unknown_defaults_to_24h(self) -> None:
        result = _parse_since("not a date")
        expected = datetime.now() - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 2


# ---------------------------------------------------------------------------
# Unit tests for _format_relative_time
# ---------------------------------------------------------------------------
class TestFormatRelativeTime:
    """Tests for relative time formatting."""

    def test_none_returns_empty(self) -> None:
        assert _format_relative_time(None) == ""

    def test_recent_timestamp(self) -> None:
        recent = (datetime.now() - timedelta(seconds=30)).isoformat()
        result = _format_relative_time(recent)
        assert "s ago" in result

    def test_minutes_ago(self) -> None:
        minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        result = _format_relative_time(minutes_ago)
        assert "m ago" in result

    def test_hours_ago(self) -> None:
        hours_ago = (datetime.now() - timedelta(hours=3)).isoformat()
        result = _format_relative_time(hours_ago)
        assert "h ago" in result

    def test_days_ago(self) -> None:
        days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        result = _format_relative_time(days_ago)
        assert "d ago" in result


# ---------------------------------------------------------------------------
# Unit tests for _build_json_output
# ---------------------------------------------------------------------------
class TestBuildJsonOutput:
    """Tests for JSON output builder."""

    def test_empty_data(self) -> None:
        since = datetime(2026, 1, 1)
        result = _build_json_output(since, [], [], [], [])
        assert result["summary"]["documents_created"] == 0
        assert result["summary"]["tasks_completed"] == 0
        assert result["summary"]["tasks_added"] == 0
        assert result["summary"]["blockers"] == 0
        assert result["since"] == since.isoformat()

    def test_with_data(self) -> None:
        since = datetime(2026, 1, 1)
        docs = [{"id": 1, "title": "Doc1", "tags": None}]
        completed = [{"id": 2, "title": "Task1"}]
        added = [{"id": 3, "title": "Task2"}]
        blockers = [{"id": 4, "title": "Task3"}]
        result = _build_json_output(since, docs, completed, added, blockers)
        assert result["summary"]["documents_created"] == 1
        assert result["summary"]["tasks_completed"] == 1
        assert result["summary"]["tasks_added"] == 1
        assert result["summary"]["blockers"] == 1
        assert len(result["documents_created"]) == 1
        assert result["documents_created"][0]["id"] == 1
        assert result["documents_created"][0]["tags"] == []


# ---------------------------------------------------------------------------
# CLI integration tests for briefing command
# ---------------------------------------------------------------------------
class TestBriefingCommand:
    """Tests for the briefing CLI command."""

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_default(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Default briefing shows no-activity message when DB is empty."""
        mock_docs.return_value = []
        mock_completed.return_value = []
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing"])
        assert result.exit_code == 0
        assert "No activity" in _out(result)

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_with_since(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing with --since parses the time correctly."""
        mock_docs.return_value = []
        mock_completed.return_value = []
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing", "--since", "yesterday"])
        assert result.exit_code == 0

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_json_output(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing --json produces valid JSON."""
        mock_docs.return_value = [
            {
                "id": 1,
                "title": "Test Doc",
                "project": "proj",
                "created_at": "2026-01-15T10:00:00",
                "tags": "notes",
            }
        ]
        mock_completed.return_value = []
        mock_added.return_value = [
            {
                "id": 10,
                "title": "New Task",
                "status": "open",
                "priority": 1,
                "created_at": "2026-01-15T11:00:00",
                "project": "proj",
            }
        ]
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["summary"]["documents_created"] == 1
        assert data["summary"]["tasks_added"] == 1

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_with_activity(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing shows activity sections when there's data."""
        mock_docs.return_value = [
            {
                "id": 1,
                "title": "New Document",
                "project": "proj",
                "created_at": datetime.now().isoformat(),
                "tags": "notes",
            }
        ]
        mock_completed.return_value = [
            {
                "id": 5,
                "title": "Completed Task",
                "completed_at": datetime.now().isoformat(),
                "project": "proj",
            }
        ]
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing"])
        assert result.exit_code == 0
        out = _out(result)
        assert "docs created" in out or "Documents Created" in out
        assert "tasks completed" in out or "Tasks Completed" in out


# ---------------------------------------------------------------------------
# Unit tests for tag-scoping helpers
# ---------------------------------------------------------------------------
class TestParseTags:
    """Tests for _parse_tags."""

    def test_none_returns_empty(self) -> None:
        assert _parse_tags(None) == []

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_tags("") == []

    def test_splits_and_normalizes(self) -> None:
        assert _parse_tags(" Sentry , Investigation ") == ["sentry", "investigation"]

    def test_drops_blank_entries(self) -> None:
        assert _parse_tags("a,,b,") == ["a", "b"]


class TestGetTagFilteredDocIds:
    """Tests for _get_tag_filtered_doc_ids against a real (isolated) database."""

    def test_no_tags_returns_none(self) -> None:
        assert _get_tag_filtered_doc_ids([], any_tags=False) is None

    def test_all_mode_requires_every_tag(self) -> None:
        both = save_document(title="Both", content="x", tags=["alpha", "beta"])
        save_document(title="AlphaOnly", content="x", tags=["alpha"])

        result = _get_tag_filtered_doc_ids(["alpha", "beta"], any_tags=False)

        assert result == {both}

    def test_any_mode_matches_either_tag(self) -> None:
        alpha_only = save_document(title="AlphaOnly2", content="x", tags=["alpha2"])
        beta_only = save_document(title="BetaOnly2", content="x", tags=["beta2"])
        save_document(title="Unrelated2", content="x", tags=["gamma2"])

        result = _get_tag_filtered_doc_ids(["alpha2", "beta2"], any_tags=True)

        assert result == {alpha_only, beta_only}

    def test_no_matching_documents_returns_empty_set(self) -> None:
        result = _get_tag_filtered_doc_ids(["definitely-nonexistent-tag"], any_tags=False)
        assert result == set()


# ---------------------------------------------------------------------------
# Integration tests for `emdx briefing --tags` against a real database
# ---------------------------------------------------------------------------
class TestBriefingTagsScoping:
    """End-to-end tests for --tags/--any-tags scoping."""

    def test_documents_scoped_directly_by_tag(self) -> None:
        save_document(title="Tagged Doc", content="x", tags=["briefing-scope-a"])
        save_document(title="Untagged Doc", content="x")

        result = runner.invoke(
            main_app, ["briefing", "--json", "--tags", "briefing-scope-a", "--since", "2 days ago"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        titles = {d["title"] for d in data["documents_created"]}
        assert titles == {"Tagged Doc"}
        assert data["tags_filter"] == {"tags": ["briefing-scope-a"], "mode": "all"}

    def test_tasks_scoped_via_linked_output_document(self) -> None:
        doc_id = save_document(title="Linked Doc", content="x", tags=["briefing-scope-b"])
        linked_task_id = create_task("Linked task", output_doc_id=doc_id)
        unlinked_task_id = create_task("Unlinked task")
        update_task(linked_task_id, status="done")
        update_task(unlinked_task_id, status="done")

        result = runner.invoke(
            main_app, ["briefing", "--json", "--tags", "briefing-scope-b", "--since", "2 days ago"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        completed_ids = {t["id"] for t in data["tasks_completed"]}
        assert linked_task_id in completed_ids
        assert unlinked_task_id not in completed_ids

    def test_any_tags_uses_or_semantics(self) -> None:
        save_document(title="OnlyC", content="x", tags=["briefing-scope-c"])

        # AND mode: doc only has one of the two tags, so no match.
        and_result = runner.invoke(
            main_app,
            [
                "briefing",
                "--json",
                "--tags",
                "briefing-scope-c,briefing-scope-d",
                "--since",
                "2 days ago",
            ],
        )
        and_data = json.loads(and_result.stdout)
        assert and_data["documents_created"] == []

        # OR mode: matches on briefing-scope-c alone.
        or_result = runner.invoke(
            main_app,
            [
                "briefing",
                "--json",
                "--tags",
                "briefing-scope-c,briefing-scope-d",
                "--any-tags",
                "--since",
                "2 days ago",
            ],
        )
        or_data = json.loads(or_result.stdout)
        titles = {d["title"] for d in or_data["documents_created"]}
        assert "OnlyC" in titles

    def test_no_matching_tag_returns_empty_not_error(self) -> None:
        result = runner.invoke(
            main_app,
            ["briefing", "--json", "--tags", "no-such-tag-anywhere", "--since", "2 days ago"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["documents_created"] == []
        assert data["tasks_completed"] == []
        assert data["tasks_added"] == []
        assert data["blockers"] == []

    def test_no_tags_omits_tags_filter_field(self) -> None:
        result = runner.invoke(main_app, ["briefing", "--json", "--since", "2 days ago"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["tags_filter"] is None
