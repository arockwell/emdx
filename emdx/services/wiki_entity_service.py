"""Entity index page generation for auto-wiki.

Generates glossary/index pages for significant entities in the knowledge base.
Each entity page aggregates all documents mentioning it with context snippets,
co-occurring entities (via PMI), and links to related topic articles.

Three tiers:
- A (Full Page): df >= 5, high page score — full page with snippets + related
- B (Stub Page): df 3-4 — mini page listing docs
- C (Index Only): df 2 — appears in alphabetical index, no dedicated page
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..database import db

# ── Page scoring constants ──────────────────────────────────────────

# Type weights for page-worthiness scoring
ENTITY_TYPE_WEIGHTS: dict[str, float] = {
    "concept": 1.0,
    "tech_term": 0.9,
    "proper_noun": 0.8,
    "heading": 0.7,
}

# Minimum doc frequency for each tier
TIER_A_MIN_DF = 5
TIER_B_MIN_DF = 3
TIER_C_MIN_DF = 2

# Score threshold for Tier A (full page)
TIER_A_MIN_SCORE = 30.0

# Max snippet length in characters
SNIPPET_MAX_CHARS = 250

# Max co-occurring entities to show per page
MAX_RELATED_ENTITIES = 10


@dataclass
class EntitySnippet:
    """A context snippet for an entity from a specific document."""

    doc_id: int
    doc_title: str
    snippet: str
    heading_context: str = ""


@dataclass
class EntityPage:
    """A generated entity index page."""

    entity: str
    entity_type: str
    doc_frequency: int
    page_score: float
    tier: str  # "A", "B", "C"
    snippets: list[EntitySnippet] = field(default_factory=list)
    related_entities: list[tuple[str, float, int]] = field(default_factory=list)
    first_seen: str = ""


@dataclass
class EntityIndexResult:
    """Result from generating entity index."""

    tier_a_count: int  # Full pages
    tier_b_count: int  # Stub pages
    tier_c_count: int  # Index only
    total_entities: int
    filtered_noise: int


def _compute_page_scores() -> list[tuple[str, str, int, float, float]]:
    """Compute page-worthiness scores for all entities.

    Returns list of (entity, entity_type, doc_freq, avg_confidence, page_score)
    sorted by page_score descending.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT entity, entity_type, COUNT(DISTINCT document_id) as df, "
            "AVG(confidence) as avg_conf "
            "FROM document_entities de "
            "JOIN documents d ON de.document_id = d.id "
            "WHERE d.is_deleted = 0 "
            "GROUP BY entity "
            "HAVING df >= ? "
            "ORDER BY df DESC",
            (TIER_C_MIN_DF,),
        )
        rows = cursor.fetchall()

        total_docs_row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE is_deleted = 0"
        ).fetchone()
        total_docs = total_docs_row[0] if total_docs_row else 1

    results: list[tuple[str, str, int, float, float]] = []
    for entity, entity_type, df, avg_conf in rows:
        idf = math.log(1 + total_docs / max(df, 1))
        type_weight = ENTITY_TYPE_WEIGHTS.get(entity_type, 0.5)
        page_score = df * idf * avg_conf * type_weight
        results.append((entity, entity_type, df, avg_conf, page_score))

    results.sort(key=lambda x: x[4], reverse=True)
    return results


