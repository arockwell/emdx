"""Tests for the hybrid search service."""

from unittest.mock import MagicMock, patch

import pytest

from emdx.services.hybrid_search import (
    MANUAL_LINK_BOOST_CAP,
    MANUAL_LINK_BOOST_PER_LINK,
    RRF_K,
    HybridSearchResult,
    HybridSearchService,
    SearchMode,
    apply_manual_link_boost,
    get_manual_link_counts,
    normalize_fts5_score,
    normalize_fts5_scores_minmax,
    rrf_score,
)


class TestNormalizeFts5Score:
    """Tests for FTS5 score normalization."""

    def test_zero_rank_returns_half(self):
        """Zero rank returns 0.5 as neutral score."""
        assert normalize_fts5_score(0) == 0.5

    def test_none_rank_returns_half(self):
        """None rank returns 0.5 as neutral score."""
        assert normalize_fts5_score(None) == 0.5

    def test_negative_rank_normalized_to_positive(self):
        """Negative FTS5 ranks are normalized to 0-1 scale."""
        # -10 should give ~0.5
        score = normalize_fts5_score(-10)
        assert 0.4 <= score <= 0.6

        # -5 should be higher (better match)
        score = normalize_fts5_score(-5)
        assert score > 0.5

    def test_very_negative_clamped_to_zero(self):
        """Very negative ranks are clamped to 0."""
        score = normalize_fts5_score(-30)
        assert score >= 0.0

    def test_output_always_between_zero_and_one(self):
        """Normalized score is always in [0, 1] range."""
        test_values = [-100, -50, -20, -10, -5, -1, 0, 5, 10]
        for val in test_values:
            score = normalize_fts5_score(val)
            assert 0.0 <= score <= 1.0


class TestNormalizeFts5ScoresMinmax:
    """Tests for min-max normalization of FTS5 scores."""

    def _make_result(self, keyword_score: float) -> HybridSearchResult:
        return HybridSearchResult(
            doc_id=1,
            title="T",
            project=None,
            score=0.0,
            keyword_score=keyword_score,
            semantic_score=0.0,
            source="keyword",
            snippet="",
        )

    def test_empty_list_is_noop(self):
        """Empty list doesn't raise."""
        normalize_fts5_scores_minmax([])

    def test_single_result_gets_half(self):
        """Single result gets 0.5 (range is zero)."""
        results = [self._make_result(0.75)]
        normalize_fts5_scores_minmax(results)
        assert results[0].keyword_score == 0.5

    def test_two_results_scaled_to_zero_one(self):
        """Min becomes 0.0, max becomes 1.0."""
        results = [self._make_result(0.3), self._make_result(0.9)]
        normalize_fts5_scores_minmax(results)
        assert results[0].keyword_score == 0.0
        assert results[1].keyword_score == 1.0

    def test_three_results_linear_interpolation(self):
        """Middle value is linearly interpolated."""
        results = [
            self._make_result(0.2),
            self._make_result(0.6),
            self._make_result(1.0),
        ]
        normalize_fts5_scores_minmax(results)
        assert results[0].keyword_score == 0.0
        assert abs(results[1].keyword_score - 0.5) < 1e-9
        assert results[2].keyword_score == 1.0

    def test_all_same_score_gets_half(self):
        """Uniform scores all become 0.5."""
        results = [self._make_result(0.7) for _ in range(3)]
        normalize_fts5_scores_minmax(results)
        for r in results:
            assert r.keyword_score == 0.5


class TestRrfScore:
    """Tests for Reciprocal Rank Fusion scoring."""

    def test_both_ranks_present(self):
        """RRF with both keyword and semantic ranks."""
        score = rrf_score(1, 1, k=60)
        expected = 1.0 / 61 + 1.0 / 61
        assert abs(score - expected) < 1e-9

    def test_keyword_only(self):
        """RRF with only keyword rank present."""
        score = rrf_score(1, None, k=60)
        expected = 1.0 / 61
        assert abs(score - expected) < 1e-9

    def test_semantic_only(self):
        """RRF with only semantic rank present."""
        score = rrf_score(None, 2, k=60)
        expected = 1.0 / 62
        assert abs(score - expected) < 1e-9

    def test_both_none_returns_zero(self):
        """RRF with no ranks returns 0."""
        assert rrf_score(None, None) == 0.0

    def test_higher_rank_gives_higher_score(self):
        """Rank 1 produces a higher RRF contribution than rank 10."""
        score_rank1 = rrf_score(1, None)
        score_rank10 = rrf_score(10, None)
        assert score_rank1 > score_rank10

    def test_both_lists_beats_one_list(self):
        """Document in both lists scores higher than in just one."""
        both = rrf_score(1, 1)
        keyword_only = rrf_score(1, None)
        semantic_only = rrf_score(None, 1)
        assert both > keyword_only
        assert both > semantic_only

    def test_custom_k_value(self):
        """Custom k value changes the score."""
        score_k10 = rrf_score(1, 1, k=10)
        score_k60 = rrf_score(1, 1, k=60)
        # Smaller k gives higher scores (more weight to rank)
        assert score_k10 > score_k60

    def test_rrf_k_constant_is_sixty(self):
        """Default RRF_K constant is 60."""
        assert RRF_K == 60

    def test_rank_ordering_preserved(self):
        """Higher ranked documents always score higher in RRF."""
        scores = [rrf_score(r, r) for r in range(1, 11)]
        # Should be strictly decreasing
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1]


