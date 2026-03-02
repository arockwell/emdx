"""Entity extraction and entity-match wikification service.

Layer 3 of the auto-wikify system. Extracts key entities (concepts,
technical terms, proper nouns) from documents using heuristics, then
cross-references them to create links between documents that share
entities — even if their titles don't match.

Supports two extraction modes:
- Heuristic (default): Zero cost, uses markdown structure and text patterns.
- LLM (opt-in via --llm): Uses Claude for richer entity types and
  relationship extraction.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from typing import TypedDict

from ..database import db, document_links

logger = logging.getLogger(__name__)

# Entities shorter than this are excluded to avoid noise
MIN_ENTITY_LENGTH = 4

# Cross-referencing thresholds
MAX_DF_RATIO = 0.05  # Skip entities in >5% of docs (too generic)
MIN_SHARED_ENTITIES = 2  # Must share ≥2 entities to create a link
MAX_ENTITY_LINKS = 10  # Max entity-match links per document
MIN_ENTITY_SCORE = 0.15  # Minimum IDF-Jaccard score to keep a link

# Common words that look like entities but aren't useful
STOPWORD_ENTITIES = frozenset(
    {
        "todo",
        "note",
        "notes",
        "test",
        "true",
        "false",
        "none",
        "null",
        "self",
        "this",
        "that",
        "some",
        "each",
        "also",
        "from",
        "with",
        "into",
        "have",
        "will",
        "just",
        "then",
        "when",
        "here",
        "more",
        "like",
        "what",
        "need",
        "make",
        "want",
        "done",
        "used",
        "only",
        "very",
        "next",
        "step",
        "back",
        "file",
        "code",
        "data",
        "type",
        "work",
        "time",
        "well",
        "good",
        "best",
        "last",
        "first",
        "same",
        "most",
        "much",
        "many",
        "even",
        "still",
        "after",
        "before",
        "other",
        "which",
        "about",
        "would",
        "could",
        "should",
        "there",
        "being",
        "these",
        "those",
        "their",
        "where",
        "every",
        "thing",
        "things",
        "using",
        "example",
        "examples",
    }
)

# Generic structural headings that appear in many docs — not useful for linking
HEADING_STOPWORDS = frozenset(
    {
        # Document structure
        "summary",
        "overview",
        "conclusion",
        "conclusions",
        "introduction",
        "background",
        "context",
        "description",
        "details",
        "discussion",
        "analysis",
        "results",
        "findings",
        "recommendations",
        "recommendation",
        "next steps",
        "action items",
        "appendix",
        "references",
        "resources",
        "prerequisites",
        "requirements",
        "setup",
        # Status/progress headings
        "status",
        "progress",
        "updates",
        "update",
        "key points",
        "key takeaways",
        "key findings",
        # Task/project headings
        "implementation",
        "approach",
        "plan",
        "changes",
        "changes made",
        "modifications",
        "issues",
        "testing",
        "test results",
        "verification",
        "deployment",
        "configuration",
        "examples",
        "usage",
        "quick start",
        "troubleshooting",
        "debugging",
        "workarounds",
        # Meta headings
        "related",
        "see also",
        "links",
        "current state",
        "proposed solution",
        "problem",
        "solution",
        "goals",
        "scope",
        # Agent output boilerplate
        "executive summary",
        "files changed",
        "pr created",
        "high priority",
        "medium priority",
        "low priority",
        "success criteria",
    }
)

# Noisy concept/bold patterns — labels and field names, not real concepts
CONCEPT_STOPWORDS = frozenset(
    {
        "file:",
        "issue:",
        "location:",
        "recommendation:",
        "date:",
        "impact:",
        "severity:",
        "status:",
        "scope:",
        "fix:",
        "note:",
        "problem:",
        "total",
        "find",
        "critical",
        "necessary",
        "status",
        "files modified",
        "high priority",
        "medium priority",
        "low priority",
    }
)

# Proper noun patterns that are regex artifacts, not real proper nouns
_PROPER_NOUN_SUFFIX_NOISE = frozenset(
    {
        "successfully",
        "fixed",
        "added",
        "the",
        "this",
        "that",
        "all",
        "are",
        "was",
        "has",
        "had",
    }
)

# Patterns that identify headings (## Heading Text)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

# Backtick-wrapped terms (`some_thing`)
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Bold text (**something**)
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")

# Capitalized multi-word phrases (two+ Title Case words in a row)
# Matches "Auth Module" but not "the auth module"
_CAPITALIZED_PHRASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

# Leading articles/prepositions to strip from capitalized phrases
_LEADING_ARTICLES = frozenset({"the", "a", "an", "in", "on", "at", "of", "for", "to", "by"})


@dataclass
class ExtractedEntity:
    """An entity extracted from a document."""

    text: str
    normalized: str
    entity_type: str
    confidence: float


@dataclass
class EntityWikifyResult:
    """Result of entity-match wikification."""

    doc_id: int
    entities_extracted: int
    links_created: int
    linked_doc_ids: list[int] = field(default_factory=list)
    skipped_existing: int = 0


def _normalize_entity(text: str) -> str:
    """Normalize an entity for comparison and storage."""
    normalized = text.strip().lower()
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _is_valid_entity(normalized: str) -> bool:
    """Check if an entity is worth keeping."""
    if len(normalized) < MIN_ENTITY_LENGTH:
        return False
    if normalized in STOPWORD_ENTITIES:
        return False
    # Skip pure numbers
    if normalized.replace(" ", "").isdigit():
        return False
    return True


def extract_entities(content: str, title: str = "") -> list[ExtractedEntity]:
    """Extract entities from document content using heuristics.

    Sources (in priority order):
    1. Markdown headings — high confidence concepts
    2. Backtick-wrapped terms — explicit technical terms
    3. Bold text — emphasized concepts
    4. Capitalized multi-word phrases — proper nouns / named concepts
    """
    seen: set[str] = set()
    entities: list[ExtractedEntity] = []

    def _add(text: str, entity_type: str, confidence: float) -> None:
        normalized = _normalize_entity(text)
        if normalized not in seen and _is_valid_entity(normalized):
            seen.add(normalized)
            entities.append(
                ExtractedEntity(
                    text=text.strip(),
                    normalized=normalized,
                    entity_type=entity_type,
                    confidence=confidence,
                )
            )

    # Don't extract the document's own title as an entity
    title_normalized = _normalize_entity(title) if title else ""
    if title_normalized:
        seen.add(title_normalized)

    # 1. Headings — these are explicit section labels, high signal
    for match in _HEADING_RE.finditer(content):
        heading = match.group(1).strip()
        # Strip trailing punctuation and markdown artifacts
        heading = re.sub(r"[#*`]+$", "", heading).strip()
        # Skip generic structural headings
        if _normalize_entity(heading) in HEADING_STOPWORDS:
            continue
        _add(heading, "heading", 0.95)

    # 2. Backtick terms — explicit code/technical references
    for match in _BACKTICK_RE.finditer(content):
        term = match.group(1).strip()
        # Skip shell commands and file paths
        if " " in term and any(c in term for c in "/$|>"):
            continue
        _add(term, "tech_term", 0.9)

    # 3. Bold text — emphasized concepts
    for match in _BOLD_RE.finditer(content):
        bold = match.group(1).strip()
        # Skip single-character bold and pure formatting
        if len(bold) < MIN_ENTITY_LENGTH:
            continue
        # Skip noisy label-like concepts
        if _normalize_entity(bold) in CONCEPT_STOPWORDS:
            continue
        _add(bold, "concept", 0.85)

    # 4. Capitalized phrases — proper nouns and named things
    for match in _CAPITALIZED_PHRASE_RE.finditer(content):
        phrase = match.group(1).strip()
        # Strip leading articles ("The Session Handler" → "Session Handler")
        words = phrase.split()
        while words and words[0].lower() in _LEADING_ARTICLES:
            words.pop(0)
        # Strip trailing noise words ("Summary Successfully" → skip)
        while words and words[-1].lower() in _PROPER_NOUN_SUFFIX_NOISE:
            words.pop()
        if len(words) >= 2:
            phrase = " ".join(words)
            # Skip if it matches a heading stopword (e.g. "Executive Summary")
            if _normalize_entity(phrase) in HEADING_STOPWORDS:
                continue
            _add(phrase, "proper_noun", 0.7)

    return entities


def _save_entities(doc_id: int, entities: list[ExtractedEntity]) -> int:
    """Save extracted entities to the database. Returns count saved."""
    if not entities:
        return 0

    with db.get_connection() as conn:
        cursor = conn.cursor()
        saved = 0
        for entity in entities:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO document_entities "
                    "(document_id, entity, entity_type, confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (doc_id, entity.normalized, entity.entity_type, entity.confidence),
                )
                if cursor.rowcount > 0:
                    saved += 1
            except Exception:
                logger.debug("Failed to save entity %r for doc %d", entity.normalized, doc_id)
        conn.commit()
    return saved


def _get_document_content(doc_id: int) -> tuple[str, str] | None:
    """Fetch document title and content by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT title, content FROM documents WHERE id = ? AND is_deleted = 0",
            (doc_id,),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None


