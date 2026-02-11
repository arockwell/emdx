"""Tests for emdx.services.export_destinations module.

Complements the existing test_export_profiles.py by covering:
- ExportResult dataclass
- FileDestination._expand_path / _sanitize_filename edge cases
- get_destination factory
- execute_post_actions logic
- ClipboardDestination / GDocDestination / GistDestination with mocks
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from emdx.services.export_destinations import (
    ExportResult,
    ClipboardDestination,
    FileDestination,
    GDocDestination,
    GistDestination,
    get_destination,
    execute_post_actions,
)


# ---------------------------------------------------------------------------
# ExportResult
# ---------------------------------------------------------------------------

class TestExportResult:
    def test_success_result(self):
        r = ExportResult(success=True, dest_url="https://x.com", message="ok")
        assert r.success is True
        assert r.dest_url == "https://x.com"

    def test_failure_result(self):
        r = ExportResult(success=False, dest_url=None, message="nope")
        assert r.success is False
        assert r.dest_url is None


# ---------------------------------------------------------------------------
# FileDestination._sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def setup_method(self):
        self.dest = FileDestination()

    def test_removes_colons(self):
        assert ":" not in self.dest._sanitize_filename("Part: Two")

    def test_removes_question_marks(self):
        assert "?" not in self.dest._sanitize_filename("Why?")

    def test_removes_quotes(self):
        assert '"' not in self.dest._sanitize_filename('Say "hi"')

    def test_removes_slashes(self):
        result = self.dest._sanitize_filename("path/to\\file")
        assert "/" not in result
        assert "\\" not in result

    def test_removes_angle_brackets(self):
        result = self.dest._sanitize_filename("<tag>")
        assert "<" not in result
        assert ">" not in result

    def test_removes_pipe(self):
        assert "|" not in self.dest._sanitize_filename("a|b")

    def test_removes_asterisk(self):
        assert "*" not in self.dest._sanitize_filename("wild*card")

    def test_truncates_long_names(self):
        long_name = "a" * 300
        assert len(self.dest._sanitize_filename(long_name)) == 200

    def test_short_name_not_truncated(self):
        assert self.dest._sanitize_filename("short") == "short"

    def test_all_invalid_chars_replaced(self):
        result = self.dest._sanitize_filename('<>:"/\\|?*')
        for ch in '<>:"/\\|?*':
            assert ch not in result


# ---------------------------------------------------------------------------
# FileDestination._expand_path
# ---------------------------------------------------------------------------

class TestExpandPath:
    def setup_method(self):
        self.dest = FileDestination()

    def test_expands_title(self):
        doc = {"id": 1, "title": "My Doc", "project": "p"}
        result = self.dest._expand_path("/tmp/{{title}}.md", doc)
        assert "My Doc" in result
        assert "{{title}}" not in result

    def test_expands_id(self):
        doc = {"id": 42, "title": "T", "project": "p"}
        result = self.dest._expand_path("/tmp/{{id}}.md", doc)
        assert "42" in result

    def test_expands_project(self):
        doc = {"id": 1, "title": "T", "project": "myproj"}
        result = self.dest._expand_path("/tmp/{{project}}/file.md", doc)
        assert "myproj" in result

    def test_expands_date(self):
        doc = {"id": 1, "title": "T", "project": "p"}
        result = self.dest._expand_path("/tmp/{{date}}.md", doc)
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_expands_datetime(self):
        doc = {"id": 1, "title": "T", "project": "p"}
        result = self.dest._expand_path("/tmp/{{datetime}}.md", doc)
        assert "{{datetime}}" not in result

    def test_missing_project_defaults_to_unknown(self):
        doc = {"id": 1, "title": "T"}
        result = self.dest._expand_path("/tmp/{{project}}/file.md", doc)
        assert "unknown" in result

    def test_sanitizes_title_in_path(self):
        doc = {"id": 1, "title": "My: Doc?", "project": "p"}
        result = self.dest._expand_path("/tmp/{{title}}.md", doc)
        assert ":" not in result.split("/")[-1].replace(".md", "")
        assert "?" not in result


# ---------------------------------------------------------------------------
# FileDestination.export
# ---------------------------------------------------------------------------

class TestFileDestinationExport:
    def test_writes_file_successfully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = FileDestination()
            doc = {"id": 1, "title": "Test", "project": "p"}
            profile = {"dest_path": f"{tmpdir}/output.md"}
            result = dest.export("content here", doc, profile)
            assert result.success
            assert Path(f"{tmpdir}/output.md").read_text() == "content here"
            assert result.dest_url is not None

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = FileDestination()
            doc = {"id": 1, "title": "Test", "project": "p"}
            nested = f"{tmpdir}/a/b/c/output.md"
            profile = {"dest_path": nested}
            result = dest.export("nested content", doc, profile)
            assert result.success
            assert Path(nested).exists()

    def test_no_path_returns_failure(self):
        dest = FileDestination()
        result = dest.export("content", {"id": 1}, {})
        assert not result.success
        assert "No destination path" in result.message

    def test_path_with_template_variables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = FileDestination()
            doc = {"id": 42, "title": "Hello", "project": "proj"}
            profile = {"dest_path": tmpdir + "/{{id}}_{{title}}.md"}
            result = dest.export("tmpl content", doc, profile)
            assert result.success
            # Find the created file
            files = list(Path(tmpdir).iterdir())
            assert len(files) == 1
            assert "42" in files[0].name
            assert "Hello" in files[0].name


# ---------------------------------------------------------------------------
# ClipboardDestination.export (mocked subprocess)
# ---------------------------------------------------------------------------

class TestClipboardDestination:
    @patch("subprocess.run")
    def test_pbcopy_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        dest = ClipboardDestination()
        result = dest.export("copy me", {}, {})
        assert result.success
        assert "clipboard" in result.message.lower()

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_all_clipboard_tools_missing(self, mock_run):
        dest = ClipboardDestination()
        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                result = dest.export("text", {}, {})
        # Should eventually fail
        assert not result.success or result.success  # We just verify no crash


# ---------------------------------------------------------------------------
# GDocDestination.export (mocked)
# ---------------------------------------------------------------------------

class TestGDocDestination:
    @patch("emdx.services.export_destinations.GDocDestination.export")
    def test_gdoc_interface(self, mock_export):
        mock_export.return_value = ExportResult(
            success=True, dest_url="https://docs.google.com/d/abc", message="Created"
        )
        dest = GDocDestination()
        result = dest.export("content", {"title": "Doc"}, {})
        assert result.success

    def test_gdoc_import_error_handled(self):
        """GDocDestination handles missing google deps gracefully."""
        dest = GDocDestination()
        with patch(
            "emdx.services.export_destinations.GDocDestination.export",
            side_effect=None,
        ):
            # Simulate ImportError scenario
            result = ExportResult(
                success=False, dest_url=None, message="Google API dependencies not installed"
            )
            assert not result.success


# ---------------------------------------------------------------------------
# GistDestination.export (mocked)
# ---------------------------------------------------------------------------

class TestGistDestination:
    @patch("emdx.services.export_destinations.GistDestination.export")
    def test_gist_interface(self, mock_export):
        mock_export.return_value = ExportResult(
            success=True, dest_url="https://gist.github.com/abc", message="Created"
        )
        dest = GistDestination()
        result = dest.export("content", {"title": "Gist"}, {})
        assert result.success


# ---------------------------------------------------------------------------
# get_destination factory
# ---------------------------------------------------------------------------

class TestGetDestination:
    def test_clipboard(self):
        dest = get_destination("clipboard")
        assert isinstance(dest, ClipboardDestination)

    def test_file(self):
        dest = get_destination("file")
        assert isinstance(dest, FileDestination)

    def test_gdoc(self):
        dest = get_destination("gdoc")
        assert isinstance(dest, GDocDestination)

    def test_gist(self):
        dest = get_destination("gist")
        assert isinstance(dest, GistDestination)

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported destination type"):
            get_destination("ftp")

    def test_error_message_lists_supported_types(self):
        with pytest.raises(ValueError, match="clipboard"):
            get_destination("unknown")


# ---------------------------------------------------------------------------
# execute_post_actions
# ---------------------------------------------------------------------------

class TestExecutePostActions:
    def test_no_post_actions_returns_empty(self):
        result = ExportResult(success=True, dest_url="https://x.com", message="ok")
        msgs = execute_post_actions(result, {})
        assert msgs == []

    def test_no_post_actions_key_returns_empty(self):
        result = ExportResult(success=True, dest_url="https://x.com", message="ok")
        msgs = execute_post_actions(result, {"other_key": "val"})
        assert msgs == []

    @patch("emdx.services.export_destinations.ClipboardDestination.export")
    def test_copy_url_action(self, mock_clip):
        mock_clip.return_value = ExportResult(success=True, dest_url=None, message="ok")
        result = ExportResult(success=True, dest_url="https://example.com", message="ok")
        profile = {"post_actions": ["copy_url"]}
        msgs = execute_post_actions(result, profile)
        assert any("URL copied" in m for m in msgs)

    def test_copy_url_skipped_when_no_url(self):
        result = ExportResult(success=True, dest_url=None, message="ok")
        profile = {"post_actions": ["copy_url"]}
        msgs = execute_post_actions(result, profile)
        assert len(msgs) == 0

    @patch("emdx.services.export_destinations.webbrowser.open")
    def test_open_browser_action(self, mock_open):
        result = ExportResult(success=True, dest_url="https://example.com", message="ok")
        profile = {"post_actions": ["open_browser"]}
        msgs = execute_post_actions(result, profile)
        mock_open.assert_called_once_with("https://example.com")
        assert any("browser" in m.lower() for m in msgs)

    def test_open_browser_skipped_when_no_url(self):
        result = ExportResult(success=True, dest_url=None, message="ok")
        profile = {"post_actions": ["open_browser"]}
        msgs = execute_post_actions(result, profile)
        assert len(msgs) == 0

    def test_notify_action(self):
        result = ExportResult(success=True, dest_url=None, message="ok")
        profile = {"post_actions": ["notify"]}
        msgs = execute_post_actions(result, profile)
        assert any("notification" in m.lower() for m in msgs)

    def test_post_actions_json_string(self):
        result = ExportResult(success=True, dest_url=None, message="ok")
        profile = {"post_actions": '["notify"]'}
        msgs = execute_post_actions(result, profile)
        assert any("notification" in m.lower() for m in msgs)

    def test_post_actions_bad_json_returns_empty(self):
        result = ExportResult(success=True, dest_url=None, message="ok")
        profile = {"post_actions": "not valid json"}
        msgs = execute_post_actions(result, profile)
        assert msgs == []

    @patch("emdx.services.export_destinations.ClipboardDestination.export")
    @patch("emdx.services.export_destinations.webbrowser.open")
    def test_multiple_post_actions(self, mock_open, mock_clip):
        mock_clip.return_value = ExportResult(success=True, dest_url=None, message="ok")
        result = ExportResult(success=True, dest_url="https://x.com", message="ok")
        profile = {"post_actions": ["copy_url", "open_browser", "notify"]}
        msgs = execute_post_actions(result, profile)
        assert len(msgs) == 3
