"""
Database connection management for emdx
"""

import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config.constants import EMDX_CONFIG_DIR
from . import migrations

logger = logging.getLogger(__name__)

# Keep up to 5 rolling daily backups
_MAX_BACKUPS = 5


def auto_backup(db_path: Path) -> None:
    """Create a daily rolling backup of the database if it has data.

    Backups are stored alongside the DB as knowledge.db.backup-YYYY-MM-DD.
    Only one backup per day; older backups beyond _MAX_BACKUPS are pruned.
    Skips backup for test databases or empty/missing files.
    """
    if os.environ.get("EMDX_TEST_DB"):
        return
    if not db_path.exists() or db_path.stat().st_size == 0:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    backup_path = db_path.parent / f"{db_path.name}.backup-{today}"

    if backup_path.exists():
        return  # Already backed up today

    try:
        shutil.copy2(db_path, backup_path)
        logger.debug("Auto-backup created: %s", backup_path.name)
    except OSError as e:
        logger.warning("Auto-backup failed: %s", e)
        return

    # Prune old rolling backups (keep _MAX_BACKUPS most recent)
    pattern = f"{db_path.name}.backup-????-??-??"
    backups = sorted(db_path.parent.glob(pattern), reverse=True)
    for old_backup in backups[_MAX_BACKUPS:]:
        try:
            old_backup.unlink()
            logger.debug("Pruned old backup: %s", old_backup.name)
        except OSError:
            pass


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable.

    When running tests, set EMDX_TEST_DB to a temp file path to prevent
    tests from polluting the real database.
    """
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"


class DatabaseConnection:
    """SQLite database connection manager for emdx"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = get_db_path()
        else:
            self.db_path = db_path

    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager"""
        conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row  # Enable column access by name

        # Enable foreign key constraints for this connection
        conn.execute("PRAGMA foreign_keys = ON")

        # Register datetime adapter
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
        sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))

        try:
            yield conn
        finally:
            conn.close()

    def ensure_schema(self):
        """Ensure the database schema is up to date.

        All schema creation is handled by the migrations system.
        This method simply runs any pending migrations.
        Creates a daily rolling backup before running migrations.
        """
        auto_backup(self.db_path)
        migrations.run_migrations(self.db_path)


# Global instance for backward compatibility
db_connection = DatabaseConnection()
