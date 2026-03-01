"""Tests for cloud backup service and CLI commands."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from emdx.services.backup_providers.github import GitHubGistProvider
from emdx.services.backup_types import BackupMetadata
from emdx.services.cloud_backup_service import CloudBackupService, get_provider

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
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_app() -> typer.Typer:
    from emdx.commands.maintain import app

    return app


@pytest.fixture
def mock_gh_auth() -> MagicMock:
    """Mock a successful gh auth status check."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    result.stdout = ""
    result.stderr = ""
    return result


@pytest.fixture
def sample_metadata() -> BackupMetadata:
    """Sample backup metadata for tests."""
    return BackupMetadata(
        backup_id="abc123",
        provider="github",
        filename="emdx-backup-2026-03-01_120000.db.gz",
        size_bytes=1024,
        created_at="2026-03-01T12:00:00+00:00",
        description="emdx backup 2026-03-01_120000",
    )


# ── Provider factory tests ──────────────────────────────────────────


class TestGetProvider:
    def test_get_github_provider(self) -> None:
        provider = get_provider("github")
        assert provider.name == "github"
        assert isinstance(provider, GitHubGistProvider)

    def test_get_gdrive_provider(self) -> None:
        provider = get_provider("gdrive")
        assert provider.name == "gdrive"

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("s3")  # type: ignore[arg-type]


# ── GitHubGistProvider tests ────────────────────────────────────────