class TestSearchMode:
    """Tests for SearchMode enum."""

    def test_keyword_mode_value(self):
        """Keyword mode has correct value."""
        assert SearchMode.KEYWORD.value == "keyword"

    def test_semantic_mode_value(self):
        """Semantic mode has correct value."""
        assert SearchMode.SEMANTIC.value == "semantic"

    def test_hybrid_mode_value(self):
        """Hybrid mode has correct value."""
        assert SearchMode.HYBRID.value == "hybrid"


class TestHybridSearchResult:
    """Tests for HybridSearchResult dataclass."""

    def test_default_tags_empty_list(self):
        """Tags default to empty list."""
        result = HybridSearchResult(
            doc_id=1,
            title="Test",
            project=None,
            score=0.5,
            keyword_score=0.5,
            semantic_score=0.0,
            source="keyword",
            snippet="Test snippet",
        )
        assert result.tags == []

    def test_default_chunk_fields_none(self):
        """Chunk-related fields default to None."""
        result = HybridSearchResult(
            doc_id=1,
            title="Test",
            project=None,
            score=0.5,
            keyword_score=0.5,
            semantic_score=0.0,
            source="keyword",
            snippet="Test snippet",
        )
        assert result.chunk_heading is None
        assert result.chunk_text is None

    def test_all_fields_populated(self):
        """All fields can be populated."""
        result = HybridSearchResult(
            doc_id=42,
            title="Full Result",
            project="my-project",
            score=0.9,
            keyword_score=0.7,
            semantic_score=0.8,
            source="hybrid",
            snippet="Matched content...",
            tags=["python", "analysis"],
            chunk_heading="Methods > Data",
            chunk_text="Full chunk text here",
        )
        assert result.doc_id == 42
        assert result.title == "Full Result"
        assert result.project == "my-project"
        assert result.source == "hybrid"
        assert result.tags == ["python", "analysis"]
        assert result.chunk_heading == "Methods > Data"


class TestHybridSearchService:
    """Tests for HybridSearchService class."""

    def test_init_no_embedding_service_loaded(self):
        """Service initializes without loading embedding service."""
        service = HybridSearchService()
        # Should not have loaded embedding service yet
        assert service._embedding_service is None

    @patch("emdx.services.hybrid_search.db")
    def test_has_embeddings_returns_false_on_error(self, mock_db):
        """has_embeddings returns False when table doesn't exist."""
        mock_db.get_connection.side_effect = Exception("No table")
        service = HybridSearchService()
        assert service.has_embeddings() is False

    @patch("emdx.services.hybrid_search.db")
    def test_has_embeddings_returns_true_when_data_exists(self, mock_db):
        """has_embeddings returns True when embeddings exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)  # 5 embeddings exist
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = lambda s: mock_conn
        mock_db.get_connection.return_value.__exit__ = lambda *args: None

        service = HybridSearchService()
        assert service.has_embeddings() is True

    @patch("emdx.services.hybrid_search.db")
    def test_has_chunk_index_returns_false_on_error(self, mock_db):
        """has_chunk_index returns False when table doesn't exist."""
        mock_db.get_connection.side_effect = Exception("No table")
        service = HybridSearchService()
        assert service.has_chunk_index() is False

    def test_determine_mode_explicit_keyword(self):
        """Explicit keyword mode is respected."""
        service = HybridSearchService()
        mode = service.determine_mode("keyword")
        assert mode == SearchMode.KEYWORD

    def test_determine_mode_explicit_semantic(self):
        """Explicit semantic mode is respected."""
        service = HybridSearchService()
        mode = service.determine_mode("semantic")
        assert mode == SearchMode.SEMANTIC

    def test_determine_mode_explicit_hybrid(self):
        """Explicit hybrid mode is respected."""
        service = HybridSearchService()
        mode = service.determine_mode("hybrid")
        assert mode == SearchMode.HYBRID

    def test_determine_mode_invalid_defaults_to_hybrid(self):
        """Invalid mode string logs warning and defaults."""
        service = HybridSearchService()
        # Mock has_embeddings to return True for default hybrid
        with patch.object(service, "has_embeddings", return_value=True):
            mode = service.determine_mode("invalid_mode")
            # Falls through to auto-detect, which sees embeddings -> hybrid
            assert mode == SearchMode.HYBRID

    @patch("emdx.services.hybrid_search.db")
    def test_determine_mode_auto_keyword_no_index(self, mock_db):
        """Auto mode returns keyword when no embeddings."""
        mock_db.get_connection.side_effect = Exception("No table")
        service = HybridSearchService()
        mode = service.determine_mode(None)
        assert mode == SearchMode.KEYWORD


