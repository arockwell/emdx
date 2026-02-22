"""Wiki article synthesis service.

Generates wiki articles from topic clusters by feeding source documents
through a 6-step pipeline:

1. PREPARE  — gather source docs, pre-process with privacy filter
2. ROUTE    — decide synthesis strategy (stuff vs hierarchical)
3. OUTLINE  — generate article structure from entity/cluster data
4. WRITE    — LLM synthesis with privacy-aware prompt
5. VALIDATE — post-scan for leaked sensitive data
6. SAVE     — store as emdx document + wiki_articles metadata

Articles are stored as regular emdx documents (tagged ``wiki-article``)
so they get free FTS5, embeddings, links, and TUI browsing.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field

from ..database import db
from ..database.documents import save_document
from ..database.types import WikiArticleTimingDict
from .wiki_clustering_service import get_topic_docs, get_topics
from .wiki_privacy_service import (
    build_privacy_prompt_section,
    postprocess_validate,
    preprocess_content,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

# Max chars per source document before truncation
MAX_DOC_CHARS = 12_000

# Max total source chars before switching to hierarchical strategy
STUFF_THRESHOLD_CHARS = 80_000

# Default model — Sonnet for speed/cost balance on bulk generation
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Wiki article tag applied to all generated articles
WIKI_ARTICLE_TAG = "wiki-article"

# Max articles to generate in one batch
DEFAULT_BATCH_LIMIT = 10


@dataclass
class ArticleSource:
    """A source document prepared for synthesis."""

    doc_id: int
    title: str
    content: str  # pre-processed (privacy-filtered)
    content_hash: str
    char_count: int
    relevance_score: float = 1.0


@dataclass
class SynthesisOutline:
    """Generated outline for an article."""

    topic_label: str
    topic_slug: str
    suggested_title: str
    section_hints: list[str]
    entity_focus: list[str]
    strategy: str  # "stuff" or "hierarchical"


@dataclass
class WikiArticleResult:
    """Result of generating a single wiki article."""

    topic_id: int
    topic_label: str
    document_id: int  # the emdx doc ID where article was saved
    article_id: int  # the wiki_articles row ID
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    timing: WikiArticleTimingDict | None = None


@dataclass
class WikiGenerationResult:
    """Result of a batch wiki generation run."""

    articles_generated: int
    articles_skipped: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    results: list[WikiArticleResult] = field(default_factory=list)


# ── Step 1: PREPARE ──────────────────────────────────────────────────


def _prepare_sources(doc_ids: list[int], topic_id: int | None = None) -> list[ArticleSource]:
    """Fetch and pre-process source documents for synthesis.

    Applies Layer 1 privacy filtering and computes content hashes
    for staleness tracking. When *topic_id* is given, relevance_score
    from wiki_topic_members is used to scale each source's content
    contribution (truncating to ``MAX_DOC_CHARS * relevance_score``).
    """
    sources: list[ArticleSource] = []

    # Fetch relevance scores if topic_id provided
    weight_map: dict[int, float] = {}
    if topic_id is not None:
        with db.get_connection() as conn:
            weight_rows = conn.execute(
                "SELECT document_id, relevance_score FROM wiki_topic_members WHERE topic_id = ?",
                (topic_id,),
            ).fetchall()
        weight_map = {row[0]: row[1] for row in weight_rows}

    with db.get_connection() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        cursor = conn.execute(
            f"SELECT id, title, content FROM documents "
            f"WHERE id IN ({placeholders}) AND is_deleted = 0 "
            f"ORDER BY id",
            doc_ids,
        )
        rows = cursor.fetchall()

    for row in rows:
        doc_id, title, content = row[0], row[1], row[2]
        relevance = weight_map.get(doc_id, 1.0)

        # Apply Layer 1 privacy filtering
        filtered, warnings = preprocess_content(content)
        if warnings:
            logger.info("Doc #%d pre-processing: %s", doc_id, ", ".join(warnings))

        # Scale max chars by relevance_score
        effective_max = int(MAX_DOC_CHARS * relevance)
        if effective_max <= 0:
            continue
        if len(filtered) > effective_max:
            filtered = filtered[:effective_max] + "\n\n[... content truncated ...]"

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        sources.append(
            ArticleSource(
                doc_id=doc_id,
                title=title,
                content=filtered,
                content_hash=content_hash,
                char_count=len(filtered),
                relevance_score=relevance,
            )
        )

    return sources


# ── Step 2: ROUTE ─────────────────────────────────────────────────────


def _route_strategy(sources: list[ArticleSource]) -> str:
    """Decide synthesis strategy based on total source size.

    Returns "stuff" if all sources fit in a single context window,
    or "hierarchical" for large clusters needing chunk-then-merge.
    """
    total_chars = sum(s.char_count for s in sources)
    if total_chars <= STUFF_THRESHOLD_CHARS:
        return "stuff"
    return "hierarchical"


# ── Step 3: OUTLINE ───────────────────────────────────────────────────


def _build_outline(
    topic_label: str,
    topic_slug: str,
    top_entities: list[str],
    source_count: int,
    strategy: str,
) -> SynthesisOutline:
    """Build a synthesis outline from cluster metadata.

    The outline guides the LLM on what sections to produce and
    which entities to emphasize.
    """
    # Generate suggested title from topic label
    # Clean up slash-separated entity labels into a readable title
    parts = [p.strip() for p in topic_label.split("/")]
    if len(parts) >= 3:
        suggested_title = f"{parts[0]}: {parts[1]} and {parts[2]}"
    elif len(parts) == 2:
        suggested_title = f"{parts[0]} and {parts[1]}"
    else:
        suggested_title = parts[0]

    # Build section hints based on entity types and count
    section_hints = ["Overview", "Key Concepts"]
    if source_count >= 5:
        section_hints.append("Architecture & Design Decisions")
    if source_count >= 8:
        section_hints.append("Implementation Details")
    section_hints.append("Related Topics")

    return SynthesisOutline(
        topic_label=topic_label,
        topic_slug=topic_slug,
        suggested_title=suggested_title,
        section_hints=section_hints,
        entity_focus=top_entities[:8],
        strategy=strategy,
    )


# ── Step 4: WRITE ─────────────────────────────────────────────────────


def _build_synthesis_prompt(
    outline: SynthesisOutline,
    sources: list[ArticleSource],
    audience: str = "team",
    editorial_prompt: str | None = None,
) -> tuple[str, str]:
    """Build the system and user prompts for wiki article synthesis.

    Returns (system_prompt, user_message).
    """
    privacy_section = build_privacy_prompt_section(audience)

    system_prompt = (
        "You are a technical wiki author. Your task is to synthesize "
        "multiple knowledge base documents into a single, coherent wiki article.\n\n"
        "## Output Format\n"
        "Write a complete markdown article with:\n"
        f'- Title as a level-1 heading (suggested: "{outline.suggested_title}")\n'
        "- Well-organized sections with level-2 headings\n"
        "- Code examples preserved verbatim from sources\n"
        "- No references to 'the source documents' — write as standalone content\n\n"
        "## Section Structure\n"
        f"Suggested sections: {', '.join(outline.section_hints)}\n"
        "Adapt as needed based on the actual content.\n\n"
        "## Key Entities to Emphasize\n"
        f"These are the most important concepts for this topic: "
        f"{', '.join(outline.entity_focus)}\n"
        "Ensure these are well-covered in the article.\n\n"
        f"{privacy_section}\n"
        "## Important Rules\n"
        "- Start directly with the markdown title. No preamble.\n"
        "- Consolidate redundant information across sources.\n"
        "- Preserve technical accuracy — don't hallucinate details.\n"
        "- Keep code snippets, commands, and configs verbatim.\n"
        "- If sources disagree, note the discrepancy.\n"
    )

    if editorial_prompt:
        system_prompt += f"\n## Editorial Guidance\n{editorial_prompt}\n"

    # Build source document context
    source_parts: list[str] = []
    for src in sources:
        source_parts.append(f"### Source #{src.doc_id}: {src.title}\n\n{src.content}")
    source_context = "\n\n---\n\n".join(source_parts)

    user_message = (
        f"Synthesize these {len(sources)} documents about "
        f'"{outline.topic_label}" into a wiki article.\n\n'
        f"{source_context}"
    )

    return system_prompt, user_message


def _synthesize_article(
    outline: SynthesisOutline,
    sources: list[ArticleSource],
    audience: str = "team",
    model: str | None = None,
    editorial_prompt: str | None = None,
) -> tuple[str, int, int, float]:
    """Run LLM synthesis to generate the wiki article.

    Returns (article_content, input_tokens, output_tokens, cost_usd).
    """
    from .synthesis_service import _execute_prompt

    system_prompt, user_message = _build_synthesis_prompt(
        outline, sources, audience, editorial_prompt=editorial_prompt
    )

    result = _execute_prompt(
        system_prompt=system_prompt,
        user_message=user_message,
        title=f"Wiki: {outline.suggested_title}",
        model=model or DEFAULT_MODEL,
    )

    content = result.output_content or ""

    # Estimate cost based on model
    used_model = model or DEFAULT_MODEL
    if "opus" in used_model:
        input_price = 15.0  # per 1M tokens
        output_price = 75.0
    elif "haiku" in used_model:
        input_price = 0.25
        output_price = 1.25
    else:  # sonnet
        input_price = 3.0
        output_price = 15.0

    cost = (result.input_tokens / 1_000_000) * input_price + (
        result.output_tokens / 1_000_000
    ) * output_price

    return content, result.input_tokens, result.output_tokens, cost


def _synthesize_hierarchical(
    outline: SynthesisOutline,
    sources: list[ArticleSource],
    audience: str = "team",
    model: str | None = None,
    editorial_prompt: str | None = None,
) -> tuple[str, int, int, float]:
    """Hierarchical synthesis for large clusters.

    Splits sources into chunks, synthesizes each chunk, then
    merges the chunk summaries into a final article.
    """
    from .synthesis_service import _execute_prompt

    chunk_size = 5
    chunks = [sources[i : i + chunk_size] for i in range(0, len(sources), chunk_size)]

    chunk_summaries: list[str] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0

    # Phase 1: Summarize each chunk
    for i, chunk in enumerate(chunks):
        system_prompt = (
            "Summarize these documents into a concise overview, "
            "preserving key facts, code snippets, and decisions. "
            "This summary will be combined with others to create a wiki article.\n"
            f"Topic: {outline.topic_label}\n"
            "Write 500-1000 words. Start directly with content, no preamble."
        )

        source_parts = [f"### Source #{s.doc_id}: {s.title}\n\n{s.content}" for s in chunk]
        user_message = "\n\n---\n\n".join(source_parts)

        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            title=f"Wiki chunk {i + 1}/{len(chunks)}: {outline.topic_label}",
            model=model or DEFAULT_MODEL,
        )

        chunk_summaries.append(result.output_content or "")
        total_input += result.input_tokens
        total_output += result.output_tokens

    # Phase 2: Merge chunk summaries into final article
    merge_sources = [
        ArticleSource(
            doc_id=0,
            title=f"Chunk {i + 1} Summary",
            content=summary,
            content_hash="",
            char_count=len(summary),
        )
        for i, summary in enumerate(chunk_summaries)
    ]

    content, merge_input, merge_output, merge_cost = _synthesize_article(
        outline, merge_sources, audience, model, editorial_prompt=editorial_prompt
    )

    total_input += merge_input
    total_output += merge_output

    # Calculate total cost
    used_model = model or DEFAULT_MODEL
    if "opus" in used_model:
        input_price, output_price = 15.0, 75.0
    elif "haiku" in used_model:
        input_price, output_price = 0.25, 1.25
    else:
        input_price, output_price = 3.0, 15.0

    total_cost = (total_input / 1_000_000) * input_price + (total_output / 1_000_000) * output_price

    return content, total_input, total_output, total_cost


# ── Step 5: VALIDATE ──────────────────────────────────────────────────


def _validate_article(content: str) -> tuple[str, list[str]]:
    """Apply Layer 3 post-processing validation.

    Re-scans LLM output for any leaked sensitive data.
    """
    return postprocess_validate(content)


# ── Step 6: SAVE ──────────────────────────────────────────────────────


def _compute_source_hash(sources: list[ArticleSource]) -> str:
    """Compute a combined hash of all source documents.

    Used for staleness detection — if sources change, the article
    needs regeneration.
    """
    combined = ",".join(
        f"{s.doc_id}:{s.content_hash}" for s in sorted(sources, key=lambda s: s.doc_id)
    )
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def _save_article(
    topic_id: int,
    content: str,
    outline: SynthesisOutline,
    sources: list[ArticleSource],
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    timing: WikiArticleTimingDict | None = None,
) -> tuple[int, int]:
    """Save generated article as an emdx document and create metadata.

    Returns (document_id, article_id).
    """
    source_hash = _compute_source_hash(sources)

    timing_cols = ""
    timing_vals: list[int] = []
    if timing:
        timing_cols = (
            ", prepare_ms = ?, route_ms = ?, outline_ms = ?"
            ", write_ms = ?, validate_ms = ?, save_ms = ?"
        )
        timing_vals = [
            timing["prepare_ms"],
            timing["route_ms"],
            timing["outline_ms"],
            timing["write_ms"],
            timing["validate_ms"],
            timing["save_ms"],
        ]

    # Check if an article already exists for this topic
    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT wa.id, wa.document_id FROM wiki_articles wa WHERE wa.topic_id = ?",
            (topic_id,),
        ).fetchone()

    if existing:
        article_id, doc_id = existing[0], existing[1]
        # Stash current content before overwriting
        with db.get_connection() as conn:
            old_row = conn.execute(
                "SELECT content FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            old_content = old_row[0] if old_row else ""

            # Update existing document content
            conn.execute(
                "UPDATE documents SET content = ?, title = ?, "
                "doc_type = 'wiki', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (content, outline.suggested_title, doc_id),
            )
            # Update article metadata with previous content stashed
            conn.execute(
                "UPDATE wiki_articles SET source_hash = ?, model = ?, "
                "input_tokens = ?, output_tokens = ?, cost_usd = ?, "
                "is_stale = 0, stale_reason = '', "
                "previous_content = ?, "
                f"version = version + 1, generated_at = CURRENT_TIMESTAMP{timing_cols} "
                "WHERE id = ?",
                [source_hash, model, input_tokens, output_tokens, cost_usd, old_content]
                + timing_vals
                + [article_id],
            )
            # Replace source provenance
            conn.execute(
                "DELETE FROM wiki_article_sources WHERE article_id = ?",
                (article_id,),
            )
            for src in sources:
                conn.execute(
                    "INSERT INTO wiki_article_sources "
                    "(article_id, document_id, content_hash) VALUES (?, ?, ?)",
                    (article_id, src.doc_id, src.content_hash),
                )
            conn.commit()
        return doc_id, article_id

    # Create new document
    doc_id = save_document(
        title=outline.suggested_title,
        content=content,
        tags=[WIKI_ARTICLE_TAG],
        doc_type="wiki",
    )

    # Build INSERT with optional timing columns
    insert_cols = (
        "topic_id, document_id, article_type, source_hash, model, "
        "input_tokens, output_tokens, cost_usd"
    )
    insert_placeholders = "?, ?, 'topic_article', ?, ?, ?, ?, ?"
    insert_vals: list[str | int | float] = [
        topic_id,
        doc_id,
        source_hash,
        model,
        input_tokens,
        output_tokens,
        cost_usd,
    ]
    if timing:
        insert_cols += ", prepare_ms, route_ms, outline_ms, write_ms, validate_ms, save_ms"
        insert_placeholders += ", ?, ?, ?, ?, ?, ?"
        insert_vals.extend(timing_vals)

    # Create wiki_articles metadata row
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO wiki_articles ({insert_cols}) VALUES ({insert_placeholders})",
            insert_vals,
        )
        article_id = cursor.lastrowid
        assert article_id is not None

        # Save source provenance
        for src in sources:
            conn.execute(
                "INSERT INTO wiki_article_sources "
                "(article_id, document_id, content_hash) VALUES (?, ?, ?)",
                (article_id, src.doc_id, src.content_hash),
            )
        conn.commit()

    return doc_id, article_id


def _extract_h1(content: str) -> str | None:
    """Extract the first H1 heading from markdown content."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _slugify_label(label: str) -> str:
    """Convert a label to a URL-friendly slug."""
    slug = label.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:80].strip("-")


