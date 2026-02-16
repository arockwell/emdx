"""Tests for the QA Presenter and related components."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from emdx.ui.qa.qa_presenter import QAEntry, QAPresenter, QASource, QAStateVM


class TestQADataclasses:
    """Tests for QA-related dataclasses."""

    def test_qa_source_creation(self) -> None:
        """Verify QASource dataclass has required fields."""
        source = QASource(doc_id=42, title="Test Document")
        assert source.doc_id == 42
        assert source.title == "Test Document"

    def test_qa_entry_defaults(self) -> None:
        """Verify QAEntry dataclass has correct defaults."""
        entry = QAEntry(question="What is Python?")
        assert entry.question == "What is Python?"
        assert entry.answer == ""
        assert entry.sources == []
        assert entry.method == ""
        assert entry.is_loading is False
        assert entry.error is None
        assert entry.elapsed_ms == 0
        assert isinstance(entry.timestamp, datetime)

    def test_qa_entry_full_fields(self) -> None:
        """Verify QAEntry with all fields set."""
        sources = [QASource(doc_id=1, title="Doc 1"), QASource(doc_id=2, title="Doc 2")]
        entry = QAEntry(
            question="How does authentication work?",
            answer="Authentication uses JWT tokens...",
            sources=sources,
            method="semantic",
            is_loading=False,
            error=None,
            elapsed_ms=450,
        )
        assert entry.question == "How does authentication work?"
        assert entry.answer == "Authentication uses JWT tokens..."
        assert len(entry.sources) == 2
        assert entry.method == "semantic"
        assert entry.elapsed_ms == 450

    def test_qa_state_vm_defaults(self) -> None:
        """Verify QAStateVM dataclass has correct defaults."""
        state = QAStateVM()
        assert state.entries == []
        assert state.is_asking is False
        assert state.has_claude_cli is False
        assert state.has_embeddings is False
        assert state.status_text == ""


class TestQAPresenterInitialization:
    """Tests for QAPresenter initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_claude_cli_available(self) -> None:
        """Test initialization when Claude CLI is available."""
        presenter = QAPresenter()
        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch.object(presenter, "_has_embeddings", return_value=False),
        ):
            await presenter.initialize()

        assert presenter.state.has_claude_cli is True
        assert "Ready" in presenter.state.status_text

    @pytest.mark.asyncio
    async def test_initialize_without_claude_cli(self) -> None:
        """Test initialization when Claude CLI is not available."""
        presenter = QAPresenter()
        with (
            patch("shutil.which", return_value=None),
            patch.object(presenter, "_has_embeddings", return_value=False),
        ):
            await presenter.initialize()

        assert presenter.state.has_claude_cli is False
        assert "Claude CLI not found" in presenter.state.status_text

    @pytest.mark.asyncio
    async def test_initialize_with_embeddings(self) -> None:
        """Test initialization when embeddings are available."""
        presenter = QAPresenter()
        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch.object(presenter, "_has_embeddings", return_value=True),
        ):
            await presenter.initialize()

        assert presenter.state.has_embeddings is True
        assert "semantic" in presenter.state.status_text

    @pytest.mark.asyncio
    async def test_initialize_calls_on_state_update(self) -> None:
        """Test that initialization triggers state update callback."""
        mock_callback = AsyncMock()
        presenter = QAPresenter(on_state_update=mock_callback)
        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch.object(presenter, "_has_embeddings", return_value=False),
        ):
            await presenter.initialize()

        mock_callback.assert_called()
        # Callback should receive the state
        assert mock_callback.call_args[0][0] == presenter.state