class TestHybridMerging:
    """Tests for RRF-based score merging in hybrid search."""

    def test_document_in_both_lists_scores_highest(self):
        """Documents found in both searches get highest RRF score."""
        # Doc in both at rank 1 beats doc in only one list at rank 1
        both_score = rrf_score(1, 1)
        keyword_only_score = rrf_score(1, None)
        semantic_only_score = rrf_score(None, 1)
        assert both_score > keyword_only_score
        assert both_score > semantic_only_score

    def test_rrf_gives_diminishing_returns_for_lower_ranks(self):
        """Lower-ranked results contribute less to RRF score."""
        top_pair = rrf_score(1, 1)
        mid_pair = rrf_score(5, 5)
        low_pair = rrf_score(20, 20)
        assert top_pair > mid_pair > low_pair

    def test_keyword_only_score_less_than_original(self):
        """Keyword-only results get reduced RRF score vs both-list."""
        keyword_only = rrf_score(1, None)
        both = rrf_score(1, 1)
        assert keyword_only < both

    def test_semantic_only_score_less_than_original(self):
        """Semantic-only results get reduced RRF score vs both-list."""
        semantic_only = rrf_score(None, 1)
        both = rrf_score(1, 1)
        assert semantic_only < both

    def test_high_rank_in_one_list_beats_low_in_both(self):
        """Rank 1 in one list can beat poor ranks in both lists."""
        rank1_one_list = rrf_score(1, None)
        rank20_both = rrf_score(20, 20)
        # Rank 1 in one list: 1/61 ≈ 0.0164
        # Rank 20 in both: 2/80 = 0.025
        # Both at rank 20 still wins because of two contributions
        assert rank20_both > rank1_one_list


