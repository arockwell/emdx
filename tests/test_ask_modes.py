"""Tests for ask service modes (think, challenge, debug, cite) and confidence scoring."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from emdx.services.ask_service import (
    SYSTEM_PROMPT_ANSWER,
    SYSTEM_PROMPT_CHALLENGE,
    SYSTEM_PROMPT_DEBUG,
    SYSTEM_PROMPT_THINK,
    Answer,
    AskMode,
    AskService,
    ConfidenceSignals,
    _build_chunk_context,
    _build_doc_context,
    _calculate_query_term_coverage,
    _calculate_topic_coherence,
    _extract_cited_ids,
)

# ── AskMode enum ────────────────────────────────────────────────────────


class TestAskMode:
    """Tests for the AskMode enum."""

    def test_all_modes_defined(self) -> None:
        """All 4 modes should be defined."""
        assert AskMode.ANSWER.value == "answer"
        assert AskMode.THINK.value == "think"
        assert AskMode.CHALLENGE.value == "challenge"
        assert AskMode.DEBUG.value == "debug"

    def test_mode_count(self) -> None:
        """Should have exactly 4 modes."""
        assert len(AskMode) == 4


# ── System prompts ──────────────────────────────────────────────────────


class TestSystemPrompts:
    """Tests for mode-specific system prompts."""

    def test_answer_prompt_mentions_documents(self) -> None:
        """Answer prompt should mention citing documents."""
        assert "Document #42" in SYSTEM_PROMPT_ANSWER

    def test_think_prompt_has_for_and_against(self) -> None:
        """Think prompt should instruct for/against analysis."""
        assert "Evidence For" in SYSTEM_PROMPT_THINK
        assert "Evidence Against" in SYSTEM_PROMPT_THINK
        assert "Synthesis" in SYSTEM_PROMPT_THINK
        assert "Counterarguments" in SYSTEM_PROMPT_THINK

    def test_challenge_prompt_is_adversarial(self) -> None:
        """Challenge prompt should be devil's advocate."""
        assert "devil's advocate" in SYSTEM_PROMPT_CHALLENGE
        assert "Contradicting Evidence" in SYSTEM_PROMPT_CHALLENGE
        assert "Past Failures" in SYSTEM_PROMPT_CHALLENGE
        assert "Strongest Counterargument" in SYSTEM_PROMPT_CHALLENGE

    def test_debug_prompt_is_socratic(self) -> None:
        """Debug prompt should be a Socratic debugging partner."""
        assert "Socratic" in SYSTEM_PROMPT_DEBUG
        assert "Diagnostic Questions" in SYSTEM_PROMPT_DEBUG
        assert "Past Incidents" in SYSTEM_PROMPT_DEBUG
        assert "Investigation Steps" in SYSTEM_PROMPT_DEBUG


# ── ConfidenceSignals ───────────────────────────────────────────────────


