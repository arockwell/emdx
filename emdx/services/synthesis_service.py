"""
AI-powered document synthesis service for EMDX.

Uses Claude API to intelligently merge multiple documents into a single
synthesized document, preserving key information while reducing redundancy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..database import db

logger = logging.getLogger(__name__)

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False



def _require_anthropic() -> None:
    """Raise ImportError with helpful message if anthropic is not installed."""
    if not HAS_ANTHROPIC:
        raise ImportError(
            "anthropic is required for synthesis features. "
            "Install it with: pip install 'emdx[ai]'"
        )


@dataclass
class SynthesisResult:
    """Result of a document synthesis operation."""

    content: str
    title: str
    input_tokens: int
    output_tokens: int
    source_doc_ids: list[int]


class SynthesisService:
    """AI-powered document synthesis using Claude API."""

    # Always use Opus for synthesis - quality critical, infrequent operation
    DEFAULT_MODEL = "claude-opus-4-20250514"
    MAX_TOKENS = 8000

    def __init__(self, model: str | None = None):
        """Initialize the synthesis service.

        Args:
            model: Model to use (defaults to claude-opus-4)
        """
        self.model = model or self.DEFAULT_MODEL
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load Anthropic client."""
        _require_anthropic()
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def synthesize_documents(
        self,
        doc_ids: list[int],
        title_hint: str | None = None,
    ) -> SynthesisResult:
        """Synthesize multiple documents into a single coherent document.

        Args:
            doc_ids: List of document IDs to synthesize
            title_hint: Optional hint for the synthesized document title

        Returns:
            SynthesisResult containing the synthesized content and metadata

        Raises:
            ValueError: If no valid documents found
            ImportError: If anthropic is not installed
        """
        _require_anthropic()

        # Fetch documents from database
        documents = self._fetch_documents(doc_ids)
        if not documents:
            raise ValueError(f"No valid documents found for IDs: {doc_ids}")

        # Build context from documents
        context_parts = []
        for doc in documents:
            context_parts.append(
                f"## Document #{doc['id']}: {doc['title']}\n\n{doc['content']}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # Build title hint for the prompt
        titles = [doc["title"] for doc in documents]
        title_context = f"The source documents are titled: {', '.join(titles)}"
        if title_hint:
            title_context += f"\n\nSuggested title direction: {title_hint}"

        # Generate synthesized content
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            system="""You are a document synthesis expert. Your task is to intelligently merge
multiple related documents into a single, coherent document that:

1. Preserves ALL key information, facts, and insights from the source documents
2. Eliminates redundancy and repetition
3. Organizes information logically with clear structure
4. Maintains the original tone and technical level
5. Uses markdown formatting for readability

Your output should be a complete markdown document with:
- A clear, descriptive title (as a level-1 heading)
- Well-organized sections
- No references to "the source documents" - write as a standalone document

IMPORTANT: Start your response with the title as a markdown heading, then the content.
Do not include any preamble or explanation - just the synthesized document.""",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Synthesize the following documents into a single coherent document.\n\n"
                        f"{title_context}\n\n---\n\n{context}"
                    ),
                }
            ],
        )

        # Extract content and title
        content_block = response.content[0]
        content = content_block.text if hasattr(content_block, "text") else str(content_block)
        title = self._extract_title(content, titles)

        return SynthesisResult(
            content=content,
            title=title,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            source_doc_ids=doc_ids,
        )

    def _fetch_documents(self, doc_ids: list[int]) -> list[dict]:
        """Fetch documents from database without updating access tracking.

        Args:
            doc_ids: List of document IDs to fetch

        Returns:
            List of document dictionaries
        """
        if not doc_ids:
            return []

        documents = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(doc_ids))
            cursor.execute(
                f"""
                SELECT id, title, content, project
                FROM documents
                WHERE id IN ({placeholders}) AND is_deleted = FALSE
                ORDER BY id
                """,
                doc_ids,
            )
            for row in cursor.fetchall():
                documents.append(dict(row))

        return documents

    def _extract_title(self, content: str, fallback_titles: list[str]) -> str:
        """Extract title from synthesized content.

        Args:
            content: Synthesized markdown content
            fallback_titles: Original document titles for fallback

        Returns:
            Extracted or generated title
        """
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()

        # Fallback: combine original titles
        if len(fallback_titles) == 1:
            return f"{fallback_titles[0]} (synthesized)"
        return f"Synthesis: {fallback_titles[0]} + {len(fallback_titles) - 1} more"

    def estimate_cost(
        self,
        doc_ids: list[int],
    ) -> dict[str, float | int]:
        """Estimate the API cost for synthesizing documents.

        Args:
            doc_ids: List of document IDs to synthesize

        Returns:
            Dictionary with estimated tokens and cost
        """
        documents = self._fetch_documents(doc_ids)
        if not documents:
            return {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}

        # Estimate input tokens (rough approximation: 1 token ≈ 4 characters)
        total_chars = sum(
            len(doc["title"]) + len(doc["content"]) for doc in documents
        )
        # Add overhead for prompts
        estimated_input_tokens = (total_chars // 4) + 500

        # Estimate output tokens (synthesis usually shorter than input)
        estimated_output_tokens = min(estimated_input_tokens // 2, self.MAX_TOKENS)

        # Claude Opus pricing (as of 2024): $15/M input, $75/M output
        input_cost = (estimated_input_tokens / 1_000_000) * 15
        output_cost = (estimated_output_tokens / 1_000_000) * 75
        estimated_cost = input_cost + output_cost

        return {
            "input_tokens": estimated_input_tokens,
            "output_tokens": estimated_output_tokens,
            "estimated_cost": round(estimated_cost, 4),
            "document_count": len(documents),
        }
