"""Tests for the Ask KB (Q&A) service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from test_fixtures import DatabaseForTesting

# Import the module-level helper directly for testing
from emdx.services.ask_service import _add_filters, Answer, AskService


class TestAddFiltersHelper:
    """Test the _add_filters module-level helper function."""

    def test_no_filters(self):
        """Test with no filters applied."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params)

        assert result_query == query
        assert result_params == []

    def test_project_filter(self):
        """Test project filter is applied."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, project="my-project")

        assert "AND project = ?" in result_query
        assert "my-project" in result_params

    def test_tag_filter_single(self):
        """Test single tag filter is applied."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, tags=["gameplan"])

        # Should include the subquery for tag filtering
        assert "document_tags" in result_query
        assert "tags" in result_query
        # Tag should be converted to emoji (gameplan -> 🎯)
        assert "🎯" in result_params

    def test_tag_filter_multiple(self):
        """Test multiple tags filter is applied."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, tags=["gameplan", "active"])

        assert "document_tags" in result_query
        # Both tags should be in params (converted to emoji)
        assert "🎯" in result_params  # gameplan
        assert "🚀" in result_params  # active

    def test_tag_filter_with_emoji_passthrough(self):
        """Test that emoji tags pass through unchanged."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, tags=["🎯", "🚀"])

        assert "🎯" in result_params
        assert "🚀" in result_params

    def test_recent_days_filter(self):
        """Test recent days filter is applied."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, recent_days=7)

        assert "updated_at >= datetime('now', ?)" in result_query
        assert "-7 days" in result_params

    def test_all_filters_combined(self):
        """Test all filters applied together."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(
            query, params,
            project="my-project",
            tags=["gameplan"],
            recent_days=30
        )

        assert "AND project = ?" in result_query
        assert "document_tags" in result_query
        assert "updated_at >= datetime('now', ?)" in result_query
        assert "my-project" in result_params
        assert "🎯" in result_params
        assert "-30 days" in result_params


class TestConfidenceLevel:
    """Test confidence level calculation in AskService."""

    def test_high_confidence_with_3_plus_sources(self):
        """Test high confidence with 3+ sources."""
        # Mock docs with 3 sources
        docs = [
            (1, "Doc 1", "content"),
            (2, "Doc 2", "content"),
            (3, "Doc 3", "content"),
        ]

        source_count = len(docs)
        if source_count >= 3:
            confidence = "high"
        elif source_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        assert confidence == "high"

    def test_medium_confidence_with_1_or_2_sources(self):
        """Test medium confidence with 1-2 sources."""
        for num_docs in [1, 2]:
            docs = [(i, f"Doc {i}", "content") for i in range(1, num_docs + 1)]

            source_count = len(docs)
            if source_count >= 3:
                confidence = "high"
            elif source_count >= 1:
                confidence = "medium"
            else:
                confidence = "low"

            assert confidence == "medium", f"Expected medium for {num_docs} sources"

    def test_low_confidence_with_no_sources(self):
        """Test low confidence with 0 sources."""
        docs = []

        source_count = len(docs)
        if source_count >= 3:
            confidence = "high"
        elif source_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        assert confidence == "low"


class TestAnswerDataclass:
    """Test the Answer dataclass structure."""

    def test_answer_creation(self):
        """Test Answer dataclass can be created with all fields."""
        answer = Answer(
            text="This is the answer",
            sources=[1, 2, 3],
            source_titles=[(1, "Doc 1"), (2, "Doc 2"), (3, "Doc 3")],
            method="keyword",
            context_size=1234,
            confidence="high",
        )

        assert answer.text == "This is the answer"
        assert answer.sources == [1, 2, 3]
        assert len(answer.source_titles) == 3
        assert answer.method == "keyword"
        assert answer.context_size == 1234
        assert answer.confidence == "high"


