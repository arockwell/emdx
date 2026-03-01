"""Google Drive backup provider (optional dependency)."""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ..backup_types import BackupMetadata, ProviderAuthStatus

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource as DriveService

logger = logging.getLogger(__name__)

# Name of the folder in Google Drive for emdx backups
_DRIVE_FOLDER_NAME = "emdx-backups"

# Config directory for credentials
_CONFIG_DIR = Path.home() / ".config" / "emdx"
_CREDENTIALS_FILE = _CONFIG_DIR / "gdrive_credentials.json"
_TOKEN_FILE = _CONFIG_DIR / "gdrive_token.json"


def _ensure_config_dir() -> None:
    """Create config directory with secure permissions."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _set_secure_permissions(path: Path) -> None:
    """Set file permissions to 0o600 (owner read/write only)."""
    os.chmod(path, 0o600)


class GoogleDriveProvider:
    """Cloud backup provider that stores database snapshots in Google Drive.

    Requires google-api-python-client and google-auth-oauthlib.
    These are optional dependencies -- the provider raises a clear error
    if they are not installed.
    """

    def __init__(self) -> None:
        self._service: DriveService | None = None
        self._folder_id: str | None = None

    @property
    def name(self) -> str:
        return "gdrive"

    def _get_service(self) -> DriveService:
        """Build and return an authenticated Drive API service.

        Raises:
            RuntimeError: If dependencies are missing or auth fails.
        """
        if self._service is not None:
            return self._service

        try:
            from google.oauth2.credentials import (  # type: ignore[import-untyped]
                Credentials,
            )
            from googleapiclient.discovery import (  # type: ignore[import-untyped]
                build,
            )
        except ImportError:
            raise RuntimeError(
                "Google Drive support requires google-api-python-client and "
                "google-auth-oauthlib. Install them with:\n"
                "  pip install google-api-python-client google-auth-oauthlib"
            ) from None

        if not _TOKEN_FILE.exists():
            raise RuntimeError(
                "Google Drive not authenticated. Run:\n  emdx maintain cloud-backup auth gdrive"
            )

        token_data = json.loads(_TOKEN_FILE.read_text())
        creds = Credentials.from_authorized_user_info(token_data)

        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import (  # type: ignore[import-untyped]
                Request,
            )

            creds.refresh(Request())
            _TOKEN_FILE.write_text(creds.to_json())
            _set_secure_permissions(_TOKEN_FILE)

        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _get_or_create_folder(self) -> str:
        """Get or create the emdx-backups folder in Drive."""
        if self._folder_id is not None:
            return self._folder_id

        service = self._get_service()

        # Search for existing folder
        query = (
            f"name = '{_DRIVE_FOLDER_NAME}' and "
            "mimeType = 'application/vnd.google-apps.folder' and "
            "trashed = false"
        )
        results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            self._folder_id = files[0]["id"]
        else:
            # Create the folder
            folder_metadata = {
                "name": _DRIVE_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = service.files().create(body=folder_metadata, fields="id").execute()
            self._folder_id = folder["id"]

        return self._folder_id  # type: ignore[return-value]

    def check_auth(self) -> ProviderAuthStatus:
        """Check if Google Drive authentication is configured."""
        try:
            self._get_service()
            return ProviderAuthStatus(
                provider=self.name,
                authenticated=True,
                message="Google Drive is authenticated",
            )
        except RuntimeError as e:
            return ProviderAuthStatus(
                provider=self.name,
                authenticated=False,
                message=str(e),
            )

    def upload(self, db_path: str, description: str = "") -> BackupMetadata:
        """Upload a database backup to Google Drive."""
        from googleapiclient.http import (  # type: ignore[import-untyped]
            MediaFileUpload,
        )

        source = Path(db_path)
        if not source.exists():
            raise RuntimeError(f"Database file not found: {db_path}")

        service = self._get_service()
        folder_id = self._get_or_create_folder()

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        gz_filename = f"emdx-backup-{timestamp}.db.gz"
        desc = description or f"emdx backup {timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            gz_path = Path(tmpdir) / gz_filename
            with (
                open(source, "rb") as f_in,
                gzip.open(gz_path, "wb") as f_out,
            ):
                shutil.copyfileobj(f_in, f_out)

            size_bytes = gz_path.stat().st_size

            file_metadata = {
                "name": gz_filename,
                "parents": [folder_id],
                "description": desc,
            }
            media = MediaFileUpload(
                str(gz_path),
                mimetype="application/gzip",
                resumable=True,
            )
            uploaded = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id,name,size",
                )
                .execute()
            )

        file_id: str = uploaded["id"]
        logger.info(
            "Uploaded backup to Google Drive: %s (%d bytes)",
            file_id,
            size_bytes,
        )

        return BackupMetadata(
            backup_id=file_id,
            provider=self.name,
            filename=gz_filename,
            size_bytes=size_bytes,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            description=desc,
        )

    def download(self, backup_id: str, target_dir: str) -> str:
        """Download a backup from Google Drive."""
        from googleapiclient.http import (  # type: ignore[import-untyped]
            MediaIoBaseDownload,
        )

        service = self._get_service()
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        # Get file metadata for the filename
        file_meta = service.files().get(fileId=backup_id, fields="name").execute()
        filename = file_meta.get("name", f"backup-{backup_id}.db.gz")
        dest_path = target / filename

        request = service.files().get_media(fileId=backup_id)

        import io

        fh = io.FileIO(str(dest_path), "wb")
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.close()

        logger.info("Downloaded backup %s to %s", backup_id, dest_path)
        return str(dest_path)

    def list_backups(self) -> list[BackupMetadata]:
        """List all emdx backups in Google Drive, newest first."""
        try:
            service = self._get_service()
            folder_id = self._get_or_create_folder()
        except RuntimeError:
            return []

        query = f"'{folder_id}' in parents and name contains 'emdx-backup-' and trashed = false"
        results = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name, size, createdTime, description)",
                orderBy="createdTime desc",
            )
            .execute()
        )

        backups: list[BackupMetadata] = []
        for f in results.get("files", []):
            backups.append(
                BackupMetadata(
                    backup_id=f["id"],
                    provider=self.name,
                    filename=f.get("name", ""),
                    size_bytes=int(f.get("size", 0)),
                    created_at=f.get("createdTime", ""),
                    description=f.get("description", ""),
                )
            )

        return backups

    def delete(self, backup_id: str) -> bool:
        """Delete a backup from Google Drive."""
        try:
            service = self._get_service()
            service.files().delete(fileId=backup_id).execute()
            logger.info("Deleted Drive file %s", backup_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete Drive file %s: %s", backup_id, e)
            return False


def run_gdrive_auth_flow() -> ProviderAuthStatus:
    """Run the OAuth2 authentication flow for Google Drive.

    This is interactive and requires a browser.

    Returns:
        Authentication status after the flow.
    """
    try:
        from google_auth_oauthlib.flow import (  # type: ignore[import-untyped]
            InstalledAppFlow,
        )
    except ImportError:
        return ProviderAuthStatus(
            provider="gdrive",
            authenticated=False,
            message=(
                "google-auth-oauthlib is required. Install with:\n"
                "  pip install google-auth-oauthlib"
            ),
        )

    if not _CREDENTIALS_FILE.exists():
        return ProviderAuthStatus(
            provider="gdrive",
            authenticated=False,
            message=(
                f"OAuth credentials file not found at {_CREDENTIALS_FILE}\n"
                "Download it from Google Cloud Console > APIs & Services > "
                "Credentials > OAuth 2.0 Client IDs"
            ),
        )

    scopes = ["https://www.googleapis.com/auth/drive.file"]

    flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_FILE), scopes)
    creds = flow.run_local_server(port=0)

    _ensure_config_dir()
    _TOKEN_FILE.write_text(creds.to_json())
    _set_secure_permissions(_TOKEN_FILE)

    return ProviderAuthStatus(
        provider="gdrive",
        authenticated=True,
        message="Google Drive authentication successful",
    )
