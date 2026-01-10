"""
Maintenance Application Service.

Orchestrates maintenance operations across multiple services,
providing a testable, reusable API for knowledge base maintenance.

This module extracts the complex orchestration logic from commands/maintain.py
into a dedicated application service layer.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..config.settings import get_db_path
from ..models.tags import add_tags_to_document
from ..services.auto_tagger import AutoTagger
from ..services.document_merger import DocumentMerger
from ..services.duplicate_detector import DuplicateDetector
from ..services.health_monitor import HealthMonitor
from ..services.lifecycle_tracker import LifecycleTracker


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
    composing multiple services to perform complex workflows.

    Example:
        app = MaintenanceApplication()

        # Run full maintenance
        report = app.maintain_all(dry_run=True)

        # Run specific operations
        result = app.clean_duplicates(dry_run=False)
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize maintenance application with optional database path.

        Args:
            db_path: Path to database. Uses default if not provided.
        """
        self._db_path = db_path or get_db_path()

        # Lazily initialize services
        self._duplicate_detector: Optional[DuplicateDetector] = None
        self._auto_tagger: Optional[AutoTagger] = None
        self._document_merger: Optional[DocumentMerger] = None
        self._health_monitor: Optional[HealthMonitor] = None
        self._lifecycle_tracker: Optional[LifecycleTracker] = None

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

    @property
    def lifecycle_tracker(self) -> LifecycleTracker:
        """Lazy-loaded lifecycle tracker service."""
        if self._lifecycle_tracker is None:
            self._lifecycle_tracker = LifecycleTracker()
        return self._lifecycle_tracker

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
        report.add_result(self.transition_lifecycle(dry_run=dry_run))
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
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Find duplicates
            duplicates = self.duplicate_detector.find_duplicates()
            duplicate_count = (
                sum(len(group) - 1 for group in duplicates) if duplicates else 0
            )

            # Find empty documents
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
                    message=f"Would remove {total} documents ({duplicate_count} duplicates, {empty_count} empty)",
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
        finally:
            conn.close()

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
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row

        try:
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
        finally:
            conn.close()

    def merge_similar(
        self, dry_run: bool = True, threshold: float = 0.7
    ) -> MaintenanceResult:
        """
        Merge similar documents.

        Args:
            dry_run: If True, only report what would be done.
            threshold: Similarity threshold for merging.

        Returns:
            MaintenanceResult with operation details.
        """
        # Find merge candidates
        candidates = self.document_merger.find_merge_candidates(
            similarity_threshold=threshold
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
                    f"'{candidate.doc1['title']}' ↔ '{candidate.doc2['title']}' ({candidate.similarity:.0%})"
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
        conn = sqlite3.connect(self._db_path)

        try:
            cursor = conn.cursor()

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
                except Exception:
                    continue

            return MaintenanceResult(
                operation="merge",
                success=True,
                items_processed=len(candidates),
                items_affected=merged_count,
                message=f"Merged {merged_count} document pairs",
            )
        finally:
            conn.close()

    def transition_lifecycle(self, dry_run: bool = True) -> MaintenanceResult:
        """
        Auto-transition stale gameplans.

        Args:
            dry_run: If True, only report what would be done.

        Returns:
            MaintenanceResult with operation details.
        """
        # Find transition suggestions
        suggestions = self.lifecycle_tracker.auto_detect_transitions()

        if not suggestions:
            return MaintenanceResult(
                operation="lifecycle",
                success=True,
                items_processed=0,
                items_affected=0,
                message="All gameplans are in appropriate stages",
            )

        if dry_run:
            preview = []
            for s in suggestions[:3]:
                preview.append(
                    f"'{s['title']}': {s['current_stage']} → {s['suggested_stage']}"
                )

            return MaintenanceResult(
                operation="lifecycle",
                success=True,
                items_processed=len(suggestions),
                items_affected=len(suggestions),
                message=f"Would transition {len(suggestions)} gameplans",
                details=preview,
            )

        # Apply transitions
        success_count = 0
        for s in suggestions:
            if self.lifecycle_tracker.transition_document(
                s["doc_id"], s["suggested_stage"], f"Auto-detected: {s['reason']}"
            ):
                success_count += 1

        return MaintenanceResult(
            operation="lifecycle",
            success=True,
            items_processed=len(suggestions),
            items_affected=success_count,
            message=f"Transitioned {success_count} gameplans",
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
                message=f"Would clean {total_items} items ({analysis['orphaned_tags']} orphaned tags, {analysis['old_trash']} old trash)",
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
