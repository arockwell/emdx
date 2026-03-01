"""Tests for ask-KB improvements: --tags, --recent-days, and --machine flags."""

from __future__ import annotations

import json
from unittest.mock import patch

from emdx.services.ask_service import (
    Answer,
    AskMode,
    AskService,
    ConfidenceSignals,
)


def _make_answer(
    confidence: str = "high",
    source_count: int = 3,
    mode: AskMode = AskMode.ANSWER,
) -> Answer:
    """Build a mock Answer with the given parameters."""
    source_titles = [(i, f"Doc {i}") for i in range(1, source_count + 1)]
    sources = [s[0] for s in source_titles]
    signals = ConfidenceSignals(
        retrieval_score_mean=0.75,
        retrieval_score_spread=0.1,
        source_count=source_count,
        query_term_coverage=0.8,
        topic_coherence=0.6,
        recency_score=0.5,
    )
    return Answer(
        text="Test answer text",
        sources=sources,
        source_titles=source_titles,
        method="keyword",
        context_size=5000,
        confidence=confidence,
        mode=mode,
        confidence_signals=signals,
    )


# ── --tags filtering ──────────────────────────────────────────────────


class TestAskTagFiltering:
    """Tests for --tags filtering in ask mode."""

    def test_tags_passed_to_ask_service(self) -> None:
        """--tags should be forwarded to AskService.ask()."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ) as mock_ask,
            patch("builtins.print"),
        ):
            _find_ask(
                "what is auth",
                limit=10,
                project=None,
                tags="security,active",
                json_output=True,
            )

        mock_ask.assert_called_once()
        call_kwargs = mock_ask.call_args
        assert call_kwargs.kwargs.get("tags") == "security,active"

    def test_tag_filter_in_service(self) -> None:
        """AskService._get_filtered_doc_ids should filter by tags."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        doc1 = save_document("Tagged Doc", "auth content", None)
        add_tags_to_document(doc1, ["security"])

        doc2 = save_document("Untagged Doc", "auth content", None)

        service = AskService()

        # With security tag filter, only doc1 should match
        result = service._get_filtered_doc_ids(tags="security", recent_days=None)
        assert result is not None
        assert doc1 in result
        assert doc2 not in result

    def test_multiple_tags_require_all(self) -> None:
        """Comma-separated tags should require ALL tags (AND logic)."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        doc1 = save_document("Both Tags", "content", None)
        add_tags_to_document(doc1, ["security", "active"])

        doc2 = save_document("One Tag", "content", None)
        add_tags_to_document(doc2, ["security"])

        service = AskService()
        result = service._get_filtered_doc_ids(tags="security,active", recent_days=None)
        assert result is not None
        assert doc1 in result
        assert doc2 not in result


# ── --recent-days filtering ───────────────────────────────────────────


class TestAskRecentDaysFiltering:
    """Tests for --recent-days filtering in ask mode."""

    def test_recent_days_passed_to_ask_service(self) -> None:
        """--recent-days should be forwarded to AskService.ask()."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ) as mock_ask,
            patch("builtins.print"),
        ):
            _find_ask(
                "what changed recently",
                limit=10,
                project=None,
                tags=None,
                recent_days=7,
                json_output=True,
            )

        mock_ask.assert_called_once()
        assert mock_ask.call_args.kwargs.get("recent_days") == 7

    def test_recent_days_filter_includes_new_docs(self) -> None:
        """Recent docs should be included by recent_days filter."""
        from emdx.models.documents import save_document

        doc_id = save_document("Fresh Doc", "new content", None)

        service = AskService()
        result = service._get_filtered_doc_ids(tags=None, recent_days=7)
        assert result is not None
        assert doc_id in result

    def test_recent_days_keyword_retrieval(self) -> None:
        """Keyword retrieval should respect recent_days filter."""
        from emdx.models.documents import save_document

        doc_id = save_document("Recent Search Doc", "searchable_unique_term_abc", None)

        service = AskService()
        docs, method = service._retrieve_keyword(
            "searchable_unique_term_abc",
            10,
            None,
            recent_days=7,
        )
        doc_ids = [d[0] for d in docs]
        assert doc_id in doc_ids

    def test_combined_tags_and_recent_days(self) -> None:
        """Tags and recent_days filters should work together."""
        from emdx.models.documents import save_document
        from emdx.models.tags import add_tags_to_document

        doc1 = save_document("Tagged Recent", "content", None)
        add_tags_to_document(doc1, ["gameplan"])

        service = AskService()
        result = service._get_filtered_doc_ids(tags="gameplan", recent_days=7)
        assert result is not None
        assert doc1 in result


