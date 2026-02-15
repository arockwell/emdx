"""
Maintenance Application Service.

Orchestrates maintenance operations across multiple services,
providing a testable, reusable API for knowledge base maintenance.

This module extracts the complex orchestration logic from commands/maintain.py
into a dedicated application service layer.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Union

from ..config.settings import get_db_path
from ..database.connection import DatabaseConnection
from ..models.tags import add_tags_to_document
from ..services.auto_tagger import AutoTagger
from ..services.document_merger import DocumentMerger
from ..services.duplicate_detector import DuplicateDetector
from ..services.health_monitor import HealthMonitor
from ..services.similarity import SimilarityService

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceResult:
    """Result of a maintenance operation."""

    operation: str
    success: bool
    items_processed: int = 0
    items_affected: int = 0
    message: str = ""
    details: list[str] = field(default_factory=list)


@dataclass
class MaintenanceReport:
    """Complete report from a maintenance run."""

    dry_run: bool
    results: list[MaintenanceResult] = field(default_factory=list)
    overall_success: bool = True

    def add_result(self, result: MaintenanceResult) -> None:
        """Add a result to the report."""
        self.results.append(result)
        if not result.success:
            self.overall_success = False

    @property
    def total_affected(self) -> int:
        """Total items affected across all operations."""
        return sum(r.items_affected for r in self.results)

    @property
    def summary(self) -> str:
        """Human-readable summary of the maintenance run."""
        if not self.results:
            return "No maintenance operations performed"

        lines = []
        for result in self.results:
            if result.items_affected > 0:
                lines.append(result.message)

        if not lines:
            return "No maintenance needed"

        prefix = "Would perform:" if self.dry_run else "Performed:"
        return f"{prefix} " + "; ".join(lines)


class MaintenanceApplication:
    """
    Application service for orchestrating maintenance operations.

    Provides a high-level API for maintaining the knowledge base,
    composing multiple services to perform complex operations.

    Example:
        app = MaintenanceApplication()

        # Run full maintenance
        report = app.maintain_all(dry_run=True)

        # Run specific operations
        result = app.clean_duplicates(dry_run=False)
    """

    def __init__(self, db_path: Union[str, Path] | None = None):
        """
        Initialize maintenance application with optional database path.

        Args:
            db_path: Path to database. Uses default if not provided.
        """
        self._db_path = Path(db_path) if db_path else get_db_path()
        self._db = DatabaseConnection(self._db_path)

        # Lazily initialize services
        self._duplicate_detector: DuplicateDetector | None = None
        self._auto_tagger: AutoTagger | None = None
        self._document_merger: DocumentMerger | None = None
        self._health_monitor: HealthMonitor | None = None

    @property
    def duplicate_detector(self) -> DuplicateDetector:
        """Lazy-loaded duplicate detector service."""
        if self._duplicate_detector is None:
            self._duplicate_detector = DuplicateDetector()
        return self._duplicate_detector

    @property
    def auto_tagger(self) -> AutoTagger:
        """Lazy-loaded auto tagger service."""
        if self._auto_tagger is None:
            self._auto_tagger = AutoTagger()
        return self._auto_tagger

    @property
    def document_merger(self) -> DocumentMerger:
        """Lazy-loaded document merger service."""
        if self._document_merger is None:
            self._document_merger = DocumentMerger()
        return self._document_merger

    @property
    def health_monitor(self) -> HealthMonitor:
        """Lazy-loaded health monitor service."""
        if self._health_monitor is None:
            self._health_monitor = HealthMonitor()
        return self._health_monitor

    def maintain_all(
        self,
        dry_run: bool = True,
        threshold: float = 0.7,
    ) -> MaintenanceReport:
        """
        Run all maintenance operations.

        Args:
            dry_run: If True, only report what would be done.
            threshold: Similarity threshold for merging.

        Returns:
            MaintenanceReport with results of all operations.
        """
        report = MaintenanceReport(dry_run=dry_run)

        # Run operations in order
        report.add_result(self.clean_duplicates(dry_run=dry_run))
        report.add_result(self.auto_tag_documents(dry_run=dry_run))
        report.add_result(self.merge_similar(dry_run=dry_run, threshold=threshold))
        report.add_result(self.garbage_collect(dry_run=dry_run))

        return report

    def clean_duplicates(self, dry_run: bool = True) -> MaintenanceResult:
        """
        Remove duplicate and empty documents.

        Args:
            dry_run: If True, only report what would be done.

        Returns:
            MaintenanceResult with operation details.
        """
        # Find duplicates
        duplicates = self.duplicate_detector.find_duplicates()
        duplicate_count = (
            sum(len(group) - 1 for group in duplicates) if duplicates else 0
        )

        # Find empty documents
        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT COUNT(*) FROM documents
                WHERE is_deleted = 0 AND LENGTH(content) < 10
            """
            )
            empty_count = cursor.fetchone()[0]

        total = duplicate_count + empty_count

        if total == 0:
            return MaintenanceResult(
                operation="clean",
                success=True,
                items_processed=0,
                items_affected=0,
                message="No duplicates or empty documents found",
            )

        if dry_run:
            return MaintenanceResult(
                operation="clean",
                success=True,
                items_processed=total,
                items_affected=total,
                message=f"Would remove {total} documents ({duplicate_count} duplicates, {empty_count} empty)",  # noqa: E501
            )

        # Remove duplicates
        deleted_dupes = 0
        if duplicate_count > 0:
            docs_to_delete = self.duplicate_detector.get_documents_to_delete(
                duplicates, "highest-views"
            )
            deleted_dupes = self.duplicate_detector.delete_documents(docs_to_delete)

        # Remove empty documents
        deleted_empty = 0
        if empty_count > 0:
            with self._db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE documents
                    SET is_deleted = 1, deleted_at = ?
                    WHERE is_deleted = 0 AND LENGTH(content) < 10
                """,
                    (datetime.now().isoformat(),),
                )
                deleted_empty = cursor.rowcount
                conn.commit()

        return MaintenanceResult(
            operation="clean",
            success=True,
            items_processed=total,
            items_affected=deleted_dupes + deleted_empty,
            message=f"Removed {deleted_dupes + deleted_empty} documents",
            details=[
                f"Deleted {deleted_dupes} duplicates",
                f"Deleted {deleted_empty} empty documents",
            ],
        )

    def auto_tag_documents(
        self, dry_run: bool = True, confidence_threshold: float = 0.6, limit: int = 100
    ) -> MaintenanceResult:
        """
        Auto-tag untagged documents.

        Args:
            dry_run: If True, only report what would be done.
            confidence_threshold: Minimum confidence for tag application.
            limit: Maximum documents to process.

        Returns:
            MaintenanceResult with operation details.
        """
        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            # Find untagged documents
            cursor.execute(
                """
                SELECT d.id, d.title, d.content
                FROM documents d
                WHERE d.is_deleted = 0
                AND NOT EXISTS (
                    SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
                )
                LIMIT ?
            """,
                (limit,),
            )

            untagged = cursor.fetchall()

        if not untagged:
            return MaintenanceResult(
                operation="auto_tag",
                success=True,
                items_processed=0,
                items_affected=0,
                message="All documents are already tagged",
            )

        if dry_run:
            # Preview suggestions
            preview = []
            for doc in untagged[:3]:
                suggestions = self.auto_tagger.analyze_document(
                    doc["title"], doc["content"]
                )
                if suggestions:
                    tags = [
                        tag
                        for tag, conf in suggestions[:3]
                        if conf > confidence_threshold
                    ]
                    if tags:
                        preview.append(f"#{doc['id']}: {', '.join(tags)}")

            return MaintenanceResult(
                operation="auto_tag",
                success=True,
                items_processed=len(untagged),
                items_affected=len(untagged),
                message=f"Would auto-tag {len(untagged)} documents",
                details=preview,
            )

        # Actually tag documents
        tagged_count = 0
        for doc in untagged:
            suggestions = self.auto_tagger.analyze_document(
                doc["title"], doc["content"]
            )
            if suggestions:
                tags = [
                    tag
                    for tag, conf in suggestions
                    if conf > confidence_threshold
                ][:3]
                if tags:
                    add_tags_to_document(doc["id"], tags)
                    tagged_count += 1

        return MaintenanceResult(
            operation="auto_tag",
            success=True,
            items_processed=len(untagged),
            items_affected=tagged_count,
            message=f"Auto-tagged {tagged_count} documents",
        )

    def merge_similar(
        self, dry_run: bool = True, threshold: float = 0.7,
        progress_callback: Callable | None = None,
        use_tfidf: bool = True,
    ) -> MaintenanceResult:
        """
        Merge similar documents.

        Args:
            dry_run: If True, only report what would be done.
            threshold: Similarity threshold for merging.
            progress_callback: Optional callback(current, total, found) for progress updates.
            use_tfidf: If True, use fast TF-IDF similarity (recommended).
                       If False, use slower pairwise comparison.

        Returns:
            MaintenanceResult with operation details.
        """
        if use_tfidf:
            # Use fast TF-IDF based similarity (matrix operations)
            similarity_service = SimilarityService()
            pairs = similarity_service.find_all_duplicate_pairs(
                min_similarity=threshold,
                progress_callback=progress_callback,
            )

            if not pairs:
                return MaintenanceResult(
                    operation="merge",
                    success=True,
                    items_processed=0,
                    items_affected=0,
                    message="No similar documents found",
                )

            if dry_run:
                preview = []
                # Fetch document details to show which would be kept
                with self._db.get_connection() as conn:
                    cursor = conn.cursor()
                    for doc1_id, doc2_id, title1, title2, sim in pairs[:5]:
                        # Get access counts to determine which would be kept
                        cursor.execute(
                            "SELECT id, access_count, LENGTH(content) as len FROM documents WHERE id IN (?, ?)",  # noqa: E501
                            (doc1_id, doc2_id)
                        )
                        docs = {row['id']: row for row in cursor.fetchall()}

                        # Determine which would be kept (higher access count, then longer content)
                        doc1 = docs.get(doc1_id, {'access_count': 0, 'len': 0})
                        doc2 = docs.get(doc2_id, {'access_count': 0, 'len': 0})

                        if doc1['access_count'] > doc2['access_count']:
                            keep_title, merge_title = title1, title2
                        elif doc2['access_count'] > doc1['access_count']:
                            keep_title, merge_title = title2, title1
                        elif (doc1['len'] or 0) >= (doc2['len'] or 0):
                            keep_title, merge_title = title1, title2
                        else:
                            keep_title, merge_title = title2, title1

                        preview.append(f"'{merge_title}' → '{keep_title}' ({sim:.0%})")

                return MaintenanceResult(
                    operation="merge",
                    success=True,
                    items_processed=len(pairs),
                    items_affected=len(pairs),
                    message=f"Would merge {len(pairs)} document pairs",
                    details=preview,
                )

            # Fast path: merge using pairs data directly
            merged_count = 0
            for doc1_id, doc2_id, _title1, _title2, _sim in pairs:
                try:
                    with self._db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """SELECT id, title, content, access_count
                               FROM documents WHERE id IN (?, ?) AND is_deleted = 0""",
                            (doc1_id, doc2_id)
                        )
                        docs = {row['id']: dict(row) for row in cursor.fetchall()}

                    if len(docs) != 2:
                        continue

                    doc1, doc2 = docs.get(doc1_id, {}), docs.get(doc2_id, {})

                    # Keep doc with more views, else longer content
                    if doc1.get('access_count', 0) > doc2.get('access_count', 0):
                        keep, remove = doc1, doc2
                    elif doc2.get('access_count', 0) > doc1.get('access_count', 0):
                        keep, remove = doc2, doc1
                    elif len(doc1.get('content', '') or '') >= len(doc2.get('content', '') or ''):
                        keep, remove = doc1, doc2
                    else:
                        keep, remove = doc2, doc1

                    merged_content = self.document_merger._merge_content(
                        keep.get("content", "") or "",
                        remove.get("content", "") or "",
                        keep.get("title", ""),
                        remove.get("title", "")
                    )

                    with self._db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """UPDATE documents SET content = ?, updated_at = ? WHERE id = ?""",
                            (merged_content, datetime.now().isoformat(), keep["id"]),
                        )
                        cursor.execute(
                            """UPDATE documents SET is_deleted = 1, deleted_at = ? WHERE id = ?""",
                            (datetime.now().isoformat(), remove["id"]),
                        )
                        conn.commit()
                    merged_count += 1
                except Exception as e:
                    logger.warning("Failed to merge documents %s and %s: %s", doc1_id, doc2_id, e)
                    continue

            return MaintenanceResult(
                operation="merge",
                success=True,
                items_processed=len(pairs),
                items_affected=merged_count,
                message=f"Merged {merged_count} document pairs",
            )

        # Fall back to old slow method (only when use_tfidf=False)
        candidates = self.document_merger.find_merge_candidates(
            similarity_threshold=threshold,
            progress_callback=progress_callback
        )

        if not candidates:
            return MaintenanceResult(
                operation="merge",
                success=True,
                items_processed=0,
                items_affected=0,
                message="No similar documents found",
            )

        if dry_run:
            preview = []
            for candidate in candidates[:3]:
                preview.append(
                    f"'{candidate.doc1['title']}' ↔ '{candidate.doc2['title']}' ({candidate.similarity:.0%})"  # noqa: E501
                )

            return MaintenanceResult(
                operation="merge",
                success=True,
                items_processed=len(candidates),
                items_affected=len(candidates),
                message=f"Would merge {len(candidates)} document pairs",
                details=preview,
            )

        # Actually merge documents
        merged_count = 0

        for candidate in candidates:
            try:
                # Keep the document with more views
                if (
                    candidate.doc1["access_count"]
                    >= candidate.doc2["access_count"]
                ):
                    keep, remove = candidate.doc1, candidate.doc2
                else:
                    keep, remove = candidate.doc2, candidate.doc1

                # Merge content
                merged_content = self.document_merger._merge_content(
                    keep["content"], remove["content"]
                )

                with self._db.get_connection() as conn:
                    cursor = conn.cursor()

                    # Update the kept document
                    cursor.execute(
                        """
                        UPDATE documents
                        SET content = ?, updated_at = ?
                        WHERE id = ?
                    """,
                        (merged_content, datetime.now().isoformat(), keep["id"]),
                    )

                    # Delete the other document
                    cursor.execute(
                        """
                        UPDATE documents
                        SET is_deleted = 1, deleted_at = ?
                        WHERE id = ?
                    """,
                        (datetime.now().isoformat(), remove["id"]),
                    )

                    conn.commit()
                merged_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to merge documents %s and %s: %s", keep["id"], remove["id"], e
                )
                continue

        return MaintenanceResult(
            operation="merge",
            success=True,
            items_processed=len(candidates),
            items_affected=merged_count,
            message=f"Merged {merged_count} document pairs",
        )

    def garbage_collect(self, dry_run: bool = True) -> MaintenanceResult:
        """
        Run garbage collection on the database.

        Args:
            dry_run: If True, only report what would be done.

        Returns:
            MaintenanceResult with operation details.
        """
        from ..commands.gc import GarbageCollector

        gc = GarbageCollector(self._db_path)
        analysis = gc.analyze()

        if not analysis["recommendations"]:
            return MaintenanceResult(
                operation="gc",
                success=True,
                items_processed=0,
                items_affected=0,
                message="No garbage collection needed",
            )

        total_items = analysis["orphaned_tags"] + analysis["old_trash"]

        if dry_run:
            return MaintenanceResult(
                operation="gc",
                success=True,
                items_processed=total_items,
                items_affected=total_items,
                message=f"Would clean {total_items} items ({analysis['orphaned_tags']} orphaned tags, {analysis['old_trash']} old trash)",  # noqa: E501
            )

        # Perform cleanup
        cleaned = 0
        details = []

        if analysis["orphaned_tags"] > 0:
            deleted_tags = gc.clean_orphaned_tags()
            cleaned += deleted_tags
            details.append(f"Removed {deleted_tags} orphaned tags")

        if analysis["old_trash"] > 0:
            deleted_trash = gc.clean_old_trash()
            cleaned += deleted_trash
            details.append(f"Deleted {deleted_trash} old trash items")

        if analysis["fragmentation"] > 20:
            vacuum_result = gc.vacuum_database()
            saved_mb = vacuum_result["space_saved"] / 1024 / 1024
            details.append(f"Vacuumed database, saved {saved_mb:.1f} MB")

        return MaintenanceResult(
            operation="gc",
            success=True,
            items_processed=total_items,
            items_affected=cleaned,
            message=f"Cleaned {cleaned} items",
            details=details,
        )

    def get_health_metrics(self) -> dict:
        """
        Get current health metrics for the knowledge base.

        Returns:
            Dictionary with health scores and recommendations.
        """
        return self.health_monitor.calculate_overall_health()