class TestGitHubGistProvider:
    def test_name(self) -> None:
        provider = GitHubGistProvider()
        assert provider.name == "github"

    @patch("subprocess.run")
    def test_check_auth_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        provider = GitHubGistProvider()
        status = provider.check_auth()
        assert status["authenticated"] is True
        assert status["provider"] == "github"

    @patch("subprocess.run")
    def test_check_auth_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not logged in")
        provider = GitHubGistProvider()
        status = provider.check_auth()
        assert status["authenticated"] is False

    @patch("subprocess.run")
    def test_check_auth_gh_not_installed(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("gh not found")
        provider = GitHubGistProvider()
        status = provider.check_auth()
        assert status["authenticated"] is False
        assert "not installed" in status["message"]

    @patch("subprocess.run")
    def test_upload_success(self, mock_run: MagicMock, db_path: Path) -> None:
        # Mock the gh gist create call
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/abc123def456\n",
            stderr="",
        )
        provider = GitHubGistProvider()
        metadata = provider.upload(str(db_path))

        assert metadata["backup_id"] == "abc123def456"
        assert metadata["provider"] == "github"
        assert metadata["size_bytes"] > 0
        assert "emdx-backup-" in metadata["filename"]

        # Verify --secret flag was used
        call_args = mock_run.call_args[0][0]
        assert "--secret" in call_args

    @patch("subprocess.run")
    def test_upload_nonexistent_db(self, mock_run: MagicMock) -> None:
        provider = GitHubGistProvider()
        with pytest.raises(RuntimeError, match="not found"):
            provider.upload("/nonexistent/path.db")

    @patch("subprocess.run")
    def test_upload_gh_failure(self, mock_run: MagicMock, db_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="auth required",
        )
        provider = GitHubGistProvider()
        with pytest.raises(RuntimeError, match="auth required"):
            provider.upload(str(db_path))

    @patch("subprocess.run")
    def test_list_backups_parses_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "abc123\temdx backup 2026-03-01\t1 file\tsecret\t2026-03-01\n"
                "def456\temdx backup 2026-02-28\t1 file\tsecret\t2026-02-28\n"
                "ghi789\tother gist\t2 files\tpublic\t2026-02-27\n"
            ),
            stderr="",
        )
        provider = GitHubGistProvider()
        backups = provider.list_backups()

        # Should only return emdx backups (2 of 3)
        assert len(backups) == 2
        assert backups[0]["backup_id"] == "abc123"
        assert backups[1]["backup_id"] == "def456"

    @patch("subprocess.run")
    def test_list_backups_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        provider = GitHubGistProvider()
        assert provider.list_backups() == []

    @patch("subprocess.run")
    def test_list_backups_gh_error(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        provider = GitHubGistProvider()
        assert provider.list_backups() == []

    @patch("subprocess.run")
    def test_delete_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        provider = GitHubGistProvider()
        assert provider.delete("abc123") is True

    @patch("subprocess.run")
    def test_delete_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        provider = GitHubGistProvider()
        assert provider.delete("abc123") is False

    def test_download_success(self, db_path: Path, tmp_path: Path) -> None:
        """Test download clones gist and copies the .db.gz file."""
        import gzip
        import shutil

        # We need to simulate what gh gist clone does:
        # it creates files in the target directory
        def fake_run(args: list[str], **kwargs: object) -> MagicMock:
            if len(args) >= 5 and args[1] == "gist" and args[2] == "clone":
                # args = ["gh", "gist", "clone", backup_id, tmpdir]
                clone_dir = args[4]
                gz_path = Path(clone_dir) / "emdx-backup-test.db.gz"
                with (
                    open(db_path, "rb") as f_in,
                    gzip.open(gz_path, "wb") as f_out,
                ):
                    shutil.copyfileobj(f_in, f_out)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            provider = GitHubGistProvider()
            target_dir = tmp_path / "downloads"
            result_path = provider.download("abc123", str(target_dir))

        assert Path(result_path).exists()
        assert result_path.endswith(".db.gz")


# ── CloudBackupService tests ────────────────────────────────────────


class TestCloudBackupService:
    @patch("subprocess.run")
    def test_upload_returns_result(self, mock_run: MagicMock, db_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/test123\n",
            stderr="",
        )
        svc = CloudBackupService(provider_name="github")
        result = svc.upload(str(db_path))

        assert result["success"] is True
        assert result["metadata"] is not None
        assert result["metadata"]["backup_id"] == "test123"

    @patch("subprocess.run")
    def test_upload_handles_failure(self, mock_run: MagicMock, db_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth error")
        svc = CloudBackupService(provider_name="github")
        result = svc.upload(str(db_path))

        assert result["success"] is False
        assert "failed" in result["message"].lower()

    @patch("subprocess.run")
    def test_check_auth(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        svc = CloudBackupService(provider_name="github")
        status = svc.check_auth()
        assert status["authenticated"] is True


# ── CLI tests ───────────────────────────────────────────────────────


class TestCloudBackupCLI:
    def test_help_text(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "--help"])
        assert result.exit_code == 0
        assert "cloud" in result.output.lower()

    def test_upload_help(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "upload", "--help"])
        assert result.exit_code == 0
        assert "upload" in result.output.lower()

    def test_list_help(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "list", "--help"])
        assert result.exit_code == 0

    def test_download_help(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "download", "--help"])
        assert result.exit_code == 0

    def test_auth_help(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "auth", "--help"])
        assert result.exit_code == 0

    @patch("subprocess.run")
    def test_upload_command(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
        db_path: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/gist789\n",
            stderr="",
        )
        with patch("emdx.commands.backup.get_db_path", return_value=db_path):
            result = runner.invoke(cli_app, ["cloud-backup", "upload"])

        assert result.exit_code == 0
        assert "Uploaded" in result.output

    @patch("subprocess.run")
    def test_upload_command_json(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
        db_path: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/gist789\n",
            stderr="",
        )
        with patch("emdx.commands.backup.get_db_path", return_value=db_path):
            result = runner.invoke(cli_app, ["cloud-backup", "upload", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    @patch("subprocess.run")
    def test_list_command(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=("abc1\temdx backup 2026-03-01\t1 file\tsecret\t2026-03-01\n"),
            stderr="",
        )
        result = runner.invoke(cli_app, ["cloud-backup", "list"])
        assert result.exit_code == 0
        assert "abc1" in result.output

    @patch("subprocess.run")
    def test_list_command_empty(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.invoke(cli_app, ["cloud-backup", "list"])
        assert result.exit_code == 0
        assert "No cloud backups found" in result.output

    @patch("subprocess.run")
    def test_list_command_json(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=("abc1\temdx backup 2026-03-01\t1 file\tsecret\t2026-03-01\n"),
            stderr="",
        )
        result = runner.invoke(cli_app, ["cloud-backup", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("subprocess.run")
    def test_auth_github_authenticated(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.invoke(cli_app, ["cloud-backup", "auth", "github"])
        assert result.exit_code == 0
        assert "authenticated" in result.output.lower()

    @patch("subprocess.run")
    def test_auth_github_not_authenticated(
        self,
        mock_run: MagicMock,
        runner: CliRunner,
        cli_app: typer.Typer,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not logged in")
        result = runner.invoke(cli_app, ["cloud-backup", "auth", "github"])
        assert result.exit_code == 0
        assert "not authenticated" in result.output.lower()

    def test_auth_unknown_provider(self, runner: CliRunner, cli_app: typer.Typer) -> None:
        result = runner.invoke(cli_app, ["cloud-backup", "auth", "s3"])
        assert result.exit_code == 1

    def test_upload_no_db(self, runner: CliRunner, cli_app: typer.Typer, tmp_path: Path) -> None:
        with patch(
            "emdx.commands.backup.get_db_path",
            return_value=tmp_path / "nonexistent.db",
        ):
            result = runner.invoke(cli_app, ["cloud-backup", "upload"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ── Backup types tests ──────────────────────────────────────────────


class TestBackupTypes:
    def test_backup_metadata_fields(self, sample_metadata: BackupMetadata) -> None:
        assert sample_metadata["backup_id"] == "abc123"
        assert sample_metadata["provider"] == "github"
        assert sample_metadata["size_bytes"] == 1024

    def test_metadata_json_serializable(self, sample_metadata: BackupMetadata) -> None:
        serialized = json.dumps(sample_metadata)
        deserialized = json.loads(serialized)
        assert deserialized["backup_id"] == "abc123"
