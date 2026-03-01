"""Tests for the code-drift detection command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from emdx.commands.code_drift import (
    CodeDriftReport,
    StaleReference,
    _extract_rename_target,
    _search_codebase,
    code_drift_command,
    detect_code_drift,
    extract_code_identifiers,
)

# ── extract_code_identifiers tests ────────────────────────────────────


class TestExtractCodeIdentifiers:
    """Tests for backtick identifier extraction."""

    def test_extracts_function_names(self) -> None:
        content = "Use `my_function()` to do stuff."
        result = extract_code_identifiers(content)
        assert "my_function()" in result

    def test_extracts_class_names(self) -> None:
        content = "The `MyClass` handles this."
        result = extract_code_identifiers(content)
        assert "MyClass" in result

    def test_extracts_file_paths(self) -> None:
        content = "See `path/to/file.py` for details."
        result = extract_code_identifiers(content)
        assert "path/to/file.py" in result

    def test_extracts_dotted_names(self) -> None:
        content = "Call `module.attribute` to get it."
        result = extract_code_identifiers(content)
        assert "module.attribute" in result

    def test_skips_cli_flags(self) -> None:
        content = "Use `--verbose` and `-v` flags."
        result = extract_code_identifiers(content)
        assert "--verbose" not in result
        assert "-v" not in result

    def test_skips_short_identifiers(self) -> None:
        content = "The `id` field."
        result = extract_code_identifiers(content)
        assert "id" not in result

    def test_skips_boolean_literals(self) -> None:
        content = "Set to `true` or `false`."
        result = extract_code_identifiers(content)
        assert "true" not in result
        assert "false" not in result

    def test_deduplicates(self) -> None:
        content = "Use `MyClass` here and `MyClass` there."
        result = extract_code_identifiers(content)
        assert result.count("MyClass") == 1

    def test_returns_sorted(self) -> None:
        content = "`Zebra` and `Alpha` classes."
        result = extract_code_identifiers(content)
        assert result == ["Alpha", "Zebra"]

    def test_empty_content(self) -> None:
        result = extract_code_identifiers("")
        assert result == []

    def test_no_backticks(self) -> None:
        content = "Just plain text without any code."
        result = extract_code_identifiers(content)
        assert result == []

    def test_multiple_types(self) -> None:
        content = "Use `my_func()` from `MyClass` in `src/main.py` via `os.path`."
        result = extract_code_identifiers(content)
        assert "my_func()" in result
        assert "MyClass" in result
        assert "src/main.py" in result
        assert "os.path" in result

    def test_skips_plain_words_in_backticks(self) -> None:
        """Single lowercase words that aren't code patterns."""
        content = "The `important` thing is `working`."
        result = extract_code_identifiers(content)
        assert "important" not in result
        assert "working" not in result


# ── _search_codebase tests ────────────────────────────────────────────


