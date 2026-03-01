"""Title-match wikification service.

Scans document content for mentions of other documents' titles
and creates bidirectional links in the document_links table.

This is Layer 1 of the auto-wikify system — zero cost, no AI,
no embeddings. Every document title is a potential link target,
similar to how Wikipedia works.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..database import db, document_links

logger = logging.getLogger(__name__)

# Titles shorter than this are excluded to avoid false positives
MIN_TITLE_LENGTH = 4

# Common titles that are too generic to be useful as link targets
STOPWORD_TITLES = frozenset(
    {
        "notes",
        "todo",
        "todos",
        "draft",
        "temp",
        "test",
        "untitled",
        "readme",
        "changelog",
        "note",
        "scratch",
        "misc",
        "stuff",
        "ideas",
        "plan",
        "log",
        "docs",
        "help",
        "info",
        "data",
        "config",
    }
)


@dataclass
class TitleCandidate:
    """A document title that can be matched against content."""

    doc_id: int
    title: str
    normalized: str
    pattern: re.Pattern[str]


@dataclass
class WikifyResult:
    """Result of wikifying a document."""

    doc_id: int
    links_created: int
    linked_doc_ids: list[int] = field(default_factory=list)
    skipped_existing: int = 0
    dry_run_matches: list[tuple[int, str]] = field(default_factory=list)


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison.

    Lowercases and strips leading/trailing punctuation.
    """
    normalized = title.lower().strip()
    # Strip leading/trailing punctuation but keep internal punctuation
    normalized = re.sub(r"^[^\w]+|[^\w]+$", "", normalized)
    return normalized


def _build_title_pattern(normalized_title: str) -> re.Pattern[str]:
    r"""Build a word-boundary regex pattern for a title.

    Uses \b word boundaries so "auth" doesn't match "authorization"
    but "auth module" matches "the auth module broke".
    """
    escaped = re.escape(normalized_title)
    return re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)


def _load_title_candidates(
    exclude_doc_id: int | None = None,
    project: str | None = None,
) -> list[TitleCandidate]:
    """Load all document titles as match candidates.

    Filters out:
    - Deleted documents
    - Titles shorter than MIN_TITLE_LENGTH
    - Stopword titles
    - The document being wikified (if exclude_doc_id is set)

    Args:
        exclude_doc_id: Document ID to exclude from candidates.
        project: If set, only load candidates from this project.
    """
    with db.get_connection() as conn:
        if project is not None:
            cursor = conn.execute(
                "SELECT id, title FROM documents WHERE is_deleted = 0 AND project = ?",
                (project,),
            )
        else:
            cursor = conn.execute("SELECT id, title FROM documents WHERE is_deleted = 0")
        rows = cursor.fetchall()

    candidates: list[TitleCandidate] = []
    for row in rows:
        doc_id = row[0]
        title = row[1]

        if exclude_doc_id is not None and doc_id == exclude_doc_id:
            continue

        normalized = _normalize_title(title)

        if len(normalized) < MIN_TITLE_LENGTH:
            continue

        if normalized in STOPWORD_TITLES:
            continue

        pattern = _build_title_pattern(normalized)
        candidates.append(
            TitleCandidate(
                doc_id=doc_id,
                title=title,
                normalized=normalized,
                pattern=pattern,
            )
        )

    return candidates


def _get_document_content(doc_id: int) -> str | None:
    """Fetch document content by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT content FROM documents WHERE id = ? AND is_deleted = 0",
            (doc_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def _get_document_project(doc_id: int) -> str | None:
    """Fetch document project by ID."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT project FROM documents WHERE id = ? AND is_deleted = 0",
            (doc_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def title_match_wikify(
    doc_id: int,
    dry_run: bool = False,
    cross_project: bool = False,
) -> WikifyResult:
    """Find title mentions in a document and create links.

    Scans the document's content for word-boundary matches against
    all other document titles. Creates bidirectional links with
    method='title_match' and score=1.0.

    Args:
        doc_id: The document to wikify.
        dry_run: If True, report matches without creating links.
        cross_project: If True, match titles across all projects.
            If False, only match within the document's project.

    Returns:
        WikifyResult with details of links created or matches found.
    """
    content = _get_document_content(doc_id)
    if content is None:
        logger.warning("Document %d not found or deleted", doc_id)
        return WikifyResult(doc_id=doc_id, links_created=0)

    # Determine project scope
    scope_project: str | None = None
    if not cross_project:
        scope_project = _get_document_project(doc_id)

    content_lower = content.lower()
    candidates = _load_title_candidates(exclude_doc_id=doc_id, project=scope_project)

    # Get existing links to avoid duplicates
    existing = set(document_links.get_linked_doc_ids(doc_id))

    matches: list[tuple[int, str]] = []
    skipped = 0

    for candidate in candidates:
        if candidate.pattern.search(content_lower):
            if candidate.doc_id in existing:
                skipped += 1
                continue
            matches.append((candidate.doc_id, candidate.title))

    if dry_run:
        return WikifyResult(
            doc_id=doc_id,
            links_created=0,
            dry_run_matches=matches,
            skipped_existing=skipped,
        )

    if not matches:
        return WikifyResult(
            doc_id=doc_id,
            links_created=0,
            skipped_existing=skipped,
        )

    # Create links in batch
    links_to_create = [(doc_id, target_id, 1.0, "title_match") for target_id, _title in matches]
    created = document_links.create_links_batch(links_to_create)

    return WikifyResult(
        doc_id=doc_id,
        links_created=created,
        linked_doc_ids=[target_id for target_id, _title in matches[:created]],
        skipped_existing=skipped,
    )


def wikify_all(
    dry_run: bool = False,
    cross_project: bool = False,
) -> tuple[int, int]:
    """Backfill title-match wikification for all documents.

    Args:
        dry_run: If True, report matches without creating links.
        cross_project: If True, match titles across all projects.

    Returns:
        Tuple of (total_links_created_or_would_create, documents_processed).
    """
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT id FROM documents WHERE is_deleted = 0")
        doc_ids = [row[0] for row in cursor.fetchall()]

    total = 0
    for did in doc_ids:
        result = title_match_wikify(did, dry_run=dry_run, cross_project=cross_project)
        if dry_run:
            total += len(result.dry_run_matches)
        else:
            total += result.links_created

    return total, len(doc_ids)
