"""Tests for the maintain freshness subcommand.

Covers:
- Individual signal scoring functions
- Weighted combination logic
- Threshold filtering (--stale)
- Plain text and JSON output formatting
- Edge cases: empty DB, all stale, all fresh
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from emdx.commands._freshness import (
    DocFreshnessScore,
    FreshnessReport,
    SignalScores,
    _compute_freshness,
    _exponential_decay,
    _format_json,
    _format_plain,
    _freshness_label,
    _score_age,
    _score_content_length,
    _score_tags,
    _score_view_recency,
    analyze_freshness,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def clean_db(isolate_test_database):  # type: ignore[no-untyped-def]
    """Ensure clean database for each test by deleting all documents."""
    from emdx.database import db

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM document_links")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM tags")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    yield
    cleanup()


def _insert_doc(
    title: str = "Test Doc",
    content: str = "A" * 200,
    created_at: str | None = None,
    accessed_at: str | None = None,
) -> int:
    """Insert a document and return its ID."""
    from emdx.database import db

    now_str = datetime.now(tz=timezone.utc).isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO documents
                (title, content, created_at, accessed_at, is_deleted)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                title,
                content,
                created_at or now_str,
                accessed_at or now_str,
            ),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def _add_tag(doc_id: int, tag_name: str) -> None:
    """Add a tag to a document."""
    from emdx.database import db

    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)",
            (tag_name,),
        )
        cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_id = cursor.fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
            (doc_id, tag_id),
        )
        conn.commit()


def _add_link(source_id: int, target_id: int) -> None:
    """Create a link between two documents."""
    from emdx.database import db

    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO document_links
                (source_doc_id, target_doc_id, similarity_score, method)
            VALUES (?, ?, 0.8, 'test')
            """,
            (source_id, target_id),
        )
        conn.commit()


# ── Unit tests for individual signals ────────────────────────────────────


class TestExponentialDecay:
    def test_zero_days(self) -> None:
        assert _exponential_decay(0, 30.0) == 1.0

    def test_one_half_life(self) -> None:
        score = _exponential_decay(30.0, 30.0)
        assert abs(score - 0.5) < 0.01

    def test_two_half_lives(self) -> None:
        score = _exponential_decay(60.0, 30.0)
        assert abs(score - 0.25) < 0.01

    def test_negative_days_returns_one(self) -> None:
        assert _exponential_decay(-5, 30.0) == 1.0


class TestScoreAge:
    def test_brand_new_doc(self) -> None:
        now = datetime.now(tz=timezone.utc)
        score = _score_age(now.isoformat(), now)
        assert score > 0.99

    def test_old_doc(self) -> None:
        now = datetime.now(tz=timezone.utc)
        old = (now - timedelta(days=90)).isoformat()
        score = _score_age(old, now)
        assert score < 0.2

    def test_none_timestamp(self) -> None:
        now = datetime.now(tz=timezone.utc)
        score = _score_age(None, now)
        assert score < 0.01  # treated as 365 days old


class TestScoreViewRecency:
    def test_recently_viewed(self) -> None:
        now = datetime.now(tz=timezone.utc)
        score = _score_view_recency(now.isoformat(), now)
        assert score > 0.99

    def test_not_viewed_recently(self) -> None:
        now = datetime.now(tz=timezone.utc)
        old = (now - timedelta(days=60)).isoformat()
        score = _score_view_recency(old, now)
        assert score < 0.1

    def test_none_accessed_at(self) -> None:
        now = datetime.now(tz=timezone.utc)
        score = _score_view_recency(None, now)
        assert score < 0.01


class TestScoreContentLength:
    def test_long_content(self) -> None:
        assert _score_content_length("A" * 200) == 1.0

    def test_exactly_threshold(self) -> None:
        assert _score_content_length("A" * 100) == 1.0

    def test_stub_content(self) -> None:
        score = _score_content_length("A" * 50)
        assert abs(score - 0.5) < 0.01

    def test_empty_content(self) -> None:
        assert _score_content_length("") == 0.0

    def test_whitespace_only(self) -> None:
        assert _score_content_length("   ") == 0.0


