"""Tests for the maintain compact subcommand."""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from emdx.main import app
from emdx.models.documents import delete_document, save_document

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestMaintainCompact:
    def test_compact_runs_and_reports_sizes(self):
        # Create some churn so VACUUM has something to reclaim
        doc_ids = [save_document(f"Compact test {i}", "body " * 500, None) for i in range(5)]
        for doc_id in doc_ids:
            delete_document(str(doc_id))

        result = runner.invoke(app, ["maintain", "compact"])
        assert result.exit_code == 0
        assert "Compacted" in _out(result)
        assert "reclaimed" in _out(result)

    def test_compact_json_output(self):
        result = runner.invoke(app, ["maintain", "compact", "--json"])
        assert result.exit_code == 0
        data = json.loads(_out(result))
        assert data["success"] is True
        assert data["size_before_bytes"] >= data["size_after_bytes"]
        assert data["reclaimed_bytes"] == data["size_before_bytes"] - data["size_after_bytes"]
        assert data["duration_seconds"] >= 0
