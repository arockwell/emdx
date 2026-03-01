"""
Q&A service for EMDX - RAG over your knowledge base.

Uses semantic search when available (embeddings indexed),
falls back to keyword search (FTS) otherwise.

Uses the Claude CLI (--print mode) for answer generation.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..database import db

if TYPE_CHECKING:
    from .embedding_service import ChunkMatch, EmbeddingService

# Type alias for SQL parameters used in dynamic query building
SqlParam = str | int | float

logger = logging.getLogger(__name__)

# Context budget: ~12000 chars (~3000 tokens) max for LLM context
CONTEXT_BUDGET_CHARS = 12000
# Expanded budget for --think mode which needs more context
THINK_CONTEXT_BUDGET_CHARS = 18000

ANSWER_TIMEOUT = 120  # seconds


class AskMode(Enum):
    """Mode for the ask service — determines system prompt and behavior."""

    ANSWER = "answer"
    THINK = "think"
    CHALLENGE = "challenge"
    DEBUG = "debug"


# ── System prompts for each mode ───────────────────────────────────────

SYSTEM_PROMPT_ANSWER = (
    "You answer questions using the provided knowledge base context.\n\n"
    "Rules:\n"
    "- Only answer based on the provided documents\n"
    "- Cite document IDs when referencing information "
    '(e.g., "According to Document #42...")\n'
    "- If the context doesn't contain relevant information, "
    "say so clearly\n"
    "- Be concise but complete\n"
    "- If documents contain conflicting information, "
    "note the discrepancy"
)

SYSTEM_PROMPT_THINK = (
    "You are a deliberative analyst building a position paper from "
    "the user's own knowledge base.\n\n"
    "Your task:\n"
    "1. **Organize evidence FOR** the queried position — cite "
    "specific doc IDs (e.g., [#42])\n"
    "2. **Organize evidence AGAINST** — cite doc IDs showing "
    "risks, past failures, or contradictions\n"
    "3. **Synthesize a reasoned position** that weighs both sides, "
    "noting which evidence is stronger and why\n"
    "4. **Identify counterarguments** the user should anticipate\n\n"
    "Format your response as:\n"
    "## Evidence For\n(bullet points with [#ID] citations)\n\n"
    "## Evidence Against\n(bullet points with [#ID] citations)\n\n"
    "## Synthesis\n(your reasoned position)\n\n"
    "## Counterarguments to Anticipate\n(bullet points)\n\n"
    "Rules:\n"
    "- Only use information from the provided documents\n"
    "- Every claim must cite at least one document ID\n"
    "- Be honest about gaps in the evidence\n"
    "- If the knowledge base lacks relevant information, say so"
)

SYSTEM_PROMPT_CHALLENGE = (
    "You are a devil's advocate. Your job is to find evidence "
    "AGAINST the queried position using the user's own knowledge "
    "base.\n\n"
    "Your task:\n"
    "1. **Find every piece of evidence** in the provided documents "
    "that contradicts, undermines, or complicates the position\n"
    "2. **Identify past failures** — failed attempts, abandoned "
    "efforts, or known pitfalls documented in the KB\n"
    "3. **Surface hidden assumptions** the position relies on\n"
    "4. **Propose the strongest counterargument** possible\n\n"
    "Format your response as:\n"
    "## Contradicting Evidence\n"
    "(bullet points with [#ID] citations)\n\n"
    "## Past Failures & Abandoned Efforts\n"
    "(bullet points with [#ID] citations, or 'None found' "
    "if absent)\n\n"
    "## Hidden Assumptions\n(bullet points)\n\n"
    "## Strongest Counterargument\n(a concise paragraph)\n\n"
    "Rules:\n"
    "- Only use information from the provided documents\n"
    "- Every claim must cite at least one document ID\n"
    "- Be maximally adversarial — find the strongest case against\n"
    "- If the KB lacks contradicting evidence, say so honestly"
)

SYSTEM_PROMPT_DEBUG = (
    "You are a Socratic debugging partner. Based on the user's "
    "knowledge base — which contains their past bugs, fixes, and "
    "technical notes — ask targeted diagnostic questions and "
    "reference relevant past incidents.\n\n"
    "Your task:\n"
    "1. **Identify matching patterns** — search the context for "
    "similar errors, symptoms, or affected components\n"
    "2. **Reference past incidents** — cite specific doc IDs where "
    "similar issues were resolved\n"
    "3. **Ask diagnostic questions** — numbered, targeted questions "
    "to narrow down the root cause\n"
    "4. **Suggest investigation steps** based on how similar issues "
    "were resolved before\n\n"
    "Format your response as:\n"
    "## Relevant Past Incidents\n"
    "(bullet points with [#ID] citations, or 'None found')\n\n"
    "## Diagnostic Questions\n"
    "(numbered list of targeted questions)\n\n"
    "## Suggested Investigation Steps\n"
    "(numbered list based on past resolutions)\n\n"
    "Rules:\n"
    "- Only reference information from the provided documents\n"
    "- Ask questions that narrow the search space, not generic ones\n"
    "- Prioritize questions based on what the KB suggests is most "
    "likely\n"
    "- If no relevant past incidents exist, say so and focus on "
    "diagnostic questions"
)

CITE_PROMPT_ADDITION = (
    "\n\nCITATION REQUIREMENT: Cite your sources inline using "
    "[#ID] format (e.g., [#42]). Every factual claim must have "
    "at least one citation. Use the chunk reference numbers "
    "provided in the context."
)

# ── Mode-to-prompt mapping ─────────────────────────────────────────────

_MODE_PROMPTS: dict[AskMode, str] = {
    AskMode.ANSWER: SYSTEM_PROMPT_ANSWER,
    AskMode.THINK: SYSTEM_PROMPT_THINK,
    AskMode.CHALLENGE: SYSTEM_PROMPT_CHALLENGE,
    AskMode.DEBUG: SYSTEM_PROMPT_DEBUG,
}

_MODE_TITLES: dict[AskMode, str] = {
    AskMode.ANSWER: "Ask",
    AskMode.THINK: "Think",
    AskMode.CHALLENGE: "Challenge",
    AskMode.DEBUG: "Debug",
}

# ── Confidence scoring ─────────────────────────────────────────────────

CONFIDENCE_HIGH = 0.7
CONFIDENCE_MEDIUM = 0.4
CONFIDENCE_LOW = 0.2


@dataclass
class ConfidenceSignals:
    """Individual signals used to calculate confidence."""

    retrieval_score_mean: float = 0.0
    retrieval_score_spread: float = 0.0
    source_count: int = 0
    query_term_coverage: float = 0.0
    topic_coherence: float = 0.0
    recency_score: float = 0.0

    @property
    def composite_score(self) -> float:
        """Weighted combination of all signals into 0-1 score."""
        # Weights: source count and retrieval quality matter most
        weights = {
            "retrieval_score_mean": 0.25,
            "source_count": 0.25,
            "query_term_coverage": 0.20,
            "topic_coherence": 0.10,
            "recency_score": 0.10,
            "retrieval_score_spread": 0.10,
        }
        # Normalize source count to 0-1 (5+ sources = 1.0)
        source_norm = min(self.source_count / 5.0, 1.0)
        # Invert spread — low spread = high confidence
        spread_score = max(0.0, 1.0 - self.retrieval_score_spread * 2)

        raw = (
            weights["retrieval_score_mean"] * self.retrieval_score_mean
            + weights["source_count"] * source_norm
            + weights["query_term_coverage"] * self.query_term_coverage
            + weights["topic_coherence"] * self.topic_coherence
            + weights["recency_score"] * self.recency_score
            + weights["retrieval_score_spread"] * spread_score
        )
        return min(max(raw, 0.0), 1.0)

    @property
    def level(self) -> str:
        """Convert composite score to level string."""
        score = self.composite_score
        if score >= CONFIDENCE_HIGH:
            return "high"
        elif score >= CONFIDENCE_MEDIUM:
            return "medium"
        elif score >= CONFIDENCE_LOW:
            return "low"
        else:
            return "insufficient"


def _has_claude_cli() -> bool:
    """Check if the Claude CLI is available."""
    return shutil.which("claude") is not None


def _execute_claude_prompt(
    system_prompt: str,
    user_message: str,
    title: str,
    model: str | None = None,
) -> str:
    """Execute a Q&A prompt via the Claude CLI --print mode.

    Combines system and user messages into a single prompt
    for --print mode.

    Returns:
        The answer text from Claude.

    Raises:
        RuntimeError: If the CLI execution fails.
    """
    prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_message}"

    cmd = ["claude", "--print", prompt]
    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ANSWER_TIMEOUT,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"Exit code {result.returncode}"
            raise RuntimeError(f"Answer generation failed: {error_msg}")

        return result.stdout.strip()
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Answer generation timed out after {ANSWER_TIMEOUT}s") from e


@dataclass
class Answer:
    """An answer from the knowledge base."""

    text: str
    sources: list[int]  # Document IDs used
    source_titles: list[tuple[int, str]]  # (doc_id, title) pairs
    method: str  # "semantic" or "keyword"
    context_size: int  # Characters of context used
    confidence: str  # "high", "medium", "low", or "insufficient"
    mode: AskMode = AskMode.ANSWER
    confidence_signals: ConfidenceSignals | None = None
    cited_ids: list[int] = field(default_factory=list)


class AskService:
    """Answer questions using your knowledge base."""

    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
    MIN_EMBEDDINGS_FOR_SEMANTIC = 50

    def __init__(self, model: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self._embedding_service: EmbeddingService | None = None

    def _get_embedding_service(self) -> EmbeddingService | None:
        if self._embedding_service is None:
            try:
                from .embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except ImportError:
                logger.warning("sentence-transformers not installed, semantic search unavailable")
                return None
        return self._embedding_service

    def _has_embeddings(self) -> bool:
        """Check if we have enough embeddings for semantic search."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return False

        try:
            stats = embedding_service.stats()
            return bool(stats.indexed_documents >= self.MIN_EMBEDDINGS_FOR_SEMANTIC)
        except Exception as e:
            logger.debug(f"Could not check embedding stats: {e}")
            return False

    def ask(
        self,
        question: str,
        limit: int = 10,
        project: str | None = None,
        force_keyword: bool = False,
        tags: str | None = None,
        recent_days: int | None = None,
        mode: AskMode = AskMode.ANSWER,
        cite: bool = False,
    ) -> Answer:
        """
        Ask a question about your knowledge base.

        Args:
            question: The question to answer
            limit: Max documents to retrieve
            project: Limit to specific project
            force_keyword: Force keyword search even if embeddings
            tags: Comma-separated tags to filter by
            recent_days: Limit to documents created in last N days
            mode: AskMode determining system prompt behavior
            cite: If True, use chunk-level retrieval for citations
        """
        # Think/challenge modes retrieve more broadly
        effective_limit = limit
        if mode in (AskMode.THINK, AskMode.CHALLENGE):
            effective_limit = max(limit, 20)

        # Choose retrieval method
        if force_keyword or not self._has_embeddings():
            docs, method = self._retrieve_keyword(
                question,
                effective_limit,
                project,
                tags=tags,
                recent_days=recent_days,
            )
        else:
            docs, method = self._retrieve_semantic(
                question,
                effective_limit,
                project,
                tags=tags,
                recent_days=recent_days,
            )

        # Optionally retrieve chunks for cite mode
        chunks: list[ChunkMatch] = []
        if cite:
            chunks = self._retrieve_chunks(question, limit=effective_limit * 3)

        # Generate answer with mode-specific prompt
        answer_text, context_size = self._generate_answer(
            question, docs, mode=mode, cite=cite, chunks=chunks
        )

        # Calculate multi-signal confidence
        signals = self._calculate_confidence_signals(question, docs, method)

        # Post-process citations if cite mode
        cited_ids: list[int] = []
        if cite:
            source_ids = {d[0] for d in docs}
            chunk_ids = {c.doc_id for c in chunks}
            valid_ids = source_ids | chunk_ids
            cited_ids = _extract_cited_ids(answer_text, valid_ids)

        # Build source titles list
        source_titles = [(d[0], d[1]) for d in docs]

        return Answer(
            text=answer_text,
            sources=[d[0] for d in docs],
            source_titles=source_titles,
            method=method,
            context_size=context_size,
            confidence=signals.level,
            mode=mode,
            confidence_signals=signals,
            cited_ids=cited_ids,
        )

    def _calculate_confidence_signals(
        self,
        question: str,
        docs: list[tuple[int, str, str]],
        method: str,
    ) -> ConfidenceSignals:
        """Calculate multi-signal confidence assessment.

        6 signals:
        1. Retrieval score mean (semantic similarity)
        2. Retrieval score spread (std dev)
        3. Source count
        4. Query term coverage
        5. Topic coherence (avg pairwise similarity)
        6. Recency score (newer docs = higher)
        """
        signals = ConfidenceSignals(source_count=len(docs))

        if not docs:
            return signals

        # Signal 1 & 2: Retrieval scores (only for semantic)
        if method == "semantic":
            scores = self._get_retrieval_scores(question, docs)
            if scores:
                signals.retrieval_score_mean = sum(scores) / len(scores)
                if len(scores) > 1:
                    mean = signals.retrieval_score_mean
                    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
                    signals.retrieval_score_spread = math.sqrt(variance)
        else:
            # For keyword search, use a baseline score
            signals.retrieval_score_mean = 0.5

        # Signal 4: Query term coverage
        signals.query_term_coverage = _calculate_query_term_coverage(question, docs)

        # Signal 5: Topic coherence (simplified — keyword overlap)
        signals.topic_coherence = _calculate_topic_coherence(docs)

        # Signal 6: Recency
        signals.recency_score = self._calculate_recency(docs)

        return signals

    def _get_retrieval_scores(
        self,
        question: str,
        docs: list[tuple[int, str, str]],
    ) -> list[float]:
        """Get similarity scores for docs against the question."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return []

        try:
            doc_ids = {d[0] for d in docs}
            matches = embedding_service.search(question, limit=len(docs) * 2)
            return [m.similarity for m in matches if m.doc_id in doc_ids]
        except Exception as e:
            logger.debug(f"Could not get retrieval scores: {e}")
            return []

    def _calculate_recency(self, docs: list[tuple[int, str, str]]) -> float:
        """Calculate recency score based on doc creation dates.

        Returns 0-1 where 1.0 = all docs created in last 7 days.
        """
        doc_ids = [d[0] for d in docs]
        if not doc_ids:
            return 0.0

        placeholders = ", ".join("?" * len(doc_ids))
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Score: fraction of docs created in last 30 days
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM documents
                WHERE id IN ({placeholders})
                AND created_at > datetime('now', '-30 days')
                """,
                doc_ids,
            )
            recent_count: int = cursor.fetchone()[0]

        return min(recent_count / max(len(doc_ids), 1), 1.0)

    def _calculate_confidence(self, source_count: int) -> str:
        """Calculate confidence level based on number of sources.

        Legacy method — kept for backward compatibility.
        Prefer _calculate_confidence_signals() for new code.
        """
        if source_count >= 3:
            return "high"
        elif source_count >= 1:
            return "medium"
        else:
            return "low"

    def _get_filtered_doc_ids(
        self,
        tags: str | None = None,
        recent_days: int | None = None,
        project: str | None = None,
    ) -> set[int] | None:
        """
        Get document IDs matching tag and recency filters.

        Returns None if no filters applied (all docs match).
        Returns empty set if filters applied but no docs match.
        """
        if not tags and not recent_days:
            return None  # No filtering needed

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Start with all non-deleted docs
            base_conditions = ["d.is_deleted = 0"]
            params: list[SqlParam] = []

            if project:
                base_conditions.append("d.project = ?")
                params.append(project)

            # Recent days filter
            if recent_days:
                base_conditions.append("d.created_at > datetime('now', ?)")
                params.append(f"-{recent_days} days")

            # Tag filter
            if tags:
                tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

                if tag_list:
                    placeholders = ", ".join("?" * len(tag_list))
                    query = f"""
                        SELECT d.id FROM documents d
                        JOIN document_tags dt
                            ON d.id = dt.document_id
                        JOIN tags t ON dt.tag_id = t.id
                        WHERE {" AND ".join(base_conditions)}
                        AND t.name IN ({placeholders})
                        GROUP BY d.id
                        HAVING COUNT(DISTINCT t.name) = ?
                    """
                    params.extend(tag_list)
                    params.append(len(tag_list))

                    cursor.execute(query, params)
                    return {row[0] for row in cursor.fetchall()}

            # No tags, just recent filter
            query = f"""
                SELECT d.id FROM documents d
                WHERE {" AND ".join(base_conditions)}
            """
            cursor.execute(query, params)
            return {row[0] for row in cursor.fetchall()}

    def _retrieve_keyword(
        self,
        question: str,
        limit: int,
        project: str | None = None,
        tags: str | None = None,
        recent_days: int | None = None,
    ) -> tuple[list[tuple[int, str, str]], str]:
        """Retrieve documents using FTS keyword search."""
        docs: list[tuple[int, str, str]] = []
        seen: set[int] = set()

        filtered_ids = self._get_filtered_doc_ids(tags, recent_days, project)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            def passes_filter(doc_id: int) -> bool:
                if filtered_ids is None:
                    return True
                return doc_id in filtered_ids

            # 1. Extract and search for explicit references
            ticket_refs = re.findall(r"[A-Z]{2,10}-\d+", question)
            doc_refs = re.findall(r"#(\d+)", question)

            for doc_id in doc_refs:
                try:
                    doc_id_int = int(doc_id)
                    cursor.execute(
                        "SELECT id, title, content FROM documents WHERE id = ? AND is_deleted = 0",
                        (doc_id_int,),
                    )
                    row = cursor.fetchone()
                    if row and row[0] not in seen and passes_filter(row[0]):
                        docs.append(row)
                        seen.add(row[0])
                except ValueError:
                    pass

            for ticket in ticket_refs:
                query = (
                    "SELECT id, title, content "
                    "FROM documents "
                    "WHERE content LIKE ? AND is_deleted = 0"
                )
                params: list[SqlParam] = [f"%{ticket}%"]

                if project:
                    query += " AND project = ?"
                    params.append(project)

                query += " LIMIT 3"
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    if row[0] not in seen and passes_filter(row[0]):
                        docs.append(row)
                        seen.add(row[0])

            # 2. FTS search for question terms
            terms = re.sub(r"[^\w\s]", " ", question).strip()
            if terms and len(docs) < limit:
                query = """
                    SELECT d.id, d.title, d.content
                    FROM documents d
                    JOIN documents_fts fts ON d.id = fts.rowid
                    WHERE fts.documents_fts MATCH ?
                    AND d.is_deleted = 0
                """
                fts_params: list[SqlParam] = [terms]

                if project:
                    query += " AND d.project = ?"
                    fts_params.append(project)

                query += " ORDER BY rank LIMIT ?"
                fts_params.append((limit - len(docs)) * 3)

                try:
                    cursor.execute(query, fts_params)
                    for row in cursor.fetchall():
                        if row[0] not in seen and passes_filter(row[0]):
                            docs.append(row)
                            seen.add(row[0])
                            if len(docs) >= limit:
                                break
                except Exception as e:
                    logger.debug(f"FTS search failed: {e}")

            # 3. Fallback to recent docs if nothing found
            if not docs:
                query = """
                    SELECT id, title, content
                    FROM documents
                    WHERE is_deleted = 0
                """
                fallback_params: list[SqlParam] = []

                if project:
                    query += " AND project = ?"
                    fallback_params.append(project)

                query += " ORDER BY updated_at DESC LIMIT ?"
                fallback_params.append(limit * 3)

                cursor.execute(query, fallback_params)
                for row in cursor.fetchall():
                    if passes_filter(row[0]):
                        docs.append(row)
                        if len(docs) >= limit:
                            break

        return docs[:limit], "keyword"

    def _retrieve_semantic(
        self,
        question: str,
        limit: int,
        project: str | None = None,
        tags: str | None = None,
        recent_days: int | None = None,
    ) -> tuple[list[tuple[int, str, str]], str]:
        """Retrieve documents using semantic (embedding) search."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return self._retrieve_keyword(question, limit, project, tags, recent_days)

        filtered_ids = self._get_filtered_doc_ids(tags, recent_days, project)

        try:
            matches = embedding_service.search(question, limit=limit * 3)

            docs: list[tuple[int, str, str]] = []
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for match in matches:
                    if filtered_ids is not None and match.doc_id not in filtered_ids:
                        continue

                    query = "SELECT id, title, content FROM documents WHERE id = ?"
                    sem_params: list[SqlParam] = [match.doc_id]

                    if project:
                        query += " AND project = ?"
                        sem_params.append(project)

                    cursor.execute(query, sem_params)
                    row = cursor.fetchone()
                    if row:
                        docs.append(row)

                    if len(docs) >= limit:
                        break

            if docs:
                return docs, "semantic"

            return self._retrieve_keyword(question, limit, project, tags, recent_days)

        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            return self._retrieve_keyword(question, limit, project, tags, recent_days)

    def _retrieve_chunks(
        self,
        question: str,
        limit: int = 30,
    ) -> list[ChunkMatch]:
        """Retrieve chunk-level matches for citation mode."""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return []

        try:
            return embedding_service.search_chunks(question, limit=limit)
        except Exception as e:
            logger.debug(f"Chunk retrieval failed: {e}")
            return []

    def _generate_answer(
        self,
        question: str,
        docs: list[tuple[int, str, str]],
        mode: AskMode = AskMode.ANSWER,
        cite: bool = False,
        chunks: list[ChunkMatch] | None = None,
    ) -> tuple[str, int]:
        """Generate answer from retrieved documents."""
        if not docs:
            return (
                "I couldn't find any relevant documents to "
                "answer this question. Try rephrasing or check "
                "if you have documents on this topic.",
                0,
            )

        if not _has_claude_cli():
            raise ImportError(
                "Claude CLI is required for AI Q&A features. "
                "Install it from: "
                "https://docs.anthropic.com/claude-code"
            )

        # Select context budget based on mode
        budget = (
            THINK_CONTEXT_BUDGET_CHARS
            if mode in (AskMode.THINK, AskMode.CHALLENGE)
            else CONTEXT_BUDGET_CHARS
        )

        # Build context — use chunks if cite mode, else docs
        if cite and chunks:
            context, context_size = _build_chunk_context(chunks, docs, budget)
        else:
            context, context_size = _build_doc_context(docs, budget)

        # Select system prompt for mode
        system_prompt = _MODE_PROMPTS[mode]
        if cite:
            system_prompt += CITE_PROMPT_ADDITION

        # Build user message
        mode_label = _MODE_TITLES[mode]
        if mode == AskMode.DEBUG:
            user_label = "Error/Issue"
        elif mode in (AskMode.THINK, AskMode.CHALLENGE):
            user_label = "Position to analyze"
        else:
            user_label = "Question"

        user_message = (
            f"Context from my knowledge base:\n\n{context}\n\n---\n\n{user_label}: {question}"
        )

        try:
            result = _execute_claude_prompt(
                system_prompt=system_prompt,
                user_message=user_message,
                title=f"{mode_label}: {question[:50]}",
                model=self.model,
            )
            return result, context_size
        except RuntimeError as e:
            logger.error(f"Claude CLI error: {e}")
            return f"Error generating answer: {e}", context_size


# ── Helper functions ───────────────────────────────────────────────────


def _build_doc_context(
    docs: list[tuple[int, str, str]],
    budget: int,
) -> tuple[str, int]:
    """Build context string from documents with budget."""
    context_parts: list[str] = []
    total_chars = 0

    for doc_id, title, content in docs:
        remaining_budget = budget - total_chars

        if remaining_budget <= 0:
            logger.debug(f"Context budget exhausted, skipping doc #{doc_id}")
            break

        max_doc_chars = min(3000, remaining_budget - 100)
        if max_doc_chars <= 100:
            break

        truncated = content[:max_doc_chars] if len(content) > max_doc_chars else content
        doc_context = f"# Document #{doc_id}: {title}\n\n{truncated}"
        context_parts.append(doc_context)
        total_chars += len(doc_context) + 10

    context = "\n\n---\n\n".join(context_parts)
    return context, len(context)


def _build_chunk_context(
    chunks: list[ChunkMatch],
    docs: list[tuple[int, str, str]],
    budget: int,
) -> tuple[str, int]:
    """Build context from chunks with [#ID] references."""
    context_parts: list[str] = []
    total_chars = 0
    seen_doc_ids: set[int] = set()

    # First, add chunk-level context
    for chunk in chunks:
        remaining = budget - total_chars
        if remaining <= 200:
            break

        heading = chunk.display_heading
        header = f"[#{chunk.doc_id}]"
        if heading:
            header += f" {heading}"
        header += f' (from "{chunk.title}")'

        text = chunk.chunk_text[: min(1500, remaining - 100)]
        part = f"{header}\n{text}"
        context_parts.append(part)
        total_chars += len(part) + 10
        seen_doc_ids.add(chunk.doc_id)

    # Add any docs not covered by chunks (summary only)
    for doc_id, title, content in docs:
        if doc_id in seen_doc_ids:
            continue
        remaining = budget - total_chars
        if remaining <= 200:
            break

        summary = content[:500]
        part = f'[#{doc_id}] "{title}"\n{summary}'
        context_parts.append(part)
        total_chars += len(part) + 10

    context = "\n\n---\n\n".join(context_parts)
    return context, len(context)


def _extract_cited_ids(text: str, valid_ids: set[int]) -> list[int]:
    """Extract [#ID] citations from answer text.

    Only returns IDs that exist in the provided context.
    """
    pattern = re.compile(r"\[#(\d+)\]")
    cited = []
    seen: set[int] = set()
    for match in pattern.finditer(text):
        doc_id = int(match.group(1))
        if doc_id in valid_ids and doc_id not in seen:
            cited.append(doc_id)
            seen.add(doc_id)
    return cited


def _calculate_query_term_coverage(question: str, docs: list[tuple[int, str, str]]) -> float:
    """Calculate what % of query terms appear in retrieved docs."""
    terms = set(re.sub(r"[^\w\s]", " ", question).lower().split())
    # Remove stop words
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "and",
        "or",
        "not",
        "it",
        "this",
        "that",
        "my",
        "i",
        "we",
        "you",
        "how",
        "what",
        "why",
        "when",
        "where",
        "do",
        "does",
        "did",
        "should",
        "would",
        "could",
        "can",
        "will",
        "be",
        "have",
        "has",
    }
    terms -= stop_words

    if not terms:
        return 1.0  # No meaningful terms = vacuously true

    # Combine all doc content
    all_content = " ".join(f"{title} {content}".lower() for _, title, content in docs)

    covered = sum(1 for t in terms if t in all_content)
    return covered / len(terms)


def _calculate_topic_coherence(
    docs: list[tuple[int, str, str]],
) -> float:
    """Calculate topic coherence via keyword overlap.

    Uses Jaccard similarity between doc keyword sets,
    averaged over all pairs. Higher = docs are about
    the same topic.
    """
    if len(docs) < 2:
        return 1.0  # Single doc is perfectly coherent

    # Extract keyword sets per doc (title + first 500 chars)
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "and",
        "or",
        "not",
        "it",
        "this",
        "that",
    }
    doc_keywords: list[set[str]] = []
    for _, title, content in docs:
        words = set(
            re.sub(
                r"[^\w\s]",
                " ",
                f"{title} {content[:500]}",
            )
            .lower()
            .split()
        )
        words -= stop_words
        doc_keywords.append(words)

    # Average pairwise Jaccard similarity
    similarities: list[float] = []
    for i in range(len(doc_keywords)):
        for j in range(i + 1, len(doc_keywords)):
            a, b = doc_keywords[i], doc_keywords[j]
            if not a and not b:
                similarities.append(1.0)
            elif not a or not b:
                similarities.append(0.0)
            else:
                jaccard = len(a & b) / len(a | b)
                similarities.append(jaccard)

    return sum(similarities) / len(similarities) if similarities else 0.0