class TestSearchCodebase:
    """Tests for codebase search with mocked subprocess."""

    @patch("emdx.commands.code_drift.subprocess.run")
    def test_found_with_rg(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="src/foo.py\n")
        assert _search_codebase("my_func()", use_rg=True) is True
        # Should strip () and search for my_func
        call_args = mock_run.call_args[0][0]
        assert "rg" in call_args
        assert "my_func" in call_args

    @patch("emdx.commands.code_drift.subprocess.run")
    def test_not_found_with_rg(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _search_codebase("missing_func()", use_rg=True) is False

    @patch("emdx.commands.code_drift.subprocess.run")
    def test_fallback_to_grep(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="src/bar.py\n")
        assert _search_codebase("MyClass", use_rg=False) is True
        call_args = mock_run.call_args[0][0]
        assert "grep" in call_args


# ── _extract_rename_target tests ──────────────────────────────────────


class TestExtractRenameTarget:
    """Tests for rename detection in git diffs."""

    def test_detects_function_rename(self) -> None:
        diff = "--- a/foo.py\n+++ b/foo.py\n-def old_func():\n+def new_func():\n"
        result = _extract_rename_target(diff, "old_func")
        assert result == "new_func"

    def test_detects_class_rename(self) -> None:
        diff = "--- a/foo.py\n+++ b/foo.py\n-class OldClass:\n+class NewClass:\n"
        result = _extract_rename_target(diff, "OldClass")
        assert result == "NewClass"

    def test_returns_none_when_no_match(self) -> None:
        diff = "--- a/foo.py\n+++ b/foo.py\n+some unrelated change\n"
        result = _extract_rename_target(diff, "missing_name")
        assert result is None

    def test_returns_none_for_same_name(self) -> None:
        diff = "--- a/foo.py\n+++ b/foo.py\n-def same_func():\n+def same_func():\n+    pass\n"
        result = _extract_rename_target(diff, "same_func")
        assert result is None


# ── detect_code_drift tests ──────────────────────────────────────────


class TestDetectCodeDrift:
    """Tests for the main drift detection logic."""

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_detects_stale_reference(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        mock_docs.return_value = [
            (1, "Test Doc", "Use `NonExistentClass` here."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = False
        mock_search.return_value = False

        report = detect_code_drift()

        assert report["total_docs_scanned"] == 1
        assert report["total_identifiers_checked"] == 1
        assert len(report["stale_references"]) == 1
        ref = report["stale_references"][0]
        assert ref["doc_id"] == 1
        assert ref["identifier"] == "NonExistentClass"
        assert ref["reason"] == "not found in codebase"

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_no_drift_when_all_found(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        mock_docs.return_value = [
            (1, "Good Doc", "Use `ExistingClass` here."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = True
        mock_search.return_value = True

        report = detect_code_drift()

        assert report["total_docs_scanned"] == 1
        assert report["total_identifiers_checked"] == 1
        assert len(report["stale_references"]) == 0

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_no_docs(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        mock_docs.return_value = []
        mock_has_tool.return_value = True
        mock_git_repo.return_value = True

        report = detect_code_drift()

        assert report["total_docs_scanned"] == 0
        assert report["total_identifiers_checked"] == 0
        assert len(report["stale_references"]) == 0

    @patch("emdx.commands.code_drift._get_documents")
    @patch("emdx.commands.code_drift._search_codebase")
    @patch("emdx.commands.code_drift._check_git_history")
    @patch("emdx.commands.code_drift._has_tool")
    @patch("emdx.commands.code_drift._is_git_repo")
    def test_includes_git_history_info(
        self,
        mock_git_repo: MagicMock,
        mock_has_tool: MagicMock,
        mock_git_history: MagicMock,
        mock_search: MagicMock,
        mock_docs: MagicMock,
    ) -> None:
        mock_docs.return_value = [
            (1, "Doc", "Use `OldFunc()` here."),
        ]
        mock_has_tool.return_value = True
        mock_git_repo.return_value = True
        mock_search.return_value = False
        mock_git_history.return_value = (
            "last changed in abc1234 (rename old to new)",
            "new_func",
        )

        report = detect_code_drift()

        assert len(report["stale_references"]) == 1
        ref = report["stale_references"][0]
        assert "abc1234" in ref["reason"]
        assert ref["suggestion"] == "new_func"


# ── CLI command tests ─────────────────────────────────────────────────


class TestCodeDriftCommand:
    """Tests for the CLI command output formatting."""

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_json_output(self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=1,
            total_identifiers_checked=2,
            stale_references=[
                StaleReference(
                    doc_id=1,
                    doc_title="Test",
                    identifier="MissingClass",
                    reason="not found in codebase",
                    suggestion=None,
                ),
            ],
        )

        code_drift_command(project=None, limit=None, output_json=True, fix=False)

        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert data["total_docs_scanned"] == 1
        assert len(data["stale_references"]) == 1
        assert data["stale_references"][0]["identifier"] == "MissingClass"

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_no_docs_message(
        self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=0,
            total_identifiers_checked=0,
            stale_references=[],
        )

        code_drift_command(project=None, limit=None, output_json=False, fix=False)

        captured = capsys.readouterr()
        assert "No documents to check." in captured.out

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_clean_message(
        self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=5,
            total_identifiers_checked=10,
            stale_references=[],
        )

        code_drift_command(project=None, limit=None, output_json=False, fix=False)

        captured = capsys.readouterr()
        assert "All code references look current!" in captured.out

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_stale_refs_output(
        self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=2,
            total_identifiers_checked=5,
            stale_references=[
                StaleReference(
                    doc_id=42,
                    doc_title="My Doc",
                    identifier="OldClass",
                    reason="not found in codebase",
                    suggestion=None,
                ),
            ],
        )

        code_drift_command(project=None, limit=None, output_json=False, fix=False)

        captured = capsys.readouterr()
        assert "#42" in captured.out
        assert "My Doc" in captured.out
        assert "`OldClass`" in captured.out
        assert "not found in codebase" in captured.out

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_fix_flag_shows_suggestion(
        self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=1,
            total_identifiers_checked=1,
            stale_references=[
                StaleReference(
                    doc_id=1,
                    doc_title="Doc",
                    identifier="OldFunc()",
                    reason="last changed in abc123 (rename)",
                    suggestion="new_func",
                ),
            ],
        )

        code_drift_command(project=None, limit=None, output_json=False, fix=True)

        captured = capsys.readouterr()
        assert "suggestion: `new_func`" in captured.out

    @patch("emdx.commands.code_drift.detect_code_drift")
    def test_fix_flag_no_suggestion_no_line(
        self, mock_detect: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_detect.return_value = CodeDriftReport(
            total_docs_scanned=1,
            total_identifiers_checked=1,
            stale_references=[
                StaleReference(
                    doc_id=1,
                    doc_title="Doc",
                    identifier="Missing()",
                    reason="not found in codebase",
                    suggestion=None,
                ),
            ],
        )

        code_drift_command(project=None, limit=None, output_json=False, fix=True)

        captured = capsys.readouterr()
        assert "suggestion:" not in captured.out
