"""Protocol-based provider interface for cloud backup."""

from __future__ import annotations

from typing import Protocol

from ..backup_types import BackupMetadata, ProviderAuthStatus


class BackupProvider(Protocol):
    """Protocol for cloud backup providers.

    Implementations must provide methods for uploading, downloading,
    listing, and deleting backups from a remote storage provider.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    def upload(self, db_path: str, description: str = "") -> BackupMetadata:
        """Upload a database backup to the provider.

        Args:
            db_path: Path to the database file to upload.
            description: Optional description for the backup.

        Returns:
            Metadata about the uploaded backup.

        Raises:
            RuntimeError: If the upload fails.
        """
        ...

    def download(self, backup_id: str, target_dir: str) -> str:
        """Download a backup from the provider.

        Args:
            backup_id: Provider-specific identifier for the backup.
            target_dir: Directory to download the backup into.

        Returns:
            Path to the downloaded file.

        Raises:
            RuntimeError: If the download fails.
        """
        ...

    def list_backups(self) -> list[BackupMetadata]:
        """List all backups stored with this provider.

        Returns:
            List of backup metadata, newest first.
        """
        ...

    def delete(self, backup_id: str) -> bool:
        """Delete a backup from the provider.

        Args:
            backup_id: Provider-specific identifier for the backup.

        Returns:
            True if deletion was successful, False otherwise.
        """
        ...

    def check_auth(self) -> ProviderAuthStatus:
        """Check whether the provider is authenticated.

        Returns:
            Authentication status with details.
        """
        ...
