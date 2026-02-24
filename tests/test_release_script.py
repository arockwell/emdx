"""Tests for scripts/release.py — changelog and tag detection."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from release import (  # noqa: E402
    categorize_commits,
    get_commits_since_version,
    get_latest_tag,
)


class TestGetLatestTag:
    """Tests for get_latest_tag() semver filtering."""

    def _mock_run(self, stdout: str) -> MagicMock:
        """Create a mock subprocess result."""
        result = MagicMock()
        result.stdout = stdout
        return result

    @patch("release.subprocess.run")
    def test_returns_latest_semver_tag(self, mock_run: Any) -> None:
        mock_run.return_value = self._mock_run("v0.22.1\nv0.22.0\nv0.21.0\n")
        assert get_latest_tag() == "v0.22.1"

    @patch("release.subprocess.run")
    def test_skips_non_semver_tags(self, mock_run: Any) -> None:
        mock_run.return_value = self._mock_run("vendor-setup\nv0.22.1\nv0.22.0\n")
        assert get_latest_tag() == "v0.22.1"

    @patch("release.subprocess.run")
    def test_returns_none_when_no_tags(self, mock_run: Any) -> None:
        mock_run.return_value = self._mock_run("")
        assert get_latest_tag() is None

    @patch("release.subprocess.run")
    def test_returns_none_when_no_semver_tags(self, mock_run: Any) -> None:
        mock_run.return_value = self._mock_run("vendor-setup\nv-beta\n")
        assert get_latest_tag() is None

    @patch("release.subprocess.run")
    def test_skips_prerelease_suffixes(self, mock_run: Any) -> None:
        mock_run.return_value = self._mock_run("v1.0.0-rc1\nv0.22.1\n")
        assert get_latest_tag() == "v0.22.1"


class TestGetCommitsSinceVersion:
    """Tests for get_commits_since_version() tag auto-detection."""

    @patch("release.subprocess.run")
    @patch("release.get_latest_tag", return_value="v0.22.1")
    def test_auto_detects_latest_tag(self, mock_tag: Any, mock_run: Any) -> None:
        result = MagicMock()
        result.stdout = "abc1234|fix: something\ndef5678|feat: new thing\n"
        mock_run.return_value = result

        get_commits_since_version()

        # Should have called git log with v0.22.1..HEAD
        cmd = mock_run.call_args[0][0]
        assert "v0.22.1..HEAD" in cmd

    @patch("release.subprocess.run")
    @patch("release.get_latest_tag", return_value=None)
    def test_returns_all_commits_when_no_tags(self, mock_tag: Any, mock_run: Any) -> None:
        result = MagicMock()
        result.stdout = "abc1234|fix: something\n"
        mock_run.return_value = result

        get_commits_since_version()

        # Should NOT have a version range — gets all commits
        cmd = mock_run.call_args[0][0]
        assert not any(".." in arg for arg in cmd)

    @patch("release.subprocess.run")
    def test_explicit_version_overrides_auto_detect(self, mock_run: Any) -> None:
        result = MagicMock()
        result.stdout = "abc1234|fix: something\n"
        mock_run.return_value = result

        get_commits_since_version("0.20.0")

        cmd = mock_run.call_args[0][0]
        assert "v0.20.0..HEAD" in cmd


class TestCategorizeCommits:
    """Tests for commit categorization."""

    def test_categorizes_feat_commits(self) -> None:
        commits = [{"hash": "abc1234", "message": "feat: add dark mode"}]
        cats = categorize_commits(commits)
        assert cats["features"] == ["add dark mode"]

    def test_categorizes_fix_commits(self) -> None:
        commits = [{"hash": "abc1234", "message": "fix: resolve crash"}]
        cats = categorize_commits(commits)
        assert cats["fixes"] == ["resolve crash"]

    def test_categorizes_scoped_feat(self) -> None:
        commits = [{"hash": "abc1234", "message": "feat(ui): add button"}]
        cats = categorize_commits(commits)
        assert cats["features"] == ["**ui**: add button"]

    def test_skips_merge_commits(self) -> None:
        commits = [{"hash": "abc1234", "message": "Merge branch 'main'"}]
        cats = categorize_commits(commits)
        assert all(len(v) == 0 for v in cats.values())

    @pytest.mark.parametrize(
        "prefix,category",
        [
            ("refactor", "refactor"),
            ("docs", "docs"),
            ("perf", "perf"),
            ("chore", "chore"),
        ],
    )
    def test_categorizes_by_prefix(self, prefix: str, category: str) -> None:
        commits = [{"hash": "abc1234", "message": f"{prefix}: some change"}]
        cats = categorize_commits(commits)
        assert len(cats[category]) == 1
