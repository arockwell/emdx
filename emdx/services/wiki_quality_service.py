"""Wiki article quality scoring service.

Scores wiki articles across four dimensions (all 0.0-1.0):
1. Coverage  — how much of the source material is reflected
2. Freshness — how recently the article and its sources were updated
3. Coherence — structural quality (headings, sections, length)
4. Source density — ratio of sources to article length

Composite scoring with configurable weights produces a single 0.0-1.0 score.
Optionally runs a Claude LLM assessment for deeper qualitative feedback.
"""

from __future__ import annotations

import logging
import math
import re
import time

from ..database import db

logger = logging.getLogger(__name__)

# ── Weights for composite scoring ────────────────────────────────────

WEIGHT_COVERAGE = 0.35
WEIGHT_FRESHNESS = 0.25
WEIGHT_COHERENCE = 0.25
WEIGHT_SOURCE_DENSITY = 0.15

# ── Coherence heuristic thresholds ───────────────────────────────────

# Ideal article length range (characters)
MIN_GOOD_LENGTH = 800
MAX_GOOD_LENGTH = 15_000

# Minimum heading count for a well-structured article
MIN_HEADINGS = 2

# Maximum heading count before it feels fragmented
MAX_HEADINGS = 20

# ── Source density thresholds ────────────────────────────────────────

# Ideal chars-per-source ratio
IDEAL_CHARS_PER_SOURCE = 1500


def _score_coverage(
    article_content: str,
    source_contents: list[str],
) -> float:
    """Score how well the article covers its source material.

    Uses a simple token-overlap heuristic: what fraction of unique
    source tokens (lowercased, length >= 4) appear in the article.
    Returns 0.0-1.0.
    """
    if not source_contents or not article_content:
        return 0.0

    # Build a set of meaningful tokens from sources
    source_tokens: set[str] = set()
    for src in source_contents:
        for token in re.findall(r"[a-zA-Z_]\w{3,}", src.lower()):
            source_tokens.add(token)

    if not source_tokens:
        return 0.0

    # Check which appear in the article
    article_lower = article_content.lower()
    hits = sum(1 for t in source_tokens if t in article_lower)

    raw = hits / len(source_tokens)
    # Clamp to [0, 1] and apply a gentle sigmoid so partial overlap
    # doesn't slam to 0 or 1
    return min(1.0, raw * 1.2)


def _score_freshness(
    article_generated_at: str | None,
    source_updated_ats: list[str | None],
) -> float:
    """Score article freshness based on generation recency and source staleness.

    Considers:
    - Days since article was generated (exponential decay)
    - Whether any source has been updated AFTER the article was generated

    Returns 0.0-1.0.
    """
    if not article_generated_at:
        return 0.0

    now = time.time()

    # Parse article generation timestamp
    try:
        from datetime import datetime

        gen_dt = datetime.fromisoformat(article_generated_at.replace("Z", "+00:00"))
        gen_ts = gen_dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0

    days_since = max(0.0, (now - gen_ts) / 86400)

    # Recency score: exponential decay with half-life of 30 days
    recency = math.exp(-0.023 * days_since)

    # Staleness penalty: check if sources updated after article generation
    stale_sources = 0
    total_sources = 0
    for updated_at in source_updated_ats:
        if not updated_at:
            continue
        total_sources += 1
        try:
            src_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if src_dt.timestamp() > gen_ts:
                stale_sources += 1
        except (ValueError, AttributeError):
            continue

    if total_sources > 0:
        stale_ratio = stale_sources / total_sources
        staleness_penalty = stale_ratio * 0.5  # up to 50% penalty
        recency = max(0.0, recency - staleness_penalty)

    return min(1.0, recency)


