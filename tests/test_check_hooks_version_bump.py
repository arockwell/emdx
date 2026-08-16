"""Tests for the hooks/-vs-plugin-version CI guard (pure logic, no git calls)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_hooks_version_bump import check, hooks_changed, version_bumped  # noqa: E402


class TestHooksChanged:
    def test_true_when_a_hooks_file_changed(self) -> None:
        assert hooks_changed(["hooks/save-subagent-output.sh", "README.md"])

    def test_false_when_no_hooks_file_changed(self) -> None:
        assert not hooks_changed(["emdx/cli.py", "README.md"])

    def test_false_on_empty_diff(self) -> None:
        assert not hooks_changed([])

    def test_ignores_lookalike_paths_outside_hooks_root(self) -> None:
        assert not hooks_changed(
            [".claude/hooks/prime.sh", "vscode-extension/webview/src/hooks/useVscode.ts"]
        )


class TestVersionBumped:
    def test_true_when_version_differs(self) -> None:
        assert version_bumped("0.34.2", "0.34.3")

    def test_false_when_version_unchanged(self) -> None:
        assert not version_bumped("0.34.2", "0.34.2")

    def test_false_when_head_version_missing(self) -> None:
        assert not version_bumped("0.34.2", None)

    def test_true_when_base_version_missing_and_head_present(self) -> None:
        assert version_bumped(None, "0.34.2")


class TestCheck:
    def test_passes_when_hooks_untouched(self) -> None:
        ok, _ = check(["README.md"], "0.34.2", "0.34.2")
        assert ok

    def test_passes_when_hooks_changed_and_version_bumped(self) -> None:
        ok, _ = check(["hooks/hooks.json"], "0.34.2", "0.34.3")
        assert ok

    def test_fails_when_hooks_changed_without_version_bump(self) -> None:
        ok, message = check(["hooks/save-subagent-output.sh"], "0.34.2", "0.34.2")
        assert not ok
        assert "plugin.json" in message

    def test_passes_for_version_bump_only_pr(self) -> None:
        """A release PR that only bumps the version touches no hooks files."""
        ok, _ = check(
            [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", "pyproject.toml"],
            "0.34.2",
            "0.34.3",
        )
        assert ok
