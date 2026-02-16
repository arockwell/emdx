"""
Synthesis service for EMDX.

Provides AI-powered document synthesis using Claude Opus API.
Used by `emdx distill` and `emdx compact` commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False

logger = logging.getLogger(__name__)


# Default model for synthesis (Opus for quality-critical tasks)
DEFAULT_SYNTHESIS_MODEL = "claude-opus-4-5-20251101"


@dataclass
class SynthesisResult:
    """Result of a synthesis operation."""

    content: str
    source_ids: list[int]  # Document IDs that were synthesized
    token_count: int  # Input tokens used
    model: str


class SynthesisService:
    """
    AI-powered document synthesis service.

    Uses Claude Opus API to intelligently combine and synthesize
    multiple documents into coherent summaries.
    """

    def __init__(self, model: str | None = None):
        """
        Initialize the synthesis service.

        Args:
            model: Claude model to use. Defaults to Opus for quality.
        """
        self.model = model or DEFAULT_SYNTHESIS_MODEL
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load Anthropic client."""
        if not HAS_ANTHROPIC:
            raise ImportError(
                "anthropic is required for synthesis features. "
                "Install it with: pip install 'emdx[ai]'"
            )
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def synthesize_documents(
        self,
        documents: list[dict[str, Any]],
        audience: str = "me",
        topic: str | None = None,
        max_tokens: int = 4000,
    ) -> SynthesisResult:
        """
        Synthesize multiple documents into a coherent summary.

        Args:
            documents: List of documents with 'id', 'title', 'content' keys.
            audience: Target audience - 'me' (personal), 'docs' (technical),
                     or 'coworkers' (team briefing).
            topic: Optional topic/focus for the synthesis.
            max_tokens: Maximum tokens for the response.

        Returns:
            SynthesisResult with the synthesized content.
        """
        if not documents:
            return SynthesisResult(
                content="No documents provided for synthesis.",
                source_ids=[],
                token_count=0,
                model=self.model,
            )

        # Build context from documents
        context_parts = []
        source_ids = []
        for doc in documents:
            doc_id = doc.get("id", 0)
            title = doc.get("title", "Untitled")
            content = doc.get("content", "")

            # Truncate very long documents (keep first 6000 chars)
            if len(content) > 6000:
                content = content[:6000] + "\n\n[...content truncated...]"

            context_parts.append(f"# Document #{doc_id}: {title}\n\n{content}")
            source_ids.append(doc_id)

        context = "\n\n---\n\n".join(context_parts)

        # Build the system prompt based on audience
        system_prompt = self._build_system_prompt(audience, topic)

        # Build the user prompt
        user_prompt = self._build_user_prompt(context, audience, topic)

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Extract token usage
            input_tokens = response.usage.input_tokens if response.usage else 0

            return SynthesisResult(
                content=response.content[0].text,
                source_ids=source_ids,
                token_count=input_tokens,
                model=self.model,
            )

        except Exception as e:
            if HAS_ANTHROPIC and isinstance(e, anthropic.APIError):
                logger.error(f"Claude API error during synthesis: {e}")
                return SynthesisResult(
                    content=f"Error during synthesis: {e}",
                    source_ids=source_ids,
                    token_count=0,
                    model=self.model,
                )
            raise

    def _build_system_prompt(self, audience: str, topic: str | None) -> str:
        """Build the system prompt based on audience."""
        base_prompt = """You are an expert at synthesizing knowledge from multiple documents.
Your task is to create a coherent, well-organized synthesis of the provided documents."""

        audience_instructions = {
            "me": """
Target audience: Personal reference
- Write in a direct, concise style
- Focus on actionable insights and key takeaways
- Include specific details and references you might need later
- Organize by themes or concepts, not by source document
- Use bullet points and headers for scannability""",
            "docs": """
Target audience: Technical documentation
- Write in a professional, technical style
- Focus on accuracy and completeness
- Include code examples, configurations, or specifications where relevant
- Use proper documentation formatting (headers, code blocks, lists)
- Organize logically with clear sections
- Cite document IDs for traceability""",
            "coworkers": """
Target audience: Team briefing
- Write in a clear, accessible style
- Focus on what's relevant for the team to know
- Highlight key decisions, blockers, and action items
- Summarize context without excessive detail
- Use a professional but approachable tone
- Organize with clear sections and bullet points""",
        }

        instructions = audience_instructions.get(audience, audience_instructions["me"])

        topic_clause = ""
        if topic:
            topic_clause = f"\n\nFocus particularly on aspects related to: {topic}"

        return f"{base_prompt}\n{instructions}{topic_clause}"

    def _build_user_prompt(
        self, context: str, audience: str, topic: str | None
    ) -> str:
        """Build the user prompt."""
        prompt = f"""Here are the documents to synthesize:

{context}

---

Please synthesize these documents into a single, coherent summary."""

        if topic:
            prompt += f"\n\nFocus on: {topic}"

        return prompt
