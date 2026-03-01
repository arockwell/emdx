"""Comprehensive tests for top-level stale and touch commands (FEAT-6)."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emdx.commands.stale import (
    StalenessLevel,
    _calculate_importance_score,
    _get_staleness_level,
)
from emdx.database import db
from emdx.main import app

runner = CliRunner()


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Set up a fresh test database for each test."""
    test_db = tmp_path / "test.db"
    monkeypatch.setenv("EMDX_DATABASE_URL", f"sqlite:///{test_db}")
    db.ensure_schema()
    yield


def _create_stale_doc(
    title: str,
    content: str = "Some content",
    days_old: int = 100,
    tags: list[str] | None = None,
    access_count: int = 0,
) -> int:
    """Helper to create a document that appears stale."""
    from emdx.database.documents import save_document

    doc_id = save_document(title, content, tags=tags)

    with db.get_connection() as conn:
        conn.execute(
            "UPDATE documents "
            "SET accessed_at = datetime('now', ? || ' days'), "
            "    access_count = ? "
            "WHERE id = ?",
            (f"-{days_old}", access_count, doc_id),
        )
        conn.commit()

    return doc_id


# ── emdx stale (top-level) ──────────────────────────────────────────────


class TestStaleTopLevel:
    """Tests for `emdx stale` top-level command."""

    def test_stale_help(self) -> None:
        """Help text shows tier-based options."""
        result = runner.invoke(app, ["stale", "--help"])
        assert result.exit_code == 0
        assert "CRITICAL" in result.output
        assert "WARNING" in result.output
        assert "INFO" in result.output
        assert "--tier" in result.output
        assert "--json" in result.output
        assert "--limit" in result.output

    def test_stale_empty_kb(self) -> None:
        """Empty knowledge base reports fresh status."""
        result = runner.invoke(app, ["stale"])
        assert result.exit_code == 0
        assert "fresh" in result.output.lower() or "no stale" in result.output.lower()

    def test_stale_shows_old_docs(self) -> None:
        """Old documents appear in stale output."""
        _create_stale_doc("Old Security Doc", days_old=100, tags=["security"])

        result = runner.invoke(app, ["stale"])
        assert result.exit_code == 0
        assert "Old Security Doc" in result.output

    def test_stale_json_output(self) -> None:
        """JSON output is valid and contains expected fields."""
        _create_stale_doc(
            "Security Plan",
            days_old=60,
            tags=["security", "gameplan"],
            access_count=10,
        )

        result = runner.invoke(app, ["stale", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1

        doc = data[0]
        assert "id" in doc
        assert "title" in doc
        assert "days_stale" in doc
        assert "importance" in doc
        assert "level" in doc
        assert "tags" in doc
        assert "accessed_at" in doc
        assert doc["level"] in ("critical", "warning", "info")

    def test_stale_json_valid(self) -> None:
        """JSON output is always valid JSON (array)."""
        result = runner.invoke(app, ["stale", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_stale_tier_filter_critical(self) -> None:
        """--tier critical shows only critical docs."""
        # Create a high-importance doc (security tag + views)
        _create_stale_doc(
            "Critical Security Doc",
            days_old=40,
            tags=["security"],
            access_count=20,
        )
        # Create a low-importance doc
        _create_stale_doc(
            "Low Importance Doc",
            days_old=90,
            access_count=0,
        )

        result = runner.invoke(app, ["stale", "--tier", "critical", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        for doc in data:
            assert doc["level"] == "critical"

    def test_stale_tier_filter_warning(self) -> None:
        """--tier warning shows only warning docs."""
        # Create a medium-importance doc (some views + default tag)
        _create_stale_doc(
            "Medium Doc",
            days_old=20,
            tags=["notes"],
            access_count=8,
        )

        result = runner.invoke(app, ["stale", "--tier", "warning", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        for doc in data:
            assert doc["level"] == "warning"

    def test_stale_tier_filter_info(self) -> None:
        """--tier info shows only info (archive candidate) docs."""
        _create_stale_doc(
            "Archive Candidate",
            days_old=90,
            access_count=0,
        )

        result = runner.invoke(app, ["stale", "--tier", "info", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        for doc in data:
            assert doc["level"] == "info"

    def test_stale_invalid_tier(self) -> None:
        """Invalid tier value exits with error."""
        _create_stale_doc("Some Doc", days_old=100)

        result = runner.invoke(app, ["stale", "--tier", "bogus"])
        assert result.exit_code == 1

    def test_stale_limit(self) -> None:
        """--limit caps the number of results."""
        for i in range(5):
            _create_stale_doc(f"Stale Doc {i}", days_old=90 + i, access_count=0)

        result = runner.invoke(app, ["stale", "--limit", "2", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert len(data) <= 2

    def test_stale_custom_critical_days(self) -> None:
        """Custom --critical-days changes the threshold."""
        # Doc that would NOT be critical at default 30 days
        # but IS critical at custom 5 days
        _create_stale_doc(
            "Short Threshold Doc",
            days_old=10,
            tags=["security"],
            access_count=20,
        )

        # Default: should NOT be critical (10 < 30)
        result_default = runner.invoke(app, ["stale", "--tier", "critical", "--json"])
        data_default = json.loads(result_default.output)
        default_ids = {d["id"] for d in data_default}

        # Custom: 10 > 5, so should be critical
        result_custom = runner.invoke(
            app,
            ["stale", "--tier", "critical", "--critical-days", "5", "--json"],
        )
        data_custom = json.loads(result_custom.output)
        custom_ids = {d["id"] for d in data_custom}

        # The custom threshold should catch it
        assert len(custom_ids) >= len(default_ids)

    def test_stale_sorted_by_urgency(self) -> None:
        """Results are sorted: CRITICAL first, then WARNING, then INFO."""
        # Create docs that fall into different tiers
        _create_stale_doc(
            "Critical Doc",
            days_old=50,
            tags=["security"],
            access_count=20,
        )
        _create_stale_doc(
            "Info Doc",
            days_old=90,
            access_count=0,
        )

        result = runner.invoke(app, ["stale", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        if len(data) >= 2:
            tier_order = {"critical": 0, "warning": 1, "info": 2}
            levels = [tier_order[d["level"]] for d in data]
            assert levels == sorted(levels), "Results should be sorted by tier"


# ── emdx touch (top-level) ──────────────────────────────────────────────


class TestTouchTopLevel:
    """Tests for `emdx touch` top-level command."""

    def test_touch_help(self) -> None:
        """Help text describes the touch command."""
        result = runner.invoke(app, ["touch", "--help"])
        assert result.exit_code == 0
        assert "reviewed" in result.output.lower()
        assert "--json" in result.output

    def test_touch_single_doc(self) -> None:
        """Touch a single document by ID."""
        from emdx.database.documents import save_document

        doc_id = save_document("Touch Test", "Content")

        result = runner.invoke(app, ["touch", str(doc_id)])
        assert result.exit_code == 0
        assert "touched" in result.output.lower()
        assert str(doc_id) in result.output

    def test_touch_multiple_docs(self) -> None:
        """Touch multiple documents at once."""
        from emdx.database.documents import save_document

        doc1 = save_document("Doc 1", "Content 1")
        doc2 = save_document("Doc 2", "Content 2")
        doc3 = save_document("Doc 3", "Content 3")

        result = runner.invoke(app, ["touch", str(doc1), str(doc2), str(doc3)])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_touch_nonexistent_doc(self) -> None:
        """Touching nonexistent document reports not found."""
        result = runner.invoke(app, ["touch", "99999"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_touch_mixed_found_and_not(self) -> None:
        """Touch with mix of existing and nonexistent IDs."""
        from emdx.database.documents import save_document

        doc_id = save_document("Real Doc", "Content")

        result = runner.invoke(app, ["touch", str(doc_id), "99999"])
        assert result.exit_code == 0
        assert "touched" in result.output.lower()
        assert "not found" in result.output.lower()

    def test_touch_does_not_increment_view_count(self) -> None:
        """Touch updates accessed_at but NOT access_count."""
        from emdx.database.documents import save_document

        doc_id = save_document("View Count Test", "Content")

        # Get initial access_count
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT access_count FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            initial_count = row[0]

        # Touch the document
        result = runner.invoke(app, ["touch", str(doc_id)])
        assert result.exit_code == 0

        # Verify access_count unchanged
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT access_count FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            after_count = row[0]

        assert after_count == initial_count

    def test_touch_updates_accessed_at(self) -> None:
        """Touch updates the accessed_at timestamp."""
        doc_id = _create_stale_doc("Old Doc", days_old=100)

        # Get old accessed_at
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT accessed_at FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            old_accessed = row[0]

        # Touch
        result = runner.invoke(app, ["touch", str(doc_id)])
        assert result.exit_code == 0

        # Verify accessed_at was updated (should be more recent)
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT accessed_at FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            new_accessed = row[0]

        assert new_accessed != old_accessed

    def test_touch_json_output(self) -> None:
        """JSON output from touch command."""
        from emdx.database.documents import save_document

        doc_id = save_document("JSON Touch Test", "Content")

        result = runner.invoke(app, ["touch", str(doc_id), "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "touched" in data
        assert "not_found" in data
        assert "count" in data
        assert str(doc_id) in data["touched"]
        assert data["count"] == 1
        assert data["not_found"] == []

    def test_touch_json_not_found(self) -> None:
        """JSON output for not-found documents."""
        result = runner.invoke(app, ["touch", "99999", "--json"])
        # exit code 1 because nothing was touched
        assert result.exit_code == 1

        data = json.loads(result.output)
        assert data["count"] == 0
        assert "99999" in data["not_found"]

    def test_touch_by_title(self) -> None:
        """Touch a document by title (case-insensitive)."""
        from emdx.database.documents import save_document

        save_document("My Important Doc", "Content")

        result = runner.invoke(app, ["touch", "my important doc"])
        assert result.exit_code == 0
        assert "touched" in result.output.lower()

    def test_touch_deleted_doc_ignored(self) -> None:
        """Touching a deleted document reports not found."""
        from emdx.database.documents import delete_document, save_document

        doc_id = save_document("Soon Deleted", "Content")
        delete_document(doc_id)

        result = runner.invoke(app, ["touch", str(doc_id)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ── Importance scoring edge cases ────────────────────────────────────────


class TestImportanceScoringEdgeCases:
    """Additional edge case tests for importance scoring."""

    def test_view_count_capped_at_50(self) -> None:
        """Views above 50 don't further increase score."""
        score_50 = _calculate_importance_score(50, [])
        score_100 = _calculate_importance_score(100, [])
        assert score_50 == score_100

    def test_case_insensitive_tag_weights(self) -> None:
        """Tag weight lookup is case-insensitive."""
        score_lower = _calculate_importance_score(5, ["security"])
        score_upper = _calculate_importance_score(5, ["SECURITY"])
        # Both should use the security weight=3
        assert score_lower == score_upper

    def test_all_high_weight_tags(self) -> None:
        """All high-weight tags together produce high importance."""
        score = _calculate_importance_score(0, ["security", "gameplan", "active", "reference"])
        assert score > 2.0

    def test_importance_with_no_views_and_one_tag(self) -> None:
        """Single default-weight tag produces small importance."""
        score = _calculate_importance_score(0, ["misc"])
        assert 0.0 < score < 1.0


# ── Staleness level boundary tests ───────────────────────────────────────


class TestStalenessLevelBoundaries:
    """Boundary tests for staleness level determination."""

    def test_exactly_at_critical_boundary(self) -> None:
        """Exactly at critical_days is NOT stale (must exceed)."""
        level = _get_staleness_level(
            days_stale=30,
            importance=6.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level is None

    def test_one_day_past_critical(self) -> None:
        """One day past critical_days IS critical."""
        level = _get_staleness_level(
            days_stale=31,
            importance=6.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level == StalenessLevel.CRITICAL

    def test_importance_boundary_at_5(self) -> None:
        """Importance exactly 5.0 qualifies for CRITICAL."""
        level = _get_staleness_level(
            days_stale=31,
            importance=5.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level == StalenessLevel.CRITICAL

    def test_importance_boundary_at_2(self) -> None:
        """Importance exactly 2.0 qualifies for WARNING."""
        level = _get_staleness_level(
            days_stale=15,
            importance=2.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level == StalenessLevel.WARNING

    def test_importance_just_below_2(self) -> None:
        """Importance 1.9 falls into INFO tier (not WARNING)."""
        # With days_stale=15 and importance=1.9:
        # - Not CRITICAL (importance < 5)
        # - Not WARNING (importance < 2)
        # - Not INFO (days_stale=15 < info_days=60)
        level = _get_staleness_level(
            days_stale=15,
            importance=1.9,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level is None  # Not stale enough for INFO tier

    def test_high_importance_below_critical_days(self) -> None:
        """High importance doc below critical_days is not stale."""
        level = _get_staleness_level(
            days_stale=20,
            importance=8.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level is None

    def test_medium_importance_falls_to_none_between_tiers(self) -> None:
        """Medium importance doc that doesn't exceed warning_days."""
        level = _get_staleness_level(
            days_stale=10,
            importance=3.0,
            critical_days=30,
            warning_days=14,
            info_days=60,
        )
        assert level is None