# ── --machine output format ───────────────────────────────────────────


class TestMachineOutput:
    """Tests for --machine output format."""

    def test_machine_output_format(self) -> None:
        """--machine should produce structured plain text output."""
        from emdx.commands.core import _find_ask

        answer = _make_answer(confidence="high", source_count=3)

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ),
            patch("builtins.print") as mock_print,
        ):
            _find_ask(
                "summarize auth",
                limit=10,
                project=None,
                tags=None,
                machine=True,
            )

        # Collect all stdout calls (file=None or no file kwarg)
        stdout_calls = [
            call for call in mock_print.call_args_list if call.kwargs.get("file") is None
        ]
        stdout_text = "\n".join(str(call.args[0]) if call.args else "" for call in stdout_calls)

        assert "ANSWER: Test answer text" in stdout_text
        assert "SOURCES:" in stdout_text
        assert '#1 "Doc 1"' in stdout_text
        assert '#2 "Doc 2"' in stdout_text
        assert '#3 "Doc 3"' in stdout_text
        assert "CONFIDENCE: high" in stdout_text

    def test_machine_output_metadata_on_stderr(self) -> None:
        """--machine should write metadata to stderr."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ),
            patch("builtins.print") as mock_print,
        ):
            _find_ask(
                "summarize auth",
                limit=10,
                project=None,
                tags=None,
                machine=True,
            )

        # Find stderr calls
        stderr_calls = [
            call for call in mock_print.call_args_list if call.kwargs.get("file") is not None
        ]
        assert len(stderr_calls) >= 1
        stderr_text = str(stderr_calls[0].args[0])
        assert "method=" in stderr_text
        assert "context_size=" in stderr_text
        assert "sources=" in stderr_text

    def test_machine_no_sources(self) -> None:
        """--machine with no sources should show '(none)'."""
        from emdx.commands.core import _find_ask

        answer = _make_answer(confidence="insufficient", source_count=0)

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ),
            patch("builtins.print") as mock_print,
        ):
            _find_ask(
                "nonexistent topic",
                limit=10,
                project=None,
                tags=None,
                machine=True,
            )

        stdout_calls = [
            call for call in mock_print.call_args_list if call.kwargs.get("file") is None
        ]
        stdout_text = "\n".join(str(call.args[0]) if call.args else "" for call in stdout_calls)
        assert "(none)" in stdout_text

    def test_machine_does_not_produce_json(self) -> None:
        """--machine should not produce JSON output."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ),
            patch("builtins.print") as mock_print,
        ):
            _find_ask(
                "test query",
                limit=10,
                project=None,
                tags=None,
                machine=True,
            )

        stdout_calls = [
            call for call in mock_print.call_args_list if call.kwargs.get("file") is None
        ]
        stdout_text = "\n".join(str(call.args[0]) if call.args else "" for call in stdout_calls)
        # Should not be valid JSON
        with_braces = stdout_text.strip()
        is_json = False
        try:
            json.loads(with_braces)
            is_json = True
        except json.JSONDecodeError:
            pass
        assert not is_json

    def test_machine_suppresses_spinner(self) -> None:
        """--machine should not show Rich spinner."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ),
            patch("builtins.print"),
            patch("emdx.commands.core.console") as mock_console,
        ):
            _find_ask(
                "test query",
                limit=10,
                project=None,
                tags=None,
                machine=True,
            )

        # console.status should not be called
        mock_console.status.assert_not_called()


# ── Confidence levels ─────────────────────────────────────────────────


class TestConfidenceLevels:
    """Tests for confidence level determination."""

    def test_high_confidence_with_many_sources(self) -> None:
        """3+ high-quality sources should yield high confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.85,
            retrieval_score_spread=0.05,
            source_count=5,
            query_term_coverage=0.9,
            topic_coherence=0.7,
            recency_score=0.8,
        )
        assert signals.level == "high"

    def test_medium_confidence(self) -> None:
        """Moderate signals should yield medium confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.5,
            retrieval_score_spread=0.2,
            source_count=2,
            query_term_coverage=0.5,
            topic_coherence=0.4,
            recency_score=0.3,
        )
        assert signals.level == "medium"

    def test_low_confidence(self) -> None:
        """Weak signals should yield low confidence."""
        signals = ConfidenceSignals(
            retrieval_score_mean=0.2,
            retrieval_score_spread=0.4,
            source_count=1,
            query_term_coverage=0.1,
            topic_coherence=0.1,
            recency_score=0.1,
        )
        assert signals.level in ("low", "insufficient")

    def test_insufficient_confidence_zero_sources(self) -> None:
        """Zero sources should yield insufficient confidence."""
        signals = ConfidenceSignals(source_count=0)
        assert signals.level == "insufficient"

    def test_machine_output_shows_confidence(self) -> None:
        """--machine output should include confidence level."""
        from emdx.commands.core import _find_ask

        for level in ("high", "medium", "low", "insufficient"):
            answer = _make_answer(confidence=level)

            with (
                patch(
                    "emdx.services.ask_service.AskService.ask",
                    return_value=answer,
                ),
                patch("builtins.print") as mock_print,
            ):
                _find_ask(
                    "test",
                    limit=10,
                    project=None,
                    tags=None,
                    machine=True,
                )

            stdout_calls = [
                call for call in mock_print.call_args_list if call.kwargs.get("file") is None
            ]
            stdout_text = "\n".join(str(call.args[0]) if call.args else "" for call in stdout_calls)
            assert f"CONFIDENCE: {level}" in stdout_text


# ── Integration: --machine with filters ───────────────────────────────


class TestMachineWithFilters:
    """Tests for --machine combined with --tags and --recent-days."""

    def test_machine_with_tags(self) -> None:
        """--machine --tags should pass tags to service and format output."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ) as mock_ask,
            patch("builtins.print"),
        ):
            _find_ask(
                "what is auth",
                limit=10,
                project=None,
                tags="security",
                machine=True,
            )

        assert mock_ask.call_args.kwargs.get("tags") == "security"

    def test_machine_with_recent_days(self) -> None:
        """--machine --recent-days should pass recent_days to service."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ) as mock_ask,
            patch("builtins.print"),
        ):
            _find_ask(
                "what changed",
                limit=10,
                project=None,
                tags=None,
                recent_days=14,
                machine=True,
            )

        assert mock_ask.call_args.kwargs.get("recent_days") == 14

    def test_machine_with_all_filters(self) -> None:
        """All filters combined should work with --machine."""
        from emdx.commands.core import _find_ask

        answer = _make_answer()

        with (
            patch(
                "emdx.services.ask_service.AskService.ask",
                return_value=answer,
            ) as mock_ask,
            patch("builtins.print"),
        ):
            _find_ask(
                "auth summary",
                limit=5,
                project="myproject",
                tags="security,active",
                recent_days=30,
                machine=True,
            )

        kwargs = mock_ask.call_args.kwargs
        assert kwargs.get("tags") == "security,active"
        assert kwargs.get("recent_days") == 30
        assert kwargs.get("project") == "myproject"


# ── _find_context with recent_days ────────────────────────────────────


class TestFindContextRecentDays:
    """Tests for --context with --recent-days."""

    def test_context_passes_recent_days(self) -> None:
        """_find_context should pass recent_days to retrieval."""
        from emdx.commands.core import _find_context

        with (
            patch.object(
                AskService,
                "_has_embeddings",
                return_value=False,
            ),
            patch.object(
                AskService,
                "_retrieve_keyword",
                return_value=(
                    [(1, "Doc 1", "content")],
                    "keyword",
                ),
            ) as mock_retrieve,
            patch("builtins.print"),
        ):
            _find_context(
                "test query",
                limit=10,
                project=None,
                tags=None,
                recent_days=7,
            )

        mock_retrieve.assert_called_once()
        assert mock_retrieve.call_args.kwargs.get("recent_days") == 7
