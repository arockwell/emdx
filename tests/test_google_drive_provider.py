"""Tests for the Google Drive backup provider.

Regression tests for path traversal in ``GoogleDriveProvider.download``:
the destination filename comes from remote-controlled Drive metadata,
which may contain '/' or '..', so it must be reduced to a safe basename
and confined to the target directory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.backup_providers.google_drive import (
    GoogleDriveProvider,
    _sanitize_remote_filename,
)


class TestSanitizeRemoteFilename:
    def test_plain_name_unchanged(self) -> None:
        assert _sanitize_remote_filename("backup.db.gz", "id1") == "backup.db.gz"

    def test_traversal_reduced_to_basename(self) -> None:
        assert _sanitize_remote_filename("../../.zshrc", "id1") == ".zshrc"

    def test_absolute_path_reduced_to_basename(self) -> None:
        assert _sanitize_remote_filename("/Users/x/.ssh/config", "id1") == "config"

    def test_windows_separators_stripped(self) -> None:
        assert _sanitize_remote_filename("..\\..\\evil.db", "id1") == "evil.db"

    @pytest.mark.parametrize("name", ["", ".", "..", "foo/..", "/", "//"])
    def test_empty_and_dot_names_fall_back(self, name: str) -> None:
        assert _sanitize_remote_filename(name, "abc123") == "backup-abc123.db.gz"


class TestDownloadPathTraversal:
    def _make_provider(self, remote_name: str) -> GoogleDriveProvider:
        provider = GoogleDriveProvider()
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = {"name": remote_name}
        provider._get_service = MagicMock(return_value=service)  # type: ignore[method-assign]
        return provider

    def _run_download(self, provider: GoogleDriveProvider, target_dir: Path) -> str:
        downloader = MagicMock()
        downloader.next_chunk.return_value = (None, True)
        with patch(
            "googleapiclient.http.MediaIoBaseDownload",
            return_value=downloader,
        ):
            return provider.download("file123", str(target_dir))

    def test_traversal_name_confined_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "restore"
        provider = self._make_provider("../../evil.db")

        result = self._run_download(provider, target)

        dest = Path(result)
        assert dest.parent == target
        assert dest.name == "evil.db"
        # Nothing escaped the target directory
        assert not (tmp_path / "evil.db").exists()
        assert dest.exists()

    def test_absolute_name_confined_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "restore"
        provider = self._make_provider("/etc/passwd")

        result = self._run_download(provider, target)

        dest = Path(result)
        assert dest.parent == target
        assert dest.name == "passwd"

    def test_dot_dot_name_uses_fallback(self, tmp_path: Path) -> None:
        target = tmp_path / "restore"
        provider = self._make_provider("..")

        result = self._run_download(provider, target)

        dest = Path(result)
        assert dest.parent == target
        assert dest.name == "backup-file123.db.gz"

    def test_benign_name_preserved(self, tmp_path: Path) -> None:
        target = tmp_path / "restore"
        provider = self._make_provider("emdx-backup-2026-07-06.db.gz")

        result = self._run_download(provider, target)

        dest = Path(result)
        assert dest.parent == target
        assert dest.name == "emdx-backup-2026-07-06.db.gz"
        assert dest.exists()
