"""Tests for the backup service and providers."""

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.backup_types import BackupMetadata, BackupRecord

# =========================================================================
# Backup Service Tests
# =========================================================================


class TestCreateBackupCopy:
    """Test create_backup_copy() produces a valid SQLite file."""

    def test_creates_valid_sqlite_copy(self, tmp_path):
        # Create a source database with some data
        src_db = tmp_path / "source.db"
        conn = sqlite3.connect(str(src_db))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        from emdx.services.backup_service import create_backup_copy

        copy_path = create_backup_copy(src_db)
        try:
            assert copy_path.exists()
            assert copy_path.stat().st_size > 0

            # Verify it's a valid SQLite file with the data
            conn2 = sqlite3.connect(str(copy_path))
            row = conn2.execute("SELECT val FROM test WHERE id = 1").fetchone()
            assert row[0] == "hello"
            conn2.close()
        finally:
            copy_path.unlink(missing_ok=True)

    def test_raises_on_missing_db(self, tmp_path):
        from emdx.services.backup_service import create_backup_copy

        with pytest.raises(FileNotFoundError):
            create_backup_copy(tmp_path / "nonexistent.db")


class TestBuildMetadata:
    """Test build_metadata() computes correct fields."""

    def test_metadata_fields(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE documents "
            "(id INTEGER PRIMARY KEY, title TEXT, content TEXT, is_deleted BOOLEAN DEFAULT 0)"
        )
        conn.execute("INSERT INTO documents (title, content) VALUES ('Doc 1', 'content')")
        conn.execute("INSERT INTO documents (title, content) VALUES ('Doc 2', 'content')")
        conn.commit()
        conn.close()

        from emdx.services.backup_service import build_metadata

        meta = build_metadata(db_path)

        assert meta["document_count"] == 2
        assert meta["file_size_bytes"] > 0
        assert len(meta["sha256"]) == 64  # hex sha256
        assert "T" in meta["timestamp"]  # ISO 8601


class TestBackupOrchestration:
    """Test the backup() orchestration function."""

    def test_backup_calls_provider(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE documents "
            "(id INTEGER PRIMARY KEY, title TEXT, content TEXT, is_deleted BOOLEAN DEFAULT 0)"
        )
        conn.execute("INSERT INTO documents (title, content) VALUES ('Doc', 'content')")
        conn.commit()
        conn.close()

        mock_provider = MagicMock()
        mock_provider.name = "test"
        mock_provider.authenticate.return_value = True
        mock_provider.upload.return_value = BackupRecord(
            id="test-123",
            provider="test",
            timestamp="2025-01-01T00:00:00",
            file_size_bytes=1024,
            sha256="abc123",
            description="test backup",
        )

        from emdx.services.backup_service import backup

        with patch("emdx.services.backup_service.get_db_path", return_value=db_path):
            record = backup(mock_provider)

        assert record["id"] == "test-123"
        mock_provider.authenticate.assert_called_once()
        mock_provider.upload.assert_called_once()

        # Verify the temp file was cleaned up
        call_args = mock_provider.upload.call_args
        temp_path = Path(call_args[0][0])
        assert not temp_path.exists()

    def test_backup_fails_on_auth_failure(self):
        mock_provider = MagicMock()
        mock_provider.name = "test"
        mock_provider.authenticate.return_value = False

        from emdx.services.backup_service import backup

        with pytest.raises(RuntimeError, match="Authentication failed"):
            backup(mock_provider)