def _score_coherence(article_content: str) -> float:
    """Score structural quality of the article.

    Checks:
    - Length (too short or too long is penalized)
    - Heading count (too few or too many is penalized)
    - Has a level-1 heading (title)
    - Paragraph structure

    Returns 0.0-1.0.
    """
    if not article_content:
        return 0.0

    content_len = len(article_content)
    score = 0.0

    # Length score (0.0-0.4)
    if content_len < MIN_GOOD_LENGTH:
        length_score = 0.4 * (content_len / MIN_GOOD_LENGTH)
    elif content_len <= MAX_GOOD_LENGTH:
        length_score = 0.4
    else:
        # Gradually penalize very long articles
        over = content_len - MAX_GOOD_LENGTH
        length_score = max(0.1, 0.4 - (over / MAX_GOOD_LENGTH) * 0.3)
    score += length_score

    # Heading structure (0.0-0.3)
    headings = re.findall(r"^#{1,3}\s+\S", article_content, re.MULTILINE)
    heading_count = len(headings)
    if heading_count == 0:
        heading_score = 0.0
    elif heading_count < MIN_HEADINGS:
        heading_score = 0.15
    elif heading_count <= MAX_HEADINGS:
        heading_score = 0.3
    else:
        heading_score = max(0.1, 0.3 - (heading_count - MAX_HEADINGS) * 0.02)
    score += heading_score

    # Has title (level-1 heading) (0.0-0.15)
    has_title = bool(re.search(r"^#\s+\S", article_content, re.MULTILINE))
    score += 0.15 if has_title else 0.0

    # Paragraph structure (0.0-0.15)
    paragraphs = [
        p.strip()
        for p in article_content.split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
    if len(paragraphs) >= 3:
        score += 0.15
    elif len(paragraphs) >= 1:
        score += 0.08

    return min(1.0, score)


def _score_source_density(
    article_content: str,
    source_count: int,
) -> float:
    """Score the source-to-content ratio.

    Articles synthesized from more sources with reasonable density score higher.
    Too few sources or extremely sparse coverage is penalized.

    Returns 0.0-1.0.
    """
    if not article_content or source_count == 0:
        return 0.0

    content_len = len(article_content)
    chars_per_source = content_len / source_count

    # Ideal: ~1500 chars per source
    # Too little content per source means shallow coverage
    # Too much means sources are underused
    if chars_per_source < 200:
        density_score = 0.2
    elif chars_per_source < IDEAL_CHARS_PER_SOURCE:
        # Ramp up from 200 to ideal
        t = (chars_per_source - 200) / (IDEAL_CHARS_PER_SOURCE - 200)
        density_score = 0.2 + t * 0.8
    elif chars_per_source <= IDEAL_CHARS_PER_SOURCE * 3:
        density_score = 1.0
    else:
        # Very long per source: gradually reduce
        over = chars_per_source - IDEAL_CHARS_PER_SOURCE * 3
        density_score = max(0.3, 1.0 - over / (IDEAL_CHARS_PER_SOURCE * 5))

    # Bonus for having 3+ sources (more cross-referencing)
    if source_count >= 5:
        density_score = min(1.0, density_score * 1.1)
    elif source_count >= 3:
        density_score = min(1.0, density_score * 1.05)

    return min(1.0, density_score)


def _composite_score(
    coverage: float,
    freshness: float,
    coherence: float,
    source_density: float,
) -> float:
    """Compute weighted composite score from dimension scores."""
    return (
        coverage * WEIGHT_COVERAGE
        + freshness * WEIGHT_FRESHNESS
        + coherence * WEIGHT_COHERENCE
        + source_density * WEIGHT_SOURCE_DENSITY
    )


def score_article(
    topic_id: int,
) -> dict[str, object]:
    """Score a single wiki article by topic ID.

    Returns a dict with keys:
        topic_id, topic_label, article_id, document_id,
        coverage, freshness, coherence, source_density,
        composite, article_title
    """
    with db.get_connection() as conn:
        # Get article info
        row = conn.execute(
            "SELECT wa.id, wa.document_id, wa.topic_id, wa.generated_at, "
            "wt.topic_label "
            "FROM wiki_articles wa "
            "JOIN wiki_topics wt ON wa.topic_id = wt.id "
            "WHERE wa.topic_id = ?",
            (topic_id,),
        ).fetchone()

        if not row:
            return {
                "topic_id": topic_id,
                "topic_label": "",
                "article_id": 0,
                "document_id": 0,
                "coverage": 0.0,
                "freshness": 0.0,
                "coherence": 0.0,
                "source_density": 0.0,
                "composite": 0.0,
                "article_title": "",
                "error": f"No article found for topic {topic_id}",
            }

        article_id = row[0]
        document_id = row[1]
        generated_at = row[3]
        topic_label = row[4]

        # Get article content
        doc_row = conn.execute(
            "SELECT title, content FROM documents WHERE id = ? AND is_deleted = 0",
            (document_id,),
        ).fetchone()

        if not doc_row:
            return {
                "topic_id": topic_id,
                "topic_label": topic_label,
                "article_id": article_id,
                "document_id": document_id,
                "coverage": 0.0,
                "freshness": 0.0,
                "coherence": 0.0,
                "source_density": 0.0,
                "composite": 0.0,
                "article_title": "",
                "error": "Article document not found or deleted",
            }

        article_title = doc_row[0]
        article_content = doc_row[1]

        # Get source document IDs and content
        source_rows = conn.execute(
            "SELECT was.document_id, d.content, d.updated_at "
            "FROM wiki_article_sources was "
            "JOIN documents d ON was.document_id = d.id "
            "WHERE was.article_id = ? AND d.is_deleted = 0",
            (article_id,),
        ).fetchall()

        source_contents = [r[1] for r in source_rows]
        source_updated_ats: list[str | None] = [r[2] for r in source_rows]
        source_count = len(source_rows)

    # Score each dimension
    coverage = _score_coverage(article_content, source_contents)
    freshness = _score_freshness(generated_at, source_updated_ats)
    coherence = _score_coherence(article_content)
    source_density = _score_source_density(article_content, source_count)
    composite = _composite_score(coverage, freshness, coherence, source_density)

    return {
        "topic_id": topic_id,
        "topic_label": topic_label,
        "article_id": article_id,
        "document_id": document_id,
        "coverage": round(coverage, 3),
        "freshness": round(freshness, 3),
        "coherence": round(coherence, 3),
        "source_density": round(source_density, 3),
        "composite": round(composite, 3),
        "article_title": article_title,
    }


def score_all_articles(
    threshold: float | None = None,
) -> list[dict[str, object]]:
    """Score all wiki articles and persist composite scores.

    Args:
        threshold: If set, only return articles scoring below this value.

    Returns:
        List of score dicts sorted worst-first (ascending composite).
    """
    with db.get_connection() as conn:
        topic_rows = conn.execute(
            "SELECT DISTINCT wa.topic_id FROM wiki_articles wa "
            "JOIN wiki_topics wt ON wa.topic_id = wt.id "
            "WHERE wt.status != 'skipped'"
        ).fetchall()

    topic_ids = [r[0] for r in topic_rows]
    results: list[dict[str, object]] = []

    for topic_id in topic_ids:
        result = score_article(topic_id)
        if "error" in result:
            logger.warning("Skipping topic %d: %s", topic_id, result.get("error"))
            continue

        # Persist composite score
        composite = result["composite"]
        article_id = result["article_id"]
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_articles SET quality_score = ? WHERE id = ?",
                (composite, article_id),
            )
            conn.commit()

        if threshold is None or float(str(composite)) < threshold:
            results.append(result)

    # Sort worst-first
    results.sort(key=lambda r: float(str(r["composite"])))
    return results


