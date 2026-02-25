"""Backup orchestration service.

Coordinates backup/restore operations using pluggable providers.
Handles creating clean SQLite copies, computing checksums, and
verifying integrity on restore.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from emdx import __version__
from emdx.config.settings import get_db_path

from .backup_types import BackupMetadata, BackupProvider, BackupRecord

logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _document_count(db_path: Path) -> int:
    """Count non-deleted documents in the database."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE is_deleted = 0"
        )
        count: int = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        logger.warning("Could not count documents in %s", db_path)
        return 0


def create_backup_copy(db_path: Path | None = None) -> Path:
    """Create a clean, self-contained copy of the database for upload.

    Uses SQLite VACUUM INTO to produce a single file with no WAL or
    journal dependencies.

    Returns the path to the temporary backup file.
    """
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    tmp = tempfile.NamedTemporaryFile(
        suffix=".db", prefix="emdx-backup-", delete=False
    )
    tmp.close()
    dest = Path(tmp.name)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"VACUUM INTO '{dest}'")
    finally:
        conn.close()

    logger.info("Created backup copy: %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def build_metadata(backup_path: Path) -> BackupMetadata:
    """Build metadata for a backup file."""
    return BackupMetadata(
        timestamp=datetime.now(timezone.utc).isoformat(),
        emdx_version=__version__,
        document_count=_document_count(backup_path),
        file_size_bytes=backup_path.stat().st_size,
        sha256=_sha256(backup_path),
    )


def backup(provider: BackupProvider) -> BackupRecord:
    """Run a full backup using the given provider.

    1. Create a clean VACUUM copy of the database
    2. Compute metadata (hash, doc count, size)
    3. Upload via provider
    4. Clean up temp file
    """
    if not provider.authenticate():
        raise RuntimeError(f"Authentication failed for provider: {provider.name}")

    backup_path = create_backup_copy()
    try:
        metadata = build_metadata(backup_path)
        record = provider.upload(str(backup_path), metadata)
        logger.info(
            "Backup complete: %s (%d docs, %s)",
            record["id"],
            metadata["document_count"],
            _format_size(metadata["file_size_bytes"]),
        )
        return record
    finally:
        backup_path.unlink(missing_ok=True)


def restore(provider: BackupProvider, backup_id: str | None = None) -> Path:
    """Restore a backup from the given provider.

    1. Download the backup (latest if no ID specified)
    2. Verify SHA-256 integrity
    3. Back up current DB to .bak
    4. Replace current DB with restored copy

    Returns the path to the restored database.
    """
    if not provider.authenticate():
        raise RuntimeError(f"Authentication failed for provider: {provider.name}")

    # Determine which backup to restore
    if backup_id is None:
        backups = provider.list_backups()
        if not backups:
            raise RuntimeError(f"No backups found on {provider.name}")
        target = backups[0]  # newest first
        backup_id = target["id"]
        expected_sha = target["sha256"]
    else:
        # Find the specific backup to get its expected hash
        backups = provider.list_backups()
        matches = [b for b in backups if b["id"] == backup_id]
        if not matches:
            raise RuntimeError(f"Backup {backup_id} not found on {provider.name}")
        expected_sha = matches[0]["sha256"]

    # Download to temp location
    tmp_dir = tempfile.mkdtemp(prefix="emdx-restore-")
    dest = Path(tmp_dir) / "restored.db"
    provider.download(backup_id, str(dest))

    # Verify integrity
    actual_sha = _sha256(dest)
    if actual_sha != expected_sha:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Integrity check failed: expected {expected_sha[:12]}..., "
            f"got {actual_sha[:12]}..."
        )

    # Back up current DB before replacing
    db_path = get_db_path()
    if db_path.exists():
        bak_path = db_path.with_suffix(".db.bak")
        shutil.copy2(str(db_path), str(bak_path))
        logger.info("Current database backed up to %s", bak_path)

    # Replace
    shutil.move(str(dest), str(db_path))
    logger.info("Database restored from backup %s", backup_id)

    # Clean up temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return db_path


def list_backups(provider: BackupProvider) -> list[BackupRecord]:
    """List available backups from the provider."""
    if not provider.authenticate():
        raise RuntimeError(f"Authentication failed for provider: {provider.name}")
    return provider.list_backups()


def _format_size(size_bytes: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes_f = size_bytes / 1024
        size_bytes = int(size_bytes_f)
    return f"{size_bytes:.1f} TB"
