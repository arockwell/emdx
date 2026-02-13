"""Export destination handlers for export profiles.

This module provides destination handlers for different export targets:
- Clipboard: Copy content to system clipboard
- File: Write content to a file
- GDoc: Export to Google Docs (wraps existing gdoc integration)
- Gist: Export to GitHub Gist (wraps existing gist integration)
"""

import logging
import os
import subprocess
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    dest_url: Optional[str]
    message: str


class ExportDestination(Protocol):
    """Protocol for export destination handlers."""

    def export(
        self, content: str, document: dict[str, Any], profile: dict[str, Any]
    ) -> ExportResult:
        """Export content to the destination.

        Args:
            content: Transformed content to export
            document: Source document dictionary
            profile: Export profile dictionary

        Returns:
            ExportResult with success status and details
        """
        ...


class ClipboardDestination:
    """Export to system clipboard."""

    def export(
        self, content: str, document: dict[str, Any], profile: dict[str, Any]
    ) -> ExportResult:
        """Copy content to clipboard."""
        try:
            # Try macOS pbcopy first
            try:
                subprocess.run(
                    ["pbcopy"], input=content.encode("utf-8"), check=True, timeout=5
                )
                return ExportResult(
                    success=True,
                    dest_url=None,
                    message="Content copied to clipboard",
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.debug("pbcopy not available: %s", e)

            # Try Linux xclip
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=content.encode("utf-8"),
                    check=True,
                    timeout=5,
                )
                return ExportResult(
                    success=True,
                    dest_url=None,
                    message="Content copied to clipboard",
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.debug("xclip not available: %s", e)

            # Try Linux xsel
            try:
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=content.encode("utf-8"),
                    check=True,
                    timeout=5,
                )
                return ExportResult(
                    success=True,
                    dest_url=None,
                    message="Content copied to clipboard",
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.debug("xsel not available: %s", e)

            # Try pyperclip as fallback
            try:
                import pyperclip

                pyperclip.copy(content)
                return ExportResult(
                    success=True,
                    dest_url=None,
                    message="Content copied to clipboard",
                )
            except ImportError as e:
                logger.debug("pyperclip not available: %s", e)

            return ExportResult(
                success=False,
                dest_url=None,
                message="No clipboard tool available (tried pbcopy, xclip, xsel, pyperclip)",
            )

        except Exception as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Failed to copy to clipboard: {e}",
            )


