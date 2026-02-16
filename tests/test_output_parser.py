"""Tests for output_parser doc ID extraction."""

import tempfile
from pathlib import Path

from emdx.utils.output_parser import extract_output_doc_id


def _write_log(content: str) -> Path:
    """Write content to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False,
    )
    tmp.write(content)
    tmp.flush()
    return Path(tmp.name)


class TestExtractOutputDocId:
    """Test extract_output_doc_id against real-world agent output patterns."""

    def test_cli_saved_as(self):
        log = _write_log("✅ Saved as #1234: My Document\n")
        assert extract_output_doc_id(log) == 1234

    def test_saved_as_plain(self):
        log = _write_log("Saved as #42\n")
        assert extract_output_doc_id(log) == 42

    def test_created_document(self):
        log = _write_log("Created document #789\n")
        assert extract_output_doc_id(log) == 789

    def test_saved_as_document(self):
        log = _write_log("saved as document #555\n")
        assert extract_output_doc_id(log) == 555

    def test_document_id_colon(self):
        log = _write_log("Document ID: 999\n")
        assert extract_output_doc_id(log) == 999

    def test_document_id_hash(self):
        log = _write_log("Document ID: #321\n")
        assert extract_output_doc_id(log) == 321

    def test_doc_id_field(self):
        log = _write_log("doc_id: 100\n")
        assert extract_output_doc_id(log) == 100

    # --- Markdown bold variants (real failures from production) ---

    def test_markdown_bold_saved_as_document(self):
        """Regression: 'Saved as **document #6435**.' was not matched."""
        log = _write_log("Saved as **document #6435**.\n")
        assert extract_output_doc_id(log) == 6435

    def test_markdown_bold_document_saved_as(self):
        """Regression: 'Document saved as **#6434**.' was not matched."""
        log = _write_log("Document saved as **#6434**.\n")
        assert extract_output_doc_id(log) == 6434

    def test_markdown_bold_document_saved_colon(self):
        """Regression: '**Document saved:** #6436' was not matched."""
        log = _write_log("**Document saved:** #6436 with tags\n")
        assert extract_output_doc_id(log) == 6436

    def test_markdown_bold_document_id(self):
        log = _write_log("**Document ID:** 5714\n")
        assert extract_output_doc_id(log) == 5714

    def test_backtick_doc_id(self):
        log = _write_log("doc ID `5704`\n")
        assert extract_output_doc_id(log) == 5704

    def test_saved_to_emdx(self):
        log = _write_log("Saved to EMDX as doc ID 5704\n")
        assert extract_output_doc_id(log) == 5704

    # --- Edge cases ---

    def test_returns_last_match(self):
        """When multiple doc IDs appear, return the last one."""
        log = _write_log(
            "Created document #100\n"
            "...some output...\n"
            "Saved as #200\n"
        )
        assert extract_output_doc_id(log) == 200

    def test_no_match_returns_none(self):
        log = _write_log("No documents were created.\n")
        assert extract_output_doc_id(log) is None

    def test_empty_file_returns_none(self):
        log = _write_log("")
        assert extract_output_doc_id(log) is None

    def test_nonexistent_file_returns_none(self):
        assert extract_output_doc_id(Path("/tmp/nonexistent.log")) is None

    def test_ansi_codes_stripped(self):
        log = _write_log("\x1b[32mSaved as #777\x1b[0m\n")
        assert extract_output_doc_id(log) == 777

    def test_rich_codes_stripped(self):
        log = _write_log("[1;32mSaved as #888[0m\n")
        assert extract_output_doc_id(log) == 888
