"""
Synthesis service for EMDX.

Provides AI-powered document synthesis for distilling and compacting KB content.
Uses Claude Opus API for high-quality synthesis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False

logger = logging.getLogger(__name__)


class Audience(str, Enum):
    """Target audience for synthesized content."""

    ME = "me"  # Personal summary, dense with context
    DOCS = "docs"  # Technical documentation style
    COWORKERS = "coworkers"  # Team briefing, accessible


@dataclass
class SynthesisResult:
    """Result of a synthesis operation."""

    content: str
    source_ids: list[int]
    source_count: int
    audience: Audience
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class SynthesisService:
    """AI-powered document synthesis service.

    Uses Claude Opus for high-quality synthesis operations like:
    - Distilling multiple documents into a coherent summary
    - Compacting redundant documents into a single comprehensive doc
    - Summarizing content for different audiences
    """

    # Always use Opus for synthesis - quality is critical
    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

    AUDIENCE_PROMPTS = {
        Audience.ME: """You are creating a personal knowledge summary for the document author.
Be concise but preserve important details, links, code snippets, and specific references.
Use technical language appropriate for the original author.
Focus on actionable insights and key decisions.
Format with headers and bullet points for easy scanning.""",
        Audience.DOCS: """You are creating technical documentation.
Write in a clear, formal documentation style.
Include code examples where relevant.
Use proper markdown formatting with headers, code blocks, and lists.
Explain concepts thoroughly but concisely.
Focus on "how it works" and "how to use it".""",
        Audience.COWORKERS: """You are creating a team briefing document.
Write in an accessible, professional tone.
Avoid jargon or explain it when necessary.
Highlight key decisions, blockers, and next steps.
Include context that team members need to understand the topic.
Use bullet points for easy reading in meetings.""",
    }

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
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
        topic: str | None = None,
        audience: Audience = Audience.ME,
        max_tokens: int = 4000,
    ) -> SynthesisResult:
        """Synthesize multiple documents into a coherent summary.

        Args:
            documents: List of document dicts with 'id', 'title', 'content' keys
            topic: Optional topic/query to focus the synthesis
            audience: Target audience for the output
            max_tokens: Maximum output tokens

        Returns:
            SynthesisResult with synthesized content and metadata
        """
        if not documents:
            return SynthesisResult(
                content="No documents to synthesize.",
                source_ids=[],
                source_count=0,
                audience=audience,
                input_tokens=0,
                output_tokens=0,
            )

        # Build context from documents
        context_parts = []
        source_ids = []
        for doc in documents:
            doc_id = doc.get("id", 0)
            title = doc.get("title", "Untitled")
            content = doc.get("content", "")

            # Truncate very long documents to fit in context
            if len(content) > 8000:
                content = content[:8000] + "\n\n[... content truncated ...]"

            context_parts.append(f"## Document #{doc_id}: {title}\n\n{content}")
            source_ids.append(doc_id)

        context = "\n\n---\n\n".join(context_parts)

        # Build the synthesis prompt
        audience_instruction = self.AUDIENCE_PROMPTS[audience]

        if topic:
            task_instruction = (
                f"Synthesize the following documents into a coherent summary "
                f"focused on: {topic}\n\n"
                f'Extract and consolidate the most relevant information about "{topic}" '
                "from all documents.\n"
                "Remove redundancy and create a unified, well-organized summary."
            )
        else:
            task_instruction = """Synthesize the following documents into a coherent summary.

Identify common themes and consolidate related information.
Remove redundancy while preserving important details.
Create a unified, well-organized summary."""

        # Call Claude API
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=f"{audience_instruction}\n\n{task_instruction}",
                messages=[
                    {
                        "role": "user",
                        "content": f"Documents to synthesize:\n\n{context}",
                    }
                ],
            )

            return SynthesisResult(
                content=response.content[0].text,
                source_ids=source_ids,
                source_count=len(documents),
                audience=audience,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        except Exception as e:
            if HAS_ANTHROPIC and isinstance(e, anthropic.APIError):
                logger.error(f"Claude API error during synthesis: {e}")
                raise
            raise

    def distill_single(
        self,
        document: dict[str, Any],
        audience: Audience = Audience.ME,
        max_tokens: int = 2000,
    ) -> SynthesisResult:
        """Distill a single document into a shorter summary.

        Args:
            document: Document dict with 'id', 'title', 'content' keys
            audience: Target audience for the output
            max_tokens: Maximum output tokens

        Returns:
            SynthesisResult with distilled content
        """
        return self.synthesize_documents(
            documents=[document],
            topic=None,
            audience=audience,
            max_tokens=max_tokens,
        )
