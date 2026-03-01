"""Cloud backup service for EMDX knowledge base.

Orchestrates cloud backup operations across multiple providers
(GitHub Gist, Google Drive) using a protocol-based provider interface.
"""

from __future__ import annotations

import logging
from typing import Literal

from .backup_providers import BackupProvider
from .backup_providers.github import GitHubGistProvider
from .backup_types import (
    BackupMetadata,
    CloudBackupResult,
    CloudDownloadResult,
    ProviderAuthStatus,
)

logger = logging.getLogger(__name__)

ProviderName = Literal["github", "gdrive"]


def get_provider(name: ProviderName) -> BackupProvider:
    """Get a backup provider instance by name.

    Args:
        name: Provider identifier ('github' or 'gdrive').

    Returns:
        A provider instance implementing the BackupProvider protocol.

    Raises:
        ValueError: If the provider name is not recognized.
        RuntimeError: If the provider's dependencies are not installed.
    """
    if name == "github":
        return GitHubGistProvider()

    if name == "gdrive":
        try:
            from .backup_providers.google_drive import GoogleDriveProvider
        except ImportError:
            raise RuntimeError(
                "Google Drive support requires google-api-python-client. "
                "Install with: pip install google-api-python-client "
                "google-auth-oauthlib"
            ) from None
        return GoogleDriveProvider()

    raise ValueError(f"Unknown provider: {name!r}. Use 'github' or 'gdrive'.")


class CloudBackupService:
    """Orchestrates cloud backup operations."""

    def __init__(self, provider_name: ProviderName = "github") -> None:
        self.provider = get_provider(provider_name)

    def upload(self, db_path: str, description: str = "") -> CloudBackupResult:
        """Upload a database backup to the cloud provider.

        Args:
            db_path: Path to the SQLite database file.
            description: Optional description for the backup.

        Returns:
            Result with success status and metadata.
        """
        try:
            metadata = self.provider.upload(db_path, description)
            return CloudBackupResult(
                success=True,
                message=f"Backup uploaded to {self.provider.name}: {metadata['backup_id']}",
                metadata=metadata,
            )
        except RuntimeError as e:
            return CloudBackupResult(
                success=False,
                message=f"Upload failed: {e}",
                metadata=None,
            )

    def download(self, backup_id: str, target_dir: str) -> CloudDownloadResult:
        """Download a backup from the cloud provider.

        Args:
            backup_id: Provider-specific backup identifier.
            target_dir: Directory to download the backup into.

        Returns:
            Result with success status and local file path.
        """
        try:
            path = self.provider.download(backup_id, target_dir)
            return CloudDownloadResult(
                success=True,
                message=f"Backup downloaded to {path}",
                path=path,
            )
        except RuntimeError as e:
            return CloudDownloadResult(
                success=False,
                message=f"Download failed: {e}",
                path=None,
            )

    def list_backups(self) -> list[BackupMetadata]:
        """List all backups from the cloud provider."""
        return self.provider.list_backups()

    def delete(self, backup_id: str) -> bool:
        """Delete a backup from the cloud provider."""
        return self.provider.delete(backup_id)

    def check_auth(self) -> ProviderAuthStatus:
        """Check authentication status for the current provider."""
        return self.provider.check_auth()
