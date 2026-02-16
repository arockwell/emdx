"""Tests for the distill command and SynthesisService."""

import re
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.services.synthesis_service import Audience, SynthesisResult, SynthesisService

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# SynthesisService tests
# ---------------------------------------------------------------------------
class TestSynthesisService:
    """Tests for the SynthesisService."""

    def test_audience_enum_values(self):
        """Audience enum has expected values."""
        assert Audience.ME.value == "me"
        assert Audience.DOCS.value == "docs"
        assert Audience.COWORKERS.value == "coworkers"

    def test_synthesis_result_total_tokens(self):
        """SynthesisResult calculates total tokens correctly."""
        result = SynthesisResult(
            content="test",
            source_ids=[1, 2],
            source_count=2,
            audience=Audience.ME,
            input_tokens=100,
            output_tokens=50,
        )
        assert result.total_tokens == 150

    def test_synthesize_empty_documents(self):
        """Synthesizing empty document list returns appropriate message."""
        service = SynthesisService()
        result = service.synthesize_documents(documents=[], topic="test")

        assert result.content == "No documents to synthesize."
        assert result.source_count == 0
        assert result.source_ids == []
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @patch("emdx.services.synthesis_service.HAS_ANTHROPIC", False)
    def test_synthesize_without_anthropic(self):
        """Synthesizing without anthropic raises ImportError."""
        service = SynthesisService()
        service._client = None  # Reset any cached client

        with pytest.raises(ImportError, match="anthropic is required"):
            service.synthesize_documents(
                documents=[{"id": 1, "title": "Test", "content": "content"}],
                topic="test",
            )

    @patch("emdx.services.synthesis_service.HAS_ANTHROPIC", True)
    @patch("emdx.services.synthesis_service.anthropic")
    def test_synthesize_with_mocked_client(self, mock_anthropic):
        """Synthesizing with mocked Claude client returns result."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Synthesized content here")]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=200)
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        service = SynthesisService()
        result = service.synthesize_documents(
            documents=[
                {"id": 1, "title": "Doc 1", "content": "Content 1"},
                {"id": 2, "title": "Doc 2", "content": "Content 2"},
            ],
            topic="authentication",
            audience=Audience.DOCS,
        )

        assert result.content == "Synthesized content here"
        assert result.source_ids == [1, 2]
        assert result.source_count == 2
        assert result.audience == Audience.DOCS
        assert result.input_tokens == 500
        assert result.output_tokens == 200

        # Verify API was called with correct parameters
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "authentication" in call_kwargs["system"]
        assert "Doc 1" in call_kwargs["messages"][0]["content"]
        assert "Doc 2" in call_kwargs["messages"][0]["content"]

    @patch("emdx.services.synthesis_service.HAS_ANTHROPIC", True)
    @patch("emdx.services.synthesis_service.anthropic")
    def test_audience_prompts_differ(self, mock_anthropic):
        """Different audiences produce different system prompts."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Result")]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        service = SynthesisService()
        docs = [{"id": 1, "title": "Test", "content": "Content"}]

        # Call with ME audience
        service._client = None  # Reset client
        service.synthesize_documents(documents=docs, audience=Audience.ME)
        me_prompt = mock_client.messages.create.call_args.kwargs["system"]

        # Reset and call with DOCS audience
        service._client = None
        mock_anthropic.Anthropic.return_value = mock_client
        service.synthesize_documents(documents=docs, audience=Audience.DOCS)
        docs_prompt = mock_client.messages.create.call_args.kwargs["system"]

        # Prompts should be different
        assert me_prompt != docs_prompt
        assert "documentation" in docs_prompt.lower()

    def test_distill_single_delegates_to_synthesize(self):
        """distill_single calls synthesize_documents with single doc."""
        service = SynthesisService()

        with patch.object(service, "synthesize_documents") as mock_synth:
            mock_synth.return_value = SynthesisResult(
                content="distilled",
                source_ids=[1],
                source_count=1,
                audience=Audience.ME,
                input_tokens=100,
                output_tokens=50,
            )

            doc = {"id": 1, "title": "Test", "content": "Content"}
            result = service.distill_single(doc, audience=Audience.COWORKERS)

            mock_synth.assert_called_once_with(
                documents=[doc],
                topic=None,
                audience=Audience.COWORKERS,
                max_tokens=2000,
            )
            assert result.content == "distilled"