class TestQAPresenterEmptyQuestion:
    """Tests for empty question handling."""

    @pytest.mark.asyncio
    async def test_ask_empty_string_returns_early(self) -> None:
        """Empty string question should return immediately without processing."""
        presenter = QAPresenter()
        initial_entry_count = len(presenter.state.entries)

        await presenter.ask("")

        # No entry should be added
        assert len(presenter.state.entries) == initial_entry_count

    @pytest.mark.asyncio
    async def test_ask_whitespace_only_returns_early(self) -> None:
        """Whitespace-only question should return immediately."""
        presenter = QAPresenter()
        initial_entry_count = len(presenter.state.entries)

        await presenter.ask("   \t\n   ")

        # No entry should be added
        assert len(presenter.state.entries) == initial_entry_count

    @pytest.mark.asyncio
    async def test_ask_empty_does_not_set_is_asking(self) -> None:
        """Empty question should not set is_asking flag."""
        presenter = QAPresenter()
        presenter._state.is_asking = False

        await presenter.ask("")

        assert presenter.state.is_asking is False


class TestQAPresenterCLIMissing:
    """Tests for handling when Claude CLI is missing."""

    @pytest.mark.asyncio
    async def test_ask_without_cli_adds_error_entry(self) -> None:
        """When Claude CLI is missing, asking should add an error entry."""
        presenter = QAPresenter()
        presenter._state.has_claude_cli = False

        await presenter.ask("What is Python?")

        # Should add an entry with error
        assert len(presenter.state.entries) == 1
        entry = presenter.state.entries[0]
        assert entry.question == "What is Python?"
        assert entry.error is not None
        assert "claude cli" in entry.error.lower()

    @pytest.mark.asyncio
    async def test_ask_without_cli_triggers_state_update(self) -> None:
        """When Claude CLI is missing, should still trigger state update."""
        mock_callback = AsyncMock()
        presenter = QAPresenter(on_state_update=mock_callback)
        presenter._state.has_claude_cli = False

        await presenter.ask("Test question")

        mock_callback.assert_called()


class TestQAPresenterIsAskingFlag:
    """Tests for is_asking flag preventing concurrent calls."""

    @pytest.mark.asyncio
    async def test_is_asking_set_during_question_processing(self) -> None:
        """is_asking should be True while processing a question."""
        presenter = QAPresenter()
        presenter._state.has_claude_cli = True

        is_asking_during_call = None

        async def capture_state(state: QAStateVM) -> None:
            nonlocal is_asking_during_call
            # Capture is_asking on first callback (should be True during processing)
            if is_asking_during_call is None and state.is_asking:
                is_asking_during_call = state.is_asking

        presenter.on_state_update = capture_state

        # Mock the retrieval and streaming to make it complete quickly
        with patch.object(presenter, "_retrieve", return_value=([], "keyword")):
            with patch.object(presenter, "_stream_answer", new_callable=AsyncMock) as mock_stream:
                mock_stream.return_value = "Test answer"
                await presenter.ask("Test question")

        # is_asking should have been True during processing
        assert is_asking_during_call is True
        # But should be False after completion
        assert presenter.state.is_asking is False

    @pytest.mark.asyncio
    async def test_is_asking_cleared_after_completion(self) -> None:
        """is_asking should be False after question completes."""
        presenter = QAPresenter()
        presenter._state.has_claude_cli = True

        with patch.object(presenter, "_retrieve", return_value=([], "keyword")):
            with patch.object(presenter, "_stream_answer", new_callable=AsyncMock) as mock_stream:
                mock_stream.return_value = "Test answer"
                await presenter.ask("Test question")

        assert presenter.state.is_asking is False

    @pytest.mark.asyncio
    async def test_is_asking_cleared_on_error(self) -> None:
        """is_asking should be False even when an error occurs."""
        presenter = QAPresenter()
        presenter._state.has_claude_cli = True

        with patch.object(presenter, "_retrieve", side_effect=Exception("Test error")):
            await presenter.ask("Test question")

        assert presenter.state.is_asking is False
        # Entry should have an error
        assert len(presenter.state.entries) == 1
        assert presenter.state.entries[0].error is not None


