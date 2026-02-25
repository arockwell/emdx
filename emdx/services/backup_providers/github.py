"""GitHub backup provider using private gists.

Uses the `gh` CLI for authentication (same pattern as emdx gist.py).
Stores the emdx backup as a private gist with a metadata JSON sidecar.

Limitations:
    - GitHub gists have a soft 100MB file size limit
    - Rate-limited by GitHub API quotas

No extra dependencies — just the `gh` CLI that emdx already uses.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from ..backup_types import BackupMetadata, BackupRecord

logger = logging.getLogger(__name__)

GIST_DESCRIPTION_PREFIX = "emdx-backup"
BACKUP_FILENAME = "emdx-backup.db"
METADATA_FILENAME = "emdx-backup-metadata.json"


def _run_gh(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command. Raises on failure."""
    cmd = ["gh"] + args
    return subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=timeout
    )


def _gh_available() -> bool:
    """Check if gh CLI is installed and authenticated."""
    try:
        result = _run_gh(["auth", "status"], timeout=10)
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


class GitHubProvider:
    """GitHub backup provider using private gists."""

    @property
    def name(self) -> str:
        return "github"

    def authenticate(self) -> bool:
        """Check that gh CLI is installed and authenticated."""
        if not _gh_available():
            logger.error(
                "GitHub CLI (gh) is not installed or not authenticated. "
                "Install from https://cli.github.com and run: gh auth login"
            )
            return False
        return True

    def upload(self, file_path: str, metadata: BackupMetadata) -> BackupRecord:
        """Upload a backup as a private gist."""
        # Write metadata sidecar
        tmp_meta = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="emdx-meta-", delete=False
        )
        json.dump(
            {
                "emdx_version": metadata["emdx_version"],
                "document_count": metadata["document_count"],
                "sha256": metadata["sha256"],
                "file_size_bytes": metadata["file_size_bytes"],
                "timestamp": metadata["timestamp"],
            },
            tmp_meta,
            indent=2,
        )
        tmp_meta.close()
        meta_path = Path(tmp_meta.name)

        # Rename backup file so gist has a clean filename
        tmp_dir = Path(tempfile.mkdtemp(prefix="emdx-gist-"))
        backup_dest = tmp_dir / BACKUP_FILENAME
        metadata_dest = tmp_dir / METADATA_FILENAME

        import shutil

        shutil.copy2(file_path, str(backup_dest))
        shutil.move(str(meta_path), str(metadata_dest))

        try:
            timestamp_short = metadata["timestamp"][:19].replace(":", "-")
            description = (
                f"{GIST_DESCRIPTION_PREFIX} {timestamp_short} "
                f"({metadata['document_count']} docs)"
            )

            result = _run_gh(
                [
                    "gist", "create",
                    str(backup_dest),
                    str(metadata_dest),
                    "--desc", description,
                ],
                timeout=120,
            )

            # gh gist create outputs the gist URL
            gist_url = result.stdout.strip()
            gist_id = gist_url.rstrip("/").split("/")[-1] if gist_url else "unknown"

            logger.info("Uploaded backup to GitHub Gist: %s", gist_url)

            return BackupRecord(
                id=gist_id,
                provider=self.name,
                timestamp=metadata["timestamp"],
                file_size_bytes=metadata["file_size_bytes"],
                sha256=metadata["sha256"],
                description=description,
            )
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    def list_backups(self) -> list[BackupRecord]:
        """List emdx backup gists, newest first."""
        try:
            result = _run_gh(
                [
                    "gist", "list",
                    "--limit", "50",
                ],
                timeout=30,
            )
        except subprocess.CalledProcessError as e:
            logger.error("Failed to list gists: %s", e.stderr)
            return []

        records: list[BackupRecord] = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            # gh gist list format: ID\tDESCRIPTION\tFILES\tVISIBILITY\tUPDATED
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            gist_id = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""

            if not description.startswith(GIST_DESCRIPTION_PREFIX):
                continue

            # Try to fetch metadata from the gist
            meta = self._fetch_metadata(gist_id)
            records.append(
                BackupRecord(
                    id=gist_id,
                    provider=self.name,
                    timestamp=meta.get("timestamp", parts[4].strip() if len(parts) > 4 else ""),
                    file_size_bytes=meta.get("file_size_bytes", 0),
                    sha256=meta.get("sha256", ""),
                    description=description,
                )
            )

        return records

    def download(self, backup_id: str, dest_path: str) -> str:
        """Download a backup gist to dest_path."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="emdx-gist-dl-"))
        try:
            _run_gh(
                ["gist", "clone", backup_id, str(tmp_dir)],
                timeout=120,
            )

            # Find the backup file in the cloned gist
            backup_file = tmp_dir / BACKUP_FILENAME
            if not backup_file.exists():
                # Try any .db file
                db_files = list(tmp_dir.glob("*.db"))
                if not db_files:
                    raise FileNotFoundError(
                        f"No .db file found in gist {backup_id}"
                    )
                backup_file = db_files[0]

            import shutil

            shutil.copy2(str(backup_file), dest_path)
            logger.info("Downloaded backup %s to %s", backup_id, dest_path)
            return dest_path
        finally:
            import shutil

            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    # ── Internal helpers ──────────────────────────────────────────────

    def _fetch_metadata(self, gist_id: str) -> dict[str, str | int]:
        """Fetch metadata JSON from a gist. Returns empty dict on failure."""
        try:
            result = _run_gh(
                ["gist", "view", gist_id, "--filename", METADATA_FILENAME, "--raw"],
                timeout=15,
            )
            return json.loads(result.stdout)  # type: ignore[no-any-return]
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return {}
