"""Google Drive backup provider.

Uses OAuth2 for authentication (browser-based consent flow).
Stores credentials in ~/.config/emdx/google_credentials.json.
Backs up to a dedicated 'emdx-backups' folder in the user's Drive.

Setup:
    1. Create a Google Cloud project at https://console.cloud.google.com
    2. Enable the Google Drive API
    3. Create OAuth 2.0 credentials (Desktop application)
    4. Download the client secrets JSON
    5. Run: emdx maintain backup auth --provider google_drive
       and provide the path to the client secrets file
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from emdx.config.constants import EMDX_CONFIG_DIR

from ..backup_types import BackupMetadata, BackupRecord

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = EMDX_CONFIG_DIR / "google_credentials.json"
CLIENT_SECRETS_FILE = EMDX_CONFIG_DIR / "google_client_secrets.json"
FOLDER_NAME = "emdx-backups"


class GoogleDriveProvider:
    """Google Drive backup provider using OAuth2."""

    @property
    def name(self) -> str:
        return "google_drive"

    def authenticate(self) -> bool:
        """Authenticate with Google Drive via OAuth2.

        On first run, opens a browser for consent. Subsequent runs use
        stored credentials (refreshing the token as needed).
        """
        try:
            self._get_service()
            return True
        except Exception as e:
            logger.error("Google Drive authentication failed: %s", e)
            return False

    def upload(self, file_path: str, metadata: BackupMetadata) -> BackupRecord:
        """Upload a backup file to Google Drive."""
        from googleapiclient.http import MediaFileUpload

        service = self._get_service()
        folder_id = self._ensure_folder(service)

        timestamp = metadata["timestamp"].replace(":", "-").replace("+", "_")
        filename = f"emdx-backup-{timestamp}.db"

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "description": json.dumps({
                "emdx_version": metadata["emdx_version"],
                "document_count": metadata["document_count"],
                "sha256": metadata["sha256"],
                "file_size_bytes": metadata["file_size_bytes"],
            }),
            "properties": {
                "emdx_backup": "true",
                "sha256": metadata["sha256"],
                "emdx_version": metadata["emdx_version"],
                "document_count": str(metadata["document_count"]),
            },
        }

        media = MediaFileUpload(file_path, mimetype="application/x-sqlite3")
        result = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id,name,size")
            .execute()
        )

        file_id: str = result["id"]
        logger.info("Uploaded backup to Google Drive: %s (%s)", filename, file_id)

        return BackupRecord(
            id=file_id,
            provider=self.name,
            timestamp=metadata["timestamp"],
            file_size_bytes=metadata["file_size_bytes"],
            sha256=metadata["sha256"],
            description=f"{filename} ({metadata['document_count']} docs)",
        )

    def list_backups(self) -> list[BackupRecord]:
        """List backups in the emdx-backups folder, newest first."""
        service = self._get_service()
        folder_id = self._find_folder(service)
        if folder_id is None:
            return []

        results = (
            service.files()
            .list(
                q=(
                    f"'{folder_id}' in parents"
                    " and trashed = false"
                    " and properties has { key='emdx_backup' and value='true' }"
                ),
                orderBy="createdTime desc",
                fields="files(id,name,size,createdTime,description,properties)",
                pageSize=50,
            )
            .execute()
        )

        records: list[BackupRecord] = []
        for f in results.get("files", []):
            props = f.get("properties", {})
            records.append(
                BackupRecord(
                    id=f["id"],
                    provider=self.name,
                    timestamp=f.get("createdTime", ""),
                    file_size_bytes=int(f.get("size", 0)),
                    sha256=props.get("sha256", ""),
                    description=f.get("name", ""),
                )
            )

        return records

    def download(self, backup_id: str, dest_path: str) -> str:
        """Download a backup file from Google Drive."""
        from googleapiclient.http import MediaIoBaseDownload

        service = self._get_service()

        with open(dest_path, "wb") as f:
            request = service.files().get_media(fileId=backup_id)
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()

        logger.info("Downloaded backup %s to %s", backup_id, dest_path)
        return dest_path

    def setup_auth(self, client_secrets_path: str) -> bool:
        """Set up OAuth2 credentials from a client secrets file.

        Copies the client secrets to the emdx config dir and runs
        the OAuth2 consent flow.

        Returns True if authentication succeeded.
        """
        import shutil

        src = Path(client_secrets_path)
        if not src.exists():
            raise FileNotFoundError(f"Client secrets file not found: {src}")

        EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(CLIENT_SECRETS_FILE))
        logger.info("Copied client secrets to %s", CLIENT_SECRETS_FILE)

        # Force a fresh auth flow
        CREDENTIALS_FILE.unlink(missing_ok=True)
        return self.authenticate()

    # ── Internal helpers ──────────────────────────────────────────────

    def _get_service(self):  # type: ignore[no-untyped-def]
        """Build an authenticated Drive API service."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None

        if CREDENTIALS_FILE.exists():
            creds = Credentials.from_authorized_user_file(
                str(CREDENTIALS_FILE), SCOPES
            )

        if creds is None or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CLIENT_SECRETS_FILE.exists():
                    raise FileNotFoundError(
                        "Google OAuth not configured. Run:\n"
                        "  emdx maintain backup auth --provider google_drive\n"
                        "with your client_secrets.json file."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CLIENT_SECRETS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)

            EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CREDENTIALS_FILE.write_text(creds.to_json())

        return build("drive", "v3", credentials=creds)

    def _ensure_folder(self, service) -> str:  # type: ignore[no-untyped-def]
        """Find or create the emdx-backups folder. Returns folder ID."""
        folder_id = self._find_folder(service)
        if folder_id:
            return folder_id

        folder_metadata = {
            "name": FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "properties": {"emdx_backup_folder": "true"},
        }
        folder = (
            service.files()
            .create(body=folder_metadata, fields="id")
            .execute()
        )
        folder_id = folder["id"]
        logger.info("Created Google Drive folder: %s (%s)", FOLDER_NAME, folder_id)
        return folder_id  # type: ignore[no-any-return]

    def _find_folder(self, service) -> str | None:  # type: ignore[no-untyped-def]
        """Find the emdx-backups folder by name. Returns folder ID or None."""
        results = (
            service.files()
            .list(
                q=(
                    f"name = '{FOLDER_NAME}'"
                    " and mimeType = 'application/vnd.google-apps.folder'"
                    " and trashed = false"
                ),
                fields="files(id)",
                pageSize=1,
            )
            .execute()
        )
        files = results.get("files", [])
        if files:
            return files[0]["id"]  # type: ignore[no-any-return]
        return None
