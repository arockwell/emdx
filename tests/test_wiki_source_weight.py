"""Tests for wiki source weight, exclude/include commands (Issue #1247)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _setup_topic_with_members(
    conn: sqlite3.Connection,
    topic_id: int = 80,
    doc_ids: list[int] | None = None,
) -> None:
    """Insert a wiki topic with member documents."""
    if doc_ids is None:
        doc_ids = [180, 181, 182]

    conn.execute(
        "INSERT INTO wiki_topics "
        "(id, topic_slug, topic_label, entity_fingerprint, status) "
        "VALUES (?, 'test-weight-topic', 'Weight Test Topic', 'fp', 'active')",
        (topic_id,),
    )
    for did in doc_ids:
        conn.execute(
            "INSERT OR IGNORE INTO documents (id, title, content, is_deleted) "
            "VALUES (?, ?, 'Content for doc', 0)",
            (did, f"Source Doc {did}"),
        )
        conn.execute(
            "INSERT INTO wiki_topic_members "
            "(topic_id, document_id, relevance_score, is_primary) "
            "VALUES (?, ?, 1.0, 1)",
            (topic_id, did),
        )
    conn.commit()


def _cleanup(conn: sqlite3.Connection, topic_id: int = 80) -> None:
    """Remove test data."""
    conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM wiki_topics WHERE id = ?", (topic_id,))
    conn.execute("DELETE FROM documents WHERE id IN (180, 181, 182)")
    conn.commit()


class TestWikiSourcesCommand:
    """Test 'emdx maintain wiki sources' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_sources_lists_all_members(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "sources", "80"])
        assert result.exit_code == 0
        assert "Weight Test Topic" in result.output
        assert "#180" in result.output
        assert "#181" in result.output
        assert "#182" in result.output

    def test_sources_shows_weight_and_status(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "sources", "80"])
        assert result.exit_code == 0
        assert "w=1.00" in result.output
        assert "included" in result.output

    def test_sources_shows_excluded_status(self) -> None:
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_topic_members SET is_primary = 0 "
                "WHERE topic_id = 80 AND document_id = 181"
            )
            conn.commit()

        result = runner.invoke(app, ["maintain", "wiki", "sources", "80"])
        assert result.exit_code == 0
        assert "EXCLUDED" in result.output

    def test_sources_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "sources", "999"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestWikiWeightCommand:
    """Test 'emdx maintain wiki weight' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_weight_sets_relevance_score(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "weight", "80", "180", "0.5"])
        assert result.exit_code == 0
        assert "0.50" in result.output

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT relevance_score FROM wiki_topic_members "
                "WHERE topic_id = 80 AND document_id = 180"
            ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(0.5)

    def test_weight_shows_old_and_new(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "weight", "80", "180", "0.3"])
        assert result.exit_code == 0
        assert "1.00" in result.output  # old weight
        assert "0.30" in result.output  # new weight

    def test_weight_rejects_invalid_range(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "weight", "80", "180", "1.5"])
        assert result.exit_code == 1
        assert "between 0.0 and 1.0" in result.output

    def test_weight_rejects_negative(self) -> None:
        # Negative floats are parsed as flags by click, so exit_code is 2
        result = runner.invoke(app, ["maintain", "wiki", "weight", "80", "180", "-0.1"])
        assert result.exit_code != 0

    def test_weight_nonexistent_member(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "weight", "80", "999", "0.5"])
        assert result.exit_code == 1
        assert "not a member" in result.output


class TestWikiExcludeCommand:
    """Test 'emdx maintain wiki exclude' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_exclude_sets_is_primary_to_zero(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "exclude", "80", "181"])
        assert result.exit_code == 0
        assert "Excluded" in result.output

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT is_primary FROM wiki_topic_members "
                "WHERE topic_id = 80 AND document_id = 181"
            ).fetchone()
        assert row is not None
        assert row[0] == 0

    def test_exclude_nonexistent_member(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "exclude", "80", "999"])
        assert result.exit_code == 1
        assert "not a member" in result.output


