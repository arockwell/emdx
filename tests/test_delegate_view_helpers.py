"""Tests for _extract_pr_url helper from delegate command module."""

from emdx.commands.delegate import _extract_pr_url


class TestExtractPrUrl:
    def test_extracts_pr_url_from_description(self) -> None:
        desc = "pr:https://github.com/owner/repo/pull/123"
        assert _extract_pr_url(desc) == "https://github.com/owner/repo/pull/123"

    def test_extracts_pr_url_with_surrounding_text(self) -> None:
        desc = "Created PR: https://github.com/owner/repo/pull/456 — done"
        assert _extract_pr_url(desc) == "https://github.com/owner/repo/pull/456"

    def test_returns_none_when_no_pr_url(self) -> None:
        assert _extract_pr_url("no url here, just a description") is None

    def test_returns_none_for_none_description(self) -> None:
        assert _extract_pr_url(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert _extract_pr_url("") is None