# ---------------------------------------------------------------------------
# Distill command tests
# ---------------------------------------------------------------------------
class TestDistillCommand:
    """Tests for the distill CLI command."""

    @patch("emdx.commands.distill.db")
    def test_distill_requires_topic_or_tags(self, mock_db):
        """Distill without topic or tags shows error."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()

        result = runner.invoke(app, [])
        assert result.exit_code != 0
        assert "topic" in _out(result).lower() or "tags" in _out(result).lower()

    @patch("emdx.services.synthesis_service.SynthesisService")
    @patch("emdx.commands.distill._get_documents_by_query")
    @patch("emdx.commands.distill.db")
    def test_distill_with_topic(self, mock_db, mock_get_docs, mock_service_class):
        """Distill with topic searches and synthesizes."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = [
            {"id": 1, "title": "Auth Doc", "content": "Auth content"},
        ]

        mock_service = MagicMock()
        mock_service.synthesize_documents.return_value = SynthesisResult(
            content="# Authentication Summary\n\nKey points here.",
            source_ids=[1],
            source_count=1,
            audience=Audience.ME,
            input_tokens=200,
            output_tokens=100,
        )
        mock_service_class.return_value = mock_service

        result = runner.invoke(app, ["authentication"])
        assert result.exit_code == 0
        assert "Authentication Summary" in _out(result)

    @patch("emdx.services.synthesis_service.SynthesisService")
    @patch("emdx.commands.distill._get_documents_by_tags")
    @patch("emdx.commands.distill.db")
    def test_distill_with_tags(self, mock_db, mock_get_docs, mock_service_class):
        """Distill with --tags searches by tags."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = [
            {"id": 5, "title": "Security Doc", "content": "Security info"},
        ]

        mock_service = MagicMock()
        mock_service.synthesize_documents.return_value = SynthesisResult(
            content="Security summary",
            source_ids=[5],
            source_count=1,
            audience=Audience.ME,
            input_tokens=150,
            output_tokens=80,
        )
        mock_service_class.return_value = mock_service

        result = runner.invoke(app, ["--tags", "security,active"])
        assert result.exit_code == 0
        mock_get_docs.assert_called_once_with(["security", "active"], limit=20)

    @patch("emdx.services.synthesis_service.SynthesisService")
    @patch("emdx.commands.distill._get_documents_by_query")
    @patch("emdx.commands.distill.db")
    def test_distill_audience_option(self, mock_db, mock_get_docs, mock_service_class):
        """Distill --for option sets audience."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = [{"id": 1, "title": "T", "content": "C"}]

        mock_service = MagicMock()
        mock_service.synthesize_documents.return_value = SynthesisResult(
            content="Doc output",
            source_ids=[1],
            source_count=1,
            audience=Audience.DOCS,
            input_tokens=100,
            output_tokens=50,
        )
        mock_service_class.return_value = mock_service

        result = runner.invoke(app, ["--for", "docs", "API design"])
        assert result.exit_code == 0

        # Verify audience was passed correctly
        mock_service.synthesize_documents.assert_called_once()
        call_kwargs = mock_service.synthesize_documents.call_args.kwargs
        assert call_kwargs["audience"] == Audience.DOCS

    @patch("emdx.services.synthesis_service.SynthesisService")
    @patch("emdx.commands.distill._get_documents_by_query")
    @patch("emdx.commands.distill.db")
    def test_distill_quiet_mode(self, mock_db, mock_get_docs, mock_service_class):
        """Distill --quiet outputs only content."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = [{"id": 1, "title": "T", "content": "C"}]

        mock_service = MagicMock()
        mock_service.synthesize_documents.return_value = SynthesisResult(
            content="Just the content",
            source_ids=[1],
            source_count=1,
            audience=Audience.ME,
            input_tokens=100,
            output_tokens=50,
        )
        mock_service_class.return_value = mock_service

        result = runner.invoke(app, ["--quiet", "topic"])
        output = _out(result)
        assert result.exit_code == 0
        assert "Just the content" in output
        # Quiet mode shouldn't show stats
        assert "Tokens:" not in output
        assert "Sources:" not in output

    @patch("emdx.commands.distill._get_documents_by_query")
    @patch("emdx.commands.distill.db")
    def test_distill_no_documents_found(self, mock_db, mock_get_docs):
        """Distill with no matching documents shows message."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = []

        result = runner.invoke(app, ["nonexistent-topic-xyz"])
        assert result.exit_code == 0
        assert "No documents found" in _out(result)

    @patch("emdx.commands.distill.db")
    def test_distill_invalid_audience(self, mock_db):
        """Distill with invalid --for shows error."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()

        result = runner.invoke(app, ["--for", "invalid", "topic"])
        assert result.exit_code != 0
        assert "Unknown audience" in _out(result)

    @patch("emdx.models.tags.add_tags_to_document")
    @patch("emdx.database.documents.save_document")
    @patch("emdx.services.synthesis_service.SynthesisService")
    @patch("emdx.commands.distill._get_documents_by_query")
    @patch("emdx.commands.distill.db")
    def test_distill_save_option(
        self, mock_db, mock_get_docs, mock_service_class, mock_save, mock_add_tags
    ):
        """Distill --save saves the output to KB."""
        from emdx.commands.distill import app

        mock_db.ensure_schema = MagicMock()
        mock_get_docs.return_value = [{"id": 1, "title": "T", "content": "C"}]

        mock_service = MagicMock()
        mock_service.synthesize_documents.return_value = SynthesisResult(
            content="Saved content",
            source_ids=[1],
            source_count=1,
            audience=Audience.ME,
            input_tokens=100,
            output_tokens=50,
        )
        mock_service_class.return_value = mock_service

        mock_save.return_value = 42

        result = runner.invoke(app, ["--save", "--title", "My Summary", "topic"])
        assert result.exit_code == 0
        assert "#42" in _out(result)

        mock_save.assert_called_once_with(title="My Summary", content="Saved content")
        mock_add_tags.assert_called_once_with(42, ["distilled", "for-me"])