def _get_document_project(doc_id: int) -> str | None:
    """Fetch document project by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT project FROM documents WHERE id = ? AND is_deleted = 0",
            (doc_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def _get_entities_for_doc(doc_id: int) -> dict[str, float]:
    """Get entity -> confidence mapping for a document."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT entity, confidence FROM document_entities WHERE document_id = ?",
            (doc_id,),
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


def _get_entity_doc_frequencies() -> dict[str, int]:
    """Get document frequency for all entities (batch query)."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT entity, COUNT(DISTINCT document_id) FROM document_entities GROUP BY entity"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


def _get_total_doc_count() -> int:
    """Get count of non-deleted documents."""
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def _find_docs_with_entity(
    entity: str,
    exclude_doc_id: int,
    project: str | None = None,
) -> list[int]:
    """Find all documents that have a specific entity.

    Args:
        entity: The entity text to search for.
        exclude_doc_id: Document ID to exclude from results.
        project: If set, only return docs in this project.
    """
    with db.get_connection() as conn:
        if project is not None:
            cursor = conn.execute(
                "SELECT DISTINCT de.document_id "
                "FROM document_entities de "
                "JOIN documents d ON de.document_id = d.id "
                "WHERE de.entity = ? AND de.document_id != ? "
                "AND d.project = ? AND d.is_deleted = 0",
                (entity, exclude_doc_id, project),
            )
        else:
            cursor = conn.execute(
                "SELECT DISTINCT document_id "
                "FROM document_entities "
                "WHERE entity = ? AND document_id != ?",
                (entity, exclude_doc_id),
            )
        return [row[0] for row in cursor.fetchall()]


def extract_and_save_entities(doc_id: int) -> int:
    """Extract entities from a document and save them.

    Returns count of new entities saved.
    """
    doc = _get_document_content(doc_id)
    if doc is None:
        return 0

    title, content = doc
    entities = extract_entities(content, title)
    return _save_entities(doc_id, entities)


def _idf(total_docs: int, doc_freq: int) -> float:
    """Smoothed inverse document frequency: log(1 + N/df).

    Uses log(1 + N/df) instead of log(N/df) to avoid zero scores when
    an entity appears in all documents (common in small corpora/tests).
    """
    return math.log(1 + total_docs / max(doc_freq, 1))


def entity_match_wikify(
    doc_id: int,
    entity_doc_freq: dict[str, int] | None = None,
    total_docs: int | None = None,
    cross_project: bool = False,
) -> EntityWikifyResult:
    """Cross-reference a document's entities to find and link related docs.

    Uses IDF-weighted Jaccard similarity to score links. Filters out
    high-frequency entities (>5% of docs), requires >=2 shared entities,
    and caps at top-K links per document.

    Args:
        doc_id: The document to wikify via entity matching.
        entity_doc_freq: Pre-computed entity doc frequencies (for batch).
        total_docs: Pre-computed total doc count (for batch).
        cross_project: If True, match entities across all projects.
            If False, only match within the document's project.

    Returns:
        EntityWikifyResult with details of entities and links.
    """
    # First ensure this doc has entities extracted
    doc = _get_document_content(doc_id)
    if doc is None:
        logger.warning("Document %d not found or deleted", doc_id)
        return EntityWikifyResult(doc_id=doc_id, entities_extracted=0, links_created=0)

    title, content = doc
    entities = extract_entities(content, title)
    _save_entities(doc_id, entities)

    if not entities:
        return EntityWikifyResult(doc_id=doc_id, entities_extracted=0, links_created=0)

    # Determine project scope
    scope_project: str | None = None
    if not cross_project:
        scope_project = _get_document_project(doc_id)

    # Lazy-load frequencies if not provided (single-doc mode)
    if entity_doc_freq is None:
        entity_doc_freq = _get_entity_doc_frequencies()
    if total_docs is None:
        total_docs = _get_total_doc_count()

    max_docs = max(int(total_docs * MAX_DF_RATIO), 3)  # floor of 3

    # Get existing links to avoid duplicates
    existing = set(document_links.get_linked_doc_ids(doc_id))

    # Build source entity map: entity -> confidence
    src_entities: dict[str, float] = {e.normalized: e.confidence for e in entities}

    # Find candidate targets, skipping high-frequency entities
    # target_id -> set of shared entity names
    target_shared: dict[int, set[str]] = {}
    for entity in entities:
        df = entity_doc_freq.get(entity.normalized, 1)
        if df > max_docs:
            continue  # Too common to be informative
        matching_doc_ids = _find_docs_with_entity(entity.normalized, doc_id, project=scope_project)
        for mid in matching_doc_ids:
            if mid not in existing:
                if mid not in target_shared:
                    target_shared[mid] = set()
                target_shared[mid].add(entity.normalized)

    # Filter: require minimum shared entities
    target_shared = {
        tid: shared for tid, shared in target_shared.items() if len(shared) >= MIN_SHARED_ENTITIES
    }

    if not target_shared:
        return EntityWikifyResult(
            doc_id=doc_id,
            entities_extracted=len(entities),
            links_created=0,
            skipped_existing=len(existing),
        )

    # Score using IDF-weighted Jaccard similarity
    scored: list[tuple[int, float]] = []
    for target_id, shared in target_shared.items():
        target_entities = _get_entities_for_doc(target_id)

        # IDF-weighted sum for shared entities
        shared_weight = sum(
            _idf(total_docs, entity_doc_freq.get(e, 1))
            * max(src_entities.get(e, 0.5), target_entities.get(e, 0.5))
            for e in shared
        )

        # IDF-weighted Jaccard denominator (union of both entity sets)
        union_entities = set(src_entities) | set(target_entities)
        union_weight = sum(_idf(total_docs, entity_doc_freq.get(e, 1)) for e in union_entities)

        if union_weight > 0:
            score = shared_weight / union_weight
            if score >= MIN_ENTITY_SCORE:
                scored.append((target_id, score))

    # Sort by score descending, cap at top-K
    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:MAX_ENTITY_LINKS]

    if not scored:
        return EntityWikifyResult(
            doc_id=doc_id,
            entities_extracted=len(entities),
            links_created=0,
            skipped_existing=len(existing),
        )

    # Create links
    links_to_create: list[tuple[int, int, float, str]] = [
        (doc_id, tid, score, "entity_match") for tid, score in scored
    ]

    created = document_links.create_links_batch(links_to_create)

    return EntityWikifyResult(
        doc_id=doc_id,
        entities_extracted=len(entities),
        links_created=created,
        linked_doc_ids=[t[1] for t in links_to_create[:created]],
        skipped_existing=len(existing),
    )


def entity_wikify_all(
    *,
    rebuild: bool = False,
    cross_project: bool = False,
) -> tuple[int, int, int]:
    """Backfill entity extraction and cross-referencing for all docs.

    Args:
        rebuild: If True, delete all entity_match links first.
        cross_project: If True, match entities across all projects.

    Returns:
        Tuple of (total_entities, total_links, docs_processed).
    """
    if rebuild:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM document_links WHERE link_type = 'entity_match'")
            conn.commit()
        logger.info("Cleared all entity_match links for rebuild")

    with db.get_connection() as conn:
        cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
        doc_ids = [row[0] for row in cursor.fetchall()]

    # Precompute frequencies once for the whole batch
    entity_doc_freq = _get_entity_doc_frequencies()
    total_docs = len(doc_ids)

    total_entities = 0
    total_links = 0

    for did in doc_ids:
        result = entity_match_wikify(
            did,
            entity_doc_freq=entity_doc_freq,
            total_docs=total_docs,
            cross_project=cross_project,
        )
        total_entities += result.entities_extracted
        total_links += result.links_created

    return total_entities, total_links, len(doc_ids)


def cleanup_noisy_entities() -> tuple[int, int]:
    """Delete noisy entities from the database and re-extract with current filters.

    Removes entities matching stopwords, noise patterns (trailing articles,
    agent boilerplate like "Summary Fixed"), type annotations, and other
    noise that leaked in before filters were added.

    Returns:
        Tuple of (entities_deleted, docs_re_extracted).
    """
    # Build pattern set for SQL cleanup
    noise_patterns: set[str] = set()

    # Heading stopwords in any entity_type
    noise_patterns.update(HEADING_STOPWORDS)

    # Concept stopwords
    noise_patterns.update(CONCEPT_STOPWORDS)

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 1. Delete entities that match stopword sets directly
        placeholders = ",".join("?" * len(noise_patterns))
        cursor.execute(
            f"DELETE FROM document_entities WHERE entity IN ({placeholders})",
            list(noise_patterns),
        )
        deleted_exact = cursor.rowcount

        # 2. Delete "Summary X" / "Conclusion X" / "Overview X" patterns
        #    These are proper nouns starting with heading stopwords
        deleted_pattern = 0
        heading_prefixes = [
            "summary %",
            "conclusion %",
            "overview %",
            "executive summary %",
            "test results %",
            "recommendations %",
            "key findings %",
        ]
        for prefix in heading_prefixes:
            cursor.execute(
                "DELETE FROM document_entities WHERE entity LIKE ?",
                (prefix,),
            )
            deleted_pattern += cursor.rowcount

        # 3. Delete type annotations (dict[str, any], list[dict[...]])
        cursor.execute(
            "DELETE FROM document_entities "
            "WHERE entity LIKE 'dict[%' OR entity LIKE 'list[%' "
            "OR entity LIKE 'tuple[%' OR entity LIKE 'set[%'"
        )
        deleted_types = cursor.rowcount

        conn.commit()
        total_deleted = deleted_exact + deleted_pattern + deleted_types

    # 4. Re-extract entities for all docs with current filters
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
        doc_ids = [row[0] for row in cursor.fetchall()]

    # Clear and re-extract
    with db.get_connection() as conn:
        conn.execute("DELETE FROM document_entities")
        conn.commit()

    re_extracted = 0
    for did in doc_ids:
        count = extract_and_save_entities(did)
        if count > 0:
            re_extracted += 1

    return total_deleted, re_extracted


# ── LLM-powered entity extraction ───────────────────────────────────

# Richer entity types supported by LLM extraction
LLM_ENTITY_TYPES = frozenset(
    {
        "person",
        "organization",
        "technology",
        "concept",
        "location",
        "event",
        "project",
        "tool",
        "api",
        "library",
    }
)

# Model shorthand → full model ID mapping
_MODEL_MAP: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20250315",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}

# Cost per million tokens (input, output) for estimation
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "haiku": (0.80, 4.00),
    "sonnet": (3.00, 15.00),
    "opus": (15.00, 75.00),
}

# Maximum content length to send to the LLM (chars)
_MAX_CONTENT_LENGTH = 12000

# Timeout for Claude CLI invocation (seconds)
_CLAUDE_TIMEOUT = 60


class LLMEntity(TypedDict):
    """An entity extracted by the LLM."""

    name: str
    entity_type: str
    confidence: float


class LLMRelationship(TypedDict):
    """A relationship between entities extracted by the LLM."""

    source: str
    target: str
    relationship_type: str
    confidence: float


class LLMExtractionResult(TypedDict):
    """Full result from LLM entity extraction."""

    entities: list[LLMEntity]
    relationships: list[LLMRelationship]


class LLMExtractionStats(TypedDict):
    """Statistics from an LLM extraction run."""

    doc_id: int
    entities_saved: int
    relationships_saved: int
    model: str
    estimated_input_tokens: int
    estimated_cost_usd: float


def resolve_model(shorthand: str) -> str:
    """Resolve a model shorthand to a full model ID.

    Args:
        shorthand: 'haiku', 'sonnet', 'opus', or a full model ID.

    Returns:
        The full model ID string.
    """
    return _MODEL_MAP.get(shorthand.lower(), shorthand)


def estimate_cost(content_length: int, model: str = "haiku") -> float:
    """Estimate cost in USD for extracting entities from content.

    Uses a rough 4 chars/token heuristic for input estimation
    and assumes ~500 output tokens for structured JSON response.
    """
    key = model.lower() if model.lower() in _MODEL_COSTS else "haiku"
    input_cost, output_cost = _MODEL_COSTS[key]
    estimated_input_tokens = min(content_length, _MAX_CONTENT_LENGTH) // 4
    estimated_output_tokens = 500
    cost = (
        estimated_input_tokens * input_cost / 1_000_000
        + estimated_output_tokens * output_cost / 1_000_000
    )
    return cost


def _build_extraction_prompt(content: str, title: str) -> str:
    """Build the prompt for LLM entity extraction."""
    truncated = content[:_MAX_CONTENT_LENGTH]
    entity_types = ", ".join(sorted(LLM_ENTITY_TYPES))
    return f"""Extract entities and relationships from this document.

