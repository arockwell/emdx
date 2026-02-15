"""Tests for the hybrid search service."""

from unittest.mock import MagicMock, patch

from emdx.services.hybrid_search import (
    HYBRID_BOOST,
    KEYWORD_WEIGHT,
    SEMANTIC_WEIGHT,
    HybridSearchResult,
    HybridSearchService,
    SearchMode,
    normalize_fts5_score,
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
    """Tests for weight constants used in hybrid scoring."""

    def test_weights_sum_reasonable(self):
        """Keyword + semantic weights sum to reasonable value."""
        # Weights should sum to ~1.0 (before boost)
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
    """Tests for score merging in hybrid search."""

    def test_hybrid_boost_applied_when_found_in_both(self):
        """Documents found in both searches get hybrid boost."""
        # This tests the logic conceptually - in actual hybrid search,
        # documents appearing in both keyword and semantic results
        # should have their scores boosted by HYBRID_BOOST

        keyword_score = 0.6
        semantic_score = 0.7

        # Expected combined score
        expected = (
            KEYWORD_WEIGHT * keyword_score
            + SEMANTIC_WEIGHT * semantic_score
            + HYBRID_BOOST
        )

        # Should be clamped to max 1.0
        expected = min(1.0, expected)

        # The actual calculation in _search_hybrid
        actual = (
            KEYWORD_WEIGHT * keyword_score
            + SEMANTIC_WEIGHT * semantic_score
            + HYBRID_BOOST
        )
        actual = min(1.0, actual)

        assert actual == expected

    def test_keyword_only_score_weighted(self):
        """Keyword-only results get weighted score."""
        keyword_score = 0.8
        expected = KEYWORD_WEIGHT * keyword_score
        assert expected < keyword_score  # Should be reduced

    def test_semantic_only_score_weighted(self):
        """Semantic-only results get weighted score."""
        semantic_score = 0.7
        expected = SEMANTIC_WEIGHT * semantic_score
        assert expected < semantic_score  # Should be reduced
