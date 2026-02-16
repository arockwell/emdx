"""
Document synthesis service for EMDX.

Uses Claude API (Opus model) to intelligently merge multiple documents
into a single synthesized document. This is the core service used by
the `compact` command and will be shared with future commands like `distill`.
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
    """Result from document synthesis."""

    content: str
    title: str
    input_tokens: int
    output_tokens: int
    source_doc_ids: list[int]

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens


class SynthesisService:
    """Service for synthesizing multiple documents into one.

    Uses Claude Opus for high-quality synthesis. The service is designed
    to be shared between multiple commands (compact, distill, etc.).
    """

    # Always use Opus for synthesis - quality is critical
    DEFAULT_MODEL = "claude-opus-4-5-20251101"

    def __init__(self, model: str | None = None):
        """Initialize the synthesis service.

        Args:
            model: Optional model override. Defaults to Claude Opus.
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
        purpose: str | None = None,
    ) -> SynthesisResult:
        """Synthesize multiple documents into a single document.

        Args:
            doc_ids: List of document IDs to synthesize
            purpose: Optional description of synthesis purpose/goal

        Returns:
            SynthesisResult with synthesized content and token usage

        Raises:
            ValueError: If no valid documents found for given IDs
            ImportError: If anthropic package not installed
        """
        _require_anthropic()

        if not doc_ids:
            raise ValueError("No document IDs provided for synthesis")

        # Fetch documents
        documents = self._fetch_documents(doc_ids)
        if not documents:
            raise ValueError(f"No valid documents found for IDs: {doc_ids}")

        # Build context from documents
        context_parts = []
        for doc_id, title, content in documents:
            context_parts.append(f"## Document #{doc_id}: {title}\n\n{content}")

        context = "\n\n---\n\n".join(context_parts)

        # Build synthesis prompt
        system_prompt = self._build_system_prompt(purpose)
        user_prompt = self._build_user_prompt(context, documents)

        # Call Claude API
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
        )

        # Parse response
        synthesized_content = response.content[0].text
        title = self._extract_title(synthesized_content, documents)

        return SynthesisResult(
            content=synthesized_content,
            title=title,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            source_doc_ids=[doc[0] for doc in documents],
        )

    def _fetch_documents(self, doc_ids: list[int]) -> list[tuple[int, str, str]]:
        """Fetch documents by IDs.

        Args:
            doc_ids: List of document IDs

        Returns:
            List of tuples (id, title, content) for found documents
        """
        documents = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(doc_ids))
            cursor.execute(
                f"SELECT id, title, content FROM documents "
                f"WHERE id IN ({placeholders}) AND is_deleted = 0 "
                f"ORDER BY id",
                doc_ids,
            )
            for row in cursor.fetchall():
                documents.append((row[0], row[1], row[2]))
        return documents

    def _build_system_prompt(self, purpose: str | None) -> str:
        """Build the system prompt for synthesis."""
        base_prompt = """You are a knowledge synthesis expert. Your task is to merge \
multiple related documents into a single, comprehensive document that:

1. **Preserves all important information** - No key insights should be lost
2. **Eliminates redundancy** - Remove duplicate information while keeping the best version
3. **Maintains coherent structure** - Create logical sections and flow
4. **Resolves conflicts** - If documents contain conflicting info, note the discrepancy
5. **Improves clarity** - Clean up formatting, fix obvious errors

Output a well-structured markdown document. Start with a clear title as an H1 heading.

Rules:
- Keep technical details intact
- Preserve specific examples and code snippets
- Maintain links and references
- Note which original documents contributed to each section (as a comment like [from #42])
- If the documents cover different aspects of a topic, organize them into logical sections
- If they're different versions of the same thing, create a unified best version"""

        if purpose:
            base_prompt += f"\n\nSynthesis purpose: {purpose}"

        return base_prompt

    def _build_user_prompt(
        self, context: str, documents: list[tuple[int, str, str]]
    ) -> str:
        """Build the user prompt for synthesis."""
        doc_summary = ", ".join([f"#{doc[0]} ({doc[1][:50]}...)" for doc in documents])
        return f"""Please synthesize the following {len(documents)} documents into a single \
comprehensive document.

Source documents: {doc_summary}

---

{context}

---

Create a synthesized document that combines all the information above. \
Start with an H1 title that captures the combined topic."""

    def _extract_title(
        self, content: str, documents: list[tuple[int, str, str]]
    ) -> str:
        """Extract title from synthesized content or generate one.

        Args:
            content: Synthesized markdown content
            documents: Original documents for fallback

        Returns:
            Extracted or generated title
        """
        # Try to extract H1 title from content
        lines = content.strip().split("\n")
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()

        # Fallback: combine first two document titles
        if len(documents) >= 2:
            return f"{documents[0][1]} + {documents[1][1]} [synthesis]"
        elif documents:
            return f"{documents[0][1]} [synthesis]"
        else:
            return "Synthesized Document"

    def estimate_cost(self, doc_ids: list[int]) -> dict[str, Any]:
        """Estimate the cost of synthesizing documents.

        Args:
            doc_ids: List of document IDs

        Returns:
            Dictionary with estimated tokens and cost
        """
        documents = self._fetch_documents(doc_ids)
        if not documents:
            return {
                "document_count": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_cost_usd": 0.0,
            }

        # Estimate tokens (rough approximation: ~4 chars per token)
        total_chars = sum(len(doc[2]) for doc in documents)
        estimated_input_tokens = total_chars // 4 + 500  # Add prompt overhead

        # Output is typically 30-50% of input for synthesis
        estimated_output_tokens = estimated_input_tokens // 3

        # Opus pricing: $15/MTok input, $75/MTok output (as of 2024)
        input_cost = (estimated_input_tokens / 1_000_000) * 15
        output_cost = (estimated_output_tokens / 1_000_000) * 75
        total_cost = input_cost + output_cost

        return {
            "document_count": len(documents),
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost_usd": round(total_cost, 4),
        }
