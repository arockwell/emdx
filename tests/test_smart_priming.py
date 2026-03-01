"""Tests for --smart flag on emdx prime command."""
# mypy: disable-error-code="no-untyped-def"

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.prime import (
    _get_smart_recent_docs,
    _get_tag_map,
    _relative_time,
    app,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper data factories
# ---------------------------------------------------------------------------


def _make_task(
    id=1,
    title="Test task",
    description="",
    priority=5,
    status="open",
    source_doc_id=None,
    epic_key=None,
    epic_seq=None,
):
    return {
        "id": id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "source_doc_id": source_doc_id,
        "epic_key": epic_key,
        "epic_seq": epic_seq,
    }


# ---------------------------------------------------------------------------
# Unit tests for _relative_time
# ---------------------------------------------------------------------------


class TestRelativeTime:
    def test_just_now(self):
        now = datetime.now(timezone.utc).isoformat()
        result = _relative_time(now)
        assert result == "just now"

    def test_minutes_ago(self):
        from datetime import timedelta

        dt = datetime.now(timezone.utc) - timedelta(minutes=15)
        result = _relative_time(dt.isoformat())
        assert result == "15m ago"

    def test_hours_ago(self):
        from datetime import timedelta

        dt = datetime.now(timezone.utc) - timedelta(hours=3)
        result = _relative_time(dt.isoformat())
        assert result == "3h ago"

    def test_days_ago(self):
        from datetime import timedelta

        dt = datetime.now(timezone.utc) - timedelta(days=5)
        result = _relative_time(dt.isoformat())
        assert result == "5d ago"

    def test_invalid_string(self):
        result = _relative_time("not-a-date")
        assert result == "unknown"

    def test_naive_timestamp(self):
        """SQLite stores naive timestamps; they should still work."""
        from datetime import timedelta

        dt = datetime.now(timezone.utc) - timedelta(hours=2)
        # Strip timezone info to simulate SQLite naive timestamp
        naive_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        result = _relative_time(naive_str)
        assert result == "2h ago"


# ---------------------------------------------------------------------------
# Unit tests for _get_smart_recent_docs
# ---------------------------------------------------------------------------


class TestGetSmartRecentDocs:
    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_docs_with_relative_time(self, mock_conn):
        from datetime import timedelta

        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "Recent Doc", ts, 5),
        ]
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_smart_recent_docs()

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["title"] == "Recent Doc"
        assert result[0]["access_count"] == 5
        assert result[0]["relative_time"] == "1h ago"

    @patch("emdx.commands.prime.db.get_connection")
    def test_empty_when_no_recent_docs(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_smart_recent_docs()
        assert result == []

    @patch("emdx.commands.prime.db.get_connection")
    def test_respects_limit(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1, "Doc", "2025-01-01", 1)]
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        _get_smart_recent_docs(limit=3)

        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (3,)


# ---------------------------------------------------------------------------
# Unit tests for _get_tag_map
# ---------------------------------------------------------------------------


