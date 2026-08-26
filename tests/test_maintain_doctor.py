"""Tests for `emdx maintain doctor` — path-as-content damage scan (#1086)."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emdx.commands.maintain import app as maintain_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_documents(isolate_test_database: Path) -> Generator[None, None, None]:
    from emdx.database.connection import db_connection

    def _clean() -> None:
        with db_connection.get_connection() as conn:
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM documents")
            conn.commit()

    _clean()
    yield
    _clean()


def _save(title: str, content: str) -> int:
    from emdx.database.documents import save_document

    return save_document(title, content)


class TestMaintainDoctor:
    def test_no_damage_found(self) -> None:
        _save("Healthy doc", "# Real content\n\nWith multiple lines.")
        _save("Short but fine", "just a note")

        result = runner.invoke(maintain_app, ["doctor"])
        assert result.exit_code == 0
        assert "No damaged documents found" in result.output

    def test_detects_path_body_with_missing_file(self) -> None:
        doc_id = _save("Lost doc", "/tmp/definitely-gone-12345.md")

        result = runner.invoke(maintain_app, ["doctor"])
        assert result.exit_code == 0
        assert f"#{doc_id}" in result.output
        assert "/tmp/definitely-gone-12345.md" in result.output
        assert "file missing" in result.output

    def test_detects_recoverable_path_body(self, tmp_path: Path) -> None:
        real_file = tmp_path / "still-here.md"
        real_file.write_text("the original content")
        doc_id = _save("Recoverable doc", str(real_file))

        result = runner.invoke(maintain_app, ["doctor"])
        assert result.exit_code == 0
        assert "file exists" in result.output
        assert f"emdx edit {doc_id} --file {real_file}" in result.output

    def test_home_relative_path_detected(self) -> None:
        _save("Tilde doc", "~/notes/gone.md")

        result = runner.invoke(maintain_app, ["doctor"])
        assert "~/notes/gone.md" in result.output

    def test_ignores_multiline_and_spaced_content(self) -> None:
        _save("Multiline", "/tmp/path.md\nplus real content")
        _save("Sentence", "/tmp is a directory I like")
        _save("Relative path", "some_file.md")

        result = runner.invoke(maintain_app, ["doctor"])
        assert "No damaged documents found" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        real_file = tmp_path / "here.md"
        real_file.write_text("content")
        recoverable_id = _save("Recoverable", str(real_file))
        lost_id = _save("Lost", "/tmp/gone-forever-98765.md")
        _save("Healthy", "normal content here")

        result = runner.invoke(maintain_app, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 2
        by_id = {d["id"]: d for d in data["damaged"]}
        assert by_id[recoverable_id]["file_exists"] is True
        assert by_id[lost_id]["file_exists"] is False
