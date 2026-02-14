"""Tests for the contextual save service."""

import json
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.contextual_save import (
    DUPLICATE_THRESHOLD,
    NEW_TOPIC_THRESHOLD,
    RELATED_THRESHOLD,
    CheckResult,
    SimilarDoc,
    _fallback_keyword_search,
    _generate_recommendation,
    _suggest_tags_from_neighbors,
    check_for_similar,
    format_check_output,
)


class TestSimilarDoc:
    """Tests for SimilarDoc dataclass."""

    def test_similar_doc_creation(self):
        """Test creating a SimilarDoc instance."""
        doc = SimilarDoc(
            doc_id=42,
            title="Test Document",
            project="test-project",
            similarity=0.85,
            tags=["python", "testing"],
        )

        assert doc.doc_id == 42
        assert doc.title == "Test Document"
        assert doc.project == "test-project"
        assert doc.similarity == 0.85
        assert doc.tags == ["python", "testing"]


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test creating a CheckResult instance."""
        result = CheckResult(
            similar_docs=[],
            suggested_tags=["python"],
            suggested_project="test-project",
            recommendation="New topic.",
            classification="new",
        )

        assert result.similar_docs == []
        assert result.suggested_tags == ["python"]
        assert result.suggested_project == "test-project"
        assert result.recommendation == "New topic."
        assert result.classification == "new"

    def test_has_duplicates_true(self):
        """Test has_duplicates returns True when there are high-similarity docs."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.85, tags=[]),
            ],
            suggested_tags=[],
            suggested_project=None,
            recommendation="",
            classification="duplicate",
        )
        assert result.has_duplicates() is True

    def test_has_duplicates_false(self):
        """Test has_duplicates returns False when no docs above threshold."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.5, tags=[]),
            ],
            suggested_tags=[],
            suggested_project=None,
            recommendation="",
            classification="related",
        )
        assert result.has_duplicates() is False

    def test_has_related_true(self):
        """Test has_related returns True when docs are in related range."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.6, tags=[]),
            ],
            suggested_tags=[],
            suggested_project=None,
            recommendation="",
            classification="related",
        )
        assert result.has_related() is True

    def test_has_related_false_too_high(self):
        """Test has_related returns False when docs are above related threshold."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.9, tags=[]),
            ],
            suggested_tags=[],
            suggested_project=None,
            recommendation="",
            classification="duplicate",
        )
        assert result.has_related() is False

    def test_has_related_false_too_low(self):
        """Test has_related returns False when docs are below related threshold."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.3, tags=[]),
            ],
            suggested_tags=[],
            suggested_project=None,
            recommendation="",
            classification="new",
        )
        assert result.has_related() is False


class TestSuggestTagsFromNeighbors:
    """Tests for _suggest_tags_from_neighbors function."""

    def test_suggest_tags_empty_docs(self):
        """Test with empty document list."""
        assert _suggest_tags_from_neighbors([]) == []

    def test_suggest_tags_single_doc(self):
        """Test with single document."""
        docs = [
            SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.8, tags=["python", "testing"]),
        ]
        suggestions = _suggest_tags_from_neighbors(docs)
        assert len(suggestions) <= 3
        assert "python" in suggestions or "testing" in suggestions

    def test_suggest_tags_multiple_docs_with_overlap(self):
        """Test with multiple docs that share tags."""
        docs = [
            SimilarDoc(doc_id=1, title="Test1", project=None, similarity=0.8, tags=["python", "testing"]),
            SimilarDoc(doc_id=2, title="Test2", project=None, similarity=0.7, tags=["python", "docs"]),
            SimilarDoc(doc_id=3, title="Test3", project=None, similarity=0.6, tags=["python", "api"]),
        ]
        suggestions = _suggest_tags_from_neighbors(docs)
        # python appears 3 times, should be first
        assert "python" in suggestions
        assert len(suggestions) <= 3

    def test_suggest_tags_respects_max_tags(self):
        """Test that max_tags parameter is respected."""
        docs = [
            SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.8, tags=["a", "b", "c", "d", "e"]),
        ]
        suggestions = _suggest_tags_from_neighbors(docs, max_tags=2)
        assert len(suggestions) <= 2


class TestGenerateRecommendation:
    """Tests for _generate_recommendation function."""

    def test_duplicate_recommendation(self):
        """Test recommendation for duplicate content."""
        docs = [SimilarDoc(doc_id=42, title="Test", project=None, similarity=0.85, tags=[])]
        recommendation, classification = _generate_recommendation(docs, 0.85)

        assert classification == "duplicate"
        assert "#42" in recommendation
        assert "85%" in recommendation
        assert "updating" in recommendation.lower() or "update" in recommendation.lower()

    def test_related_recommendation(self):
        """Test recommendation for related content."""
        docs = [SimilarDoc(doc_id=42, title="Test", project=None, similarity=0.6, tags=[])]
        recommendation, classification = _generate_recommendation(docs, 0.6)

        assert classification == "related"
        assert "#42" in recommendation
        assert "60%" in recommendation

    def test_new_topic_recommendation(self):
        """Test recommendation for new content."""
        docs = [SimilarDoc(doc_id=42, title="Test", project=None, similarity=0.3, tags=[])]
        recommendation, classification = _generate_recommendation(docs, 0.3)

        assert classification == "new"
        assert "New topic" in recommendation


