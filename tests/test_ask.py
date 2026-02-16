"""Tests for the AI ask command and AskService."""

from emdx.services.ask_service import CONTEXT_BUDGET_CHARS, Answer, AskService


class TestAnswerDataclass:
    """Tests for the Answer dataclass."""

    def test_answer_has_all_fields(self) -> None:
        """Verify Answer dataclass has all required fields."""
        answer = Answer(
            text="Test answer",
            sources=[1, 2, 3],
            source_titles=[(1, "Doc 1"), (2, "Doc 2"), (3, "Doc 3")],
            method="keyword",
            context_size=500,
            confidence="high",
        )
        assert answer.text == "Test answer"
        assert answer.sources == [1, 2, 3]
        assert answer.source_titles == [(1, "Doc 1"), (2, "Doc 2"), (3, "Doc 3")]
        assert answer.method == "keyword"
        assert answer.context_size == 500
        assert answer.confidence == "high"


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    def test_high_confidence_with_3_or_more_sources(self) -> None:
        """3+ sources should yield high confidence."""
        service = AskService()
        assert service._calculate_confidence(3) == "high"
        assert service._calculate_confidence(5) == "high"
        assert service._calculate_confidence(10) == "high"

    def test_medium_confidence_with_1_or_2_sources(self) -> None:
        """1-2 sources should yield medium confidence."""
        service = AskService()
        assert service._calculate_confidence(1) == "medium"
        assert service._calculate_confidence(2) == "medium"

    def test_low_confidence_with_no_sources(self) -> None:
        """0 sources should yield low confidence."""
        service = AskService()
        assert service._calculate_confidence(0) == "low"


class TestFilterHelper:
    """Tests for _get_filtered_doc_ids helper."""

    def test_no_filters_returns_none(self) -> None:
        """No filters should return None (all docs match)."""
        service = AskService()
        result = service._get_filtered_doc_ids(tags=None, recent_days=None)
        assert result is None

    def test_tag_filter_normalizes_aliases(self) -> None:
        """Text aliases should be normalized to emojis."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        # Create a doc with emoji tag
        doc_id = save_document("Test Doc", "Content", None)
        add_tags_to_document(doc_id, ["🎯"])  # gameplan emoji

        service = AskService()
        # Search using text alias "gameplan" should find the doc
        result = service._get_filtered_doc_ids(tags="gameplan", recent_days=None)
        assert result is not None
        assert doc_id in result

    def test_recent_days_filter(self) -> None:
        """Recent days filter should work."""
        from emdx.models.documents import save_document

        # Create a recent doc
        doc_id = save_document("Recent Doc", "Content", None)

        service = AskService()
        # Recent docs should be found
        result = service._get_filtered_doc_ids(tags=None, recent_days=7)
        assert result is not None
        assert doc_id in result

    def test_combined_tag_and_recent_filter(self) -> None:
        """Tag and recent filters should work together."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        # Create a recent doc with tags
        doc_id = save_document("Tagged Recent Doc", "Content", None)
        add_tags_to_document(doc_id, ["🎯"])

        service = AskService()
        result = service._get_filtered_doc_ids(tags="gameplan", recent_days=7)
        assert result is not None
        assert doc_id in result


class TestContextBudget:
    """Tests for context budget enforcement."""

    def test_context_budget_constant_defined(self) -> None:
        """Context budget constant should be ~12000 chars."""
        assert CONTEXT_BUDGET_CHARS == 12000

    def test_generate_answer_respects_budget(self) -> None:
        """_generate_answer should not exceed context budget."""
        from unittest.mock import patch

        service = AskService()

        # Create docs that would exceed budget if not truncated
        large_content = "x" * 5000  # 5000 chars each
        docs: list[tuple[int, str, str]] = [
            (1, "Doc 1", large_content),
            (2, "Doc 2", large_content),
            (3, "Doc 3", large_content),
            (4, "Doc 4", large_content),
        ]

        # Mock the Claude CLI call
        with patch(
            "emdx.services.ask_service._execute_claude_prompt",
            return_value="Test answer",
        ):
            text, context_size = service._generate_answer("test question", docs)

        # Context size should not exceed budget
        assert context_size <= CONTEXT_BUDGET_CHARS + 100  # Small margin for separators

    def test_empty_docs_returns_helpful_message(self) -> None:
        """Empty docs should return a helpful message."""
        service = AskService()
        text, context_size = service._generate_answer("question", [])
        assert "couldn't find" in text.lower()
        assert context_size == 0


class TestRetrieveWithFilters:
    """Tests for retrieval methods with filters."""

    def test_keyword_retrieval_with_tag_filter(self) -> None:
        """Keyword retrieval should respect tag filters."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        # Create docs with different tags
        doc1 = save_document("Security Doc", "authentication content", None)
        add_tags_to_document(doc1, ["🔐"])  # security-ish

        doc2 = save_document("General Doc", "authentication content", None)
        # No tags

        service = AskService()
        # Without filter, both should be found
        docs_all, _ = service._retrieve_keyword("authentication", 10, None, tags=None)
        doc_ids_all = [d[0] for d in docs_all]
        assert doc1 in doc_ids_all
        assert doc2 in doc_ids_all

    def test_keyword_retrieval_with_recent_filter(self) -> None:
        """Keyword retrieval should respect recent days filter."""
        from emdx.models.documents import save_document

        # Create a recent doc
        doc_id = save_document("Test Doc", "search content here", None)

        service = AskService()
        docs, _ = service._retrieve_keyword("search", 10, None, recent_days=7)
        doc_ids = [d[0] for d in docs]
        assert doc_id in doc_ids


class TestSourceTitles:
    """Tests for source title extraction."""

    def test_source_titles_structure(self) -> None:
        """Source titles should be list of (id, title) tuples matching sources."""
        from unittest.mock import patch

        from emdx.models.documents import save_document

        # Create test docs with unique content
        unique_content = "xyzzy_unique_test_content_98765"
        save_document("Test Source Title Doc", unique_content, None)

        service = AskService()

        # Mock the Claude CLI call
        with patch(
            "emdx.services.ask_service._execute_claude_prompt",
            return_value="Test answer",
        ):
            result = service.ask(f"question about {unique_content}", limit=5, force_keyword=True)

        # Verify structure: source_titles should match sources
        assert len(result.source_titles) == len(result.sources)

        # Each source_title entry should be a (doc_id, title) tuple
        for doc_id, title in result.source_titles:
            assert isinstance(doc_id, int)
            assert isinstance(title, str)
            assert doc_id in result.sources
