"""Regression test for Issue #1120.

`emdx wiki topics` should surface a clear, actionable error when the optional
python-igraph/leidenalg clustering dependencies are not installed, instead of
letting a raw ModuleNotFoundError/ImportError traceback escape.
"""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from emdx.main import app

runner = CliRunner()


def test_wiki_topics_reports_clean_error_when_clustering_deps_missing() -> None:
    """discover_topics() raising ImportError should not crash the CLI with a traceback."""
    with patch(
        "emdx.services.wiki_clustering_service.discover_topics",
        side_effect=ImportError(
            "Wiki clustering requires python-igraph and leidenalg, which are not installed. "
            "Install with: pip install python-igraph leidenalg "
            "(dev checkout: poetry install --with wiki)"
        ),
    ):
        result = runner.invoke(app, ["wiki", "topics"])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "python-igraph" in result.output
    assert "leidenalg" in result.output
    assert "Traceback" not in result.output