class FileDestination:
    """Export to a file."""

    def export(
        self, content: str, document: dict[str, Any], profile: dict[str, Any]
    ) -> ExportResult:
        """Write content to a file."""
        dest_path = profile.get("dest_path")
        if not dest_path:
            return ExportResult(
                success=False,
                dest_url=None,
                message="No destination path specified in profile",
            )

        try:
            # Expand template variables in path
            path = self._expand_path(dest_path, document)

            # Expand user home directory
            path = os.path.expanduser(path)

            # Create parent directories if needed
            parent = Path(path).parent
            parent.mkdir(parents=True, exist_ok=True)

            # Write content
            Path(path).write_text(content, encoding="utf-8")

            return ExportResult(
                success=True,
                dest_url=f"file://{os.path.abspath(path)}",
                message=f"Content written to {path}",
            )

        except Exception as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Failed to write file: {e}",
            )

    def _expand_path(self, path: str, document: dict[str, Any]) -> str:
        """Expand template variables in file path."""
        # Sanitize title for filename
        title = document.get("title", "untitled")
        safe_title = self._sanitize_filename(title)

        replacements = {
            "{{title}}": safe_title,
            "{{date}}": datetime.now().strftime("%Y-%m-%d"),
            "{{datetime}}": datetime.now().strftime("%Y-%m-%d_%H-%M"),
            "{{project}}": document.get("project") or "unknown",
            "{{id}}": str(document.get("id", "0")),
        }

        result = path
        for key, value in replacements.items():
            result = result.replace(key, value)

        return result

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a string for use as a filename."""
        # Remove/replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "-")
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        return filename


class GDocDestination:
    """Export to Google Docs."""

    def export(
        self, content: str, document: dict[str, Any], profile: dict[str, Any]
    ) -> ExportResult:
        """Export content to Google Docs.

        This wraps the existing gdoc integration from emdx/commands/gdoc.py.
        """
        try:
            # Import gdoc functionality lazily
            from emdx.commands.gdoc import (
                get_google_credentials,
                MarkdownToDocsConverter,
            )
            from googleapiclient.discovery import build

            # Get credentials
            creds = get_google_credentials()
            if not creds:
                return ExportResult(
                    success=False,
                    dest_url=None,
                    message="Google authentication required. Run 'emdx gdoc-auth' first.",
                )

            # Build services
            docs_service = build("docs", "v1", credentials=creds)
            drive_service = build("drive", "v3", credentials=creds)

            # Create the document
            title = document.get("title", "Untitled")
            doc = docs_service.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]

            # Convert markdown to Google Docs format and insert
            converter = MarkdownToDocsConverter(content)
            requests = converter.convert()

            if requests:
                docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests}
                ).execute()

            # Move to folder if specified
            folder_name = profile.get("gdoc_folder")
            if folder_name:
                self._move_to_folder(drive_service, doc_id, folder_name)

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

            return ExportResult(
                success=True,
                dest_url=doc_url,
                message=f"Created Google Doc: {title}",
            )

        except ImportError as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Google API dependencies not installed: {e}",
            )
        except Exception as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Failed to create Google Doc: {e}",
            )

    def _move_to_folder(self, drive_service, file_id: str, folder_name: str) -> None:
        """Move a file to a folder, creating the folder if needed."""
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = (
                drive_service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            folders = results.get("files", [])

            if folders:
                folder_id = folders[0]["id"]
            else:
                # Create folder
                folder_metadata = {
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                folder = (
                    drive_service.files()
                    .create(body=folder_metadata, fields="id")
                    .execute()
                )
                folder_id = folder["id"]

            # Move file to folder
            file = drive_service.files().get(fileId=file_id, fields="parents").execute()
            previous_parents = ",".join(file.get("parents", []))
            drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields="id, parents",
            ).execute()

        except Exception as e:
            # Don't fail the export if folder move fails
            logger.warning("Failed to move file to folder '%s': %s", folder_name, e)


class GistDestination:
    """Export to GitHub Gist."""

    def export(
        self, content: str, document: dict[str, Any], profile: dict[str, Any]
    ) -> ExportResult:
        """Export content to GitHub Gist.

        This wraps the existing gist integration from emdx/commands/gist.py.
        """
        try:
            # Import gist functionality lazily
            from emdx.commands.gist import (
                get_github_auth,
                create_gist_with_gh,
                sanitize_filename,
            )

            # Get authentication
            token = get_github_auth()
            if not token:
                return ExportResult(
                    success=False,
                    dest_url=None,
                    message="GitHub authentication required. Set GITHUB_TOKEN or run 'gh auth login'.",
                )

            # Prepare gist content
            title = document.get("title", "Untitled")
            filename = sanitize_filename(title)
            description = f"{title} - emdx export"
            if document.get("project"):
                description += f" (Project: {document['project']})"

            public = profile.get("gist_public", False)

            result = create_gist_with_gh(content, filename, description, public)

            if result:
                return ExportResult(
                    success=True,
                    dest_url=result["url"],
                    message=f"Created {'public' if public else 'secret'} gist",
                )
            else:
                return ExportResult(
                    success=False,
                    dest_url=None,
                    message="Failed to create gist",
                )

        except ImportError as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Gist dependencies not available: {e}",
            )
        except Exception as e:
            return ExportResult(
                success=False,
                dest_url=None,
                message=f"Failed to create gist: {e}",
            )


def get_destination(dest_type: str) -> ExportDestination:
    """Get the appropriate destination handler.

    Args:
        dest_type: Destination type (clipboard, file, gdoc, gist)

    Returns:
        ExportDestination handler

    Raises:
        ValueError: If destination type is not supported
    """
    destinations = {
        "clipboard": ClipboardDestination(),
        "file": FileDestination(),
        "gdoc": GDocDestination(),
        "gist": GistDestination(),
    }

    if dest_type not in destinations:
        raise ValueError(
            f"Unsupported destination type: {dest_type}. "
            f"Supported types: {', '.join(destinations.keys())}"
        )

    return destinations[dest_type]


def execute_post_actions(
    result: ExportResult, profile: dict[str, Any]
) -> list[str]:
    """Execute post-export actions.

    Args:
        result: Export result
        profile: Export profile

    Returns:
        List of action messages
    """
    import json

    post_actions = profile.get("post_actions")
    if not post_actions:
        return []

    # Parse JSON if string
    if isinstance(post_actions, str):
        try:
            post_actions = json.loads(post_actions)
        except json.JSONDecodeError:
            return []

    messages = []

    for action in post_actions:
        if action == "copy_url" and result.dest_url:
            # Copy URL to clipboard
            dest = ClipboardDestination()
            copy_result = dest.export(result.dest_url, {}, {})
            if copy_result.success:
                messages.append("URL copied to clipboard")
            else:
                messages.append(f"Failed to copy URL: {copy_result.message}")

        elif action == "open_browser" and result.dest_url:
            # Open URL in browser
            try:
                webbrowser.open(result.dest_url)
                messages.append("Opened in browser")
            except Exception as e:
                messages.append(f"Failed to open browser: {e}")

        elif action == "notify":
            # System notification (future enhancement)
            messages.append("Notification sent")

    return messages
