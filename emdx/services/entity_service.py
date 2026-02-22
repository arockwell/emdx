"""Entity extraction and entity-match wikification service.

Layer 3 of the auto-wikify system. Extracts key entities (concepts,
technical terms, proper nouns) from documents using heuristics, then
cross-references them to create links between documents that share
entities — even if their titles don't match.

Zero cost: no AI, no embeddings. Uses markdown structure and text
patterns to identify entities.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..database import db, document_links

logger = logging.getLogger(__name__)

# Entities shorter than this are excluded to avoid noise
MIN_ENTITY_LENGTH = 4

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
        _add(bold, "concept", 0.85)

    # 4. Capitalized phrases — proper nouns and named things
    for match in _CAPITALIZED_PHRASE_RE.finditer(content):
        phrase = match.group(1).strip()
        # Strip leading articles ("The Session Handler" → "Session Handler")
        words = phrase.split()
        while words and words[0].lower() in _LEADING_ARTICLES:
            words.pop(0)
        if len(words) >= 2:
            phrase = " ".join(words)
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


def _get_entities_for_doc(doc_id: int) -> set[str]:
    """Get all entity strings for a document."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT entity FROM document_entities WHERE document_id = ?",
            (doc_id,),
        )
        return {row[0] for row in cursor.fetchall()}


def _find_docs_with_entity(entity: str, exclude_doc_id: int) -> list[int]:
    """Find all documents that have a specific entity."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT DISTINCT document_id FROM document_entities "
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


def entity_match_wikify(doc_id: int) -> EntityWikifyResult:
    """Cross-reference a document's entities to find and link related docs.

    For each entity in the source document, finds other documents that
    share the same entity and creates links with method='entity_match'.

    Args:
        doc_id: The document to wikify via entity matching.

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

    # Get existing links to avoid duplicates
    existing = set(document_links.get_linked_doc_ids(doc_id))

    # Find other docs that share entities with this doc
    target_entity_count: dict[int, int] = {}
    for entity in entities:
        matching_doc_ids = _find_docs_with_entity(entity.normalized, doc_id)
        for mid in matching_doc_ids:
            if mid not in existing:
                target_entity_count[mid] = target_entity_count.get(mid, 0) + 1

    if not target_entity_count:
        return EntityWikifyResult(
            doc_id=doc_id,
            entities_extracted=len(entities),
            links_created=0,
            skipped_existing=len(existing),
        )

    # Create links — score based on shared entity count
    max_shared = max(target_entity_count.values())
    links_to_create: list[tuple[int, int, float, str]] = []
    for target_id, count in target_entity_count.items():
        # Score: fraction of max shared entities, scaled 0.5–1.0
        score = 0.5 + 0.5 * (count / max_shared)
        links_to_create.append((doc_id, target_id, score, "entity_match"))

    created = document_links.create_links_batch(links_to_create)

    return EntityWikifyResult(
        doc_id=doc_id,
        entities_extracted=len(entities),
        links_created=created,
        linked_doc_ids=[t[1] for t in links_to_create[:created]],
        skipped_existing=len(existing),
    )


def entity_wikify_all() -> tuple[int, int, int]:
    """Backfill entity extraction and cross-referencing for all documents.

    Returns:
        Tuple of (total_entities_extracted, total_links_created, docs_processed).
    """
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
        doc_ids = [row[0] for row in cursor.fetchall()]

    total_entities = 0
    total_links = 0

    for did in doc_ids:
        result = entity_match_wikify(did)
        total_entities += result.entities_extracted
        total_links += result.links_created

    return total_entities, total_links, len(doc_ids)