# ── Public API ────────────────────────────────────────────────────────


def generate_article(
    topic_id: int,
    audience: str = "team",
    model: str | None = None,
    dry_run: bool = False,
) -> WikiArticleResult:
    """Generate a wiki article for a single topic.

    Runs the full 6-step pipeline: PREPARE → ROUTE → OUTLINE → WRITE
    → VALIDATE → SAVE.

    Args:
        topic_id: The wiki_topics.id to generate for.
        audience: Privacy audience mode ("me", "team", "public").
        model: LLM model override.
        dry_run: If True, skip the LLM call and SAVE step.

    Returns:
        WikiArticleResult with generation metadata.
    """
    # Look up topic
    with db.get_connection() as conn:
        topic_row = conn.execute(
            "SELECT id, topic_slug, topic_label, description, "
            "status, model_override, editorial_prompt "
            "FROM wiki_topics WHERE id = ?",
            (topic_id,),
        ).fetchone()

    if not topic_row:
        return WikiArticleResult(
            topic_id=topic_id,
            topic_label="",
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=model or DEFAULT_MODEL,
            skipped=True,
            skip_reason=f"Topic {topic_id} not found",
        )

    topic_slug = topic_row[1]
    topic_label = topic_row[2]
    description = topic_row[3] or ""
    topic_status: str = topic_row[4] or "active"

    # Skip topics with status='skipped'
    if topic_status == "skipped":
        return WikiArticleResult(
            topic_id=topic_id,
            topic_label=topic_label,
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=model or DEFAULT_MODEL,
            skipped=True,
            skip_reason="Topic is skipped",
        )

    # Per-topic model override: explicit `model` arg takes priority,
    # then topic-level override, then the global default.
    topic_model_override: str | None = topic_row[5]
    if not model and topic_model_override:
        model = topic_model_override

    editorial_prompt: str | None = topic_row[6]

    # Parse top entities from description (stored as JSON array)
    import json

    try:
        top_entities = json.loads(description) if description else []
    except (json.JSONDecodeError, TypeError):
        top_entities = []

    def _ms_since(start: float) -> int:
        """Return elapsed milliseconds since *start* (monotonic)."""
        return int((time.monotonic() - start) * 1000)

    # Step 1: PREPARE
    t0 = time.monotonic()
    logger.info("[topic %d] PREPARE — fetching %s", topic_id, topic_label)
    doc_ids = get_topic_docs(topic_id)
    if not doc_ids:
        return WikiArticleResult(
            topic_id=topic_id,
            topic_label=topic_label,
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=model or DEFAULT_MODEL,
            skipped=True,
            skip_reason="No source documents for topic",
        )

    sources = _prepare_sources(doc_ids, topic_id=topic_id)
    if not sources:
        return WikiArticleResult(
            topic_id=topic_id,
            topic_label=topic_label,
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=model or DEFAULT_MODEL,
            skipped=True,
            skip_reason="All source documents empty after filtering",
        )

    total_chars = sum(s.char_count for s in sources)
    logger.info(
        "[topic %d] PREPARE — %d sources, %d chars total",
        topic_id,
        len(sources),
        total_chars,
    )

    # Check staleness — skip if source hash unchanged (pinned topics bypass)
    source_hash = _compute_source_hash(sources)
    if topic_status != "pinned":
        with db.get_connection() as conn:
            existing = conn.execute(
                "SELECT source_hash, is_stale FROM wiki_articles WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
        if existing and existing[0] == source_hash and not existing[1]:
            return WikiArticleResult(
                topic_id=topic_id,
                topic_label=topic_label,
                document_id=0,
                article_id=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                model=model or DEFAULT_MODEL,
                skipped=True,
                skip_reason="Article up to date (source hash unchanged)",
            )
    prepare_ms = _ms_since(t0)

    # Step 2: ROUTE
    t0 = time.monotonic()
    strategy = _route_strategy(sources)
    logger.info("[topic %d] ROUTE — strategy=%s", topic_id, strategy)
    route_ms = _ms_since(t0)

    # Step 3: OUTLINE
    t0 = time.monotonic()
    outline = _build_outline(
        topic_label=topic_label,
        topic_slug=topic_slug,
        top_entities=top_entities,
        source_count=len(sources),
        strategy=strategy,
    )
    logger.info(
        "[topic %d] OUTLINE — title='%s', %d sections",
        topic_id,
        outline.suggested_title,
        len(outline.section_hints),
    )
    outline_ms = _ms_since(t0)

    if dry_run:
        # Estimate cost without calling LLM
        est_input_tokens = total_chars // 4 + 500
        est_output_tokens = min(est_input_tokens // 2, 4000)

        used_model = model or DEFAULT_MODEL
        if "opus" in used_model:
            ip, op = 15.0, 75.0
        elif "haiku" in used_model:
            ip, op = 0.25, 1.25
        else:
            ip, op = 3.0, 15.0

        est_cost = (est_input_tokens / 1_000_000) * ip + (est_output_tokens / 1_000_000) * op

        return WikiArticleResult(
            topic_id=topic_id,
            topic_label=topic_label,
            document_id=0,
            article_id=0,
            input_tokens=est_input_tokens,
            output_tokens=est_output_tokens,
            cost_usd=est_cost,
            model=used_model,
            skipped=True,
            skip_reason="dry run",
            timing=WikiArticleTimingDict(
                prepare_ms=prepare_ms,
                route_ms=route_ms,
                outline_ms=outline_ms,
                write_ms=0,
                validate_ms=0,
                save_ms=0,
            ),
        )

    # Step 4: WRITE
    t0 = time.monotonic()
    used_model = model or DEFAULT_MODEL
    logger.info(
        "[topic %d] WRITE — synthesizing with %s (%s)...",
        topic_id,
        used_model.split("-")[1] if "-" in used_model else used_model,
        strategy,
    )
    if strategy == "hierarchical":
        content, input_tokens, output_tokens, cost_usd = _synthesize_hierarchical(
            outline,
            sources,
            audience,
            model,
            editorial_prompt=editorial_prompt,
        )
    else:
        content, input_tokens, output_tokens, cost_usd = _synthesize_article(
            outline,
            sources,
            audience,
            model,
            editorial_prompt=editorial_prompt,
        )
    logger.info(
        "[topic %d] WRITE — done, %d chars output, %d+%d tokens",
        topic_id,
        len(content),
        input_tokens,
        output_tokens,
    )
    write_ms = _ms_since(t0)

    # Step 5: VALIDATE
    t0 = time.monotonic()
    content, post_warnings = _validate_article(content)
    if post_warnings:
        logger.warning("[topic %d] VALIDATE — %s", topic_id, ", ".join(post_warnings))
    else:
        logger.info("[topic %d] VALIDATE — clean", topic_id)
    validate_ms = _ms_since(t0)

    # Step 6: SAVE
    t0 = time.monotonic()
    timing: WikiArticleTimingDict = WikiArticleTimingDict(
        prepare_ms=prepare_ms,
        route_ms=route_ms,
        outline_ms=outline_ms,
        write_ms=write_ms,
        validate_ms=validate_ms,
        save_ms=0,  # updated after save completes
    )
    doc_id, article_id = _save_article(
        topic_id=topic_id,
        content=content,
        outline=outline,
        sources=sources,
        model=used_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        timing=timing,
    )
    save_ms = _ms_since(t0)
    timing["save_ms"] = save_ms

    # Update save_ms in the DB now that we know it
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE wiki_articles SET save_ms = ? WHERE id = ?",
            (save_ms, article_id),
        )
        conn.commit()

    logger.info(
        "[topic %d] SAVE — doc #%d, %d+%d tokens, $%.4f",
        topic_id,
        doc_id,
        input_tokens,
        output_tokens,
        cost_usd,
    )

    # Step 7: RETITLE — update topic label from article H1 heading
    h1 = _extract_h1(content)
    if h1 and h1 != topic_label:
        new_slug = _slugify_label(h1)
        with db.get_connection() as conn:
            conflict = conn.execute(
                "SELECT id FROM wiki_topics WHERE topic_slug = ? AND id != ?",
                (new_slug, topic_id),
            ).fetchone()
            if not conflict:
                conn.execute(
                    "UPDATE wiki_topics SET topic_label = ?, topic_slug = ? WHERE id = ?",
                    (h1, new_slug, topic_id),
                )
                conn.execute(
                    "UPDATE documents SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (h1, doc_id),
                )
                conn.commit()
                logger.info(
                    "[topic %d] RETITLE — '%s' -> '%s'",
                    topic_id,
                    topic_label,
                    h1,
                )
                topic_label = h1
            else:
                logger.info(
                    "[topic %d] RETITLE skipped — slug '%s' conflicts with topic %d",
                    topic_id,
                    new_slug,
                    conflict[0],
                )

    return WikiArticleResult(
        topic_id=topic_id,
        topic_label=topic_label,
        document_id=doc_id,
        article_id=article_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        model=used_model,
        warnings=post_warnings,
        timing=timing,
    )


def generate_wiki(
    audience: str = "team",
    model: str | None = None,
    limit: int = DEFAULT_BATCH_LIMIT,
    dry_run: bool = False,
    topic_ids: list[int] | None = None,
) -> WikiGenerationResult:
    """Generate wiki articles for multiple topics.

    Args:
        audience: Privacy audience mode ("me", "team", "public").
        model: LLM model override.
        limit: Max articles to generate in this batch.
        dry_run: If True, estimate costs without calling LLM.
        topic_ids: Specific topic IDs to generate (None = all).

    Returns:
        WikiGenerationResult with batch statistics.
    """
    if topic_ids is not None:
        topics = []
        for tid in topic_ids:
            with db.get_connection() as conn:
                row = conn.execute(
                    "SELECT id, topic_label FROM wiki_topics WHERE id = ?",
                    (tid,),
                ).fetchone()
            if row:
                topics.append({"id": row[0], "label": row[1]})
    else:
        topics = get_topics()

    results: list[WikiArticleResult] = []
    generated = 0
    skipped = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for topic in topics:
        if generated >= limit:
            break

        topic_id = topic["id"]
        assert isinstance(topic_id, int)

        result = generate_article(
            topic_id=topic_id,
            audience=audience,
            model=model,
            dry_run=dry_run,
        )
        results.append(result)

        if result.skipped:
            skipped += 1
        else:
            generated += 1

        total_input += result.input_tokens
        total_output += result.output_tokens
        total_cost += result.cost_usd

    return WikiGenerationResult(
        articles_generated=generated,
        articles_skipped=skipped,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_usd=total_cost,
        results=results,
    )


def get_wiki_status() -> dict[str, int | float]:
    """Get current wiki generation status.

    Returns counts of articles, stale articles, total cost, etc.
    """
    with db.get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM wiki_articles").fetchone()
        stale = conn.execute("SELECT COUNT(*) FROM wiki_articles WHERE is_stale = 1").fetchone()
        cost = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM wiki_articles").fetchone()
        tokens = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0) FROM wiki_articles"
        ).fetchone()
        topics = conn.execute("SELECT COUNT(*) FROM wiki_topics").fetchone()

    total_val = total[0] if total else 0
    stale_val = stale[0] if stale else 0

    return {
        "total_articles": total_val,
        "stale_articles": stale_val,
        "fresh_articles": total_val - stale_val,
        "total_topics": topics[0] if topics else 0,
        "total_cost_usd": cost[0] if cost else 0.0,
        "total_input_tokens": tokens[0] if tokens else 0,
        "total_output_tokens": tokens[1] if tokens else 0,
    }


