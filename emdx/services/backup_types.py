"""TypedDict definitions for cloud backup operations."""

from __future__ import annotations

from typing import TypedDict


class BackupMetadata(TypedDict):
    """Metadata for a cloud backup entry."""

    backup_id: str
    provider: str
    filename: str
    size_bytes: int
    created_at: str
    description: str


class CloudBackupResult(TypedDict):
    """Result of a cloud backup upload operation."""

    success: bool
    message: str
    metadata: BackupMetadata | None


class CloudDownloadResult(TypedDict):
    """Result of a cloud backup download operation."""

    success: bool
    message: str
    path: str | None


class ProviderAuthStatus(TypedDict):
    """Authentication status for a cloud backup provider."""

    provider: str
    authenticated: bool
    message: str
