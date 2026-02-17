"""
Auto-tagging service for EMDX.
Analyzes document content and suggests appropriate tags based on patterns.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Union

from ..config.constants import (
    DEFAULT_MAX_SUGGESTIONS,
    DEFAULT_MAX_TAGS_PER_DOC,
    DEFAULT_TAGGING_CONFIDENCE,
)
from ..database import DatabaseConnection
from ..models.tags import get_or_create_tag
from ..services.types import BatchAutoTagResult, DocumentTagResult
from ..utils.emoji_aliases import EMOJI_ALIASES

# Type alias for SQL parameters
SqlParam = Union[str, int, float, None]


class AutoTagger:
    """Service for automatically suggesting and applying tags to documents."""

    # Default pattern rules for auto-tagging
    DEFAULT_PATTERNS = {
        # Document types
        "gameplan": {
            "title_patterns": [r"^gameplan:", r"gameplan for", r"plan to"],
            "content_patterns": [r"## goals", r"## objectives", r"## success criteria"],
            "confidence": 0.9,
            "tags": ["gameplan", "active"],
        },
        "analysis": {
            "title_patterns": [r"^analysis:", r"analyzing", r"investigation"],
            "content_patterns": [r"## findings", r"## results", r"## conclusion"],
            "confidence": 0.85,
            "tags": ["analysis"],
        },
        "notes": {
            "title_patterns": [r"^notes:", r"meeting notes", r"quick notes"],
            "content_patterns": [r"^- ", r"^\* ", r"TODO:", r"note:"],
            "confidence": 0.7,
            "tags": ["notes"],
        },
        "docs": {
            "title_patterns": [r"documentation", r"readme", r"guide", r"tutorial"],
            "content_patterns": [r"## installation", r"## usage", r"## examples"],
            "confidence": 0.8,
            "tags": ["docs"],
        },
        # Technical work
        "bug": {
            "title_patterns": [r"bug:", r"fix:", r"error:", r"issue:"],
            "content_patterns": [r"error", r"exception", r"traceback", r"bug"],
            "confidence": 0.85,
            "tags": ["bug", "active"],
        },
        "feature": {
            "title_patterns": [r"feature:", r"implement", r"add support"],
            "content_patterns": [r"new feature", r"enhancement", r"implement"],
            "confidence": 0.8,
            "tags": ["feature", "active"],
        },
        "refactor": {
            "title_patterns": [r"refactor:", r"cleanup:", r"improve"],
            "content_patterns": [r"refactor", r"cleanup", r"optimize", r"reorganize"],
            "confidence": 0.75,
            "tags": ["refactor"],
        },
        "test": {
            "title_patterns": [r"test:", r"testing", r"tests for"],
            "content_patterns": [r"test_", r"assert", r"pytest", r"unittest"],
            "confidence": 0.9,
            "tags": ["test"],
        },
        # Status detection
        "done": {
            "title_patterns": [r"✓", r"done:", r"completed:"],
            "content_patterns": [r"completed", r"finished", r"done", r"success"],
            "confidence": 0.7,
            "tags": ["done"],
        },
        "blocked": {
            "title_patterns": [r"blocked:", r"stuck:"],
            "content_patterns": [r"blocked by", r"waiting for", r"stuck on", r"cannot proceed"],
            "confidence": 0.8,
            "tags": ["blocked"],
        },
        # Priority
        "urgent": {
            "title_patterns": [r"urgent:", r"urgent\s", r"critical:", r"critical\s", r"asap"],
            "content_patterns": [r"urgent", r"critical", r"immediately", r"asap"],
            "confidence": 0.85,
            "tags": ["urgent"],
        },
    }

    def __init__(
        self,
        db_path: Union[str, Path] | None = None,
        patterns: dict | None = None,
    ):
        # Use centralized database connection management
        if db_path is not None:
            self.db = DatabaseConnection(Path(db_path) if isinstance(db_path, str) else db_path)
        else:
            self.db = DatabaseConnection()

        # Load patterns with configuration
        if patterns:
            self.patterns = patterns
        else:
            # Merge default patterns with user configuration
            from ..config.tagging_rules import merge_with_defaults

            self.patterns = merge_with_defaults({})

    def analyze_document(
        self, title: str, content: str | None = None, existing_tags: list[str] | None = None
    ) -> list[tuple[str, float]]:
        """
        Analyze a document and suggest tags with confidence scores.

        Args:
            title: Document title
            content: Document content (optional)
            existing_tags: Currently assigned tags (to avoid duplicates)

        Returns:
            List of tuples (tag, confidence) sorted by confidence
        """
        existing_set: set[str] = set(existing_tags or [])
        suggestions: defaultdict[str, float] = defaultdict(float)

        # Normalize text for matching
        title_lower = title.lower()
        content_lower = (content or "").lower()

        # Check each pattern
        for _pattern_name, rules in self.patterns.items():
            confidence = 0.0
            base_confidence = rules["confidence"]

            # Check title patterns
            title_matches = 0
            for pattern in rules.get("title_patterns", []):
                if re.search(pattern, title_lower, re.IGNORECASE):
                    title_matches += 1

            if title_matches > 0:
                confidence = base_confidence

            # Check content patterns (if content provided)
            if content and rules.get("content_patterns"):
                content_matches = 0
                for pattern in rules["content_patterns"]:
                    if re.search(pattern, content_lower, re.IGNORECASE):
                        content_matches += 1

                if content_matches > 0:
                    # Boost confidence if both title and content match
                    if title_matches > 0:
                        confidence = min(1.0, confidence + 0.1)
                    else:
                        confidence = (
                            base_confidence * 0.75
                        )  # Lower confidence for content-only match  # noqa: E501

            # Add suggested tags if confidence threshold met
            if confidence >= 0.6:
                for tag in rules["tags"]:
                    # Convert to emoji if needed
                    emoji_tag = EMOJI_ALIASES.get(tag, tag)
                    if emoji_tag not in existing_set:
                        suggestions[emoji_tag] = max(suggestions[emoji_tag], confidence)

        # Sort by confidence
        sorted_suggestions = sorted(suggestions.items(), key=lambda x: x[1], reverse=True)
        return sorted_suggestions

    def suggest_tags(
        self, document_id: int, max_suggestions: int = DEFAULT_MAX_SUGGESTIONS
    ) -> list[tuple[str, float]]:
        """
        Suggest tags for a specific document.

        Args:
            document_id: Document ID
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of tuples (tag, confidence)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get document details
            cursor.execute(
                """
                SELECT d.title, d.content, GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.id = ? AND d.is_deleted = 0
                GROUP BY d.id
            """,
                (document_id,),
            )

            doc = cursor.fetchone()

        if not doc:
            return []

        existing_tags = doc["tags"].split(",") if doc["tags"] else []
        suggestions = self.analyze_document(doc["title"], doc["content"], existing_tags)

        return suggestions[:max_suggestions]

    def auto_tag_document(
        self,
        document_id: int,
        confidence_threshold: float = DEFAULT_TAGGING_CONFIDENCE,
        max_tags: int = DEFAULT_MAX_TAGS_PER_DOC,
    ) -> list[str]:
        """
        Automatically apply high-confidence tags to a document.

        Args:
            document_id: Document ID
            confidence_threshold: Minimum confidence to apply tag
            max_tags: Maximum number of tags to apply

        Returns:
            List of applied tags
        """
        import sqlite3

        suggestions = self.suggest_tags(document_id, max_suggestions=max_tags)
        applied_tags = []

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            for tag, confidence in suggestions:
                if confidence >= confidence_threshold:
                    try:
                        # Get or create tag
                        tag_id = get_or_create_tag(conn, tag)

                        # Apply tag to document
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO document_tags (document_id, tag_id)
                            VALUES (?, ?)
                        """,
                            (document_id, tag_id),
                        )

                        if cursor.rowcount > 0:
                            applied_tags.append(tag)
                    except sqlite3.IntegrityError:
                        # Skip duplicate tag assignments
                        continue

            conn.commit()

        return applied_tags

    def batch_suggest(
        self,
        untagged_only: bool = True,
        project: str | None = None,
        limit: int | None = None,
    ) -> dict[int, list[tuple[str, float]]]:
        """
        Suggest tags for multiple documents.

        Args:
            untagged_only: Only process documents without tags
            project: Filter by project
            limit: Maximum number of documents to process

        Returns:
            Dictionary mapping document IDs to suggestions
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build query
            query = """
                SELECT d.id, d.title, d.content, GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.is_deleted = 0
            """

            params: list[SqlParam] = []

            if project:
                query += " AND d.project = ?"
                params.append(project)

            query += " GROUP BY d.id"

            if untagged_only:
                query += " HAVING tags IS NULL"

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)
            documents = cursor.fetchall()

        # Generate suggestions for each document
        suggestions = {}
        for doc in documents:
            existing_tags = doc["tags"].split(",") if doc["tags"] else []
            doc_suggestions = self.analyze_document(
                doc["title"],
                doc["content"],
                existing_tags,
            )
            if doc_suggestions:
                suggestions[doc["id"]] = doc_suggestions

        return suggestions

    def batch_auto_tag(
        self,
        document_ids: list[int] | None = None,
        untagged_only: bool = True,
        project: str | None = None,
        confidence_threshold: float = DEFAULT_TAGGING_CONFIDENCE,
        max_tags_per_doc: int = DEFAULT_MAX_TAGS_PER_DOC,
        dry_run: bool = True,
    ) -> BatchAutoTagResult:
        """
        Apply auto-tagging to multiple documents.

        Args:
            document_ids: Specific document IDs to tag (if None, process all)
            untagged_only: Only process documents without tags
            project: Filter by project
            confidence_threshold: Minimum confidence to apply tag
            max_tags_per_doc: Maximum tags per document
            dry_run: If True, don't actually apply tags

        Returns:
            Summary of operations
        """
        processed = 0
        tagged = 0
        tags_applied = 0
        documents: list[DocumentTagResult] = []

        if document_ids:
            # Process specific documents
            for doc_id in document_ids:
                doc_suggestions = self.suggest_tags(doc_id, max_suggestions=max_tags_per_doc)
                eligible_tags = [
                    (tag, conf) for tag, conf in doc_suggestions if conf >= confidence_threshold
                ]

                if eligible_tags:
                    doc_result: DocumentTagResult = {"id": doc_id, "suggested_tags": eligible_tags}

                    if not dry_run:
                        applied = self.auto_tag_document(
                            doc_id, confidence_threshold, max_tags_per_doc
                        )
                        doc_result["applied_tags"] = applied
                        tags_applied += len(applied)
                        if applied:
                            tagged += 1

                    documents.append(doc_result)

                processed += 1
        else:
            # Batch process based on criteria
            batch_suggestions = self.batch_suggest(untagged_only, project)
            processed = len(batch_suggestions)

            for doc_id, doc_suggestions in batch_suggestions.items():
                eligible_tags = [
                    (tag, conf)
                    for tag, conf in doc_suggestions[:max_tags_per_doc]
                    if conf >= confidence_threshold
                ]

                if eligible_tags:
                    batch_result: DocumentTagResult = {
                        "id": doc_id,
                        "suggested_tags": eligible_tags,
                    }

                    if not dry_run:
                        applied = self.auto_tag_document(
                            doc_id, confidence_threshold, max_tags_per_doc
                        )
                        batch_result["applied_tags"] = applied
                        tags_applied += len(applied)
                        if applied:
                            tagged += 1

                    documents.append(batch_result)

        return {
            "processed": processed,
            "tagged": tagged,
            "tags_applied": tags_applied,
            "documents": documents,
        }

    def add_custom_pattern(
        self,
        name: str,
        title_patterns: list[str] | None = None,
        content_patterns: list[str] | None = None,
        tags: list[str] | None = None,
        confidence: float = DEFAULT_TAGGING_CONFIDENCE,
    ) -> None:
        """
        Add a custom pattern for auto-tagging.

        Args:
            name: Pattern name
            title_patterns: Regex patterns for title matching
            content_patterns: Regex patterns for content matching
            tags: Tags to apply when pattern matches
            confidence: Base confidence score for this pattern
        """
        self.patterns[name] = {
            "title_patterns": title_patterns or [],
            "content_patterns": content_patterns or [],
            "tags": tags or [],
            "confidence": confidence,
        }

    def remove_pattern(self, name: str) -> None:
        """Remove a custom pattern."""
        if name in self.patterns:
            del self.patterns[name]