class TestGetTagMap:
    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_tags_with_counts(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("python", 15),
            ("security", 8),
            ("notes", 5),
        ]
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_tag_map()

        assert len(result) == 3
        assert result[0]["name"] == "python"
        assert result[0]["count"] == 15
        assert result[1]["name"] == "security"
        assert result[1]["count"] == 8

    @patch("emdx.commands.prime.db.get_connection")
    def test_empty_when_no_tags(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_tag_map()
        assert result == []


# ---------------------------------------------------------------------------
# Integration tests: --smart text output
# ---------------------------------------------------------------------------


class TestSmartTextOutput:
    """Test --smart flag produces expected text sections."""

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_shows_recent_activity(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = [
            {
                "id": 42,
                "title": "Auth Analysis",
                "accessed_at": "2025-01-15 10:00:00",
                "access_count": 7,
                "relative_time": "2h ago",
            }
        ]
        mock_key_docs.return_value = []
        mock_tag_map.return_value = []
        mock_stale.return_value = []

        result = runner.invoke(app, ["--smart"])
        assert result.exit_code == 0
        assert "RECENT ACTIVITY (7d):" in result.stdout
        assert "#42" in result.stdout
        assert "Auth Analysis" in result.stdout
        assert "2h ago" in result.stdout
        assert "7x" in result.stdout

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_shows_knowledge_map(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = []
        mock_key_docs.return_value = []
        mock_tag_map.return_value = [
            {"name": "python", "count": 15},
            {"name": "security", "count": 8},
        ]
        mock_stale.return_value = []

        result = runner.invoke(app, ["--smart"])
        assert result.exit_code == 0
        assert "KNOWLEDGE MAP:" in result.stdout
        assert "python(15)" in result.stdout
        assert "security(8)" in result.stdout

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_shows_key_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = []
        mock_key_docs.return_value = [
            {"id": 10, "title": "Design Doc", "access_count": 50},
        ]
        mock_tag_map.return_value = []
        mock_stale.return_value = []

        result = runner.invoke(app, ["--smart"])
        assert result.exit_code == 0
        assert "KEY DOCS (most accessed):" in result.stdout
        assert '#10 "Design Doc" — 50 views' in result.stdout

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_shows_stale_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = []
        mock_key_docs.return_value = []
        mock_tag_map.return_value = []
        mock_stale.return_value = [
            {"id": 5, "title": "Old Guide", "level": "WARNING", "days_stale": 45},
        ]

        result = runner.invoke(app, ["--smart"])
        assert result.exit_code == 0
        assert "STALE DOCS (needs review):" in result.stdout
        assert "#5" in result.stdout
        assert "Old Guide" in result.stdout
        assert "45d" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_skipped_in_brief_mode(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task()]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--smart", "--brief"])
        assert result.exit_code == 0
        assert "RECENT ACTIVITY" not in result.stdout
        assert "KNOWLEDGE MAP" not in result.stdout

    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_smart_skipped_in_quiet_mode(self, mock_project, mock_ip, mock_ready):
        mock_project.return_value = None
        mock_ready.return_value = [_make_task()]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--smart", "--quiet"])
        assert result.exit_code == 0
        assert "RECENT ACTIVITY" not in result.stdout
        assert "KNOWLEDGE MAP" not in result.stdout


# ---------------------------------------------------------------------------
# Integration tests: --smart --format json
# ---------------------------------------------------------------------------


class TestSmartJsonOutput:
    """Test --smart flag with JSON output."""

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_smart_has_all_sections(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = "test-project"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = [
            {
                "id": 1,
                "title": "Doc",
                "accessed_at": "2025-01-15",
                "access_count": 3,
                "relative_time": "1h ago",
            }
        ]
        mock_key_docs.return_value = [
            {"id": 2, "title": "Key", "access_count": 20},
        ]
        mock_tag_map.return_value = [
            {"name": "python", "count": 10},
        ]
        mock_stale.return_value = []

        result = runner.invoke(app, ["--format", "json", "--smart"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert "smart_recent" in data
        assert len(data["smart_recent"]) == 1
        assert data["smart_recent"][0]["relative_time"] == "1h ago"

        assert "key_docs" in data
        assert len(data["key_docs"]) == 1

        assert "tag_map" in data
        assert len(data["tag_map"]) == 1
        assert data["tag_map"][0]["name"] == "python"

    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_smart_skipped_in_brief(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_tag_map,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = []
        mock_tag_map.return_value = []

        result = runner.invoke(app, ["--format", "json", "--smart", "--brief"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "smart_recent" not in data
        assert "tag_map" not in data

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_smart_includes_stale_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_smart_recent.return_value = []
        mock_key_docs.return_value = []
        mock_tag_map.return_value = []
        mock_stale.return_value = [
            {"id": 5, "title": "Stale", "level": "WARNING", "days_stale": 30},
        ]

        result = runner.invoke(app, ["--format", "json", "--smart"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "stale_docs" in data
        assert len(data["stale_docs"]) == 1
        assert data["stale_docs"][0]["level"] == "WARNING"

    @patch("emdx.commands.prime._get_stale_docs")
    @patch("emdx.commands.prime._get_tag_map")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_smart_recent_docs")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_smart_plus_verbose_avoids_duplicate_key_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_recent,
        mock_smart_recent,
        mock_key_docs,
        mock_tag_map,
        mock_stale,
    ):
        """When both --smart and --verbose, key_docs should come from verbose."""
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_recent.return_value = []
        mock_smart_recent.return_value = []
        mock_key_docs.return_value = [
            {"id": 1, "title": "Doc", "access_count": 10},
        ]
        mock_tag_map.return_value = [{"name": "tag", "count": 1}]
        mock_stale.return_value = []

        result = runner.invoke(app, ["--format", "json", "--smart", "--verbose"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # key_docs should be present (from verbose)
        assert "key_docs" in data
        # smart_recent and tag_map should also be present
        assert "smart_recent" in data
        assert "tag_map" in data
        # key_docs should only be called once (verbose provides it,
        # smart skips it)
        assert mock_key_docs.call_count == 1
