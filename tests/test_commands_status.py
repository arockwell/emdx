"""Tests for status command helper functions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import emdx.database.connection as conn_module
from emdx.commands.status import (
    _collect_mirror_data,
    _collect_vitals_data,
    _parse_timestamp,
    _relative_time,
    _running_duration,
    _show_mirror,
    _show_vitals,
)
from emdx.database.connection import DatabaseConnection
from emdx.database.documents import save_document


def _get_conn() -> DatabaseConnection:
    """Get the current test db_connection (follows monkeypatch)."""
    return conn_module.db_connection


def _clear_all_docs() -> None:
    """Mark all documents as deleted in the test DB.

    Uses soft-delete (is_deleted = 1) to avoid foreign-key cascade
    issues with the many tables that reference documents.
    """
    with _get_conn().get_connection() as conn:
        conn.execute("UPDATE documents SET is_deleted = 1 WHERE is_deleted = 0")
        conn.commit()


class TestParseTimestamp:
    """Tests for _parse_timestamp helper."""

    def test_none_returns_none(self) -> None:
        assert _parse_timestamp(None) is None

    def test_datetime_passthrough(self) -> None:
        dt = datetime(2026, 1, 15, 10, 30)
        assert _parse_timestamp(dt) == dt

    def test_iso_string(self) -> None:
        result = _parse_timestamp("2026-01-15T10:30:00")
        assert result == datetime(2026, 1, 15, 10, 30)

    def test_iso_string_with_z(self) -> None:
        result = _parse_timestamp("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_timestamp("not a date") is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_timestamp("") is None


class TestRelativeTime:
    """Tests for _relative_time helper."""

    def test_none_returns_empty(self) -> None:
        assert _relative_time(None) == ""

    def test_recent_shows_seconds(self) -> None:
        recent = datetime.utcnow() - timedelta(seconds=30)
        result = _relative_time(recent)
        assert "s ago" in result

    def test_minutes_ago(self) -> None:
        mins_ago = datetime.utcnow() - timedelta(minutes=5)
        result = _relative_time(mins_ago)
        assert "m ago" in result
        assert "5m ago" == result

    def test_hours_ago(self) -> None:
        hours_ago = datetime.utcnow() - timedelta(hours=3)
        result = _relative_time(hours_ago)
        assert "h ago" in result
        assert "3h ago" == result

    def test_days_ago(self) -> None:
        days_ago = datetime.utcnow() - timedelta(days=2)
        result = _relative_time(days_ago)
        assert "d ago" in result
        assert "2d ago" == result


class TestRunningDuration:
    """Tests for _running_duration helper."""

    def test_none_returns_empty(self) -> None:
        assert _running_duration(None) == ""

    def test_seconds(self) -> None:
        recent = datetime.utcnow() - timedelta(seconds=45)
        result = _running_duration(recent)
        assert result.endswith("s")
        assert "m" not in result

    def test_minutes(self) -> None:
        mins_ago = datetime.utcnow() - timedelta(minutes=3, seconds=15)
        result = _running_duration(mins_ago)
        assert result.startswith("3m")

    def test_hours(self) -> None:
        hours_ago = datetime.utcnow() - timedelta(hours=2, minutes=30)
        result = _running_duration(hours_ago)
        assert result.startswith("2h")
        assert "30m" in result


# ── Vitals tests ──────────────────────────────────────────────────────


def _seed_docs(n: int = 10, project: str = "test-proj") -> list[int]:
    """Insert N documents with tags into the test database."""
    ids: list[int] = []
    for i in range(n):
        doc_id = save_document(
            f"Doc {i}",
            f"Content {i}",
            project=project,
            tags=["alpha"] if i % 2 == 0 else None,
        )
        ids.append(doc_id)
    return ids


class TestCollectVitalsData:
    """Tests for _collect_vitals_data."""

    def test_vitals_returns_correct_structure(self) -> None:
        """Vitals data contains all expected keys."""
        _seed_docs(6)
        data = _collect_vitals_data()

        assert "total_docs" in data
        assert "by_project" in data
        assert "growth_per_week" in data
        assert "embedding_coverage_pct" in data
        assert "access_distribution" in data
        assert "tag_coverage_pct" in data
        assert "tasks" in data
        assert data["total_docs"] >= 6

    def test_vitals_project_counts(self) -> None:
        """by_project sums to total_docs."""
        _seed_docs(5, project="proj-a")
        _seed_docs(3, project="proj-b")
        data = _collect_vitals_data()

        total_from_projects = sum(p["count"] for p in data["by_project"])
        assert total_from_projects == data["total_docs"]

    def test_vitals_growth_has_four_weeks(self) -> None:
        """Growth data always has 4 weekly entries."""
        _seed_docs(3)
        data = _collect_vitals_data()
        assert len(data["growth_per_week"]) == 4

    def test_vitals_access_distribution_four_buckets(self) -> None:
        """Access distribution has exactly 4 buckets."""
        _seed_docs(3)
        data = _collect_vitals_data()
        assert len(data["access_distribution"]) == 4
        ranges = [b["range"] for b in data["access_distribution"]]
        assert "0 views" in ranges
        assert "1-5 views" in ranges
        assert "6-20 views" in ranges
        assert "21+ views" in ranges

    def test_vitals_tag_coverage_percentage(self) -> None:
        """Tag coverage is between 0 and 100."""
        _seed_docs(6)
        data = _collect_vitals_data()
        assert 0 <= data["tag_coverage_pct"] <= 100

    def test_vitals_task_stats(self) -> None:
        """Task stats have open/done/total."""
        _seed_docs(2)
        data = _collect_vitals_data()
        t = data["tasks"]
        assert "open" in t
        assert "done" in t
        assert "total" in t
        assert t["total"] >= 0

    def test_vitals_embedding_coverage_no_embeddings(self) -> None:
        """Embedding coverage is 0 when no embeddings exist."""
        _seed_docs(3)
        data = _collect_vitals_data()
        # Test DB has no embeddings inserted
        assert data["embedding_coverage_pct"] == 0.0


class TestShowVitals:
    """Tests for _show_vitals display function."""

    def test_show_vitals_empty_kb(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty KB shows friendly message instead of crash."""
        _clear_all_docs()
        _show_vitals(rich_output=False)
        captured = capsys.readouterr()
        assert "No documents yet" in captured.out

    def test_show_vitals_plain(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Plain text output contains key metrics."""
        _seed_docs(6)
        _show_vitals(rich_output=False)
        captured = capsys.readouterr()
        assert "Documents:" in captured.out
        assert "Embedding coverage:" in captured.out
        assert "Tag coverage:" in captured.out
        assert "Tasks:" in captured.out

    def test_show_vitals_rich_no_crash(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Rich output mode does not crash."""
        _seed_docs(3)
        _show_vitals(rich_output=True)
        # If we get here without exception, it passed


# ── Mirror tests ──────────────────────────────────────────────────────


class TestCollectMirrorData:
    """Tests for _collect_mirror_data."""

    def test_mirror_returns_correct_structure(self) -> None:
        """Mirror data has all expected keys."""
        _seed_docs(6)
        data = _collect_mirror_data()

        assert "total_docs" in data
        assert "top_tags" in data
        assert "weekly_activity" in data
        assert "temporal_pattern" in data
        assert "project_balance" in data
        assert "staleness" in data

    def test_mirror_temporal_pattern_valid(self) -> None:
        """Temporal pattern is one of the known values."""
        _seed_docs(6)
        data = _collect_mirror_data()
        assert data["temporal_pattern"] in (
            "steady",
            "burst",
            "sporadic",
            "inactive",
        )

    def test_mirror_weekly_activity_eight_weeks(self) -> None:
        """Weekly activity has 8 entries."""
        _seed_docs(3)
        data = _collect_mirror_data()
        assert len(data["weekly_activity"]) == 8

    def test_mirror_staleness_keys(self) -> None:
        """Staleness data has 30/60/90 day breakdowns."""
        _seed_docs(6)
        data = _collect_mirror_data()
        s = data["staleness"]
        assert "over_30_days_pct" in s
        assert "over_60_days_pct" in s
        assert "over_90_days_pct" in s

    def test_mirror_staleness_values_are_percentages(self) -> None:
        """Staleness values are between 0 and 100."""
        _seed_docs(6)
        data = _collect_mirror_data()
        s = data["staleness"]
        for key in (
            "over_30_days_pct",
            "over_60_days_pct",
            "over_90_days_pct",
        ):
            assert 0 <= s[key] <= 100

    def test_mirror_top_tags(self) -> None:
        """Top tags include tagged docs."""
        _seed_docs(10)
        data = _collect_mirror_data()
        if data["top_tags"]:
            tag = data["top_tags"][0]
            assert "tag" in tag
            assert "count" in tag
            assert "pct" in tag
            assert tag["count"] > 0


class TestShowMirror:
    """Tests for _show_mirror display function."""

    def test_show_mirror_empty_kb(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty KB shows friendly message."""
        _clear_all_docs()
        _show_mirror(rich_output=False)
        captured = capsys.readouterr()
        assert "No documents yet" in captured.out

    def test_show_mirror_too_few_docs(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Less than 5 docs shows 'too few' message."""
        _clear_all_docs()
        _seed_docs(3)
        _show_mirror(rich_output=False)
        captured = capsys.readouterr()
        assert "Too few documents" in captured.out

    def test_show_mirror_narrative_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With enough docs, mirror shows narrative text."""
        # Ensure there are enough docs
        _seed_docs(10)
        _show_mirror(rich_output=False)
        captured = capsys.readouterr()
        # Should contain some narrative content
        assert len(captured.out.strip()) > 0

    def test_show_mirror_rich_no_crash(self) -> None:
        """Rich output mode does not crash."""
        _seed_docs(10)
        _show_mirror(rich_output=True)
        # If we get here without exception, it passed

    def test_show_mirror_mentions_staleness(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Mirror output mentions stale docs when some exist."""
        _clear_all_docs()
        # Create docs and make them old
        ids = _seed_docs(8)
        with _get_conn().get_connection() as conn:
            conn.execute(
                "UPDATE documents "
                "SET accessed_at = datetime('now', '-45 days') "
                "WHERE id IN ({})".format(",".join(str(i) for i in ids[:5])),
            )
            conn.commit()

        _show_mirror(rich_output=False)
        captured = capsys.readouterr()
        # Should mention stale percentage since 5/8 = 62.5% are > 30 days
        assert "%" in captured.out