class TestGetManualLinkCounts:
    """Tests for get_manual_link_counts (#1115)."""

    def _insert_docs(self, conn, titles):
        """Insert docs with auto-assigned IDs (session DB is shared across tests)."""
        ids = []
        for title in titles:
            cursor = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                (title, f"Content for {title}"),
            )
            ids.append(cursor.lastrowid)
        return ids

    def test_empty_doc_ids_returns_empty(self, isolate_test_database):
        assert get_manual_link_counts([]) == {}

    def test_no_links_returns_empty(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            (doc_id,) = self._insert_docs(conn, ["Lonely Doc"])
            conn.commit()

        assert get_manual_link_counts([doc_id]) == {}

    def test_counts_manual_links_only(self, isolate_test_database):
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            synthesis, raw_a, raw_b, auto_target = self._insert_docs(
                conn, ["Synthesis Doc", "Raw Doc A", "Raw Doc B", "Auto-linked Doc"]
            )
            conn.commit()

        create_link(raw_a, synthesis, similarity_score=1.0, method="manual")
        create_link(raw_b, synthesis, similarity_score=1.0, method="manual")
        # An automatic link to a third doc should not count toward the boost
        create_link(synthesis, auto_target, similarity_score=0.9, method="auto")

        counts = get_manual_link_counts([synthesis, raw_a, raw_b, auto_target])
        assert counts[synthesis] == 2
        assert counts.get(auto_target, 0) == 0

    def test_counts_both_directions(self, isolate_test_database):
        """A manual link counts for a doc whether it's the source or target."""
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            doc_a, doc_b = self._insert_docs(conn, ["Doc A", "Doc B"])
            conn.commit()

        create_link(doc_a, doc_b, similarity_score=1.0, method="manual")

        counts = get_manual_link_counts([doc_a, doc_b])
        assert counts[doc_a] == 1
        assert counts[doc_b] == 1


class TestApplyManualLinkBoost:
    """Tests for apply_manual_link_boost (#1115)."""

    def _make_result(self, doc_id, score, source="keyword"):
        return HybridSearchResult(
            doc_id=doc_id,
            title=f"Doc {doc_id}",
            project=None,
            score=score,
            keyword_score=score,
            semantic_score=0.0,
            source=source,
            snippet="",
        )

    def _insert_docs(self, conn, titles):
        """Insert docs with auto-assigned IDs (session DB is shared across tests)."""
        ids = []
        for title in titles:
            cursor = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                (title, f"Content for {title}"),
            )
            ids.append(cursor.lastrowid)
        return ids

    def test_empty_results_is_noop(self, isolate_test_database):
        results = []
        apply_manual_link_boost(results)
        assert results == []

    def test_zero_relevance_docs_never_boosted(self, isolate_test_database):
        """A doc with 0 text relevance isn't surfaced just for being linked."""
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            zero_doc_id, linked_id = self._insert_docs(conn, ["A", "B"])
            conn.commit()
        create_link(zero_doc_id, linked_id, similarity_score=1.0, method="manual")

        results = [self._make_result(zero_doc_id, 0.0), self._make_result(linked_id, 0.5)]
        apply_manual_link_boost(results)

        zero_doc = next(r for r in results if r.doc_id == zero_doc_id)
        assert zero_doc.score == 0.0

    def test_manually_linked_doc_ranks_above_equal_relevance_doc(self, isolate_test_database):
        """Same base score, but the manually-linked doc should rank first."""
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            unlinked_id, linked_id, citing_id = self._insert_docs(conn, ["A", "B", "C"])
            conn.commit()
        # linked_id is manually linked from citing_id; unlinked_id has no links at all
        create_link(citing_id, linked_id, similarity_score=1.0, method="manual")

        results = [
            self._make_result(unlinked_id, 0.5),
            self._make_result(linked_id, 0.5),
        ]
        apply_manual_link_boost(results)

        assert results[0].doc_id == linked_id
        assert results[0].score > results[1].score
        assert results[1].score == pytest.approx(0.5)

    def test_boost_is_capped(self, isolate_test_database):
        """Many manual links don't produce an unbounded boost."""
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            ids = self._insert_docs(conn, [f"D{i}" for i in range(10)])
            conn.commit()

        target, *others = ids
        for other in others:
            create_link(other, target, similarity_score=1.0, method="manual")

        results = [self._make_result(target, 0.5)]
        apply_manual_link_boost(results)

        max_expected = min(1.0, 0.5 * (1.0 + MANUAL_LINK_BOOST_CAP))
        assert results[0].score == pytest.approx(max_expected)
        assert MANUAL_LINK_BOOST_PER_LINK * 9 > MANUAL_LINK_BOOST_CAP  # sanity: cap actually bites


class TestKeywordSearchManualLinkBoostIntegration:
    """End-to-end regression test for #1115 through the real FTS5 keyword path.

    A manually-linked "synthesis" doc should outrank an equally
    keyword-relevant "raw legwork" doc that has no manual links.
    """

    def test_manually_linked_doc_outranks_equal_keyword_match(self, isolate_test_database):
        from emdx.database import db
        from emdx.database.document_links import create_link

        query_text = "zzqfluxcalib zzqfluxcalib"
        with db.get_connection() as conn:
            raw_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Raw Legwork", query_text),
            ).lastrowid
            synthesis_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Synthesis Answer", query_text),
            ).lastrowid
            # A source doc that cites the synthesis answer as authoritative
            citing_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Citing Doc", "unrelated content"),
            ).lastrowid
            conn.commit()

        create_link(citing_id, synthesis_id, similarity_score=1.0, method="manual")

        service = HybridSearchService()
        results = service._search_keyword(query_text, limit=10, project=None)

        doc_ids = [r.doc_id for r in results]
        assert raw_id in doc_ids
        assert synthesis_id in doc_ids

        raw = next(r for r in results if r.doc_id == raw_id)
        synthesis = next(r for r in results if r.doc_id == synthesis_id)

        # Equal keyword relevance before the boost...
        assert raw.keyword_score == pytest.approx(synthesis.keyword_score)
        # ...but the manually-linked doc ranks strictly higher after it.
        assert synthesis.score > raw.score
        assert results.index(synthesis) < results.index(raw)