class TestWikiIncludeCommand:
    """Test 'emdx maintain wiki include' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
            conn.execute(
                "UPDATE wiki_topic_members SET is_primary = 0 "
                "WHERE topic_id = 80 AND document_id = 182"
            )
            conn.commit()
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_include_sets_is_primary_to_one(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "include", "80", "182"])
        assert result.exit_code == 0
        assert "Included" in result.output

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT is_primary FROM wiki_topic_members "
                "WHERE topic_id = 80 AND document_id = 182"
            ).fetchone()
        assert row is not None
        assert row[0] == 1

    def test_include_nonexistent_member(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "include", "80", "999"])
        assert result.exit_code == 1
        assert "not a member" in result.output


class TestGetTopicDocsFiltersExcluded:
    """Test that get_topic_docs skips excluded (is_primary=0) members."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_get_topic_docs_includes_all_by_default(self) -> None:
        from emdx.services.wiki_clustering_service import get_topic_docs

        docs = get_topic_docs(80)
        assert set(docs) == {180, 181, 182}

    def test_get_topic_docs_excludes_non_primary(self) -> None:
        from emdx.services.wiki_clustering_service import get_topic_docs

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_topic_members SET is_primary = 0 "
                "WHERE topic_id = 80 AND document_id = 181"
            )
            conn.commit()

        docs = get_topic_docs(80)
        assert 181 not in docs
        assert set(docs) == {180, 182}


class TestPrepareSourcesRespectsWeights:
    """Test that _prepare_sources scales content by relevance_score."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_topic_with_members(conn)
        yield
        with db.get_connection() as conn:
            _cleanup(conn)

    def test_prepare_sources_without_topic_id_uses_default_weight(self) -> None:
        from emdx.services.wiki_synthesis_service import _prepare_sources

        sources = _prepare_sources([180, 181])
        for src in sources:
            assert src.relevance_score == 1.0

    def test_prepare_sources_with_topic_id_reads_weights(self) -> None:
        from emdx.services.wiki_synthesis_service import _prepare_sources

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_topic_members SET relevance_score = 0.5 "
                "WHERE topic_id = 80 AND document_id = 180"
            )
            conn.commit()

        sources = _prepare_sources([180, 181], topic_id=80)
        weight_map = {s.doc_id: s.relevance_score for s in sources}
        assert weight_map[180] == pytest.approx(0.5)
        assert weight_map[181] == pytest.approx(1.0)

    def test_prepare_sources_scales_content_by_weight(self) -> None:
        """A doc with weight=0.5 should get half the max char allowance."""
        from emdx.services.wiki_synthesis_service import MAX_DOC_CHARS, _prepare_sources

        # Create a document with content longer than MAX_DOC_CHARS
        long_content = "x" * (MAX_DOC_CHARS + 1000)
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET content = ? WHERE id = 180",
                (long_content,),
            )
            conn.execute(
                "UPDATE wiki_topic_members SET relevance_score = 0.5 "
                "WHERE topic_id = 80 AND document_id = 180"
            )
            conn.commit()

        sources = _prepare_sources([180], topic_id=80)
        assert len(sources) == 1
        # Content should be truncated to ~MAX_DOC_CHARS * 0.5 + truncation marker
        expected_max = int(MAX_DOC_CHARS * 0.5) + len("\n\n[... content truncated ...]")
        assert sources[0].char_count <= expected_max

    def test_prepare_sources_zero_weight_skips_doc(self) -> None:
        """A doc with weight=0.0 should be skipped entirely."""
        from emdx.services.wiki_synthesis_service import _prepare_sources

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_topic_members SET relevance_score = 0.0 "
                "WHERE topic_id = 80 AND document_id = 180"
            )
            conn.commit()

        sources = _prepare_sources([180, 181, 182], topic_id=80)
        doc_ids = {s.doc_id for s in sources}
        assert 180 not in doc_ids
        assert 181 in doc_ids
        assert 182 in doc_ids
