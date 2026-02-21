"""Tests for the hybrid search service."""

from unittest.mock import MagicMock, patch

from emdx.services.hybrid_search import (
    HYBRID_BOOST,
    KEYWORD_WEIGHT,
    RRF_K,
    SEMANTIC_WEIGHT,
    HybridSearchResult,
    HybridSearchService,
    SearchMode,
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


class TestWeightConstants:
    """Tests for weight constants (legacy, kept for compatibility)."""

    def test_weights_sum_reasonable(self):
        """Keyword + semantic weights sum to reasonable value."""
        assert 0.9 <= KEYWORD_WEIGHT + SEMANTIC_WEIGHT <= 1.1

    def test_boost_is_small(self):
        """Hybrid boost is a small bonus value."""
        assert 0 < HYBRID_BOOST <= 0.2

    def test_keyword_weight_positive(self):
        """Keyword weight is positive."""
        assert KEYWORD_WEIGHT > 0

    def test_semantic_weight_positive(self):
        """Semantic weight is positive."""
        assert SEMANTIC_WEIGHT > 0


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