class TestQAPresenterRetrieve:
    """Tests for _retrieve method with keyword and hybrid search."""

    def test_retrieve_keyword_search(self) -> None:
        """Test keyword retrieval via FTS."""
        presenter = QAPresenter()

        # Mock database connection and query
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "Python Guide", "Content about Python"),
            (2, "Testing Guide", "Content about testing"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # Force keyword-only by mocking _has_embeddings to return False
        with patch.object(presenter, "_has_embeddings", return_value=False):
            with patch.object(presenter, "_retrieve_keyword") as mock_kw:
                mock_kw.return_value = [
                    (1, "Python Guide", "Content about Python"),
                    (2, "Testing Guide", "Content about testing"),
                ]
                # We need to patch db where it's used (inside _retrieve)
                with patch("emdx.database.db") as mock_db:
                    mock_db.get_connection.return_value = mock_conn
                    docs, method = presenter._retrieve("Python testing")

        assert method == "keyword"

    def test_retrieve_with_doc_reference(self) -> None:
        """Test retrieval with explicit document reference (#42)."""
        presenter = QAPresenter()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Simulate finding the referenced document
        mock_cursor.fetchone.return_value = (42, "Referenced Doc", "Content of doc 42")
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("emdx.database.db") as mock_db:
            mock_db.get_connection.return_value = mock_conn

            with patch.object(presenter, "_has_embeddings", return_value=False):
                with patch.object(presenter, "_retrieve_keyword", return_value=[]):
                    docs, method = presenter._retrieve("Explain #42")

        # Should include the referenced document
        assert len(docs) >= 1
        assert any(d[0] == 42 for d in docs)

    def test_retrieve_semantic_when_embeddings_available(self) -> None:
        """Test that semantic retrieval is used when embeddings are available."""
        presenter = QAPresenter()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No doc refs
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # Set up mock for semantic retrieval
        with patch("emdx.database.db") as mock_db:
            mock_db.get_connection.return_value = mock_conn

            with patch.object(presenter, "_has_embeddings", return_value=True):
                with patch.object(presenter, "_retrieve_semantic") as mock_sem:
                    mock_sem.return_value = [
                        (1, "Semantic Match", "Content found via embeddings"),
                    ]
                    docs, method = presenter._retrieve("What is the architecture?")

        assert method == "semantic"
        mock_sem.assert_called()

    def test_retrieve_falls_back_to_keyword_on_semantic_failure(self) -> None:
        """Test fallback to keyword when semantic retrieval returns empty."""
        presenter = QAPresenter()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # Semantic returns empty, should fall back to keyword
        with patch("emdx.database.db") as mock_db:
            mock_db.get_connection.return_value = mock_conn

            with patch.object(presenter, "_has_embeddings", return_value=True):
                with patch.object(presenter, "_retrieve_semantic", return_value=[]):
                    with patch.object(presenter, "_retrieve_keyword") as mock_kw:
                        mock_kw.return_value = [
                            (1, "Keyword Match", "Content found via FTS"),
                        ]
                        docs, method = presenter._retrieve("test query")

        # Falls back to keyword
        mock_kw.assert_called()

    def test_retrieve_keyword_method_empty_terms(self) -> None:
        """Test _retrieve_keyword handles empty terms gracefully."""
        presenter = QAPresenter()

        # Query with only special characters should result in empty terms
        result = presenter._retrieve_keyword("!@#$%^&*()", 10)

        assert result == []

    def test_retrieve_deduplicates_results(self) -> None:
        """Test that _retrieve deduplicates documents by ID."""
        presenter = QAPresenter()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Same doc ID referenced twice
        mock_cursor.fetchone.side_effect = [
            (42, "Doc 42", "Content"),
            (42, "Doc 42", "Content"),  # Duplicate
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("emdx.database.db") as mock_db:
            mock_db.get_connection.return_value = mock_conn

            with patch.object(presenter, "_has_embeddings", return_value=False):
                with patch.object(presenter, "_retrieve_keyword", return_value=[]):
                    docs, method = presenter._retrieve("Tell me about #42 and #42")

        # Should only have one entry for doc 42
        doc_ids = [d[0] for d in docs]
        assert doc_ids.count(42) == 1


class TestQAPresenterBuildContext:
    """Tests for _build_context method."""

    def test_build_context_formats_documents(self) -> None:
        """Test that _build_context formats documents correctly."""
        presenter = QAPresenter()
        docs = [
            (1, "First Doc", "Content of first document"),
            (2, "Second Doc", "Content of second document"),
        ]

        context = presenter._build_context(docs)

        assert "# Document #1: First Doc" in context
        assert "Content of first document" in context
        assert "# Document #2: Second Doc" in context
        assert "Content of second document" in context

    def test_build_context_truncates_long_content(self) -> None:
        """Test that _build_context truncates content over 3000 chars."""
        presenter = QAPresenter()
        long_content = "x" * 5000
        docs = [(1, "Long Doc", long_content)]

        context = presenter._build_context(docs)

        # Should be truncated to 3000
        assert len(context) < len(long_content) + 100

    def test_build_context_separates_documents(self) -> None:
        """Test that documents are separated with dividers."""
        presenter = QAPresenter()
        docs = [
            (1, "Doc 1", "Content 1"),
            (2, "Doc 2", "Content 2"),
        ]

        context = presenter._build_context(docs)

        assert "---" in context


class TestQAPresenterCancel:
    """Tests for cancel functionality."""

    def test_cancel_sets_event(self) -> None:
        """Test that cancel() sets the cancel event."""
        presenter = QAPresenter()
        presenter._cancel_event = asyncio.Event()

        presenter.cancel()

        assert presenter._cancel_event.is_set()

    def test_cancel_does_nothing_when_no_event(self) -> None:
        """Test that cancel() is safe when no event exists."""
        presenter = QAPresenter()
        presenter._cancel_event = None

        # Should not raise
        presenter.cancel()


class TestQAPresenterClearHistory:
    """Tests for clear_history functionality."""

    def test_clear_history_removes_entries(self) -> None:
        """Test that clear_history removes all entries."""
        presenter = QAPresenter()
        presenter._state.entries = [
            QAEntry(question="Q1", answer="A1"),
            QAEntry(question="Q2", answer="A2"),
        ]

        presenter.clear_history()

        assert len(presenter.state.entries) == 0

    def test_clear_history_updates_status(self) -> None:
        """Test that clear_history updates status text."""
        presenter = QAPresenter()

        presenter.clear_history()

        assert "cleared" in presenter.state.status_text.lower()


class TestQAPresenterEntryCount:
    """Tests for get_entry_count method."""

    def test_get_entry_count_returns_correct_count(self) -> None:
        """Test get_entry_count returns correct number of entries."""
        presenter = QAPresenter()
        presenter._state.entries = [
            QAEntry(question="Q1"),
            QAEntry(question="Q2"),
            QAEntry(question="Q3"),
        ]

        assert presenter.get_entry_count() == 3

    def test_get_entry_count_returns_zero_when_empty(self) -> None:
        """Test get_entry_count returns 0 for empty entries."""
        presenter = QAPresenter()

        assert presenter.get_entry_count() == 0


class TestQAPresenterStateProperty:
    """Tests for state property."""

    def test_state_returns_internal_state(self) -> None:
        """Test that state property returns the internal state object."""
        presenter = QAPresenter()
        presenter._state.is_asking = True
        presenter._state.has_claude_cli = True

        state = presenter.state

        assert state.is_asking is True
        assert state.has_claude_cli is True


class TestQAPresenterStreamAnswer:
    """Tests for _stream_answer method."""

    @pytest.mark.asyncio
    async def test_stream_answer_calls_claude_cli(self) -> None:
        """Test that _stream_answer calls the Claude CLI via _execute_claude_prompt."""
        presenter = QAPresenter()

        with patch(
            "emdx.services.ask_service._execute_claude_prompt",
            return_value="Hello world",
        ):
            result = await presenter._stream_answer("Test question", "Test context")

        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_stream_answer_calls_chunk_callback(self) -> None:
        """Test that _stream_answer calls the on_answer_chunk callback."""
        chunks_received: list[str] = []

        async def capture_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        presenter = QAPresenter(on_answer_chunk=capture_chunk)

        with patch(
            "emdx.services.ask_service._execute_claude_prompt",
            return_value="Test answer",
        ):
            await presenter._stream_answer("Question", "Context")

        # Should have received the answer as a single chunk
        assert len(chunks_received) == 1
        assert chunks_received[0] == "Test answer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
