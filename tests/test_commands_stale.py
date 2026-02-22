"""Tests for the stale command module (knowledge decay)."""

from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emdx.commands.stale import (
    StalenessLevel,
    _calculate_importance_score,
    _get_staleness_level,
    get_top_stale_for_priming,
)
from emdx.database import db
from emdx.main import app

runner = CliRunner()


class TestImportanceScoring:
    """Tests for importance score calculation."""

    def test_zero_views_no_tags(self) -> None:
        """Document with no views and no tags has minimal importance."""
        score = _calculate_importance_score(0, [])
        assert score == 0.0

    def test_view_count_contributes(self) -> None:
        """View count increases importance."""
        score_low = _calculate_importance_score(5, [])
        score_high = _calculate_importance_score(20, [])
        assert score_high > score_low

    def test_high_weight_tag_increases_importance(self) -> None:
        """Security and gameplan tags increase importance significantly."""
        score_no_tags = _calculate_importance_score(5, [])
        score_security = _calculate_importance_score(5, ["security"])
        score_gameplan = _calculate_importance_score(5, ["gameplan"])

        assert score_security > score_no_tags
        assert score_gameplan > score_no_tags
        # Security has weight 3, gameplan has weight 2
        assert score_security > score_gameplan

    def test_unknown_tags_get_default_weight(self) -> None:
        """Tags not in TAG_WEIGHTS get the default weight."""
        score_known = _calculate_importance_score(5, ["security"])
        score_unknown = _calculate_importance_score(5, ["random-tag"])
        # Security has weight 3, random-tag has default weight 1
        assert score_known > score_unknown

    def test_score_normalized_to_ten(self) -> None:
        """Score is normalized to 0-10 range."""
        # Even with many views and tags, should cap at 10
        score = _calculate_importance_score(100, ["security", "gameplan", "active", "reference"])
        assert score <= 10.0

    def test_multiple_tags_combine(self) -> None:
        """Multiple tags combine their weights."""
        score_one = _calculate_importance_score(5, ["gameplan"])
        score_two = _calculate_importance_score(5, ["gameplan", "active"])
        assert score_two > score_one


class TestStalenessLevel:
    """Tests for staleness level determination."""

    def test_high_importance_critical(self) -> None:
        """High importance docs are CRITICAL after threshold."""
        level = _get_staleness_level(
            days_stale=35, importance=6.0, critical_days=30, warning_days=14, info_days=60
        )
        assert level == StalenessLevel.CRITICAL

    def test_medium_importance_warning(self) -> None:
        """Medium importance docs are WARNING after threshold."""
        level = _get_staleness_level(
            days_stale=20, importance=3.0, critical_days=30, warning_days=14, info_days=60
        )
        assert level == StalenessLevel.WARNING

    def test_low_importance_info(self) -> None:
        """Low importance docs are INFO after threshold (archive candidates)."""
        level = _get_staleness_level(
            days_stale=70, importance=1.0, critical_days=30, warning_days=14, info_days=60
        )
        assert level == StalenessLevel.INFO

    def test_not_stale_returns_none(self) -> None:
        """Recent docs return None (not stale)."""
        level = _get_staleness_level(
            days_stale=5, importance=6.0, critical_days=30, warning_days=14, info_days=60
        )
        assert level is None

    def test_custom_thresholds(self) -> None:
        """Custom day thresholds work."""
        # With shorter threshold, should become CRITICAL
        level = _get_staleness_level(
            days_stale=10, importance=6.0, critical_days=7, warning_days=3, info_days=30
        )
        assert level == StalenessLevel.CRITICAL


class TestStaleCommand:
    """Integration tests for the stale CLI command."""

    @pytest.fixture(autouse=True)
    def setup_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Generator[None, None, None]:
        """Set up a fresh test database."""
        test_db = tmp_path / "test.db"
        monkeypatch.setenv("EMDX_DATABASE_URL", f"sqlite:///{test_db}")
        db.ensure_schema()
        yield

    def test_stale_list_help(self) -> None:
        """Stale list command shows help."""
        result = runner.invoke(app, ["maintain", "stale", "list", "--help"])
        assert result.exit_code == 0
        assert "CRITICAL" in result.output
        assert "WARNING" in result.output
        assert "INFO" in result.output

    def test_stale_list_empty(self) -> None:
        """No stale documents shows success message."""
        result = runner.invoke(app, ["maintain", "stale", "list"])
        assert result.exit_code == 0
        assert "fresh" in result.output.lower() or "no stale" in result.output.lower()

    def test_stale_list_json(self) -> None:
        """JSON output works with stale documents."""
        # Create a document with old access date
        from emdx.database.documents import save_document

        doc_id = save_document("Test Stale Doc", "Content", tags=["gameplan"])

        # Manually set old accessed_at to make it stale
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET accessed_at = datetime('now', '-100 days') WHERE id = ?",
                (doc_id,),
            )
            conn.commit()

        result = runner.invoke(app, ["maintain", "stale", "list", "--json"])
        assert result.exit_code == 0
        # Should be valid JSON
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        # Should contain our stale doc
        assert len(data) >= 1


class TestTouchCommand:
    """Integration tests for the touch CLI command."""

    @pytest.fixture(autouse=True)
    def setup_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Generator[None, None, None]:
        """Set up a fresh test database."""
        test_db = tmp_path / "test.db"
        monkeypatch.setenv("EMDX_DATABASE_URL", f"sqlite:///{test_db}")
        db.ensure_schema()
        yield

    def test_touch_help(self) -> None:
        """Touch command shows help."""
        result = runner.invoke(app, ["maintain", "stale", "touch", "--help"])
        assert result.exit_code == 0
        assert "staleness" in result.output.lower()

    def test_touch_nonexistent(self) -> None:
        """Touching nonexistent document reports not found."""
        result = runner.invoke(app, ["maintain", "stale", "touch", "99999"])
        assert "not found" in result.output.lower() or result.exit_code == 1

    def test_touch_existing_doc(self) -> None:
        """Touching existing document succeeds."""
        # Create a document first
        from emdx.database.documents import save_document

        doc_id = save_document("Test Doc", "Test content")

        result = runner.invoke(app, ["maintain", "stale", "touch", str(doc_id)])
        assert result.exit_code == 0
        assert "touched" in result.output.lower()

    def test_touch_multiple_docs(self) -> None:
        """Touching multiple documents at once works."""
        from emdx.database.documents import save_document

        doc1 = save_document("Test Doc 1", "Content 1")
        doc2 = save_document("Test Doc 2", "Content 2")

        result = runner.invoke(app, ["maintain", "stale", "touch", str(doc1), str(doc2)])
        assert result.exit_code == 0
        assert "2" in result.output  # Should mention 2 documents


class TestPrimeIntegration:
    """Tests for stale docs integration with prime command."""

    def test_get_top_stale_for_priming(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_top_stale_for_priming returns stale docs."""
        test_db = tmp_path / "test.db"
        monkeypatch.setenv("EMDX_DATABASE_URL", f"sqlite:///{test_db}")
        db.ensure_schema()

        # Without any docs, should return empty list
        result = get_top_stale_for_priming(limit=5)
        assert isinstance(result, list)
        assert len(result) == 0  # No docs = no stale docs