def mark_stale(doc_id: int, reason: str = "source_updated") -> bool:
    """Mark a wiki article as stale when its source documents change.

    Called by the save pipeline to trigger regeneration.

    Args:
        doc_id: The source document ID that was updated.
        reason: Why the article is stale.

    Returns:
        True if any articles were marked stale.
    """
    with db.get_connection() as conn:
        # Find articles that used this document as a source
        cursor = conn.execute(
            "SELECT article_id FROM wiki_article_sources WHERE document_id = ?",
            (doc_id,),
        )
        article_ids = [row[0] for row in cursor.fetchall()]

        if not article_ids:
            return False

        placeholders = ",".join("?" * len(article_ids))
        conn.execute(
            f"UPDATE wiki_articles SET is_stale = 1, stale_reason = ? WHERE id IN ({placeholders})",
            [reason] + article_ids,
        )
        conn.commit()

    logger.info(
        "Marked %d article(s) stale due to doc #%d update",
        len(article_ids),
        doc_id,
    )
    return True


# ── Wiki run tracking ────────────────────────────────────────────────


def create_wiki_run(model: str, dry_run: bool = False) -> int:
    """Create a new wiki run record and return its ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO wiki_runs (model, dry_run) VALUES (?, ?)",
            (model, dry_run),
        )
        conn.commit()
        run_id: int = cursor.lastrowid  # type: ignore[assignment]
    return run_id


def complete_wiki_run(
    run_id: int,
    *,
    topics_attempted: int,
    articles_generated: int,
    articles_skipped: int,
    total_input_tokens: int,
    total_output_tokens: int,
    total_cost_usd: float,
) -> None:
    """Update a wiki run with completion data."""
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE wiki_runs SET "
            "completed_at = CURRENT_TIMESTAMP, "
            "topics_attempted = ?, "
            "articles_generated = ?, "
            "articles_skipped = ?, "
            "total_input_tokens = ?, "
            "total_output_tokens = ?, "
            "total_cost_usd = ? "
            "WHERE id = ?",
            (
                topics_attempted,
                articles_generated,
                articles_skipped,
                total_input_tokens,
                total_output_tokens,
                total_cost_usd,
                run_id,
            ),
        )
        conn.commit()


def list_wiki_runs(limit: int = 10) -> list[dict[str, object]]:
    """List recent wiki generation runs.

    Returns a list of dicts with run metadata, most recent first.
    """
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT id, started_at, completed_at, topics_attempted, "
            "articles_generated, articles_skipped, "
            "total_input_tokens, total_output_tokens, "
            "total_cost_usd, model, dry_run "
            "FROM wiki_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


# ── Article diff ──────────────────────────────────────────────────────


def get_article_diff(topic_id: int) -> str | None:
    """Return a unified diff between previous and current article content.

    Args:
        topic_id: The wiki_topics.id to get the diff for.

    Returns:
        A unified diff string, or None if no previous content exists
        or the topic/article is not found.
    """
    import difflib

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT wa.previous_content, d.content, d.title "
            "FROM wiki_articles wa "
            "JOIN documents d ON wa.document_id = d.id "
            "WHERE wa.topic_id = ?",
            (topic_id,),
        ).fetchone()

    if not row:
        return None

    previous_content: str = row[0] or ""
    current_content: str = row[1] or ""
    title: str = row[2] or ""

    if not previous_content:
        return None

    diff_lines = difflib.unified_diff(
        previous_content.splitlines(keepends=True),
        current_content.splitlines(keepends=True),
        fromfile=f"a/{title} (previous)",
        tofile=f"b/{title} (current)",
    )
    return "".join(diff_lines)
