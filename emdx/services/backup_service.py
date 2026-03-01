"""Backup service for EMDX knowledge base.

Handles creating, listing, pruning, and restoring SQLite backups with
optional gzip compression and logarithmic retention.
"""

from __future__ import annotations

import gzip
import logging
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config.constants import (
    BACKUP_DAILY_DAYS,
    BACKUP_MONTHLY_DAYS,
    BACKUP_WEEKLY_DAYS,
    BACKUP_YEARLY_DAYS,
    EMDX_BACKUP_DIR,
)

logger = logging.getLogger(__name__)


@dataclass
class BackupResult:
    """Result of a backup or restore operation."""

    success: bool
    path: Path | None
    size_bytes: int
    duration_seconds: float
    pruned_count: int
    message: str


class BackupService:
    """Manages EMDX knowledge base backups."""

    def __init__(
        self,
        db_path: Path,
        backup_dir: Path | None = None,
        retention: bool = True,
    ) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir or EMDX_BACKUP_DIR
        self.retention = retention

    def create_backup(self, compress: bool = True) -> BackupResult:
        """Create a backup of the knowledge base.

        Uses sqlite3.Connection.backup() for atomic, WAL-safe copies,
        then optionally gzip-compresses the result.
        """
        start = time.monotonic()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        backup_name = f"emdx-backup-{timestamp}.db"
        backup_path = self.backup_dir / backup_name

        try:
            # Atomic backup via SQLite backup API
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(backup_path)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()

            # Compress if requested
            if compress:
                gz_path = backup_path.with_suffix(".db.gz")
                with open(backup_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                backup_path.unlink()
                backup_path = gz_path

            size = backup_path.stat().st_size
            duration = time.monotonic() - start

            # Prune old backups
            pruned = 0
            if self.retention:
                pruned = self._prune_old_backups()

            return BackupResult(
                success=True,
                path=backup_path,
                size_bytes=size,
                duration_seconds=duration,
                pruned_count=pruned,
                message=f"Backup created: {backup_path.name}",
            )
        except Exception as e:
            duration = time.monotonic() - start
            # Clean up partial backup
            if backup_path.exists():
                backup_path.unlink()
            gz_path = backup_path.with_suffix(".db.gz")
            if gz_path.exists():
                gz_path.unlink()
            return BackupResult(
                success=False,
                path=None,
                size_bytes=0,
                duration_seconds=duration,
                pruned_count=0,
                message=f"Backup failed: {e}",
            )

    def has_backup_today(self) -> bool:
        """Check if a backup already exists for today (UTC)."""
        if not self.backup_dir.exists():
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        prefix = f"emdx-backup-{today}"
        return any(self.backup_dir.glob(f"{prefix}*"))

    def list_backups(self) -> list[Path]:
        """List all backup files, newest first."""
        if not self.backup_dir.exists():
            return []
        backups = sorted(
            self.backup_dir.glob("emdx-backup-*"),
            key=lambda p: p.name,
            reverse=True,
        )
        return backups

    def restore_backup(self, backup_path: Path) -> BackupResult:
        """Restore the knowledge base from a backup file.

        Handles both compressed (.db.gz) and uncompressed (.db) backups.
        """
        start = time.monotonic()

        if not backup_path.exists():
            return BackupResult(
                success=False,
                path=None,
                size_bytes=0,
                duration_seconds=0,
                pruned_count=0,
                message=f"Backup file not found: {backup_path}",
            )

        try:
            if backup_path.suffix == ".gz":
                # Decompress to a temp file, then restore
                temp_db = backup_path.with_suffix("")
                with gzip.open(backup_path, "rb") as f_in, open(temp_db, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                source_path = temp_db
            else:
                source_path = backup_path

            # Restore via SQLite backup API
            src = sqlite3.connect(source_path)
            dst = sqlite3.connect(self.db_path)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()

            # Clean up temp decompressed file
            if backup_path.suffix == ".gz" and source_path.exists():
                source_path.unlink()

            duration = time.monotonic() - start
            return BackupResult(
                success=True,
                path=backup_path,
                size_bytes=backup_path.stat().st_size,
                duration_seconds=duration,
                pruned_count=0,
                message=f"Restored from: {backup_path.name}",
            )
        except Exception as e:
            duration = time.monotonic() - start
            return BackupResult(
                success=False,
                path=None,
                size_bytes=0,
                duration_seconds=duration,
                pruned_count=0,
                message=f"Restore failed: {e}",
            )

    def _parse_backup_date(self, path: Path) -> datetime | None:
        """Extract date from backup filename like emdx-backup-2026-02-28_143022.db.gz."""
        name = path.name
        # Strip prefix and suffixes
        prefix = "emdx-backup-"
        if not name.startswith(prefix):
            return None
        date_part = name[len(prefix) :].split(".")[0]  # "2026-02-28_143022"
        try:
            return datetime.strptime(date_part, "%Y-%m-%d_%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _prune_old_backups(self) -> int:
        """Apply logarithmic retention policy.

        Keeps:
        - All backups from the last BACKUP_DAILY_DAYS days
        - 1 per week for weeks 2-4 (oldest in each week)
        - 1 per month for months 2-6 (oldest in each month)
        - 1 per year for last 2 years (oldest in each year)
        - Deletes everything else
        """
        backups = self.list_backups()
        if len(backups) <= 1:
            return 0

        now = datetime.now(tz=timezone.utc)
        keep: set[Path] = set()
        dated_backups: list[tuple[Path, datetime]] = []

        for backup in backups:
            dt = self._parse_backup_date(backup)
            if dt is None:
                keep.add(backup)  # Keep unparseable files
                continue
            dated_backups.append((backup, dt))

        # Tier 1: keep all from last N days
        daily_cutoff = now - timedelta(days=BACKUP_DAILY_DAYS)
        for path, dt in dated_backups:
            if dt >= daily_cutoff:
                keep.add(path)

        # Tier 2: keep 1 per week for weeks 2-4
        weekly_cutoff = now - timedelta(days=BACKUP_WEEKLY_DAYS)
        weekly_buckets: dict[str, list[tuple[Path, datetime]]] = {}
        for path, dt in dated_backups:
            if weekly_cutoff <= dt < daily_cutoff:
                # ISO week key
                week_key = dt.strftime("%Y-W%W")
                weekly_buckets.setdefault(week_key, []).append((path, dt))
        for entries in weekly_buckets.values():
            # Keep oldest in each week (best representative)
            oldest = min(entries, key=lambda x: x[1])
            keep.add(oldest[0])

        # Tier 3: keep 1 per month for months 2-6
        monthly_cutoff = now - timedelta(days=BACKUP_MONTHLY_DAYS)
        monthly_buckets: dict[str, list[tuple[Path, datetime]]] = {}
        for path, dt in dated_backups:
            if monthly_cutoff <= dt < weekly_cutoff:
                month_key = dt.strftime("%Y-%m")
                monthly_buckets.setdefault(month_key, []).append((path, dt))
        for entries in monthly_buckets.values():
            oldest = min(entries, key=lambda x: x[1])
            keep.add(oldest[0])

        # Tier 4: keep 1 per year for last 2 years
        yearly_cutoff = now - timedelta(days=BACKUP_YEARLY_DAYS)
        yearly_buckets: dict[str, list[tuple[Path, datetime]]] = {}
        for path, dt in dated_backups:
            if yearly_cutoff <= dt < monthly_cutoff:
                year_key = dt.strftime("%Y")
                yearly_buckets.setdefault(year_key, []).append((path, dt))
        for entries in yearly_buckets.values():
            oldest = min(entries, key=lambda x: x[1])
            keep.add(oldest[0])

        # Delete everything not in keep set
        pruned = 0
        for path, _ in dated_backups:
            if path not in keep:
                try:
                    path.unlink()
                    pruned += 1
                    logger.info(f"Pruned old backup: {path.name}")
                except OSError as e:
                    logger.warning(f"Failed to prune {path.name}: {e}")

        return pruned
