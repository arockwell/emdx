"""Tests for status command helper functions."""

from datetime import datetime, timedelta

from emdx.commands.status import _parse_timestamp, _relative_time, _running_duration


class TestParseTimestamp:
    """Tests for _parse_timestamp helper."""

    def test_none_returns_none(self):
        assert _parse_timestamp(None) is None

    def test_datetime_passthrough(self):
        dt = datetime(2026, 1, 15, 10, 30)
        assert _parse_timestamp(dt) == dt

    def test_iso_string(self):
        result = _parse_timestamp("2026-01-15T10:30:00")
        assert result == datetime(2026, 1, 15, 10, 30)

    def test_iso_string_with_z(self):
        result = _parse_timestamp("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_invalid_string_returns_none(self):
        assert _parse_timestamp("not a date") is None

    def test_empty_string_returns_none(self):
        assert _parse_timestamp("") is None


class TestRelativeTime:
    """Tests for _relative_time helper."""

    def test_none_returns_empty(self):
        assert _relative_time(None) == ""

    def test_recent_shows_seconds(self):
        recent = datetime.utcnow() - timedelta(seconds=30)
        result = _relative_time(recent)
        assert "s ago" in result

    def test_minutes_ago(self):
        mins_ago = datetime.utcnow() - timedelta(minutes=5)
        result = _relative_time(mins_ago)
        assert "m ago" in result
        assert "5m ago" == result

    def test_hours_ago(self):
        hours_ago = datetime.utcnow() - timedelta(hours=3)
        result = _relative_time(hours_ago)
        assert "h ago" in result
        assert "3h ago" == result

    def test_days_ago(self):
        days_ago = datetime.utcnow() - timedelta(days=2)
        result = _relative_time(days_ago)
        assert "d ago" in result
        assert "2d ago" == result


class TestRunningDuration:
    """Tests for _running_duration helper."""

    def test_none_returns_empty(self):
        assert _running_duration(None) == ""

    def test_seconds(self):
        recent = datetime.utcnow() - timedelta(seconds=45)
        result = _running_duration(recent)
        assert result.endswith("s")
        assert "m" not in result

    def test_minutes(self):
        mins_ago = datetime.utcnow() - timedelta(minutes=3, seconds=15)
        result = _running_duration(mins_ago)
        assert result.startswith("3m")

    def test_hours(self):
        hours_ago = datetime.utcnow() - timedelta(hours=2, minutes=30)
        result = _running_duration(hours_ago)
        assert result.startswith("2h")
        assert "30m" in result