def _extract_snippet(content: str, entity: str) -> tuple[str, str]:
    """Extract a context snippet around an entity mention.

    Returns (snippet, heading_context) where heading_context is the
    nearest heading above the mention.
    """
    entity_lower = entity.lower()

    # Strategy 1: Find the paragraph containing the mention
    paragraphs = content.split("\n\n")
    heading_context = ""

    for para in paragraphs:
        # Track headings
        heading_match = re.match(r"^#{1,6}\s+(.+)$", para.strip())
        if heading_match:
            heading_context = heading_match.group(1).strip()
            continue

        if entity_lower in para.lower():
            snippet = para.strip()
            if len(snippet) > SNIPPET_MAX_CHARS:
                # Find the entity mention and center the window
                idx = snippet.lower().find(entity_lower)
                start = max(0, idx - SNIPPET_MAX_CHARS // 3)
                end = min(len(snippet), idx + len(entity) + SNIPPET_MAX_CHARS * 2 // 3)
                snippet = snippet[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(para):
                    snippet = snippet + "..."
            return snippet, heading_context

    # Strategy 2: Sentence-level fallback
    sentences = re.split(r"(?<=[.!?])\s+", content)
    for i, sent in enumerate(sentences):
        if entity_lower in sent.lower():
            start = max(0, i - 1)
            end = min(len(sentences), i + 2)
            snippet = " ".join(sentences[start:end])
            if len(snippet) > SNIPPET_MAX_CHARS:
                snippet = snippet[:SNIPPET_MAX_CHARS] + "..."
            return snippet.strip(), ""

    return content[:SNIPPET_MAX_CHARS].strip() + "...", ""


def _compute_pmi(
    entity: str,
    total_docs: int,
    entity_doc_freq: dict[str, int],
) -> list[tuple[str, float, int]]:
    """Compute PMI (Pointwise Mutual Information) for co-occurring entities.

    PMI(a,b) = log2(N * co_occur / (df_a * df_b))
    Higher PMI = more surprising co-occurrence = more meaningful relationship.

    Returns list of (related_entity, pmi_score, co_occurrence_count).
    """
    df_a = entity_doc_freq.get(entity, 0)
    if df_a < TIER_C_MIN_DF:
        return []

    with db.get_connection() as conn:
        # Find entities that co-occur with this one
        cursor = conn.execute(
            "SELECT de2.entity, COUNT(DISTINCT de2.document_id) as co_occur "
            "FROM document_entities de1 "
            "JOIN document_entities de2 ON de1.document_id = de2.document_id "
            "WHERE de1.entity = ? AND de2.entity != ? "
            "GROUP BY de2.entity "
            "HAVING co_occur >= 2 "
            "ORDER BY co_occur DESC "
            "LIMIT 50",
            (entity, entity),
        )
        co_occurrences = cursor.fetchall()

    results: list[tuple[str, float, int]] = []
    for related_entity, co_occur in co_occurrences:
        df_b = entity_doc_freq.get(related_entity, 1)
        if df_b < TIER_C_MIN_DF:
            continue

        # PMI = log2(N * co_occur / (df_a * df_b))
        pmi = math.log2(max(total_docs * co_occur / (df_a * df_b), 1e-10))
        if pmi > 0:
            results.append((related_entity, pmi, co_occur))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:MAX_RELATED_ENTITIES]


def get_entity_pages(
    tier: str | None = None,
    limit: int = 0,
) -> list[EntityPage]:
    """Get entity pages with scoring and tier assignment.

    Args:
        tier: Filter to specific tier ("A", "B", "C") or None for all.
        limit: Max pages to return (0 = unlimited).

    Returns:
        List of EntityPage objects.
    """
    scored = _compute_page_scores()

    pages: list[EntityPage] = []
    for entity, entity_type, df, _avg_conf, page_score in scored:
        # Determine tier
        if df >= TIER_A_MIN_DF and page_score >= TIER_A_MIN_SCORE:
            entity_tier = "A"
        elif df >= TIER_B_MIN_DF:
            entity_tier = "B"
        else:
            entity_tier = "C"

        if tier and entity_tier != tier:
            continue

        page = EntityPage(
            entity=entity,
            entity_type=entity_type,
            doc_frequency=df,
            page_score=page_score,
            tier=entity_tier,
        )
        pages.append(page)

        if limit and len(pages) >= limit:
            break

    return pages


def get_entity_detail(entity: str) -> EntityPage | None:
    """Get a full entity page with snippets and related entities.

    Args:
        entity: The entity name to look up.

    Returns:
        EntityPage with populated snippets and related entities, or None.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT de.document_id, d.title, d.content, de.entity_type, de.confidence "
            "FROM document_entities de "
            "JOIN documents d ON de.document_id = d.id "
            "WHERE de.entity = ? AND d.is_deleted = 0 "
            "ORDER BY de.confidence DESC, d.updated_at DESC",
            (entity,),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    entity_type = rows[0][3]
    df = len(rows)
    avg_conf = sum(r[4] for r in rows) / len(rows)

    # Get total docs for IDF
    with db.get_connection() as conn:
        total_docs_row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE is_deleted = 0"
        ).fetchone()
        total_docs = total_docs_row[0] if total_docs_row else 1

    idf = math.log(1 + total_docs / max(df, 1))
    type_weight = ENTITY_TYPE_WEIGHTS.get(entity_type, 0.5)
    page_score = df * idf * avg_conf * type_weight

    if df >= TIER_A_MIN_DF and page_score >= TIER_A_MIN_SCORE:
        entity_tier = "A"
    elif df >= TIER_B_MIN_DF:
        entity_tier = "B"
    else:
        entity_tier = "C"

    # Extract snippets (deduplicated)
    snippets: list[EntitySnippet] = []
    seen_snippets: set[str] = set()
    for doc_id, title, content, _etype, _conf in rows:
        snippet_text, heading = _extract_snippet(content, entity)
        # Simple dedup: skip if snippet is very similar to one we already have
        snippet_key = snippet_text[:80].lower()
        if snippet_key in seen_snippets:
            continue
        seen_snippets.add(snippet_key)
        snippets.append(
            EntitySnippet(
                doc_id=doc_id,
                doc_title=title,
                snippet=snippet_text,
                heading_context=heading,
            )
        )

    # Compute related entities via PMI
    entity_doc_freq: dict[str, int] = {}
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT entity, COUNT(DISTINCT document_id) FROM document_entities GROUP BY entity"
        )
        for row in cursor.fetchall():
            entity_doc_freq[row[0]] = row[1]

    related = _compute_pmi(entity, total_docs, entity_doc_freq)

    # Get first seen date
    first_seen = ""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT MIN(d.created_at) FROM document_entities de "
            "JOIN documents d ON de.document_id = d.id "
            "WHERE de.entity = ?",
            (entity,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            first_seen = str(row[0])[:10]  # Just the date part

    return EntityPage(
        entity=entity,
        entity_type=entity_type,
        doc_frequency=df,
        page_score=page_score,
        tier=entity_tier,
        snippets=snippets,
        related_entities=related,
        first_seen=first_seen,
    )


def render_entity_page(page: EntityPage) -> str:
    """Render an entity page as markdown.

    Args:
        page: EntityPage with populated snippets and related entities.

    Returns:
        Markdown string for the entity page.
    """
    lines: list[str] = []

    lines.append(f"# {page.entity}")
    lines.append("")
    lines.append(
        f"**Type:** {page.entity_type} | "
        f"**Mentioned in:** {page.doc_frequency} documents"
        + (f" | **First seen:** {page.first_seen}" if page.first_seen else "")
    )
    lines.append("")

    # Snippets grouped by heading context
    if page.snippets:
        lines.append(f"## Documents ({page.doc_frequency})")
        lines.append("")
        for snippet in page.snippets:
            lines.append(f"- **#{snippet.doc_id}** {snippet.doc_title}")
            if snippet.heading_context:
                lines.append(f"  *Section: {snippet.heading_context}*")
            lines.append(f"  > {snippet.snippet}")
            lines.append("")

    # Related entities
    if page.related_entities:
        lines.append("## Related Entities")
        lines.append("")
        for related, pmi, co_occur in page.related_entities:
            bar_len = min(int(pmi * 3), 20)
            bar = "\u2588" * bar_len
            lines.append(f"- `{related}` {bar} ({co_occur} shared docs, PMI={pmi:.1f})")
        lines.append("")

    return "\n".join(lines)


def get_entity_index_stats() -> EntityIndexResult:
    """Get statistics about the entity index.

    Returns counts for each tier and total/filtered entities.
    """
    scored = _compute_page_scores()

    tier_a = 0
    tier_b = 0
    tier_c = 0

    for _entity, _etype, df, _conf, page_score in scored:
        if df >= TIER_A_MIN_DF and page_score >= TIER_A_MIN_SCORE:
            tier_a += 1
        elif df >= TIER_B_MIN_DF:
            tier_b += 1
        else:
            tier_c += 1

    # Count total entities (including those below min DF)
    with db.get_connection() as conn:
        total_row = conn.execute("SELECT COUNT(DISTINCT entity) FROM document_entities").fetchone()
        total_entities = total_row[0] if total_row else 0

    filtered = total_entities - len(scored)

    return EntityIndexResult(
        tier_a_count=tier_a,
        tier_b_count=tier_b,
        tier_c_count=tier_c,
        total_entities=total_entities,
        filtered_noise=filtered,
    )