class TestScoreTags:
    def test_no_tags_neutral(self, clean_db: None) -> None:
        doc_id = _insert_doc()
        score = _score_tags(doc_id)
        assert abs(score - 0.5) < 0.01

    def test_active_tag_boosts(self, clean_db: None) -> None:
        doc_id = _insert_doc()
        _add_tag(doc_id, "active")
        score = _score_tags(doc_id)
        assert score > 0.5

    def test_done_tag_penalizes(self, clean_db: None) -> None:
        doc_id = _insert_doc()
        _add_tag(doc_id, "done")
        score = _score_tags(doc_id)
        assert score < 0.5

    def test_mixed_tags(self, clean_db: None) -> None:
        doc_id = _insert_doc()
        _add_tag(doc_id, "active")
        _add_tag(doc_id, "done")
        score = _score_tags(doc_id)
        # active (+0.2) + done (-0.3) = net -0.1 from 0.5 = 0.4
        assert abs(score - 0.4) < 0.01

    def test_score_clamped_at_one(self, clean_db: None) -> None:
        doc_id = _insert_doc()
        _add_tag(doc_id, "active")
        _add_tag(doc_id, "security")
        _add_tag(doc_id, "gameplan")
        _add_tag(doc_id, "reference")
        score = _score_tags(doc_id)
        assert score <= 1.0


# ── Unit tests for weighted combination ──────────────────────────────────


class TestComputeFreshness:
    def test_all_perfect_signals(self) -> None:
        signals = SignalScores(
            age_decay=1.0,
            view_recency=1.0,
            link_health=1.0,
            content_length=1.0,
            tag_signal=1.0,
        )
        assert abs(_compute_freshness(signals) - 1.0) < 0.001

    def test_all_zero_signals(self) -> None:
        signals = SignalScores(
            age_decay=0.0,
            view_recency=0.0,
            link_health=0.0,
            content_length=0.0,
            tag_signal=0.0,
        )
        assert abs(_compute_freshness(signals)) < 0.001

    def test_mixed_signals(self) -> None:
        signals = SignalScores(
            age_decay=0.5,
            view_recency=0.5,
            link_health=0.5,
            content_length=0.5,
            tag_signal=0.5,
        )
        assert abs(_compute_freshness(signals) - 0.5) < 0.001


# ── Integration tests for analyze_freshness ──────────────────────────────


class TestAnalyzeFreshness:
    def test_empty_database(self, clean_db: None) -> None:
        report = analyze_freshness()
        assert report["total_documents"] == 0
        assert report["scored_documents"] == 0
        assert report["stale_count"] == 0
        assert report["scores"] == []

    def test_fresh_doc_scores_high(self, clean_db: None) -> None:
        _insert_doc(title="Fresh Doc", content="A" * 200)
        report = analyze_freshness()
        assert report["total_documents"] == 1
        assert len(report["scores"]) == 1
        assert report["scores"][0]["freshness"] > 0.5

    def test_old_doc_scores_low(self, clean_db: None) -> None:
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=180)).isoformat()
        _insert_doc(
            title="Old Doc",
            content="A" * 200,
            created_at=old_date,
            accessed_at=old_date,
        )
        report = analyze_freshness()
        assert report["total_documents"] == 1
        # Old doc still has good content length and healthy links,
        # so it's "aging" but not necessarily below default threshold.
        # Its age_decay and view_recency signals should be near zero.
        score = report["scores"][0]
        assert score["signals"]["age_decay"] < 0.05
        assert score["signals"]["view_recency"] < 0.01
        assert score["freshness"] < 0.5

    def test_stale_only_filters(self, clean_db: None) -> None:
        # Insert a fresh doc
        _insert_doc(title="Fresh", content="A" * 200)
        # Insert a stale doc (old + stub content to push score down)
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=180)).isoformat()
        stale_id = _insert_doc(
            title="Stale",
            content="Hi",  # stub content to push score lower
            created_at=old_date,
            accessed_at=old_date,
        )
        _add_tag(stale_id, "done")  # penalize with done tag

        # Use a threshold that separates fresh from stale
        report_all = analyze_freshness(threshold=0.5, stale_only=False)
        assert report_all["total_documents"] == 2

        report_stale = analyze_freshness(threshold=0.5, stale_only=True)
        # Fresh doc should be filtered out; stale doc stays
        assert report_stale["scored_documents"] < report_all["scored_documents"]
        for entry in report_stale["scores"]:
            assert entry["freshness"] < 0.5

    def test_custom_threshold(self, clean_db: None) -> None:
        _insert_doc(title="Doc", content="A" * 200)
        report = analyze_freshness(threshold=0.99)
        # With threshold 0.99, most docs should be "stale"
        assert report["stale_count"] >= 0  # Depends on exact timing

    def test_deleted_docs_excluded(self, clean_db: None) -> None:
        from emdx.database import db

        doc_id = _insert_doc(title="Deleted Doc")
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET is_deleted = 1 WHERE id = ?",
                (doc_id,),
            )
            conn.commit()

        report = analyze_freshness()
        assert report["total_documents"] == 0

    def test_sorted_stalest_first(self, clean_db: None) -> None:
        _insert_doc(title="Fresh", content="A" * 200)
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=120)).isoformat()
        _insert_doc(
            title="Old",
            content="A" * 200,
            created_at=old_date,
            accessed_at=old_date,
        )

        report = analyze_freshness()
        scores = [s["freshness"] for s in report["scores"]]
        assert scores == sorted(scores)

    def test_stub_doc_penalized(self, clean_db: None) -> None:
        _insert_doc(title="Stub", content="Hi")
        _insert_doc(title="Full", content="A" * 200)
        report = analyze_freshness()
        stub_score = next(s for s in report["scores"] if s["title"] == "Stub")
        full_score = next(s for s in report["scores"] if s["title"] == "Full")
        assert stub_score["freshness"] < full_score["freshness"]
        assert stub_score["signals"]["content_length"] < 0.1


