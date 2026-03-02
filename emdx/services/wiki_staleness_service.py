"""Wiki staleness detection service.

Checks wiki articles for staleness by comparing source document content
hashes and topic membership against what was used during generation.

Two modes:
- ``check_staleness()`` — full scan of all articles (batch)
- ``check_doc_staleness(doc_id)`` — lightweight single-doc check for hooks
"""

from __future__ import annotations

import hashlib
import logging
from typing import TypedDict

from ..database import db

logger = logging.getLogger(__name__)


# ── TypedDicts ────────────────────────────────────────────────────────


class StaleSource(TypedDict):
    """A source document whose content hash has changed."""

    doc_id: int
    doc_title: str
    old_hash: str
    new_hash: str


class MembershipChange(TypedDict):
    """A change in topic membership (doc added or removed)."""

    doc_id: int
    doc_title: str
    change_type: str  # "added" or "removed"


class StaleArticle(TypedDict):
    """A wiki article that needs regeneration."""

    article_id: int
    topic_id: int
    topic_label: str
    document_id: int
    stale_reason: str
    changed_sources: list[StaleSource]
    membership_changes: list[MembershipChange]


class StalenessResult(TypedDict):
    """Result of a full staleness scan."""

    total_articles: int
    stale_articles: int
    fresh_articles: int
    details: list[StaleArticle]


# ── Helpers ───────────────────────────────────────────────────────────


def _content_hash(content: str) -> str:
    """Compute SHA-256[:16] content hash, consistent with synthesis service."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_current_topic_members(topic_id: int) -> set[int]:
    """Get current primary member doc IDs for a topic."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT document_id FROM wiki_topic_members WHERE topic_id = ? AND is_primary = 1",
            (topic_id,),
        ).fetchall()
    return {row[0] for row in rows}


def _get_doc_title(doc_id: int) -> str:
    """Get a document's title, or a fallback string."""
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT title FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    return row[0] if row else f"(deleted doc #{doc_id})"


# ── Public API ────────────────────────────────────────────────────────


def check_staleness() -> StalenessResult:
    """Full scan of all wiki articles for staleness.

    For each article:
    1. Compare stored content_hash in wiki_article_sources against
       current document content.
    2. Compare current topic membership against article sources
       to detect added/removed documents.

    Marks stale articles in the DB (is_stale=1, stale_reason).

    Returns:
        StalenessResult with details of all stale articles.
    """
    with db.get_connection() as conn:
        articles = conn.execute(
            "SELECT wa.id, wa.topic_id, wa.document_id, wt.topic_label "
            "FROM wiki_articles wa "
            "JOIN wiki_topics wt ON wa.topic_id = wt.id"
        ).fetchall()

    details: list[StaleArticle] = []
    total = len(articles)
    stale_count = 0

    for article_row in articles:
        article_id = article_row[0]
        topic_id = article_row[1]
        document_id = article_row[2]
        topic_label = article_row[3]

        changed_sources: list[StaleSource] = []
        membership_changes: list[MembershipChange] = []

        # 1. Check source content hashes
        with db.get_connection() as conn:
            source_rows = conn.execute(
                "SELECT was.document_id, was.content_hash, d.content, d.title "
                "FROM wiki_article_sources was "
                "LEFT JOIN documents d ON was.document_id = d.id "
                "WHERE was.article_id = ?",
                (article_id,),
            ).fetchall()

        source_doc_ids: set[int] = set()
        for src_row in source_rows:
            src_doc_id = src_row[0]
            old_hash = src_row[1] or ""
            current_content = src_row[2] or ""
            src_title = src_row[3] or f"(deleted doc #{src_doc_id})"
            source_doc_ids.add(src_doc_id)

            new_hash = _content_hash(current_content)
            if old_hash and new_hash != old_hash:
                changed_sources.append(
                    StaleSource(
                        doc_id=src_doc_id,
                        doc_title=src_title,
                        old_hash=old_hash,
                        new_hash=new_hash,
                    )
                )

        # 2. Check topic membership changes
        current_members = _get_current_topic_members(topic_id)

        added = current_members - source_doc_ids
        removed = source_doc_ids - current_members

        for doc_id in added:
            membership_changes.append(
                MembershipChange(
                    doc_id=doc_id,
                    doc_title=_get_doc_title(doc_id),
                    change_type="added",
                )
            )

        for doc_id in removed:
            membership_changes.append(
                MembershipChange(
                    doc_id=doc_id,
                    doc_title=_get_doc_title(doc_id),
                    change_type="removed",
                )
            )

        # Build stale reason
        reasons: list[str] = []
        if changed_sources:
            reasons.append(f"{len(changed_sources)} source(s) changed")
        if membership_changes:
            added_count = sum(1 for m in membership_changes if m["change_type"] == "added")
            removed_count = sum(1 for m in membership_changes if m["change_type"] == "removed")
            parts: list[str] = []
            if added_count:
                parts.append(f"{added_count} added")
            if removed_count:
                parts.append(f"{removed_count} removed")
            reasons.append(f"membership changed ({', '.join(parts)})")

        if reasons:
            stale_reason = "; ".join(reasons)
            stale_count += 1

            # Mark stale in DB
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE wiki_articles SET is_stale = 1, stale_reason = ? WHERE id = ?",
                    (stale_reason, article_id),
                )
                conn.commit()

            details.append(
                StaleArticle(
                    article_id=article_id,
                    topic_id=topic_id,
                    topic_label=topic_label,
                    document_id=document_id,
                    stale_reason=stale_reason,
                    changed_sources=changed_sources,
                    membership_changes=membership_changes,
                )
            )
        else:
            # Ensure it is marked fresh
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE wiki_articles "
                    "SET is_stale = 0, stale_reason = '' "
                    "WHERE id = ? AND is_stale = 1",
                    (article_id,),
                )
                conn.commit()

    logger.info(
        "Staleness check: %d/%d articles stale",
        stale_count,
        total,
    )

    return StalenessResult(
        total_articles=total,
        stale_articles=stale_count,
        fresh_articles=total - stale_count,
        details=details,
    )


def check_doc_staleness(doc_id: int) -> bool:
    """Lightweight single-doc staleness check.

    Called from the save/edit hook. Checks if *doc_id* is a source for
    any wiki article and, if so, compares its current content hash
    against the stored hash.

    Returns:
        True if any articles were newly marked stale.
    """
    with db.get_connection() as conn:
        # Find articles that use this doc as a source
        rows = conn.execute(
            "SELECT was.article_id, was.content_hash "
            "FROM wiki_article_sources was "
            "WHERE was.document_id = ?",
            (doc_id,),
        ).fetchall()

    if not rows:
        return False

    # Get current content
    with db.get_connection() as conn:
        doc_row = conn.execute(
            "SELECT content FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

    if not doc_row:
        return False

    current_hash = _content_hash(doc_row[0] or "")
    marked = False

    for row in rows:
        article_id = row[0]
        stored_hash = row[1] or ""

        if stored_hash and current_hash != stored_hash:
            reason = f"source doc #{doc_id} content changed"
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE wiki_articles "
                    "SET is_stale = 1, stale_reason = ? "
                    "WHERE id = ? AND is_stale = 0",
                    (reason, article_id),
                )
                conn.commit()
            marked = True
            logger.info(
                "Marked article #%d stale: doc #%d changed",
                article_id,
                doc_id,
            )

    return marked
