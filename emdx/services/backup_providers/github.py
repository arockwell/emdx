"""GitHub Gist backup provider using the `gh` CLI."""

from __future__ import annotations

import gzip
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..backup_types import BackupMetadata, ProviderAuthStatus

logger = logging.getLogger(__name__)

# Prefix used to identify emdx backups among all gists
_GIST_PREFIX = "emdx-backup-"


class GitHubGistProvider:
    """Cloud backup provider that stores database snapshots as secret GitHub Gists.

    Uses the `gh` CLI (https://cli.github.com/) for all operations.
    Backups are stored as secret (unlisted) gists with gzip compression.
    """

    @property
    def name(self) -> str:
        return "github"

    def _run_gh(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a gh CLI command and return the result.

        Raises:
            RuntimeError: If gh is not installed or the command fails.
        """
        try:
            result = subprocess.run(
                ["gh", *args],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI (gh) is not installed. Install it from https://cli.github.com/"
            ) from None

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"gh command failed: {stderr}")

        return result

    def check_auth(self) -> ProviderAuthStatus:
        """Check if the gh CLI is authenticated."""
        try:
            self._run_gh(["auth", "status"])
            return ProviderAuthStatus(
                provider=self.name,
                authenticated=True,
                message="GitHub CLI is authenticated",
            )
        except RuntimeError as e:
            return ProviderAuthStatus(
                provider=self.name,
                authenticated=False,
                message=str(e),
            )

    def upload(self, db_path: str, description: str = "") -> BackupMetadata:
        """Upload a database backup as a secret GitHub Gist.

        The database is gzip-compressed before upload. The gist filename
        includes a timestamp for identification.
        """
        source = Path(db_path)
        if not source.exists():
            raise RuntimeError(f"Database file not found: {db_path}")

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        gz_filename = f"{_GIST_PREFIX}{timestamp}.db.gz"
        desc = description or f"emdx backup {timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            gz_path = Path(tmpdir) / gz_filename
            with (
                open(source, "rb") as f_in,
                gzip.open(gz_path, "wb") as f_out,
            ):
                shutil.copyfileobj(f_in, f_out)

            size_bytes = gz_path.stat().st_size

            # Create a secret gist
            result = self._run_gh(
                [
                    "gist",
                    "create",
                    "--secret",
                    "--desc",
                    desc,
                    str(gz_path),
                ]
            )

        # Parse gist URL from output to extract ID
        gist_url = result.stdout.strip()
        gist_id = gist_url.rstrip("/").rsplit("/", 1)[-1] if gist_url else ""

        if not gist_id:
            raise RuntimeError(f"Failed to parse gist ID from output: {result.stdout}")

        logger.info("Uploaded backup to gist %s (%d bytes)", gist_id, size_bytes)

        return BackupMetadata(
            backup_id=gist_id,
            provider=self.name,
            filename=gz_filename,
            size_bytes=size_bytes,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            description=desc,
        )

    def download(self, backup_id: str, target_dir: str) -> str:
        """Download a backup gist to the target directory."""
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Clone the gist files into a temp directory
            self._run_gh(
                [
                    "gist",
                    "clone",
                    backup_id,
                    tmpdir,
                ]
            )

            # Find the .db.gz file in the cloned gist
            cloned = Path(tmpdir)
            gz_files = list(cloned.glob("*.db.gz"))
            if not gz_files:
                raise RuntimeError(f"No .db.gz file found in gist {backup_id}")

            src_gz = gz_files[0]
            dest_gz = target / src_gz.name
            shutil.copy2(src_gz, dest_gz)

        logger.info("Downloaded backup %s to %s", backup_id, dest_gz)
        return str(dest_gz)

    def list_backups(self) -> list[BackupMetadata]:
        """List all emdx backup gists, newest first."""
        try:
            result = self._run_gh(
                [
                    "gist",
                    "list",
                    "--limit",
                    "100",
                ]
            )
        except RuntimeError:
            return []

        backups: list[BackupMetadata] = []

        for line in result.stdout.strip().splitlines():
            if not line:
                continue

            # gh gist list output: ID\tDESCRIPTION\tFILES\tVISIBILITY\tUPDATED
            parts = line.split("\t")
            if len(parts) < 4:
                continue

            gist_id = parts[0].strip()
            desc = parts[1].strip()

            # Filter to only emdx backups
            if not desc.startswith("emdx backup"):
                continue

            # Get the updated timestamp (last field)
            updated = parts[-1].strip() if len(parts) >= 5 else ""

            backups.append(
                BackupMetadata(
                    backup_id=gist_id,
                    provider=self.name,
                    filename=f"{_GIST_PREFIX}{gist_id}.db.gz",
                    size_bytes=0,  # gh gist list doesn't provide size
                    created_at=updated,
                    description=desc,
                )
            )

        return backups

    def delete(self, backup_id: str) -> bool:
        """Delete a backup gist."""
        try:
            self._run_gh(["gist", "delete", backup_id, "--yes"])
            logger.info("Deleted gist %s", backup_id)
            return True
        except RuntimeError as e:
            logger.warning("Failed to delete gist %s: %s", backup_id, e)
            return False