class TestConfidenceSignals:
    """Tests for multi-signal confidence scoring."""

    def test_high_confidence(self) -> None:
        """Strong signals should produce high confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.85,
            retrieval_score_spread=0.05,
            source_count=8,
            query_term_coverage=0.9,
            topic_coherence=0.7,
            recency_score=0.8,
        )
        assert signals.level == "high"
        assert signals.composite_score >= 0.7

    def test_low_confidence(self) -> None:
        """Weak signals should produce low confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.2,
            retrieval_score_spread=0.4,
            source_count=1,
            query_term_coverage=0.1,
            topic_coherence=0.1,
            recency_score=0.1,
        )
        assert signals.level in ("low", "insufficient")
        assert signals.composite_score < 0.4

    def test_insufficient_confidence(self) -> None:
        """Zero signals should produce insufficient confidence."""
        signals = ConfidenceSignals()
        assert signals.level == "insufficient"
        assert signals.composite_score < 0.2

    def test_medium_confidence(self) -> None:
        """Moderate signals should produce medium confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.5,
            retrieval_score_spread=0.15,
            source_count=3,
            query_term_coverage=0.5,
            topic_coherence=0.4,
            recency_score=0.5,
        )
        assert signals.level == "medium"
        assert 0.4 <= signals.composite_score < 0.7

    def test_composite_score_bounded(self) -> None:
        """Composite score should be between 0 and 1."""
        # Test with extreme values
        signals_max = ConfidenceSignals(
            retrieval_score_mean=1.0,
            retrieval_score_spread=0.0,
            source_count=100,
            query_term_coverage=1.0,
            topic_coherence=1.0,
            recency_score=1.0,
        )
        assert 0.0 <= signals_max.composite_score <= 1.0

        signals_min = ConfidenceSignals(
            retrieval_score_mean=0.0,
            retrieval_score_spread=1.0,
            source_count=0,
            query_term_coverage=0.0,
            topic_coherence=0.0,
            recency_score=0.0,
        )
        assert 0.0 <= signals_min.composite_score <= 1.0


# ── Query term coverage ────────────────────────────────────────────────


class TestQueryTermCoverage:
    """Tests for query term coverage calculation."""

    def test_full_coverage(self) -> None:
        """All query terms in docs should give 1.0."""
        docs = [
            (1, "Auth Guide", "authentication patterns for security"),
        ]
        coverage = _calculate_query_term_coverage("authentication security patterns", docs)
        assert coverage == 1.0

    def test_partial_coverage(self) -> None:
        """Some terms missing should give < 1.0."""
        docs = [
            (1, "Auth Guide", "authentication only"),
        ]
        coverage = _calculate_query_term_coverage("authentication security patterns", docs)
        assert 0.0 < coverage < 1.0

    def test_no_coverage(self) -> None:
        """No matching terms should give 0.0."""
        docs = [
            (1, "Cooking Guide", "pasta recipes and ingredients"),
        ]
        coverage = _calculate_query_term_coverage("authentication security patterns", docs)
        assert coverage == 0.0

    def test_stop_words_ignored(self) -> None:
        """Stop words in query should be filtered out."""
        docs = [(1, "Test", "content")]
        # Query is only stop words
        coverage = _calculate_query_term_coverage("the is a an for", docs)
        assert coverage == 1.0  # Vacuously true


# ── Topic coherence ────────────────────────────────────────────────────


class TestTopicCoherence:
    """Tests for topic coherence calculation."""

    def test_single_doc_is_coherent(self) -> None:
        """Single doc should be perfectly coherent."""
        docs = [(1, "Auth", "authentication guide")]
        assert _calculate_topic_coherence(docs) == 1.0

    def test_similar_docs_are_coherent(self) -> None:
        """Similar docs should have high coherence."""
        docs = [
            (1, "Auth Guide", "authentication patterns"),
            (2, "Auth Patterns", "authentication best practices"),
        ]
        coherence = _calculate_topic_coherence(docs)
        assert coherence > 0.3

    def test_dissimilar_docs_low_coherence(self) -> None:
        """Unrelated docs should have low coherence."""
        docs = [
            (1, "Auth Guide", "authentication patterns"),
            (2, "Cooking Guide", "pasta recipes ingredients"),
        ]
        coherence = _calculate_topic_coherence(docs)
        assert coherence < 0.3

    def test_empty_docs_edge_case(self) -> None:
        """Empty/single docs list should return 1.0 (vacuously coherent)."""
        assert _calculate_topic_coherence([]) == 1.0


# ── Citation extraction ────────────────────────────────────────────────


class TestCitationExtraction:
    """Tests for extracting [#ID] citations from text."""

    def test_basic_extraction(self) -> None:
        """Should extract [#ID] patterns."""
        text = "According to [#42], the system uses auth. See also [#13]."
        valid_ids = {42, 13, 99}
        cited = _extract_cited_ids(text, valid_ids)
        assert cited == [42, 13]

    def test_filters_invalid_ids(self) -> None:
        """Should filter out IDs not in the valid set."""
        text = "See [#42] and [#999] for details."
        valid_ids = {42}
        cited = _extract_cited_ids(text, valid_ids)
        assert cited == [42]

    def test_deduplicates(self) -> None:
        """Should not return duplicate IDs."""
        text = "[#42] shows X. [#42] also shows Y."
        valid_ids = {42}
        cited = _extract_cited_ids(text, valid_ids)
        assert cited == [42]

    def test_no_citations(self) -> None:
        """Text without citations should return empty list."""
        text = "No citations here."
        cited = _extract_cited_ids(text, {1, 2, 3})
        assert cited == []

    def test_preserves_order(self) -> None:
        """Citations should be in order of appearance."""
        text = "[#5] first, then [#2], then [#8]."
        valid_ids = {2, 5, 8}
        cited = _extract_cited_ids(text, valid_ids)
        assert cited == [5, 2, 8]


# ── Context builders ───────────────────────────────────────────────────


class TestBuildDocContext:
    """Tests for document context builder."""

    def test_basic_context(self) -> None:
        """Should build context from docs."""
        docs = [
            (1, "Doc One", "content one"),
            (2, "Doc Two", "content two"),
        ]
        context, size = _build_doc_context(docs, 12000)
        assert "Document #1" in context
        assert "Document #2" in context
        assert "content one" in context
        assert size > 0

    def test_respects_budget(self) -> None:
        """Should not exceed budget."""
        large_content = "x" * 5000
        docs = [
            (1, "Doc 1", large_content),
            (2, "Doc 2", large_content),
            (3, "Doc 3", large_content),
            (4, "Doc 4", large_content),
        ]
        context, size = _build_doc_context(docs, 12000)
        assert size <= 12100  # Small margin for separators


class TestBuildChunkContext:
    """Tests for chunk context builder."""

    def test_basic_chunk_context(self) -> None:
        """Should build context from chunks."""
        mock_chunk = MagicMock()
        mock_chunk.doc_id = 42
        mock_chunk.display_heading = '§"Auth"'
        mock_chunk.title = "Auth Guide"
        mock_chunk.chunk_text = "auth implementation details"

        chunks: list[Any] = [mock_chunk]
        docs = [(42, "Auth Guide", "full auth content")]

        context, size = _build_chunk_context(chunks, docs, 12000)
        assert "[#42]" in context
        assert "auth implementation details" in context

    def test_adds_uncovered_docs(self) -> None:
        """Should add doc summaries for docs without chunks."""
        chunks: list[Any] = []
        docs = [(42, "Auth Guide", "auth content here")]

        context, size = _build_chunk_context(chunks, docs, 12000)
        assert "[#42]" in context
        assert "Auth Guide" in context


# ── Answer dataclass ───────────────────────────────────────────────────


class TestAnswerDataclassExtended:
    """Tests for extended Answer dataclass fields."""

    def test_answer_has_mode_field(self) -> None:
        """Answer should include mode field."""
        answer = Answer(
            text="Test",
            sources=[1],
            source_titles=[(1, "Doc")],
            method="keyword",
            context_size=100,
            confidence="high",
            mode=AskMode.THINK,
        )
        assert answer.mode == AskMode.THINK

    def test_answer_has_confidence_signals(self) -> None:
        """Answer should include confidence signals."""
        signals = ConfidenceSignals(source_count=3)
        answer = Answer(
            text="Test",
            sources=[1],
            source_titles=[(1, "Doc")],
            method="keyword",
            context_size=100,
            confidence="high",
            confidence_signals=signals,
        )
        assert answer.confidence_signals is not None
        assert answer.confidence_signals.source_count == 3

    def test_answer_has_cited_ids(self) -> None:
        """Answer should include cited IDs."""
        answer = Answer(
            text="See [#1] and [#2]",
            sources=[1, 2],
            source_titles=[(1, "A"), (2, "B")],
            method="keyword",
            context_size=100,
            confidence="high",
            cited_ids=[1, 2],
        )
        assert answer.cited_ids == [1, 2]

    def test_answer_defaults(self) -> None:
        """Answer should have sensible defaults for new fields."""
        answer = Answer(
            text="Test",
            sources=[1],
            source_titles=[(1, "Doc")],
            method="keyword",
            context_size=100,
            confidence="high",
        )
        assert answer.mode == AskMode.ANSWER
        assert answer.confidence_signals is None
        assert answer.cited_ids == []


# ── AskService.ask() with modes ────────────────────────────────────────


class TestAskServiceModes:
    """Tests for AskService.ask() with different modes."""

    def test_ask_with_think_mode(self) -> None:
        """Think mode should use broader retrieval and think prompt."""
        from emdx.models.documents import save_document

        content = "unique_think_test_content_abc123"
        save_document("Think Test", content, None)

        service = AskService()

        with (
            patch(
                "emdx.services.ask_service._has_claude_cli",
                return_value=True,
            ),
            patch(
                "emdx.services.ask_service._execute_claude_prompt",
                return_value="## Evidence For\n- Point [#1]",
            ) as mock_prompt,
        ):
            result = service.ask(
                f"should I do X {content}",
                limit=5,
                force_keyword=True,
                mode=AskMode.THINK,
            )

        assert result.mode == AskMode.THINK
        # Think mode should use the think system prompt
        call_args = mock_prompt.call_args
        system_prompt_used = call_args.kwargs.get(
            "system_prompt", call_args.args[0] if call_args.args else ""
        )
        assert "deliberative analyst" in system_prompt_used

    def test_ask_with_debug_mode(self) -> None:
        """Debug mode should use debug prompt."""
        from emdx.models.documents import save_document

        content = "unique_debug_test_error_xyz789"
        save_document("Debug Test", content, None)

        service = AskService()

        with (
            patch(
                "emdx.services.ask_service._has_claude_cli",
                return_value=True,
            ),
            patch(
                "emdx.services.ask_service._execute_claude_prompt",
                return_value="## Diagnostic Questions\n1. Check logs",
            ) as mock_prompt,
        ):
            result = service.ask(
                f"TUI freezes {content}",
                limit=5,
                force_keyword=True,
                mode=AskMode.DEBUG,
            )

        assert result.mode == AskMode.DEBUG
        call_args = mock_prompt.call_args
        system_prompt_used = call_args.kwargs.get(
            "system_prompt", call_args.args[0] if call_args.args else ""
        )
        assert "Socratic" in system_prompt_used

    def test_ask_with_cite_mode(self) -> None:
        """Cite mode should add citation prompt."""
        from emdx.models.documents import save_document

        content = "unique_cite_test_content_qwe456"
        save_document("Cite Test", content, None)

        service = AskService()

        with (
            patch(
                "emdx.services.ask_service._has_claude_cli",
                return_value=True,
            ),
            patch(
                "emdx.services.ask_service._execute_claude_prompt",
                return_value="Auth works via [#1] tokens",
            ) as mock_prompt,
        ):
            result = service.ask(
                f"how does auth work {content}",
                limit=5,
                force_keyword=True,
                cite=True,
            )

        # Citation prompt should be appended
        call_args = mock_prompt.call_args
        system_prompt_used = call_args.kwargs.get(
            "system_prompt", call_args.args[0] if call_args.args else ""
        )
        assert "CITATION REQUIREMENT" in system_prompt_used
        assert result.mode == AskMode.ANSWER

    def test_ask_default_mode(self) -> None:
        """Default mode should be ANSWER."""
        from emdx.models.documents import save_document

        content = "unique_default_test_content_rty098"
        save_document("Default Test", content, None)

        service = AskService()

        with (
            patch(
                "emdx.services.ask_service._has_claude_cli",
                return_value=True,
            ),
            patch(
                "emdx.services.ask_service._execute_claude_prompt",
                return_value="Test answer",
            ),
        ):
            result = service.ask(
                f"question about {content}",
                limit=5,
                force_keyword=True,
            )

        assert result.mode == AskMode.ANSWER


# ── Confidence signals integration ─────────────────────────────────────


class TestConfidenceSignalsIntegration:
    """Tests for confidence signals in ask() flow."""

    def test_ask_returns_confidence_signals(self) -> None:
        """ask() should return ConfidenceSignals object."""
        from emdx.models.documents import save_document

        content = "unique_conf_test_content_mno321"
        save_document("Conf Test", content, None)

        service = AskService()

        with (
            patch(
                "emdx.services.ask_service._has_claude_cli",
                return_value=True,
            ),
            patch(
                "emdx.services.ask_service._execute_claude_prompt",
                return_value="Test answer",
            ),
        ):
            result = service.ask(
                f"question about {content}",
                limit=5,
                force_keyword=True,
            )

        assert result.confidence_signals is not None
        assert result.confidence_signals.source_count >= 1
        assert result.confidence in (
            "high",
            "medium",
            "low",
            "insufficient",
        )

    def test_zero_sources_gives_insufficient_confidence(self) -> None:
        """Zero sources should yield insufficient confidence signals."""
        service = AskService()
        # Directly test the signals calculation with no docs
        signals = service._calculate_confidence_signals("nonexistent query", [], "keyword")
        assert signals.source_count == 0
        assert signals.level == "insufficient"


# ── Legacy compatibility ───────────────────────────────────────────────


class TestLegacyCompatibility:
    """Tests that legacy _calculate_confidence still works."""

    def test_legacy_confidence_high(self) -> None:
        """Legacy method should still return high for 3+ sources."""
        service = AskService()
        assert service._calculate_confidence(3) == "high"
        assert service._calculate_confidence(10) == "high"

    def test_legacy_confidence_medium(self) -> None:
        """Legacy method should still return medium for 1-2."""
        service = AskService()
        assert service._calculate_confidence(1) == "medium"
        assert service._calculate_confidence(2) == "medium"

    def test_legacy_confidence_low(self) -> None:
        """Legacy method should still return low for 0."""
        service = AskService()
        assert service._calculate_confidence(0) == "low"


# ── CLI flag resolution ────────────────────────────────────────────────


class TestResolveModeFlags:
    """Tests for _resolve_ask_mode in core.py."""

    def test_ask_returns_answer_mode(self) -> None:
        """--ask should return ANSWER mode."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=True, think=False, challenge=False, debug=False, cite=False)
        assert result == AskMode.ANSWER

    def test_think_returns_think_mode(self) -> None:
        """--think should return THINK mode."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=False, think=True, challenge=False, debug=False, cite=False)
        assert result == AskMode.THINK

    def test_think_challenge_returns_challenge_mode(self) -> None:
        """--think --challenge should return CHALLENGE mode."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=False, think=True, challenge=True, debug=False, cite=False)
        assert result == AskMode.CHALLENGE

    def test_debug_returns_debug_mode(self) -> None:
        """--debug should return DEBUG mode."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=False, think=False, challenge=False, debug=True, cite=False)
        assert result == AskMode.DEBUG

    def test_cite_alone_returns_answer_mode(self) -> None:
        """--cite alone should auto-enable --ask (ANSWER)."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=False, think=False, challenge=False, debug=False, cite=True)
        assert result == AskMode.ANSWER

    def test_no_flags_returns_none(self) -> None:
        """No AI flags should return None."""
        from emdx.commands.core import _resolve_ask_mode

        result = _resolve_ask_mode(ask=False, think=False, challenge=False, debug=False, cite=False)
        assert result is None

    def test_mutual_exclusion_ask_think(self) -> None:
        """--ask and --think together should raise Exit."""
        import pytest
        from click.exceptions import Exit

        from emdx.commands.core import _resolve_ask_mode

        with pytest.raises(Exit):
            _resolve_ask_mode(ask=True, think=True, challenge=False, debug=False, cite=False)

    def test_mutual_exclusion_ask_debug(self) -> None:
        """--ask and --debug together should raise Exit."""
        import pytest
        from click.exceptions import Exit

        from emdx.commands.core import _resolve_ask_mode

        with pytest.raises(Exit):
            _resolve_ask_mode(ask=True, think=False, challenge=False, debug=True, cite=False)

    def test_challenge_without_think_raises(self) -> None:
        """--challenge without --think should raise Exit."""
        import pytest
        from click.exceptions import Exit

        from emdx.commands.core import _resolve_ask_mode

        with pytest.raises(Exit):
            _resolve_ask_mode(ask=False, think=False, challenge=True, debug=False, cite=False)
