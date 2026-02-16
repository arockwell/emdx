"""
AI-powered document synthesis service for EMDX.

Provides two synthesis services:
- SynthesisService: Used by compact command for merging related documents
- DistillService: Used by distill command for audience-aware KB synthesis

Uses Claude CLI (via UnifiedExecutor) for synthesis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..database import db
from .unified_executor import ExecutionConfig, ExecutionResult, UnifiedExecutor

logger = logging.getLogger(__name__)

SYNTHESIS_TIMEOUT = 300


def _execute_prompt(
    system_prompt: str,
    user_message: str,
    title: str,
    model: str | None = None,
) -> ExecutionResult:
    """Execute a synthesis prompt via the Claude CLI.

    Combines system and user messages into a single prompt for --print mode.

    Args:
        system_prompt: System-level instructions
        user_message: The user message content
        title: Title for the execution record
        model: Optional model override

    Returns:
        ExecutionResult from the CLI execution

    Raises:
        RuntimeError: If the CLI execution fails
    """
    prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_message}"

    config = ExecutionConfig(
        prompt=prompt,
        title=title,
        allowed_tools=[],
        timeout_seconds=SYNTHESIS_TIMEOUT,
        model=model,
    )

    executor = UnifiedExecutor()
    result = executor.execute(config)

    if not result.success:
        raise RuntimeError(
            f"Synthesis failed: {result.error_message or 'unknown error'}"
        )

    return result


# =============================================================================
# Distill service (audience-aware synthesis)
# =============================================================================


class Audience(str, Enum):
    """Target audience for synthesized content."""

    ME = "me"  # Personal summary, dense with context
    DOCS = "docs"  # Technical documentation style
    COWORKERS = "coworkers"  # Team briefing, accessible


@dataclass
class DistillResult:
    """Result of a distill operation."""

    content: str
    source_ids: list[int]
    source_count: int
    audience: Audience
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class DistillService:
    """AI-powered audience-aware synthesis for distill command.

    Uses Claude for high-quality synthesis operations like:
    - Distilling multiple documents into a coherent summary
    - Summarizing content for different audiences
    """

    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

    AUDIENCE_PROMPTS = {
        Audience.ME: (
            "You are creating a personal knowledge summary for the document author.\n"
            "Be concise but preserve important details, links, code snippets, "
            "and specific references.\n"
            "Use technical language appropriate for the original author.\n"
            "Focus on actionable insights and key decisions.\n"
            "Format with headers and bullet points for easy scanning."
        ),
        Audience.DOCS: (
            "You are creating technical documentation.\n"
            "Write in a clear, formal documentation style.\n"
            "Include code examples where relevant.\n"
            "Use proper markdown formatting with headers, code blocks, and lists.\n"
            "Explain concepts thoroughly but concisely.\n"
            'Focus on "how it works" and "how to use it".'
        ),
        Audience.COWORKERS: (
            "You are creating a team briefing document.\n"
            "Write in an accessible, professional tone.\n"
            "Avoid jargon or explain it when necessary.\n"
            "Highlight key decisions, blockers, and next steps.\n"
            "Include context that team members need to understand the topic.\n"
            "Use bullet points for easy reading in meetings."
        ),
    }

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL

    def synthesize_documents(
        self,
        documents: list[dict[str, Any]],
        topic: str | None = None,
        audience: Audience = Audience.ME,
        max_tokens: int = 4000,
    ) -> DistillResult:
        """Synthesize multiple documents into a coherent summary.

        Args:
            documents: List of document dicts with 'id', 'title', 'content' keys
            topic: Optional topic/query to focus the synthesis
            audience: Target audience for the output
            max_tokens: Maximum output tokens

        Returns:
            DistillResult with synthesized content and metadata
        """
        if not documents:
            return DistillResult(
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
                "Synthesize the following documents into a coherent summary "
                f"focused on: {topic}\n\n"
                "Extract and consolidate the most relevant information about "
                f'"{topic}" from all documents.\n'
                "Remove redundancy and create a unified, well-organized summary."
            )
        else:
            task_instruction = (
                "Synthesize the following documents into a coherent summary.\n\n"
                "Identify common themes and consolidate related information.\n"
                "Remove redundancy while preserving important details.\n"
                "Create a unified, well-organized summary."
            )

        system_prompt = f"{audience_instruction}\n\n{task_instruction}"
        user_message = f"Documents to synthesize:\n\n{context}"

        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            title=f"Distill: {topic or 'synthesis'}",
            model=self.model,
        )

        return DistillResult(
            content=result.output_content or "",
            source_ids=source_ids,
            source_count=len(documents),
            audience=audience,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    def distill_single(
        self,
        document: dict[str, Any],
        audience: Audience = Audience.ME,
        max_tokens: int = 2000,
    ) -> DistillResult:
        """Distill a single document into a shorter summary."""
        return self.synthesize_documents(
            documents=[document],
            topic=None,
            audience=audience,
            max_tokens=max_tokens,
        )


# =============================================================================
# Compact service (document merging/deduplication)
# =============================================================================


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
            RuntimeError: If CLI execution fails
        """
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

        system_prompt = (
            "You are a document synthesis expert. Your task is to "
            "intelligently merge\nmultiple related documents into a "
            "single, coherent document that:\n\n"
            "1. Preserves ALL key information, facts, and insights "
            "from the source documents\n"
            "2. Eliminates redundancy and repetition\n"
            "3. Organizes information logically with clear structure\n"
            "4. Maintains the original tone and technical level\n"
            "5. Uses markdown formatting for readability\n\n"
            "Your output should be a complete markdown document with:\n"
            "- A clear, descriptive title (as a level-1 heading)\n"
            "- Well-organized sections\n"
            '- No references to "the source documents" - write as a '
            "standalone document\n\n"
            "IMPORTANT: Start your response with the title as a markdown "
            "heading, then the content.\n"
            "Do not include any preamble or explanation - just the "
            "synthesized document."
        )
        user_message = (
            "Synthesize the following documents into a single "
            "coherent document.\n\n"
            f"{title_context}\n\n---\n\n{context}"
        )

        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            title=f"Compact: {titles[0]}",
            model=self.model,
        )

        content = result.output_content or ""
        title = self._extract_title(content, titles)

        return SynthesisResult(
            content=content,
            title=title,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            source_doc_ids=doc_ids,
        )

    def _fetch_documents(self, doc_ids: list[int]) -> list[dict]:
        """Fetch documents from database without updating access tracking."""
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
        """Extract title from synthesized content."""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()

        # Fallback: combine original titles
        if len(fallback_titles) == 1:
            return f"{fallback_titles[0]} (synthesized)"
        return (
            f"Synthesis: {fallback_titles[0]} + "
            f"{len(fallback_titles) - 1} more"
        )

    def estimate_cost(
        self,
        doc_ids: list[int],
    ) -> dict[str, float | int]:
        """Estimate the API cost for synthesizing documents."""
        documents = self._fetch_documents(doc_ids)
        if not documents:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            }

        # Estimate input tokens (rough approximation: 1 token ~ 4 characters)
        total_chars = sum(
            len(doc["title"]) + len(doc["content"]) for doc in documents
        )
        # Add overhead for prompts
        estimated_input_tokens = (total_chars // 4) + 500

        # Estimate output tokens (synthesis usually shorter than input)
        estimated_output_tokens = min(
            estimated_input_tokens // 2, self.MAX_TOKENS
        )

        # Claude Opus pricing: $15/M input, $75/M output
        input_cost = (estimated_input_tokens / 1_000_000) * 15
        output_cost = (estimated_output_tokens / 1_000_000) * 75
        estimated_cost = input_cost + output_cost

        return {
            "input_tokens": estimated_input_tokens,
            "output_tokens": estimated_output_tokens,
            "estimated_cost": round(estimated_cost, 4),
            "document_count": len(documents),
        }