def llm_quality_assessment(
    topic_id: int,
    model: str | None = None,
) -> dict[str, object]:
    """Run an LLM-based quality assessment on a wiki article.

    Sends the article content and source documents to Claude for
    structured qualitative feedback.

    Returns a dict with:
        topic_id, topic_label, assessment, suggestions, overall_grade
    """
    from .synthesis_service import _execute_prompt

    # First get the article score data
    score_data = score_article(topic_id)
    if "error" in score_data:
        return score_data

    document_id = score_data["document_id"]
    article_id = score_data["article_id"]

    with db.get_connection() as conn:
        # Get article content
        doc_row = conn.execute(
            "SELECT title, content FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        if not doc_row:
            return {
                "topic_id": topic_id,
                "error": "Article document not found",
            }

        article_title = doc_row[0]
        article_content = doc_row[1]

        # Get source contents
        source_rows = conn.execute(
            "SELECT d.title, d.content "
            "FROM wiki_article_sources was "
            "JOIN documents d ON was.document_id = d.id "
            "WHERE was.article_id = ? AND d.is_deleted = 0",
            (article_id,),
        ).fetchall()

    source_summaries = "\n\n".join(
        f"### Source: {r[0]}\n{r[1][:500]}..." if len(r[1]) > 500 else f"### Source: {r[0]}\n{r[1]}"
        for r in source_rows
    )

    system_prompt = (
        "You are a wiki quality reviewer. Assess the following wiki "
        "article for quality, accuracy, and completeness.\n\n"
        "Respond with EXACTLY this format:\n\n"
        "GRADE: [A/B/C/D/F]\n\n"
        "ASSESSMENT:\n[2-3 sentences about overall quality]\n\n"
        "STRENGTHS:\n- [strength 1]\n- [strength 2]\n\n"
        "WEAKNESSES:\n- [weakness 1]\n- [weakness 2]\n\n"
        "SUGGESTIONS:\n- [suggestion 1]\n- [suggestion 2]\n\n"
        "Be specific and actionable. Reference specific sections."
    )

    user_message = (
        f"# Article: {article_title}\n\n"
        f"{article_content}\n\n"
        f"---\n\n"
        f"# Source Documents ({len(source_rows)} sources)\n\n"
        f"{source_summaries}"
    )

    used_model = model or "claude-sonnet-4-5-20250929"

    try:
        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            title=f"Quality review: {article_title}",
            model=used_model,
        )

        output = result.output_content or ""

        # Parse grade from output
        grade_match = re.search(r"GRADE:\s*([A-F])", output)
        grade = grade_match.group(1) if grade_match else "?"

        return {
            "topic_id": topic_id,
            "topic_label": score_data.get("topic_label", ""),
            "article_title": article_title,
            "assessment": output,
            "overall_grade": grade,
            "scores": score_data,
        }
    except RuntimeError as e:
        return {
            "topic_id": topic_id,
            "topic_label": score_data.get("topic_label", ""),
            "article_title": article_title,
            "error": str(e),
            "scores": score_data,
        }