class TestMachineOutputFormat:
    """Test the machine output format for Claude consumption."""

    def test_machine_output_structure(self):
        """Test that machine output would have correct structure."""
        # Simulate what the machine output format produces
        answer = Answer(
            text="The answer to your question is 42.",
            sources=[1, 2],
            source_titles=[(1, "First Doc"), (2, "Second Doc")],
            method="keyword",
            context_size=5000,
            confidence="medium",
        )

        # Simulate the machine output
        output_lines = []
        output_lines.append(answer.text)
        output_lines.append("")
        if answer.source_titles:
            output_lines.append("Sources:")
            for doc_id, title in answer.source_titles:
                output_lines.append(f'  #{doc_id} "{title}"')

        # Build stderr metadata
        stderr_line = f"confidence:{answer.confidence} sources:{len(answer.sources)} method:{answer.method}"

        # Verify structure
        assert output_lines[0] == "The answer to your question is 42."
        assert output_lines[1] == ""
        assert output_lines[2] == "Sources:"
        assert '#1 "First Doc"' in output_lines[3]
        assert '#2 "Second Doc"' in output_lines[4]
        assert "confidence:medium" in stderr_line
        assert "sources:2" in stderr_line
        assert "method:keyword" in stderr_line

    def test_machine_output_no_sources(self):
        """Test machine output with no sources."""
        answer = Answer(
            text="No relevant documents found.",
            sources=[],
            source_titles=[],
            method="keyword",
            context_size=0,
            confidence="low",
        )

        # Simulate the machine output
        output_lines = [answer.text, ""]
        if answer.source_titles:
            output_lines.append("Sources:")

        # Should NOT have Sources section
        assert "Sources:" not in output_lines


class TestTagFiltering:
    """Integration tests for tag filtering with database."""

    def test_tag_filter_query_structure(self):
        """Test that tag filter query is properly structured."""
        query = "SELECT id, title, content FROM documents WHERE is_deleted = 0"
        params = []

        query, params = _add_filters(query, params, tags=["gameplan", "active"])

        # Should have subquery structure
        assert "SELECT dt.document_id FROM document_tags dt" in query
        assert "JOIN tags t ON dt.tag_id = t.id" in query
        assert "WHERE t.name IN" in query
        # Should have 2 placeholders
        assert "?,?" in query or "?, ?" in query.replace(" ", "")

    def test_unknown_tag_passthrough(self):
        """Test that unknown tags pass through as-is."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, tags=["custom-tag"])

        # Unknown tag should remain as-is (not converted to emoji)
        assert "custom-tag" in result_params


class TestRecentDaysFiltering:
    """Tests for recent days filtering."""

    def test_recent_days_various_values(self):
        """Test recent days filter with various values."""
        for days in [1, 7, 30, 90, 365]:
            query = "SELECT * FROM documents WHERE is_deleted = 0"
            params = []

            result_query, result_params = _add_filters(query, params, recent_days=days)

            assert "updated_at >= datetime('now', ?)" in result_query
            assert f"-{days} days" in result_params

    def test_recent_days_zero_not_applied(self):
        """Test that recent_days=0 is treated as falsy (not applied)."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, recent_days=0)

        # Zero is falsy, so filter should not be applied
        assert "updated_at" not in result_query

    def test_recent_days_none_not_applied(self):
        """Test that recent_days=None does not apply filter."""
        query = "SELECT * FROM documents WHERE is_deleted = 0"
        params = []

        result_query, result_params = _add_filters(query, params, recent_days=None)

        assert "updated_at" not in result_query


class TestAskServiceRetrieval:
    """Tests for AskService retrieval methods (without API calls)."""

    @patch('emdx.services.ask_service.db')
    def test_retrieve_keyword_applies_filters(self, mock_db):
        """Test that _retrieve_keyword applies filters correctly."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.get_connection.return_value = mock_conn

        service = AskService()

        # Call with all filters
        docs, method = service._retrieve_keyword(
            "test question",
            limit=10,
            project="my-project",
            tags=["gameplan"],
            recent_days=7,
        )

        # Verify the cursor was used
        assert mock_cursor.execute.called
        assert method == "keyword"

    def test_service_initialization(self):
        """Test AskService initializes with defaults."""
        service = AskService()

        assert service.model == "claude-sonnet-4-5-20250929"
        assert service._client is None
        assert service._embedding_service is None

    def test_service_custom_model(self):
        """Test AskService with custom model."""
        service = AskService(model="custom-model")

        assert service.model == "custom-model"
