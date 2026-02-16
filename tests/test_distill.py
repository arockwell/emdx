"""Tests for the distill command and SynthesisService."""

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.distill import app
from emdx.services.synthesis_service import SynthesisResult, SynthesisService

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# SynthesisService tests
# ---------------------------------------------------------------------------
class TestSynthesisService:
    """Tests for the SynthesisService."""

    def test_init_default_model(self):
        """Service initializes with default Opus model."""
        service = SynthesisService()
        assert "opus" in service.model.lower()

    def test_init_custom_model(self):
        """Service accepts custom model."""
        service = SynthesisService(model="claude-sonnet-4-5-20250929")
        assert "sonnet" in service.model.lower()

    def test_synthesize_empty_documents(self):
        """Synthesizing empty document list returns appropriate message."""
        service = SynthesisService()
        result = service.synthesize_documents(documents=[])

        assert "No documents" in result.content
        assert result.source_ids == []
        assert result.token_count == 0

    @patch("emdx.services.synthesis_service.HAS_ANTHROPIC", True)
    def test_synthesize_documents_success(self):
        """Successful synthesis returns result with content."""
        # Mock the client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Synthesized content here")]
        mock_response.usage = MagicMock(input_tokens=500)
        mock_client.messages.create.return_value = mock_response

        service = SynthesisService()
        service._client = mock_client

        documents = [
            {"id": 1, "title": "Doc 1", "content": "Content 1"},
            {"id": 2, "title": "Doc 2", "content": "Content 2"},
        ]

        result = service.synthesize_documents(documents=documents, audience="me")

        assert result.content == "Synthesized content here"
        assert result.source_ids == [1, 2]
        assert result.token_count == 500

    def test_build_system_prompt_me(self):
        """System prompt for 'me' audience includes personal reference style."""
        service = SynthesisService()
        prompt = service._build_system_prompt("me", None)

        assert "Personal reference" in prompt
        assert "concise" in prompt.lower()

    def test_build_system_prompt_docs(self):
        """System prompt for 'docs' audience includes technical style."""
        service = SynthesisService()
        prompt = service._build_system_prompt("docs", None)

        assert "Technical documentation" in prompt
        assert "code" in prompt.lower()

    def test_build_system_prompt_coworkers(self):
        """System prompt for 'coworkers' audience includes team briefing style."""
        service = SynthesisService()
        prompt = service._build_system_prompt("coworkers", None)

        assert "Team briefing" in prompt
        assert "action items" in prompt.lower()

    def test_build_system_prompt_with_topic(self):
        """System prompt includes topic focus when provided."""
        service = SynthesisService()
        prompt = service._build_system_prompt("me", "authentication")

        assert "authentication" in prompt

    def test_build_user_prompt(self):
        """User prompt includes context and synthesis request."""
        service = SynthesisService()
        prompt = service._build_user_prompt("document content", "me", None)

        assert "document content" in prompt
        assert "synthesize" in prompt.lower()

    def test_build_user_prompt_with_topic(self):
        """User prompt includes topic focus when provided."""
        service = SynthesisService()
        prompt = service._build_user_prompt("content", "me", "security")

        assert "security" in prompt
        assert "Focus on" in prompt


# ---------------------------------------------------------------------------
# Distill command tests
# ---------------------------------------------------------------------------
class TestDistillCommand:
    """Tests for the distill command via CLI runner."""

    @patch("emdx.commands.distill._find_documents")
    def test_distill_no_args_shows_error(self, mock_find):
        """Distill with no topic or tags shows error."""
        result = runner.invoke(app, [])
        assert result.exit_code != 0
        out = _out(result)
        # The error message should mention providing topic or tags
        assert "topic" in out.lower() or "tags" in out.lower() or "error" in out.lower()

    @patch("emdx.commands.distill._find_documents")
    def test_distill_no_documents_found(self, mock_find):
        """Distill with no matching documents shows message."""
        mock_find.return_value = []

        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0
        assert "No documents found" in _out(result)

    @patch("emdx.services.synthesis_service.SynthesisService.synthesize_documents")
    @patch("emdx.commands.distill._find_documents")
    def test_distill_success(self, mock_find, mock_synthesize):
        """Successful distill outputs synthesis."""
        mock_find.return_value = [
            {"id": 1, "title": "Doc 1", "content": "Content 1"},
            {"id": 2, "title": "Doc 2", "content": "Content 2"},
        ]

        mock_synthesize.return_value = SynthesisResult(
            content="This is the synthesized content.",
            source_ids=[1, 2],
            token_count=500,
            model="claude-opus-4-5-20251101",
        )

        result = runner.invoke(app, ["test topic"])
        assert result.exit_code == 0
        out = _out(result)
        assert "synthesized content" in out.lower()

    @patch("emdx.commands.distill._find_documents")
    def test_distill_with_tags_only(self, mock_find):
        """Distill with --tags only (no topic) works."""
        mock_find.return_value = [{"id": 1, "title": "Doc", "content": "Test"}]

        with patch(
            "emdx.services.synthesis_service.SynthesisService.synthesize_documents"
        ) as mock_synth:
            mock_synth.return_value = SynthesisResult(
                content="Tag-based synthesis.",
                source_ids=[1],
                token_count=100,
                model="claude-opus-4-5-20251101",
            )

            result = runner.invoke(app, ["--tags", "security,active"])
            assert result.exit_code == 0
            out = _out(result)
            assert "Tag-based synthesis" in out


# ---------------------------------------------------------------------------
# SynthesisResult dataclass tests
# ---------------------------------------------------------------------------
class TestSynthesisResult:
    """Tests for the SynthesisResult dataclass."""

    def test_synthesis_result_creation(self):
        """SynthesisResult can be created with all fields."""
        result = SynthesisResult(
            content="Test content",
            source_ids=[1, 2, 3],
            token_count=100,
            model="claude-opus-4-5-20251101",
        )

        assert result.content == "Test content"
        assert result.source_ids == [1, 2, 3]
        assert result.token_count == 100
        assert result.model == "claude-opus-4-5-20251101"
