"""Tests for the status command."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.main import app as main_app

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# Default status (shows stats)
# ---------------------------------------------------------------------------
class TestStatusDefault:
    """Tests for the default status command output."""

    @patch("emdx.commands.status.get_stats", create=True)
    @patch("emdx.models.documents.get_stats")
    def test_status_default_shows_stats(self, mock_get_stats: Any, *_: Any) -> None:
        """Default status shows knowledge base statistics."""
        mock_get_stats.return_value = {
            "total_documents": 10,
            "total_projects": 2,
            "total_views": 50,
            "avg_views": 5.0,
            "table_size": "1 MB",
            "most_viewed": {"title": "Top Doc", "access_count": 20},
            "newest_doc": "2026-01-15T10:00:00",
        }

        result = runner.invoke(main_app, ["status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Knowledge Base Statistics" in out or "Total Documents" in out

    @patch("emdx.models.documents.get_stats")
    def test_status_json_output(self, mock_get_stats: Any) -> None:
        """Status --json produces valid JSON."""
        mock_get_stats.return_value = {
            "total_documents": 5,
            "total_projects": 1,
            "total_views": 25,
            "avg_views": 5.0,
            "table_size": "0.5 MB",
            "most_viewed": None,
            "newest_doc": "2026-01-10",
        }

        result = runner.invoke(main_app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_documents"] == 5


# ---------------------------------------------------------------------------
# Status --stats
# ---------------------------------------------------------------------------
class TestStatusStats:
    """Tests for the status --stats flag."""

    @patch("emdx.models.documents.get_stats")
    def test_status_stats(self, mock_get_stats: Any) -> None:
        """Status --stats shows knowledge base statistics."""
        mock_get_stats.return_value = {
            "total_documents": 42,
            "total_projects": 3,
            "total_views": 100,
            "avg_views": 2.4,
            "table_size": "2 MB",
            "most_viewed": {"title": "Best Doc", "access_count": 30},
            "newest_doc": "2026-02-01",
        }

        result = runner.invoke(main_app, ["status", "--stats"])
        assert result.exit_code == 0
        out = _out(result)
        assert "42" in out or "Total Documents" in out

    @patch("emdx.models.documents.get_stats")
    def test_status_stats_json(self, mock_get_stats: Any) -> None:
        """Status --stats --json produces valid JSON."""
        mock_get_stats.return_value = {
            "total_documents": 42,
            "total_projects": 3,
            "total_views": 100,
            "avg_views": 2.4,
            "table_size": "2 MB",
            "most_viewed": None,
            "newest_doc": None,
        }

        result = runner.invoke(main_app, ["status", "--stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_documents"] == 42


# ---------------------------------------------------------------------------
# Status --health
# ---------------------------------------------------------------------------
class TestStatusHealth:
    """Tests for the status --health flag."""

    @patch("emdx.commands.status._show_health")
    def test_status_health(self, mock_show_health: Any) -> None:
        """Status --health invokes the health display."""
        result = runner.invoke(main_app, ["status", "--health"])
        assert result.exit_code == 0
        mock_show_health.assert_called_once()

    @patch("emdx.commands.status._collect_health_json")
    def test_status_health_json(self, mock_collect: Any) -> None:
        """Status --health --json produces valid JSON."""
        mock_collect.return_value = {
            "overall_score": 0.85,
            "overall_status": "good",
            "metrics": {},
            "statistics": {},
            "timestamp": "2026-01-15",
        }

        result = runner.invoke(main_app, ["status", "--health", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["overall_score"] == 0.85


# ---------------------------------------------------------------------------
# Status --vitals
# ---------------------------------------------------------------------------
class TestStatusVitals:
    """Tests for the status --vitals flag."""

    @patch("emdx.commands.status._show_vitals")
    def test_status_vitals(self, mock_show: Any) -> None:
        """Status --vitals invokes the vitals display."""
        result = runner.invoke(main_app, ["status", "--vitals"])
        assert result.exit_code == 0
        mock_show.assert_called_once()

    @patch("emdx.commands.status._collect_vitals_data")
    def test_status_vitals_json(self, mock_collect: Any) -> None:
        """Status --vitals --json produces valid JSON."""
        mock_collect.return_value = {
            "total_docs": 10,
            "by_project": [{"project": "test", "count": 10}],
            "growth_per_week": [{"week": "last 7d", "count": 3}],
            "embedding_coverage_pct": 80.0,
            "access_distribution": [{"range": "0 views", "count": 2}],
            "tag_coverage_pct": 90.0,
            "tasks": {"open": 5, "done": 10, "total": 15},
        }

        result = runner.invoke(main_app, ["status", "--vitals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_docs"] == 10


# ---------------------------------------------------------------------------
# Status --mirror
# ---------------------------------------------------------------------------
class TestStatusMirror:
    """Tests for the status --mirror flag."""

    @patch("emdx.commands.status._show_mirror")
    def test_status_mirror(self, mock_show: Any) -> None:
        """Status --mirror invokes the mirror display."""
        result = runner.invoke(main_app, ["status", "--mirror"])
        assert result.exit_code == 0
        mock_show.assert_called_once()

    @patch("emdx.commands.status._collect_mirror_data")
    def test_status_mirror_json(self, mock_collect: Any) -> None:
        """Status --mirror --json produces valid JSON."""
        mock_collect.return_value = {
            "total_docs": 20,
            "top_tags": [{"tag": "python", "count": 10, "pct": 50.0}],
            "weekly_activity": [{"week": "this week", "count": 5}],
            "temporal_pattern": "steady",
            "project_balance": [{"project": "test", "count": 20}],
            "staleness": {
                "over_30_days_pct": 10.0,
                "over_60_days_pct": 5.0,
                "over_90_days_pct": 2.0,
            },
        }

        result = runner.invoke(main_app, ["status", "--mirror", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_docs"] == 20
        assert data["temporal_pattern"] == "steady"


# ---------------------------------------------------------------------------
# Status helper: _get_status_emoji
# ---------------------------------------------------------------------------
class TestStatusEmoji:
    """Tests for the _get_status_emoji helper."""

    def test_high_score(self) -> None:
        from emdx.commands.status import _get_status_emoji

        assert _get_status_emoji(90) == "\u2705"  # checkmark

    def test_medium_score(self) -> None:
        from emdx.commands.status import _get_status_emoji

        assert _get_status_emoji(70) == "\u26a0\ufe0f"  # warning

    def test_low_score(self) -> None:
        from emdx.commands.status import _get_status_emoji

        assert _get_status_emoji(40) == "\u274c"  # x mark