class TestRestoreOrchestration:
    """Test the restore() orchestration function."""

    def test_restore_creates_bak_file(self, tmp_path):
        # Create a "current" database
        current_db = tmp_path / "knowledge.db"
        conn = sqlite3.connect(str(current_db))
        conn.execute("CREATE TABLE test (val TEXT)")
        conn.execute("INSERT INTO test VALUES ('original')")
        conn.commit()
        conn.close()

        # Create a "backup" database
        backup_db = tmp_path / "backup.db"
        conn2 = sqlite3.connect(str(backup_db))
        conn2.execute("CREATE TABLE test (val TEXT)")
        conn2.execute("INSERT INTO test VALUES ('restored')")
        conn2.commit()
        conn2.close()

        # Compute sha256 of the backup
        h = hashlib.sha256()
        with open(backup_db, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        backup_sha = h.hexdigest()

        mock_provider = MagicMock()
        mock_provider.name = "test"
        mock_provider.authenticate.return_value = True
        mock_provider.list_backups.return_value = [
            BackupRecord(
                id="bk-1",
                provider="test",
                timestamp="2025-01-01T00:00:00",
                file_size_bytes=backup_db.stat().st_size,
                sha256=backup_sha,
                description="test",
            )
        ]

        def fake_download(backup_id, dest_path):
            import shutil

            shutil.copy2(str(backup_db), dest_path)
            return dest_path

        mock_provider.download.side_effect = fake_download

        from emdx.services.backup_service import restore

        with patch("emdx.services.backup_service.get_db_path", return_value=current_db):
            restore(mock_provider)

        # .bak should exist with original data
        bak_path = current_db.with_suffix(".db.bak")
        assert bak_path.exists()
        conn3 = sqlite3.connect(str(bak_path))
        row = conn3.execute("SELECT val FROM test").fetchone()
        assert row[0] == "original"
        conn3.close()

        # Current db should now have restored data
        conn4 = sqlite3.connect(str(current_db))
        row = conn4.execute("SELECT val FROM test").fetchone()
        assert row[0] == "restored"
        conn4.close()


# =========================================================================
# GitHub Provider Tests
# =========================================================================


class TestGitHubProvider:
    """Test GitHubProvider with mocked gh CLI."""

    def test_authenticate_success(self):
        from emdx.services.backup_providers.github import GitHubProvider

        provider = GitHubProvider()
        with patch(
            "emdx.services.backup_providers.github._gh_available", return_value=True
        ):
            assert provider.authenticate() is True

    def test_authenticate_failure(self):
        from emdx.services.backup_providers.github import GitHubProvider

        provider = GitHubProvider()
        with patch(
            "emdx.services.backup_providers.github._gh_available", return_value=False
        ):
            assert provider.authenticate() is False

    def test_upload_creates_gist(self, tmp_path):
        from emdx.services.backup_providers.github import GitHubProvider

        provider = GitHubProvider()
        backup_file = tmp_path / "test.db"
        backup_file.write_bytes(b"fake db content")

        metadata = BackupMetadata(
            timestamp="2025-01-01T00:00:00+00:00",
            emdx_version="0.23.0",
            document_count=42,
            file_size_bytes=15,
            sha256="abc123",
        )

        mock_result = MagicMock()
        mock_result.stdout = "https://gist.github.com/user/abc123def456\n"
        mock_result.returncode = 0

        with patch(
            "emdx.services.backup_providers.github._run_gh", return_value=mock_result
        ):
            record = provider.upload(str(backup_file), metadata)

        assert record["provider"] == "github"
        assert record["id"] == "abc123def456"
        assert record["sha256"] == "abc123"

    def test_list_backups_filters_by_prefix(self):
        from emdx.services.backup_providers.github import GitHubProvider

        provider = GitHubProvider()
        mock_result = MagicMock()
        mock_result.stdout = (
            "abc123\temdx-backup 2025-01-01 (42 docs)\t2\tsecret\t2025-01-01\n"
            "def456\tsome other gist\t1\tpublic\t2025-01-02\n"
            "ghi789\temdx-backup 2025-01-02 (50 docs)\t2\tsecret\t2025-01-02\n"
        )

        with (
            patch(
                "emdx.services.backup_providers.github._run_gh", return_value=mock_result
            ),
            patch.object(provider, "_fetch_metadata", return_value={}),
        ):
            records = provider.list_backups()

        # Should only include emdx-backup prefixed gists
        assert len(records) == 2
        assert records[0]["id"] == "abc123"
        assert records[1]["id"] == "ghi789"


# =========================================================================
# Provider Registry Tests
# =========================================================================


class TestProviderRegistry:
    """Test get_provider() dispatch."""

    def test_unknown_provider_raises(self):
        from emdx.services.backup_providers import get_provider

        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("dropbox")

    def test_google_drive_provider_loads(self):
        from emdx.services.backup_providers import get_provider

        provider = get_provider("google_drive")
        assert provider.name == "google_drive"

    def test_github_provider_loads(self):
        from emdx.services.backup_providers import get_provider

        provider = get_provider("github")
        assert provider.name == "github"