class TestCheckForSimilar:
    """Tests for check_for_similar function."""

    def test_check_returns_new_when_no_similar(self):
        """Test that check returns 'new' classification when no similar docs found."""
        with patch("emdx.services.contextual_save._find_similar_docs") as mock_find:
            mock_find.return_value = []

            result = check_for_similar("Some unique content")

            assert result.classification == "new"
            assert result.similar_docs == []
            assert result.suggested_tags == []

    def test_check_returns_duplicate_for_high_similarity(self):
        """Test that check returns 'duplicate' for high similarity scores."""
        with patch("emdx.services.contextual_save._find_similar_docs") as mock_find:
            with patch("emdx.services.contextual_save.get_tags_for_documents") as mock_tags:
                mock_find.return_value = [
                    SimilarDoc(doc_id=1, title="Similar Doc", project="proj", similarity=0.9, tags=[]),
                ]
                mock_tags.return_value = {1: ["python"]}

                result = check_for_similar("Content that matches another doc")

                assert result.classification == "duplicate"
                assert len(result.similar_docs) == 1
                assert result.similar_docs[0].tags == ["python"]

    def test_check_combines_title_and_text(self):
        """Test that check combines title and text for matching."""
        with patch("emdx.services.contextual_save._find_similar_docs") as mock_find:
            mock_find.return_value = []

            check_for_similar("Content", title="My Title")

            # Verify the combined text was used
            call_args = mock_find.call_args
            assert "My Title" in call_args[0][0]
            assert "Content" in call_args[0][0]

    def test_check_suggests_project_from_top_match(self):
        """Test that suggested project comes from highest similarity doc."""
        with patch("emdx.services.contextual_save._find_similar_docs") as mock_find:
            with patch("emdx.services.contextual_save.get_tags_for_documents") as mock_tags:
                mock_find.return_value = [
                    SimilarDoc(doc_id=1, title="Doc1", project="top-project", similarity=0.7, tags=[]),
                    SimilarDoc(doc_id=2, title="Doc2", project="other-project", similarity=0.5, tags=[]),
                ]
                mock_tags.return_value = {}

                result = check_for_similar("Content")

                assert result.suggested_project == "top-project"


class TestFormatCheckOutput:
    """Tests for format_check_output function."""

    def test_format_post_save_output(self):
        """Test formatting for post-save (with doc_id)."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test", project=None, similarity=0.85, tags=[]),
            ],
            suggested_tags=["python"],
            suggested_project="test",
            recommendation="Update existing.",
            classification="duplicate",
        )

        output = format_check_output(result, doc_id=42)

        assert "Similar docs found" in output
        assert "#1" in output
        assert "85%" in output
        assert "emdx edit" in output  # Should suggest editing

    def test_format_post_save_no_similar(self):
        """Test formatting for post-save with no similar docs."""
        result = CheckResult(
            similar_docs=[],
            suggested_tags=[],
            suggested_project=None,
            recommendation="New topic.",
            classification="new",
        )

        output = format_check_output(result, doc_id=42)

        # Should be empty since no similar docs
        assert output == ""

    def test_format_pre_save_output(self):
        """Test formatting for pre-save check (no doc_id)."""
        result = CheckResult(
            similar_docs=[
                SimilarDoc(doc_id=1, title="Test Doc", project=None, similarity=0.6, tags=[]),
            ],
            suggested_tags=["python", "testing"],
            suggested_project="my-project",
            recommendation="Related to #1.",
            classification="related",
        )

        output = format_check_output(result, doc_id=None)

        assert "Similar existing docs" in output
        assert '"Test Doc"' in output
        assert "60%" in output
        assert "Suggested tags: python, testing" in output
        assert "Suggested project: my-project" in output
        assert "Recommendation:" in output


class TestFallbackKeywordSearch:
    """Tests for _fallback_keyword_search function."""

    def test_fallback_with_empty_keywords(self):
        """Test fallback returns empty when no valid keywords."""
        # Text with only stopwords and short words
        result = _fallback_keyword_search("the a is to in for")
        assert result == []

    def test_fallback_extracts_keywords(self):
        """Test that fallback extracts meaningful keywords."""
        with patch("emdx.services.contextual_save.db") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cursor
            mock_db.get_connection.return_value.__enter__ = lambda s: mock_conn
            mock_db.get_connection.return_value.__exit__ = lambda s, *args: None

            _fallback_keyword_search("python machine learning algorithms")

            # Should have been called with a query
            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args[0]
            query = call_args[1][0]  # The MATCH query parameter
            assert "python" in query or "machine" in query or "learning" in query

    def test_fallback_handles_db_error(self):
        """Test that fallback handles database errors gracefully."""
        with patch("emdx.services.contextual_save.db") as mock_db:
            mock_db.get_connection.side_effect = Exception("DB error")

            result = _fallback_keyword_search("python testing")

            assert result == []


class TestThresholds:
    """Tests for threshold constants."""

    def test_thresholds_are_valid(self):
        """Test that thresholds are in valid range."""
        assert 0 < DUPLICATE_THRESHOLD <= 1
        assert 0 < RELATED_THRESHOLD <= 1
        assert 0 <= NEW_TOPIC_THRESHOLD <= 1

    def test_threshold_ordering(self):
        """Test that thresholds are properly ordered."""
        assert DUPLICATE_THRESHOLD > RELATED_THRESHOLD
        # NEW_TOPIC_THRESHOLD should equal RELATED_THRESHOLD (below related = new)
        assert NEW_TOPIC_THRESHOLD == RELATED_THRESHOLD