Title: {title}

Content:
{truncated}

Return ONLY valid JSON with this exact structure:
{{
  "entities": [
    {{"name": "Entity Name", "entity_type": "type", "confidence": 0.95}}
  ],
  "relationships": [
    {{"source": "Entity A", "target": "Entity B", "relationship_type": "uses", "confidence": 0.9}}
  ]
}}

Entity types: {entity_types}
Rules:
- Extract 5-30 entities depending on document length
- Confidence 0.0-1.0 based on how clearly the entity is referenced
- Skip generic terms (the, this, example, etc.)
- Relationship types: uses, extends, implements, depends_on, related_to, part_of, created_by
- Only include relationships that are clearly stated or strongly implied"""


def _parse_llm_response(raw: str) -> LLMExtractionResult:
    """Parse the LLM response, handling markdown fences and edge cases.

    Strips markdown code fences (```json ... ```) if present,
    then parses JSON.
    """
    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    parsed = json.loads(text)

    entities: list[LLMEntity] = []
    for e in parsed.get("entities", []):
        name = str(e.get("name", "")).strip()
        entity_type = str(e.get("entity_type", "concept")).lower()
        confidence = float(e.get("confidence", 0.8))

        # Validate and filter
        normalized = _normalize_entity(name)
        if not _is_valid_entity(normalized):
            continue
        if entity_type not in LLM_ENTITY_TYPES:
            entity_type = "concept"
        confidence = max(0.0, min(1.0, confidence))

        entities.append(
            LLMEntity(
                name=name,
                entity_type=entity_type,
                confidence=confidence,
            )
        )

    relationships: list[LLMRelationship] = []
    for r in parsed.get("relationships", []):
        source = str(r.get("source", "")).strip()
        target = str(r.get("target", "")).strip()
        rel_type = str(r.get("relationship_type", "related_to"))
        confidence = float(r.get("confidence", 0.8))

        if not source or not target:
            continue
        confidence = max(0.0, min(1.0, confidence))

        relationships.append(
            LLMRelationship(
                source=source,
                target=target,
                relationship_type=rel_type,
                confidence=confidence,
            )
        )

    return LLMExtractionResult(
        entities=entities,
        relationships=relationships,
    )


def _call_claude_for_entities(
    content: str,
    title: str,
    model: str = "haiku",
) -> LLMExtractionResult:
    """Call Claude CLI to extract entities and relationships.

    Args:
        content: Document content.
        title: Document title.
        model: Model shorthand or full ID.

    Returns:
        Parsed extraction result.

    Raises:
        subprocess.TimeoutExpired: If the CLI call times out.
        RuntimeError: If the CLI call fails or response is invalid.
    """
    full_model = resolve_model(model)
    prompt = _build_extraction_prompt(content, title)

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", full_model, prompt],
            capture_output=True,
            text=True,
            timeout=_CLAUDE_TIMEOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Claude CLI not found. Install it with: npm install -g @anthropic-ai/claude-code"
        ) from None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Claude CLI failed: {stderr}") from None

    return _parse_llm_response(result.stdout)


def _save_llm_entities(
    doc_id: int,
    entities: list[LLMEntity],
    conn: sqlite3.Connection | None = None,
) -> int:
    """Save LLM-extracted entities to the database. Returns count saved."""
    if not entities:
        return 0

    def _do_save(c: sqlite3.Connection) -> int:
        cursor = c.cursor()
        saved = 0
        for entity in entities:
            normalized = _normalize_entity(entity["name"])
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO document_entities "
                    "(document_id, entity, entity_type, confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        doc_id,
                        normalized,
                        entity["entity_type"],
                        entity["confidence"],
                    ),
                )
                if cursor.rowcount > 0:
                    saved += 1
            except Exception:
                logger.debug(
                    "Failed to save LLM entity %r for doc %d",
                    normalized,
                    doc_id,
                )
        c.commit()
        return saved

    if conn is not None:
        return _do_save(conn)

    with db.get_connection() as c:
        return _do_save(c)


def _save_relationships(
    relationships: list[LLMRelationship],
    doc_id: int,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Persist relationships to entity_relationships table.

    Looks up entity IDs from document_entities by normalized name,
    then inserts relationships. Returns count saved.
    """
    if not relationships:
        return 0

    def _do_save(c: sqlite3.Connection) -> int:
        cursor = c.cursor()

        # Build name -> entity_id mapping for this document
        cursor.execute(
            "SELECT id, entity FROM document_entities WHERE document_id = ?",
            (doc_id,),
        )
        entity_map: dict[str, int] = {row[1]: row[0] for row in cursor.fetchall()}

        saved = 0
        for rel in relationships:
            src_norm = _normalize_entity(rel["source"])
            tgt_norm = _normalize_entity(rel["target"])

            src_id = entity_map.get(src_norm)
            tgt_id = entity_map.get(tgt_norm)

            if src_id is None or tgt_id is None:
                continue

            try:
                cursor.execute(
                    "INSERT INTO entity_relationships "
                    "(source_entity_id, target_entity_id, "
                    "relationship_type, confidence) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        src_id,
                        tgt_id,
                        rel["relationship_type"],
                        rel["confidence"],
                    ),
                )
                if cursor.rowcount > 0:
                    saved += 1
            except Exception:
                logger.debug(
                    "Failed to save relationship %s->%s for doc %d",
                    src_norm,
                    tgt_norm,
                    doc_id,
                )
        c.commit()
        return saved

    if conn is not None:
        return _do_save(conn)

    with db.get_connection() as c:
        return _do_save(c)


