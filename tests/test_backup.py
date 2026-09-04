"""Tests for the backup service and CLI command."""

from __future__ import annotations

import gzip
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from emdx.services.backup_service import BackupService

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a minimal SQLite database for testing."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO docs VALUES (1, 'hello')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    """Return a clean backup directory."""
    d = tmp_path / "backups"
    d.mkdir()
    return d


@pytest.fixture
def svc(db_path: Path, backup_dir: Path) -> BackupService:
    """BackupService with test paths."""
    service = BackupService(db_path=db_path, backup_dir=backup_dir)
    service.backup_dir.mkdir(parents=True, exist_ok=True)
    return service


# ── BackupService tests ────────────────────────────────────────────


class TestBackupService:
    def test_create_compressed_backup(self, svc: BackupService, backup_dir: Path) -> None:
        result = svc.create_backup(compress=True)
        assert result.success
        assert result.path is not None
        assert result.path.suffix == ".gz"
        assert result.path.exists()
        assert result.size_bytes > 0
        assert result.duration_seconds >= 0

    def test_create_uncompressed_backup(self, svc: BackupService, backup_dir: Path) -> None:
        result = svc.create_backup(compress=False)
        assert result.success
        assert result.path is not None
        assert result.path.suffix == ".db"
        assert result.path.exists()

    def test_has_backup_today_false(self, svc: BackupService) -> None:
        assert svc.has_backup_today() is False

    def test_has_backup_today_true(self, svc: BackupService) -> None:
        svc.create_backup()
        assert svc.has_backup_today() is True

    def test_has_backup_today_empty_dir(self, tmp_path: Path) -> None:
        svc = BackupService(
            db_path=tmp_path / "nonexistent.db",
            backup_dir=tmp_path / "no-such-dir",
        )
        assert svc.has_backup_today() is False

    def test_list_backups_empty(self, svc: BackupService) -> None:
        assert svc.list_backups() == []

    def test_list_backups_sorted(self, svc: BackupService, backup_dir: Path) -> None:
        backup_dir = svc.backup_dir
        # Create backups with different timestamps
        (backup_dir / "emdx-backup-2026-01-01_000000.db.gz").touch()
        (backup_dir / "emdx-backup-2026-01-03_000000.db.gz").touch()
        (backup_dir / "emdx-backup-2026-01-02_000000.db.gz").touch()
        backups = svc.list_backups()
        assert len(backups) == 3
        # Newest first
        assert backups[0].name == "emdx-backup-2026-01-03_000000.db.gz"
        assert backups[2].name == "emdx-backup-2026-01-01_000000.db.gz"

    def test_list_backups_no_dir(self, tmp_path: Path) -> None:
        svc = BackupService(
            db_path=tmp_path / "test.db",
            backup_dir=tmp_path / "no-such-dir",
        )
        assert svc.list_backups() == []

    def test_creates_backup_dir(self, db_path: Path, tmp_path: Path) -> None:
        new_dir = tmp_path / "new" / "nested" / "backups"
        svc = BackupService(db_path=db_path, backup_dir=new_dir)
        result = svc.create_backup()
        assert result.success
        assert new_dir.exists()

    def test_restore_compressed(self, svc: BackupService, tmp_path: Path) -> None:
        # Create backup
        result = svc.create_backup(compress=True)
        assert result.success and result.path is not None

        # Modify the original database
        conn = sqlite3.connect(svc.db_path)
        conn.execute("DELETE FROM docs")
        conn.commit()
        conn.close()

        # Verify deletion
        conn = sqlite3.connect(svc.db_path)
        count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        conn.close()
        assert count == 0

        # Restore
        restore_result = svc.restore_backup(result.path)
        assert restore_result.success

        # Verify restored data
        conn = sqlite3.connect(svc.db_path)
        row = conn.execute("SELECT title FROM docs WHERE id=1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hello"

    def test_restore_uncompressed(self, svc: BackupService, tmp_path: Path) -> None:
        result = svc.create_backup(compress=False)
        assert result.success and result.path is not None

        # Modify DB
        conn = sqlite3.connect(svc.db_path)
        conn.execute("DELETE FROM docs")
        conn.commit()
        conn.close()

        restore_result = svc.restore_backup(result.path)
        assert restore_result.success

        conn = sqlite3.connect(svc.db_path)
        count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        conn.close()
        assert count == 1

    def test_restore_nonexistent(self, svc: BackupService, tmp_path: Path) -> None:
        result = svc.restore_backup(tmp_path / "no-such-file.db.gz")
        assert not result.success
        assert "not found" in result.message

    def test_restore_corrupt_backup_leaves_live_db_untouched(
        self, svc: BackupService, tmp_path: Path
    ) -> None:
        """A corrupt/garbage backup must fail without modifying the live DB."""
        corrupt = tmp_path / "corrupt.db"
        corrupt.write_bytes(b"this is not a sqlite database" * 100)

        result = svc.restore_backup(corrupt, allow_different_db=True)
        assert not result.success

        # Live DB still intact and readable
        conn = sqlite3.connect(svc.db_path)
        row = conn.execute("SELECT title FROM docs WHERE id=1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hello"

    def test_restore_truncated_gz_leaves_live_db_untouched(
        self, svc: BackupService, tmp_path: Path
    ) -> None:
        """A truncated .gz backup must fail without modifying the live DB."""
        result = svc.create_backup(compress=True)
        assert result.success and result.path is not None
        data = result.path.read_bytes()
        result.path.write_bytes(data[: len(data) // 2])

        restore_result = svc.restore_backup(result.path)
        assert not restore_result.success

        conn = sqlite3.connect(svc.db_path)
        row = conn.execute("SELECT title FROM docs WHERE id=1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hello"

    def test_restore_creates_pre_restore_safety_copy(self, svc: BackupService) -> None:
        result = svc.create_backup(compress=True)
        assert result.success and result.path is not None

        # Change the live DB so the safety copy is distinguishable
        conn = sqlite3.connect(svc.db_path)
        conn.execute("UPDATE docs SET title='changed' WHERE id=1")
        conn.commit()
        conn.close()

        restore_result = svc.restore_backup(result.path)
        assert restore_result.success

        pre_restore = svc.db_path.parent / f"{svc.db_path.name}.pre-restore"
        assert pre_restore.exists()
        conn = sqlite3.connect(pre_restore)
        row = conn.execute("SELECT title FROM docs WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "changed"

    def test_restore_failure_cleans_up_temp_files(self, svc: BackupService, tmp_path: Path) -> None:
        """Failed restores must not leak decompressed/temp DB files."""
        corrupt_gz = tmp_path / "emdx-backup-corrupt.db.gz"
        with gzip.open(corrupt_gz, "wb") as f:
            f.write(b"not a sqlite database" * 100)

        result = svc.restore_backup(corrupt_gz, allow_different_db=True)
        assert not result.success

        leftovers = [
            p
            for p in svc.db_path.parent.iterdir()
            if "restore-src" in p.name or "restore-tmp" in p.name
        ]
        assert leftovers == []

    def test_retention_pruning(self, svc: BackupService, backup_dir: Path) -> None:
        """Old backups beyond retention tiers get pruned."""
        backup_dir = svc.backup_dir
        now = datetime.now(tz=timezone.utc)

        # Create backups: 10 daily, should keep all within 7 days
        for i in range(10):
            dt = now - timedelta(days=i)
            ts = dt.strftime("%Y-%m-%d_%H%M%S")
            (backup_dir / f"emdx-backup-{ts}.db.gz").touch()

        # Add some old backups (outside weekly tier)
        for i in range(30, 35):
            dt = now - timedelta(days=i)
            ts = dt.strftime("%Y-%m-%d_%H%M%S")
            (backup_dir / f"emdx-backup-{ts}.db.gz").touch()

        before_count = len(list(backup_dir.glob("emdx-backup-*")))
        assert before_count == 15

        pruned = svc._prune_old_backups()
        after_count = len(list(backup_dir.glob("emdx-backup-*")))

        # Should have pruned some old ones
        assert pruned > 0
        assert after_count < before_count

        # All recent (within 7 days) should be kept
        for i in range(7):
            dt = now - timedelta(days=i)
            date_str = dt.strftime("%Y-%m-%d")
            matches = list(backup_dir.glob(f"emdx-backup-{date_str}*"))
            assert len(matches) == 1, f"Day -{i} backup should be kept"

    def test_no_retention(self, db_path: Path, backup_dir: Path) -> None:
        """With retention=False, no pruning happens."""
        svc = BackupService(db_path=db_path, backup_dir=backup_dir, retention=False)
        backup_dir = svc.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create several old backups (far enough in the past to not collide with today)
        for i in range(5):
            dt = datetime(2025, 1 + i, 15, 12, 0, 0, tzinfo=timezone.utc)
            ts = dt.strftime("%Y-%m-%d_%H%M%S")
            path = backup_dir / f"emdx-backup-{ts}.db.gz"
            with gzip.open(path, "wb") as f:
                f.write(b"test")

        result = svc.create_backup()
        assert result.success
        assert result.pruned_count == 0
        # All 6 backups should remain (5 old + 1 new)
        assert len(list(backup_dir.glob("emdx-backup-*"))) == 6

    def test_parse_backup_date(self, svc: BackupService, tmp_path: Path) -> None:
        path = Path("emdx-backup-2026-02-28_143022.db.gz")
        dt = svc._parse_backup_date(path)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 28
        assert dt.hour == 14

    def test_parse_backup_date_invalid(self, svc: BackupService) -> None:
        assert svc._parse_backup_date(Path("random-file.db")) is None
        assert svc._parse_backup_date(Path("emdx-backup-bad.db")) is None

    def test_backup_failed_invalid_path(self, tmp_path: Path) -> None:
        """Backup fails when db_path points to a directory (not a file)."""
        dir_path = tmp_path / "a_directory"
        dir_path.mkdir()
        svc = BackupService(
            db_path=dir_path,
            backup_dir=tmp_path / "backups",
        )
        result = svc.create_backup()
        assert not result.success
        assert "failed" in result.message.lower()


# ── CLI tests ───────────────────────────────────────────────────────


class TestBackupCLI:
    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture
    def cli_app(self) -> typer.Typer:
        from emdx.commands.maintain import app

        return app

    def test_help_text(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["backup", "--help"])
        assert result.exit_code == 0
        assert "backup" in result.output.lower()

    def test_create_backup(
        self, runner: CliRunner, cli_app: typer.Typer, db_path: Path, tmp_path: Path
    ) -> None:
        backup_dir = tmp_path / "cli_backups"
        with (
            patch("emdx.config.settings.get_db_path", return_value=db_path),
            patch(
                "emdx.services.backup_service.EMDX_BACKUP_DIR",
                backup_dir,
            ),
        ):
            result = runner.invoke(cli_app, ["backup"])
        assert result.exit_code == 0
        assert "Backup created" in result.output

    def test_list_empty(
        self, runner: CliRunner, cli_app: typer.Typer, db_path: Path, tmp_path: Path
    ) -> None:
        backup_dir = tmp_path / "cli_backups"
        with (
            patch("emdx.config.settings.get_db_path", return_value=db_path),
            patch(
                "emdx.services.backup_service.EMDX_BACKUP_DIR",
                backup_dir,
            ),
        ):
            result = runner.invoke(cli_app, ["backup", "--list"])
        assert result.exit_code == 0
        assert "No backups found" in result.output

    def test_quiet_mode(
        self, runner: CliRunner, cli_app: typer.Typer, db_path: Path, tmp_path: Path
    ) -> None:
        backup_dir = tmp_path / "cli_backups"
        with (
            patch("emdx.config.settings.get_db_path", return_value=db_path),
            patch(
                "emdx.services.backup_service.EMDX_BACKUP_DIR",
                backup_dir,
            ),
        ):
            result = runner.invoke(cli_app, ["backup", "--quiet"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_json_output(
        self, runner: CliRunner, cli_app: typer.Typer, db_path: Path, tmp_path: Path
    ) -> None:
        import json

        backup_dir = tmp_path / "cli_backups"
        with (
            patch("emdx.config.settings.get_db_path", return_value=db_path),
            patch(
                "emdx.services.backup_service.EMDX_BACKUP_DIR",
                backup_dir,
            ),
        ):
            result = runner.invoke(cli_app, ["backup", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert "path" in data
        assert "size_bytes" in data


class TestBackupIsolation:
    def test_same_timestamp_daily_listing_and_retention_are_per_database(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        import shutil

        other_db = tmp_path / "other.db"
        shutil.copy2(db_path, other_db)
        a = BackupService(db_path, backup_dir=tmp_path / "backups")
        b = BackupService(other_db, backup_dir=tmp_path / "backups")
        now = datetime.now(tz=timezone.utc)
        with patch("emdx.services.backup_service.datetime") as clock:
            clock.now.return_value = now
            clock.strptime.side_effect = datetime.strptime
            first = a.create_backup()
            assert a.has_backup_today()
            assert not b.has_backup_today()
            second = a.create_backup()
            third = b.create_backup()
        assert first.success and second.success and third.success
        assert first.path != second.path
        assert first.path is not None and third.path is not None
        assert first.path.parent != third.path.parent
        assert len(a.list_backups()) == 2
        assert len(b.list_backups()) == 1
        old_a = a.backup_dir / "emdx-backup-2000-01-01_000000.db"
        old_b = b.backup_dir / "emdx-backup-2000-01-01_000000.db"
        old_a.touch()
        old_b.touch()
        assert a._prune_old_backups() == 1
        assert not old_a.exists()
        assert old_b.exists()

    def test_restore_rejects_foreign_backup_even_after_copy_into_own_directory(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        import shutil

        other_db = tmp_path / "other.db"
        shutil.copy2(db_path, other_db)
        with sqlite3.connect(other_db) as conn:
            conn.execute("UPDATE docs SET title='other'")
        a = BackupService(db_path, backup_dir=tmp_path / "backups")
        b = BackupService(other_db, backup_dir=tmp_path / "backups")
        result = b.create_backup()
        assert result.success and result.path is not None
        a.backup_dir.mkdir(parents=True)
        copied = a.backup_dir / result.path.name
        shutil.copy2(result.path, copied)
        rejected = a.restore_backup(copied)
        assert not rejected.success
        assert "--allow-different-db" in rejected.message
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT title FROM docs").fetchone() == ("hello",)
        assert a.restore_backup(copied, allow_different_db=True).success
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT title FROM docs").fetchone() == ("other",)
            assert not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='_emdx_backup_source'"
            ).fetchone()

    def test_default_database_keeps_legacy_backups(self, db_path: Path, tmp_path: Path) -> None:
        import shutil

        default_db = tmp_path / "knowledge.db"
        shutil.copy2(db_path, default_db)
        root = tmp_path / "backups"
        root.mkdir()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        legacy = root / f"emdx-backup-{today}.db"
        shutil.copy2(default_db, legacy)
        with patch("emdx.services.backup_service.EMDX_CONFIG_DIR", tmp_path):
            default = BackupService(default_db, backup_dir=root)
            other = BackupService(db_path, backup_dir=root)
        assert default.backup_dir == root
        assert default.list_backups() == [legacy]
        assert default.has_backup_today()
        assert not other.has_backup_today()
        assert default.restore_backup(legacy).success
        assert not other.restore_backup(legacy).success

    def test_canonical_paths_share_namespace(self, db_path: Path, tmp_path: Path) -> None:
        alias = tmp_path / "alias.db"
        alias.symlink_to(db_path)
        direct = BackupService(db_path, backup_dir=tmp_path / "backups")
        linked = BackupService(alias, backup_dir=tmp_path / "backups")
        assert direct.backup_dir == linked.backup_dir
        result = direct.create_backup()
        assert result.success and result.path is not None
        assert linked.restore_backup(result.path).success

    def test_cli_daily_checks_effective_database(self, db_path: Path, tmp_path: Path) -> None:
        import json
        import shutil

        from emdx.commands.maintain import app

        other_db = tmp_path / "other.db"
        shutil.copy2(db_path, other_db)
        runner = CliRunner()
        with (
            patch("emdx.services.backup_service.EMDX_BACKUP_DIR", tmp_path / "backups"),
            patch("emdx.config.settings.get_db_path") as get_db,
        ):
            get_db.return_value = db_path
            first = runner.invoke(app, ["backup", "--daily", "--json"])
            repeated = runner.invoke(app, ["backup", "--daily", "--json"])
            get_db.return_value = other_db
            other = runner.invoke(app, ["backup", "--daily", "--json"])
        assert first.exit_code == repeated.exit_code == other.exit_code == 0
        assert json.loads(repeated.output)["skipped"] is True
        assert json.loads(first.output)["path"] != json.loads(other.output)["path"]

    def test_backup_metadata_collision_preserves_live_table(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE _emdx_backup_source (important TEXT)")
            conn.execute("INSERT INTO _emdx_backup_source VALUES ('keep me')")
        service = BackupService(db_path, backup_dir=tmp_path / "backups")
        result = service.create_backup()
        assert not result.success
        assert service.list_backups() == []
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT important FROM _emdx_backup_source").fetchone() == (
                "keep me",
            )

    def test_same_database_restore_removes_backup_metadata(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        service = BackupService(db_path, backup_dir=tmp_path / "backups")
        backup = service.create_backup(compress=False)
        assert backup.success and backup.path is not None
        with sqlite3.connect(backup.path) as conn:
            assert conn.execute("SELECT database_path FROM _emdx_backup_source").fetchone() == (
                str(db_path.resolve()),
            )
        assert service.restore_backup(backup.path).success
        with sqlite3.connect(db_path) as conn:
            assert not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='_emdx_backup_source'"
            ).fetchone()
        # Restore leaves the artifact intact and permits another backup of the live database.
        with sqlite3.connect(backup.path) as conn:
            assert conn.execute("SELECT database_path FROM _emdx_backup_source").fetchone()
        assert service.create_backup().success

    def test_cli_restore_requires_explicit_foreign_database_override(
        self, db_path: Path, tmp_path: Path
    ) -> None:
        import json
        import shutil

        from emdx.commands.maintain import app

        other_db = tmp_path / "other.db"
        shutil.copy2(db_path, other_db)
        with sqlite3.connect(other_db) as conn:
            conn.execute("UPDATE docs SET title='foreign'")
        backup = BackupService(other_db, backup_dir=tmp_path / "backups").create_backup()
        assert backup.success and backup.path is not None
        runner = CliRunner()
        with patch("emdx.config.settings.get_db_path", return_value=db_path):
            rejected = runner.invoke(app, ["backup", "--json", "--restore", str(backup.path)])
            assert rejected.exit_code == 1
            assert json.loads(rejected.output)["success"] is False
            with sqlite3.connect(db_path) as conn:
                assert conn.execute("SELECT title FROM docs").fetchone() == ("hello",)
            accepted = runner.invoke(
                app,
                ["backup", "--json", "--allow-different-db", "--restore", str(backup.path)],
            )
        assert accepted.exit_code == 0
        assert json.loads(accepted.output)["success"] is True
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT title FROM docs").fetchone() == ("foreign",)
