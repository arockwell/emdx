"""Tests for wiki quality scoring service."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from emdx.services.wiki_quality_service import (
    _composite_score,
    _score_coherence,
    _score_coverage,
    _score_freshness,
    _score_source_density,
    llm_quality_assessment,
    score_all_articles,
    score_article,
)

# ── Coverage tests ───────────────────────────────────────────────────


class TestCoverage:
    """Tests for _score_coverage dimension."""

    def test_empty_content(self) -> None:
        assert _score_coverage("", ["some source"]) == 0.0

    def test_empty_sources(self) -> None:
        assert _score_coverage("some article", []) == 0.0

    def test_both_empty(self) -> None:
        assert _score_coverage("", []) == 0.0

    def test_perfect_overlap(self) -> None:
        source = "Python testing framework with pytest fixtures"
        article = "Python testing framework with pytest fixtures and more"
        score = _score_coverage(article, [source])
        assert score > 0.8

    def test_no_overlap(self) -> None:
        source = "quantum computing algorithms entanglement"
        article = "french cuisine baguettes croissants pastries"
        score = _score_coverage(article, [source])
        assert score < 0.3

    def test_partial_overlap(self) -> None:
        source = "Python testing framework pytest fixtures mocking"
        article = "Python testing is important for code quality"
        score = _score_coverage(article, [source])
        assert 0.1 < score < 0.9

    def test_multiple_sources(self) -> None:
        sources = [
            "database migrations schema versioning",
            "Python testing framework pytest fixtures",
        ]
        article = (
            "database migrations and schema versioning are important "
            "Python testing framework with pytest fixtures"
        )
        score = _score_coverage(article, sources)
        assert score > 0.5

    def test_short_tokens_ignored(self) -> None:
        """Tokens shorter than 4 chars are not counted."""
        source = "a b c de is to"
        article = "a b c de is to"
        score = _score_coverage(article, [source])
        assert score == 0.0


# ── Freshness tests ──────────────────────────────────────────────────


class TestFreshness:
    """Tests for _score_freshness dimension."""

    def test_none_generated_at(self) -> None:
        assert _score_freshness(None, []) == 0.0

    def test_recent_article(self) -> None:
        """Recently generated article should score high."""
        import datetime

        now = datetime.datetime.now(tz=datetime.timezone.utc)
        generated = now.isoformat()
        score = _score_freshness(generated, [])
        assert score > 0.9

    def test_old_article(self) -> None:
        """Article generated long ago should score low."""
        import datetime

        old = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=365)
        generated = old.isoformat()
        score = _score_freshness(generated, [])
        assert score < 0.3

    def test_stale_sources_penalty(self) -> None:
        """Sources updated after generation should reduce freshness."""
        import datetime

        now = datetime.datetime.now(tz=datetime.timezone.utc)
        generated = (now - datetime.timedelta(days=1)).isoformat()
        # Source updated after article generation
        source_updated = now.isoformat()
        score_stale = _score_freshness(generated, [source_updated])

        # Compare with no stale sources
        score_fresh = _score_freshness(generated, [generated])
        assert score_stale < score_fresh

    def test_invalid_timestamp(self) -> None:
        assert _score_freshness("not-a-date", []) == 0.0


# ── Coherence tests ──────────────────────────────────────────────────


class TestCoherence:
    """Tests for _score_coherence dimension."""

    def test_empty_content(self) -> None:
        assert _score_coherence("") == 0.0

    def test_well_structured_article(self) -> None:
        article = (
            "# Title\n\n"
            "Introduction paragraph with some context.\n\n"
            "## Section One\n\n"
            "Content for section one goes here.\n\n"
            "## Section Two\n\n"
            "Content for section two goes here.\n\n"
            "## Section Three\n\n"
            "Content for section three goes here.\n\n"
        )
        score = _score_coherence(article)
        assert score > 0.7

    def test_no_headings(self) -> None:
        article = "Just a blob of text without any structure " * 20
        score = _score_coherence(article)
        assert score < 0.6

    def test_too_short(self) -> None:
        article = "# Title\n\nShort."
        score = _score_coherence(article)
        assert score < 0.5

    def test_has_title_bonus(self) -> None:
        """Article with a level-1 heading should score higher."""
        no_title = "## Section\n\nSome content here.\n\n" * 5
        with_title = "# Title\n\n## Section\n\nSome content here.\n\n" * 5
        score_no = _score_coherence(no_title)
        score_yes = _score_coherence(with_title)
        assert score_yes > score_no

    def test_many_paragraphs(self) -> None:
        article = (
            "# Title\n\n"
            + "## Section\n\n"
            + "\n\n".join(f"Paragraph {i} with content." for i in range(10))
        )
        score = _score_coherence(article)
        assert score > 0.5


# ── Source density tests ─────────────────────────────────────────────


class TestSourceDensity:
    """Tests for _score_source_density dimension."""

    def test_empty_content(self) -> None:
        assert _score_source_density("", 5) == 0.0

    def test_zero_sources(self) -> None:
        assert _score_source_density("some content", 0) == 0.0

    def test_ideal_density(self) -> None:
        """~1500 chars per source should score high."""
        content = "x" * 4500
        score = _score_source_density(content, 3)
        assert score > 0.8

    def test_too_sparse(self) -> None:
        """Very little content per source = shallow coverage."""
        content = "x" * 100
        score = _score_source_density(content, 10)
        assert score < 0.5

    def test_many_sources_bonus(self) -> None:
        """5+ sources get a small bonus."""
        content = "x" * 7500
        score_few = _score_source_density(content, 2)
        score_many = _score_source_density(content, 5)
        # Both should be high, many-sources slightly higher
        assert score_many >= score_few


# ── Composite score tests ────────────────────────────────────────────


class TestComposite:
    """Tests for composite scoring."""

    def test_all_perfect(self) -> None:
        score = _composite_score(1.0, 1.0, 1.0, 1.0)
        assert abs(score - 1.0) < 0.01

    def test_all_zero(self) -> None:
        score = _composite_score(0.0, 0.0, 0.0, 0.0)
        assert score == 0.0

    def test_weights_applied(self) -> None:
        """Coverage has the highest weight (0.35)."""
        # Only coverage = 1.0, rest = 0.0
        score_cov = _composite_score(1.0, 0.0, 0.0, 0.0)
        # Only freshness = 1.0, rest = 0.0
        score_fresh = _composite_score(0.0, 1.0, 0.0, 0.0)
        assert score_cov > score_fresh  # coverage weight > freshness weight

    def test_source_density_lowest_weight(self) -> None:
        """Source density has the lowest weight (0.15)."""
        score_src = _composite_score(0.0, 0.0, 0.0, 1.0)
        score_cov = _composite_score(1.0, 0.0, 0.0, 0.0)
        assert score_src < score_cov


# ── Integration tests (score_article) ────────────────────────────────


class TestScoreArticle:
    """Integration tests for score_article with mocked DB."""

    def _setup_mock_db(self, conn_mock: MagicMock) -> MagicMock:
        """Set up a mock DB connection with wiki data."""
        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        conn_mock.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        # article row: (id, document_id, topic_id, generated_at, label)
        article_row = MagicMock()
        article_row.__getitem__ = lambda self, i: [
            1,
            10,
            5,
            "2026-03-01T00:00:00+00:00",
            "Test Topic",
        ][i]

        # doc row: (title, content)
        doc_row = MagicMock()
        doc_row.__getitem__ = lambda self, i: [
            "Wiki: Test Topic",
            "# Test Topic\n\n## Overview\n\nSome content here.\n\n"
            "## Details\n\nMore detailed content.\n\n",
        ][i]

        # source rows: (doc_id, content, updated_at)
        source_row = MagicMock()
        source_row.__getitem__ = lambda self, i: [
            20,
            "Source content with details",
            "2026-02-28T00:00:00+00:00",
        ][i]

        call_count = [0]

        def side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone.return_value = article_row
            elif call_count[0] == 2:
                result.fetchone.return_value = doc_row
            elif call_count[0] == 3:
                result.fetchall.return_value = [source_row]
            return result

        conn.execute = MagicMock(side_effect=side_effect)
        return conn

    @patch("emdx.services.wiki_quality_service.db")
    def test_score_article_returns_all_fields(self, mock_db: MagicMock) -> None:
        self._setup_mock_db(mock_db.get_connection)
        result = score_article(5)
        assert result["topic_id"] == 5
        assert "coverage" in result
        assert "freshness" in result
        assert "coherence" in result
        assert "source_density" in result
        assert "composite" in result
        assert "article_title" in result

    @patch("emdx.services.wiki_quality_service.db")
    def test_score_article_no_article(self, mock_db: MagicMock) -> None:
        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        mock_db.get_connection.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        execute_result = MagicMock()
        execute_result.fetchone.return_value = None
        conn.execute.return_value = execute_result

        result = score_article(999)
        assert "error" in result
        assert result["composite"] == 0.0


# ── Integration tests (score_all_articles) ───────────────────────────


class TestScoreAllArticles:
    """Tests for score_all_articles."""

    @patch("emdx.services.wiki_quality_service.score_article")
    @patch("emdx.services.wiki_quality_service.db")
    def test_score_all_sorts_worst_first(self, mock_db: MagicMock, mock_score: MagicMock) -> None:
        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        mock_db.get_connection.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        # Two topics returned
        conn.execute.return_value.fetchall.return_value = [
            (1,),
            (2,),
        ]

        mock_score.side_effect = [
            {
                "topic_id": 1,
                "composite": 0.8,
                "article_id": 1,
                "coverage": 0.9,
                "freshness": 0.7,
                "coherence": 0.8,
                "source_density": 0.6,
            },
            {
                "topic_id": 2,
                "composite": 0.3,
                "article_id": 2,
                "coverage": 0.2,
                "freshness": 0.4,
                "coherence": 0.3,
                "source_density": 0.2,
            },
        ]

        results = score_all_articles()
        assert len(results) == 2
        # Worst first
        assert results[0]["topic_id"] == 2
        assert results[1]["topic_id"] == 1

    @patch("emdx.services.wiki_quality_service.score_article")
    @patch("emdx.services.wiki_quality_service.db")
    def test_threshold_filters(self, mock_db: MagicMock, mock_score: MagicMock) -> None:
        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        mock_db.get_connection.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        conn.execute.return_value.fetchall.return_value = [(1,), (2,)]
        mock_score.side_effect = [
            {
                "topic_id": 1,
                "composite": 0.8,
                "article_id": 1,
                "coverage": 0.9,
                "freshness": 0.7,
                "coherence": 0.8,
                "source_density": 0.6,
            },
            {
                "topic_id": 2,
                "composite": 0.3,
                "article_id": 2,
                "coverage": 0.2,
                "freshness": 0.4,
                "coherence": 0.3,
                "source_density": 0.2,
            },
        ]

        results = score_all_articles(threshold=0.5)
        assert len(results) == 1
        assert results[0]["topic_id"] == 2


# ── LLM assessment tests ────────────────────────────────────────────


class TestLLMAssessment:
    """Tests for llm_quality_assessment with mocked LLM."""

    @patch("emdx.services.wiki_quality_service.score_article")
    def test_llm_returns_error_when_no_article(self, mock_score: MagicMock) -> None:
        mock_score.return_value = {
            "topic_id": 999,
            "error": "No article found for topic 999",
            "composite": 0.0,
        }
        result = llm_quality_assessment(999)
        assert "error" in result

    @patch("emdx.services.synthesis_service._execute_prompt")
    @patch("emdx.services.wiki_quality_service.db")
    @patch("emdx.services.wiki_quality_service.score_article")
    def test_llm_parses_grade(
        self,
        mock_score: MagicMock,
        mock_db: MagicMock,
        mock_prompt: MagicMock,
    ) -> None:
        mock_score.return_value = {
            "topic_id": 5,
            "topic_label": "Test",
            "article_id": 1,
            "document_id": 10,
            "coverage": 0.9,
            "freshness": 0.8,
            "coherence": 0.7,
            "source_density": 0.6,
            "composite": 0.8,
        }

        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        mock_db.get_connection.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        # doc row
        doc_row = MagicMock()
        doc_row.__getitem__ = lambda self, i: ["Test Article", "# Content\n\nBody"][i]

        source_row = MagicMock()
        source_row.__getitem__ = lambda self, i: ["Source Title", "Source content"][i]

        call_count = [0]

        def execute_side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone.return_value = doc_row
            elif call_count[0] == 2:
                result.fetchall.return_value = [source_row]
            return result

        conn.execute = MagicMock(side_effect=execute_side_effect)

        prompt_result = MagicMock()
        prompt_result.output_content = (
            "GRADE: B\n\n"
            "ASSESSMENT:\nDecent article.\n\n"
            "STRENGTHS:\n- Good structure\n\n"
            "WEAKNESSES:\n- Needs examples\n\n"
            "SUGGESTIONS:\n- Add code samples\n"
        )
        mock_prompt.return_value = prompt_result

        result = llm_quality_assessment(5)
        assert result["overall_grade"] == "B"
        assert "scores" in result

    @patch("emdx.services.synthesis_service._execute_prompt")
    @patch("emdx.services.wiki_quality_service.db")
    @patch("emdx.services.wiki_quality_service.score_article")
    def test_llm_handles_runtime_error(
        self,
        mock_score: MagicMock,
        mock_db: MagicMock,
        mock_prompt: MagicMock,
    ) -> None:
        mock_score.return_value = {
            "topic_id": 5,
            "topic_label": "Test",
            "article_id": 1,
            "document_id": 10,
            "composite": 0.5,
        }

        ctx = MagicMock()
        conn = MagicMock(spec=sqlite3.Connection)
        mock_db.get_connection.return_value = ctx
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        doc_row = MagicMock()
        doc_row.__getitem__ = lambda self, i: ["Title", "Content"][i]

        call_count = [0]

        def execute_side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone.return_value = doc_row
            elif call_count[0] == 2:
                result.fetchall.return_value = []
            return result

        conn.execute = MagicMock(side_effect=execute_side_effect)
        mock_prompt.side_effect = RuntimeError("CLI not found")

        result = llm_quality_assessment(5)
        assert "error" in result
        assert "CLI not found" in str(result["error"])