def extract_entities_llm(
    content: str,
    title: str,
    model: str = "haiku",
) -> LLMExtractionResult:
    """Extract entities and relationships using Claude LLM.

    This is the high-level extraction function. It calls Claude CLI,
    parses the response, and returns structured results.

    Args:
        content: Document content to extract from.
        title: Document title for context.
        model: Model shorthand (haiku/sonnet/opus) or full ID.

    Returns:
        LLMExtractionResult with entities and relationships.
    """
    return _call_claude_for_entities(content, title, model)


def extract_and_save_entities_llm(
    doc_id: int,
    model: str = "haiku",
) -> LLMExtractionStats:
    """Extract entities via LLM and save to database.

    Convenience wrapper that fetches document content, calls the LLM,
    saves entities and relationships, and returns statistics.

    Args:
        doc_id: Document ID to extract from.
        model: Model shorthand or full ID.

    Returns:
        LLMExtractionStats with counts and cost estimate.
    """
    doc = _get_document_content(doc_id)
    if doc is None:
        return LLMExtractionStats(
            doc_id=doc_id,
            entities_saved=0,
            relationships_saved=0,
            model=resolve_model(model),
            estimated_input_tokens=0,
            estimated_cost_usd=0.0,
        )

    title, content = doc
    result = _call_claude_for_entities(content, title, model)

    entities_saved = _save_llm_entities(doc_id, result["entities"])
    relationships_saved = _save_relationships(result["relationships"], doc_id)

    content_len = min(len(content), _MAX_CONTENT_LENGTH)
    estimated_tokens = content_len // 4

    return LLMExtractionStats(
        doc_id=doc_id,
        entities_saved=entities_saved,
        relationships_saved=relationships_saved,
        model=resolve_model(model),
        estimated_input_tokens=estimated_tokens,
        estimated_cost_usd=estimate_cost(len(content), model),
    )
