"""Backup service for EMDX knowledge base.

Handles creating, listing, pruning, and restoring SQLite backups with
optional gzip compression and logarithmic retention.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ..config.constants import (
    BACKUP_DAILY_DAYS,
    BACKUP_MONTHLY_DAYS,
    BACKUP_WEEKLY_DAYS,
    BACKUP_YEARLY_DAYS,
    EMDX_BACKUP_DIR,
    EMDX_CONFIG_DIR,
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
        self.db_path = db_path.expanduser().resolve()
        self.database_identity = str(self.db_path)
        self.is_default_database = self.db_path == (EMDX_CONFIG_DIR / "knowledge.db").resolve()
        root = (backup_dir or EMDX_BACKUP_DIR).expanduser().resolve()
        # Keep historical production backups accessible at their original location.
        namespace = hashlib.sha256(self.database_identity.encode()).hexdigest()
        self.backup_dir = root if self.is_default_database else root / namespace
        self.retention = retention

    def create_backup(self, compress: bool = True) -> BackupResult:
        """Create a backup of the knowledge base.

        Uses sqlite3.Connection.backup() for atomic, WAL-safe copies,
        then optionally gzip-compresses the result.
        """
        start = time.monotonic()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        backup_name = f"emdx-backup-{timestamp}_{uuid4().hex}.db"
        backup_path = self.backup_dir / backup_name

        try:
            # Atomic backup via SQLite backup API
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(backup_path)
            try:
                src.backup(dst)
                # Reserved backup-only table: a live-table collision fails without altering data.
                dst.execute("CREATE TABLE _emdx_backup_source (database_path TEXT)")
                dst.execute("INSERT INTO _emdx_backup_source VALUES (?)", (self.database_identity,))
                dst.commit()
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
        return any(path.name.startswith(prefix) for path in self.list_backups())

    def list_backups(self) -> list[Path]:
        """List all backup files, newest first."""
        if not self.backup_dir.exists():
            return []
        backups = sorted(
            (
                path
                for path in self.backup_dir.glob("emdx-backup-*")
                if path.is_file() and (path.name.endswith(".db") or path.name.endswith(".db.gz"))
            ),
            key=lambda p: p.name,
            reverse=True,
        )
        return backups

    def restore_backup(
        self, backup_path: Path, *, allow_different_db: bool = False
    ) -> BackupResult:
        """Restore the knowledge base from a backup file.

        Handles both compressed (.db.gz) and uncompressed (.db) backups.

        The live database is never written in place: the backup is validated
        (PRAGMA integrity_check) in a temp copy first, the current database is
        preserved as ``<name>.pre-restore``, and the validated copy is swapped
        in atomically with os.replace(). On any failure the live database is
        left untouched.
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

        # Temp files live next to the live DB so os.replace() stays on one filesystem
        temp_source = self.db_path.parent / f".{self.db_path.name}.restore-src"
        temp_restore = self.db_path.parent / f".{self.db_path.name}.restore-tmp"
        try:
            if backup_path.suffix == ".gz":
                with gzip.open(backup_path, "rb") as f_in, open(temp_source, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                source_path = temp_source
            else:
                source_path = backup_path

            # Materialize the restored DB in a temp file via the SQLite backup API
            src = sqlite3.connect(source_path)
            dst = sqlite3.connect(temp_restore)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()

            # Validate before touching the live DB
            check_conn = sqlite3.connect(temp_restore)
            try:
                has_source = check_conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_emdx_backup_source'"
                ).fetchone()
                if has_source:
                    source = check_conn.execute(
                        "SELECT database_path FROM _emdx_backup_source"
                    ).fetchall()
                    owned = source == [(self.database_identity,)]
                else:
                    # Old backups have no provenance: trust only the legacy default location.
                    owned = (
                        self.is_default_database and backup_path.resolve().parent == self.backup_dir
                    )
                if not owned and not allow_different_db:
                    raise ValueError(
                        "Backup belongs to another database or has unknown ownership. "
                        "Use --allow-different-db to deliberately restore it here."
                    )
                check_conn.execute("DROP TABLE IF EXISTS _emdx_backup_source")
                check_conn.commit()
                integrity = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                check_conn.close()
            if integrity != "ok":
                raise RuntimeError(f"backup failed integrity check: {integrity}")

            # Keep a safety copy of the current DB, then swap in the validated copy
            if self.db_path.exists():
                pre_restore = self.db_path.parent / f"{self.db_path.name}.pre-restore"
                shutil.copy2(self.db_path, pre_restore)
            os.replace(temp_restore, self.db_path)

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
        finally:
            for tmp in (temp_source, temp_restore):
                tmp.unlink(missing_ok=True)

    def _parse_backup_date(self, path: Path) -> datetime | None:
        """Extract date from backup filename like emdx-backup-2026-02-28_143022.db.gz."""
        name = path.name
        # Strip prefix and suffixes
        prefix = "emdx-backup-"
        if not name.startswith(prefix):
            return None
        date_part = name[len(prefix) :].split(".")[0]
        date_part = "_".join(date_part.split("_")[:2])
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