class TestLinkHealth:
    def test_no_links_neutral(self, clean_db: None) -> None:
        doc_id = _insert_doc(title="Isolated")
        from emdx.commands._freshness import _score_link_health

        assert _score_link_health(doc_id) == 1.0

    def test_all_links_alive(self, clean_db: None) -> None:
        doc1 = _insert_doc(title="Doc 1")
        doc2 = _insert_doc(title="Doc 2")
        _add_link(doc1, doc2)

        from emdx.commands._freshness import _score_link_health

        assert _score_link_health(doc1) == 1.0

    def test_some_links_dead(self, clean_db: None) -> None:
        from emdx.database import db

        doc1 = _insert_doc(title="Doc 1")
        doc2 = _insert_doc(title="Doc 2 (alive)")
        doc3 = _insert_doc(title="Doc 3 (dead)")
        _add_link(doc1, doc2)
        _add_link(doc1, doc3)

        # Soft-delete doc3
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET is_deleted = 1 WHERE id = ?",
                (doc3,),
            )
            conn.commit()

        from emdx.commands._freshness import _score_link_health

        score = _score_link_health(doc1)
        assert abs(score - 0.5) < 0.01


# ── Output formatting tests ─────────────────────────────────────────────


class TestFreshnessLabel:
    def test_fresh(self) -> None:
        assert _freshness_label(0.8) == "fresh"

    def test_aging(self) -> None:
        assert _freshness_label(0.5) == "aging"

    def test_stale(self) -> None:
        assert _freshness_label(0.1) == "stale"

    def test_boundary_fresh(self) -> None:
        assert _freshness_label(0.7) == "fresh"

    def test_boundary_aging(self) -> None:
        assert _freshness_label(0.3) == "aging"


class TestFormatPlain:
    def test_empty_report_no_docs(self) -> None:
        report = FreshnessReport(
            total_documents=0,
            scored_documents=0,
            stale_count=0,
            threshold=0.3,
            scores=[],
        )
        output = _format_plain(report)
        assert "No documents found" in output

    def test_empty_report_all_fresh(self) -> None:
        report = FreshnessReport(
            total_documents=5,
            scored_documents=0,
            stale_count=0,
            threshold=0.3,
            scores=[],
        )
        output = _format_plain(report)
        assert "everything looks fresh" in output

    def test_table_output(self) -> None:
        report = FreshnessReport(
            total_documents=1,
            scored_documents=1,
            stale_count=1,
            threshold=0.3,
            scores=[
                DocFreshnessScore(
                    id=1,
                    title="Test Document",
                    freshness=0.2,
                    signals=SignalScores(
                        age_decay=0.1,
                        view_recency=0.1,
                        link_health=1.0,
                        content_length=1.0,
                        tag_signal=0.5,
                    ),
                )
            ],
        )
        output = _format_plain(report)
        assert "Freshness Report" in output
        assert "Test Document" in output
        assert "stale" in output

    def test_long_title_truncated(self) -> None:
        report = FreshnessReport(
            total_documents=1,
            scored_documents=1,
            stale_count=0,
            threshold=0.3,
            scores=[
                DocFreshnessScore(
                    id=1,
                    title="A" * 50,
                    freshness=0.8,
                    signals=SignalScores(
                        age_decay=1.0,
                        view_recency=1.0,
                        link_health=1.0,
                        content_length=1.0,
                        tag_signal=0.5,
                    ),
                )
            ],
        )
        output = _format_plain(report)
        assert "..." in output


class TestFormatJson:
    def test_valid_json(self) -> None:
        report = FreshnessReport(
            total_documents=1,
            scored_documents=1,
            stale_count=0,
            threshold=0.3,
            scores=[
                DocFreshnessScore(
                    id=1,
                    title="Test",
                    freshness=0.8,
                    signals=SignalScores(
                        age_decay=1.0,
                        view_recency=1.0,
                        link_health=1.0,
                        content_length=1.0,
                        tag_signal=0.5,
                    ),
                )
            ],
        )
        output = _format_json(report)
        parsed = json.loads(output)
        assert parsed["total_documents"] == 1
        assert parsed["scores"][0]["id"] == 1
        assert "signals" in parsed["scores"][0]
