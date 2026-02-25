"""TypedDict definitions and protocol for the backup system."""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class BackupMetadata(TypedDict):
    """Metadata attached to each backup."""

    timestamp: str  # ISO 8601
    emdx_version: str
    document_count: int
    file_size_bytes: int
    sha256: str


class BackupRecord(TypedDict):
    """A record of a completed backup, returned by providers."""

    id: str  # provider-specific identifier
    provider: str  # "google_drive", "github"
    timestamp: str  # ISO 8601
    file_size_bytes: int
    sha256: str
    description: str  # human-readable summary


@runtime_checkable
class BackupProvider(Protocol):
    """Protocol that all backup providers must implement."""

    @property
    def name(self) -> str: ...

    def authenticate(self) -> bool:
        """Ensure credentials are valid. Return True if authenticated."""
        ...

    def upload(self, file_path: str, metadata: BackupMetadata) -> BackupRecord:
        """Upload a backup file. Returns a record of the upload."""
        ...

    def list_backups(self) -> list[BackupRecord]:
        """List available backups, newest first."""
        ...

    def download(self, backup_id: str, dest_path: str) -> str:
        """Download a backup to dest_path. Returns the local file path."""
        ...
