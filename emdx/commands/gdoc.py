"""
Google Docs integration for emdx - export documents to Google Docs.
"""

import os
import re
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.table import Table

from emdx.database import db
from emdx.models.documents import get_document

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import Resource

app = typer.Typer()
console = Console()

# OAuth 2.0 configuration
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# Default paths for credentials
CONFIG_DIR = Path.home() / ".config" / "emdx"
CREDENTIALS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "google_token.json"


def get_credentials() -> Optional["Credentials"]:
    """Get or refresh Google OAuth credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not CREDENTIALS_FILE.exists():
                return None

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def get_docs_service() -> Optional["Resource"]:
    """Get authenticated Google Docs API service."""
    from googleapiclient.discovery import build

    creds = get_credentials()
    if not creds:
        return None

    return build("docs", "v1", credentials=creds)


def get_drive_service() -> Optional["Resource"]:
    """Get authenticated Google Drive API service."""
    from googleapiclient.discovery import build

    creds = get_credentials()
    if not creds:
        return None

    return build("drive", "v3", credentials=creds)


class MarkdownToDocsConverter:
    """Convert markdown to Google Docs API requests."""

    def __init__(self, markdown: str):
        self.markdown = markdown
        self.requests: list[dict] = []
        self.current_index = 1  # Google Docs uses 1-based indexing

    def convert(self) -> list[dict]:
        """Convert markdown to a list of Google Docs API requests."""
        lines = self.markdown.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Handle code blocks
            if line.startswith("```"):
                # Find the end of the code block
                lang = line[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                self._add_code_block("\n".join(code_lines))
                i += 1
                continue

            # Handle headings
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                text = line.lstrip("#").strip()
                self._add_heading(text, level)
                i += 1
                continue

            # Handle unordered lists
            if line.strip().startswith("- ") or line.strip().startswith("* "):
                indent = len(line) - len(line.lstrip())
                text = line.strip()[2:]
                self._add_bullet_point(text, indent)
                i += 1
                continue

            # Handle ordered lists
            ordered_match = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)
            if ordered_match:
                indent = len(ordered_match.group(1))
                text = ordered_match.group(3)
                self._add_numbered_point(text, indent)
                i += 1
                continue

            # Handle horizontal rules
            if line.strip() in ("---", "***", "___"):
                self._add_horizontal_rule()
                i += 1
                continue

            # Handle blockquotes
            if line.startswith(">"):
                text = line.lstrip(">").strip()
                self._add_blockquote(text)
                i += 1
                continue

            # Handle regular paragraphs
            if line.strip():
                self._add_paragraph(line)

            i += 1

        return self.requests

    def _add_text(self, text: str) -> int:
        """Insert text and return the end index."""
        if not text:
            return self.current_index

        # Process inline formatting
        formatted_text, format_ranges = self._process_inline_formatting(text)

        # Insert the text
        self.requests.append({
            "insertText": {
                "location": {"index": self.current_index},
                "text": formatted_text + "\n",
            }
        })

        # Apply inline formatting
        for fmt_type, start, end in format_ranges:
            abs_start = self.current_index + start
            abs_end = self.current_index + end

            if fmt_type == "bold":
                self.requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": abs_start, "endIndex": abs_end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })
            elif fmt_type == "italic":
                self.requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": abs_start, "endIndex": abs_end},
                        "textStyle": {"italic": True},
                        "fields": "italic",
                    }
                })
            elif fmt_type == "code":
                self.requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": abs_start, "endIndex": abs_end},
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Courier New"},
                            "backgroundColor": {
                                "color": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
                            },
                        },
                        "fields": "weightedFontFamily,backgroundColor",
                    }
                })

        end_index = self.current_index + len(formatted_text) + 1
        self.current_index = end_index
        return end_index

    def _process_inline_formatting(self, text: str) -> tuple[str, list[tuple[str, int, int]]]:
        """Process inline markdown formatting and return clean text with format ranges."""
        format_ranges: list[tuple[str, int, int]] = []
        result = text

        # Process bold (**text** or __text__)
        bold_pattern = r"\*\*(.+?)\*\*|__(.+?)__"
        offset = 0
        for match in re.finditer(bold_pattern, text):
            content = match.group(1) or match.group(2)
            start = match.start() - offset
            # Remove the markers
            result = result[:start] + content + result[start + len(match.group(0)):]
            format_ranges.append(("bold", start, start + len(content)))
            offset += 4  # 4 characters for ** or __

        # Process italic (*text* or _text_) - be careful not to match ** or __
        # Reset and reprocess with updated text
        text = result
        italic_pattern = r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"
        offset = 0
        for match in re.finditer(italic_pattern, text):
            content = match.group(1) or match.group(2)
            if content:
                start = match.start() - offset
                result = result[:start] + content + result[start + len(match.group(0)):]
                format_ranges.append(("italic", start, start + len(content)))
                offset += 2  # 2 characters for * or _

        # Process inline code (`text`)
        text = result
        code_pattern = r"`([^`]+)`"
        offset = 0
        for match in re.finditer(code_pattern, text):
            content = match.group(1)
            start = match.start() - offset
            result = result[:start] + content + result[start + len(match.group(0)):]
            format_ranges.append(("code", start, start + len(content)))
            offset += 2  # 2 characters for `

        return result, format_ranges

    def _add_heading(self, text: str, level: int) -> None:
        """Add a heading."""
        start_index = self.current_index
        end_index = self._add_text(text)

        # Map markdown heading levels to Google Docs named styles
        style_map = {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
            5: "HEADING_5",
            6: "HEADING_6",
        }
        style = style_map.get(level, "HEADING_6")

        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index},
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType",
            }
        })

    def _add_paragraph(self, text: str) -> None:
        """Add a regular paragraph."""
        self._add_text(text)

    def _add_bullet_point(self, text: str, indent: int = 0) -> None:
        """Add a bullet point."""
        start_index = self.current_index
        end_index = self._add_text(text)

        self.requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": start_index, "endIndex": end_index - 1},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        })

        # Handle nesting level based on indent
        if indent > 0:
            nesting_level = min(indent // 2, 8)
            self.requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start_index, "endIndex": end_index},
                    "paragraphStyle": {"indentStart": {"magnitude": nesting_level * 36, "unit": "PT"}},
                    "fields": "indentStart",
                }
            })

    def _add_numbered_point(self, text: str, indent: int = 0) -> None:
        """Add a numbered list item."""
        start_index = self.current_index
        end_index = self._add_text(text)

        self.requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": start_index, "endIndex": end_index - 1},
                "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
            }
        })

    def _add_code_block(self, code: str) -> None:
        """Add a code block with monospace font and background."""
        if not code.strip():
            return

        start_index = self.current_index

        # Insert the code text
        self.requests.append({
            "insertText": {
                "location": {"index": self.current_index},
                "text": code + "\n",
            }
        })

        end_index = self.current_index + len(code) + 1
        self.current_index = end_index

        # Apply monospace font and background
        self.requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index - 1},
                "textStyle": {
                    "weightedFontFamily": {"fontFamily": "Courier New"},
                    "fontSize": {"magnitude": 10, "unit": "PT"},
                },
                "fields": "weightedFontFamily,fontSize",
            }
        })

        # Add background color to paragraph
        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index},
                "paragraphStyle": {
                    "shading": {
                        "backgroundColor": {
                            "color": {"rgbColor": {"red": 0.96, "green": 0.96, "blue": 0.96}}
                        }
                    }
                },
                "fields": "shading",
            }
        })

    def _add_blockquote(self, text: str) -> None:
        """Add a blockquote with indentation and styling."""
        start_index = self.current_index
        end_index = self._add_text(text)

        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index},
                "paragraphStyle": {
                    "indentStart": {"magnitude": 36, "unit": "PT"},
                    "borderLeft": {
                        "color": {"color": {"rgbColor": {"red": 0.8, "green": 0.8, "blue": 0.8}}},
                        "width": {"magnitude": 3, "unit": "PT"},
                        "padding": {"magnitude": 6, "unit": "PT"},
                    },
                },
                "fields": "indentStart,borderLeft",
            }
        })

        # Make blockquote text italic
        self.requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index - 1},
                "textStyle": {"italic": True},
                "fields": "italic",
            }
        })

    def _add_horizontal_rule(self) -> None:
        """Add a horizontal rule (as a styled paragraph)."""
        start_index = self.current_index

        self.requests.append({
            "insertText": {
                "location": {"index": self.current_index},
                "text": "\n",
            }
        })

        self.current_index += 1

        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start_index, "endIndex": self.current_index},
                "paragraphStyle": {
                    "borderBottom": {
                        "color": {"color": {"rgbColor": {"red": 0.8, "green": 0.8, "blue": 0.8}}},
                        "width": {"magnitude": 1, "unit": "PT"},
                        "padding": {"magnitude": 6, "unit": "PT"},
                    }
                },
                "fields": "borderBottom",
            }
        })


def create_google_doc(title: str, markdown_content: str) -> Optional[dict]:
    """Create a Google Doc from markdown content."""
    docs_service = get_docs_service()
    if not docs_service:
        return None

    try:
        # Create empty document
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")

        # Convert markdown to Google Docs requests
        converter = MarkdownToDocsConverter(markdown_content)
        requests = converter.convert()

        # Apply the formatting
        if requests:
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

        # Get the document URL
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        return {
            "id": doc_id,
            "url": doc_url,
            "title": title,
        }

    except Exception as e:
        console.print(f"[red]Error creating Google Doc: {e}[/red]")
        return None


def move_to_folder(doc_id: str, folder_name: str) -> bool:
    """Move a document to a folder (creates folder if needed)."""
    drive_service = get_drive_service()
    if not drive_service:
        return False

    try:
        # Search for existing folder
        results = (
            drive_service.files()
            .list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces="drive",
                fields="files(id, name)",
            )
            .execute()
        )

        folders = results.get("files", [])

        if folders:
            folder_id = folders[0]["id"]
        else:
            # Create the folder
            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder.get("id")

        # Get current parents
        file = drive_service.files().get(fileId=doc_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents", []))

        # Move to new folder
        drive_service.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()

        return True

    except Exception as e:
        console.print(f"[yellow]Warning: Could not move to folder: {e}[/yellow]")
        return False


def create(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Google Drive folder name"),
    copy_url: bool = typer.Option(False, "--copy", "-c", help="Copy doc URL to clipboard"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="Open doc in browser"),
):
    """Export a document to Google Docs."""
    # Ensure database schema is up to date
    db.ensure_schema()

    # Get the document
    doc = get_document(identifier)
    if not doc:
        console.print(f"[red]Error: Document '{identifier}' not found[/red]")
        raise typer.Exit(1)

    # Check for credentials
    if not CREDENTIALS_FILE.exists():
        console.print("[red]Error: Google OAuth credentials not configured[/red]")
        console.print("\nTo use the gdoc command, you need to set up Google OAuth:")
        console.print("1. Go to https://console.cloud.google.com/apis/credentials")
        console.print("2. Create an OAuth 2.0 Client ID (Desktop application)")
        console.print("3. Download the credentials JSON file")
        console.print(f"4. Save it as: [cyan]{CREDENTIALS_FILE}[/cyan]")
        console.print("\nMake sure to enable the Google Docs API and Google Drive API")
        console.print("in the Google Cloud Console.")
        raise typer.Exit(1)

    console.print(f"[yellow]Creating Google Doc: {doc['title']}...[/yellow]")

    # Create the Google Doc
    result = create_google_doc(doc["title"], doc["content"])

    if not result:
        console.print("[red]Error: Failed to create Google Doc[/red]")
        raise typer.Exit(1)

    # Move to folder if specified
    if folder:
        console.print(f"[yellow]Moving to folder: {folder}...[/yellow]")
        move_to_folder(result["id"], folder)

    console.print(f"[green]✓ Created Google Doc:[/green] {result['url']}")

    # Save to database
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO gdocs (document_id, gdoc_id, gdoc_url)
            VALUES (?, ?, ?)
            ON CONFLICT(document_id, gdoc_id) DO UPDATE SET
                gdoc_url = excluded.gdoc_url,
                updated_at = CURRENT_TIMESTAMP
        """,
            (doc["id"], result["id"], result["url"]),
        )
        conn.commit()

    # Post-creation actions
    if copy_url:
        try:
            import subprocess

            subprocess.run(["pbcopy"], input=result["url"].encode(), check=True)
            console.print("[green]✓ URL copied to clipboard[/green]")
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[yellow]⚠ Could not copy to clipboard[/yellow]")

    if open_browser:
        webbrowser.open(result["url"])
        console.print("[green]✓ Opened in browser[/green]")


@app.command("gdoc-list")
def list_gdocs(
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project"),
):
    """List all Google Docs created from documents."""
    db.ensure_schema()

    with db.get_connection() as conn:
        if project:
            cursor = conn.execute(
                """
                SELECT g.*, d.title, d.project
                FROM gdocs g
                JOIN documents d ON g.document_id = d.id
                WHERE d.project = ?
                ORDER BY g.created_at DESC
            """,
                (project,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT g.*, d.title, d.project
                FROM gdocs g
                JOIN documents d ON g.document_id = d.id
                ORDER BY g.created_at DESC
            """
            )

        rows = cursor.fetchall()

    if not rows:
        console.print("[yellow]No Google Docs found[/yellow]")
        return

    # Create table
    table = Table(title="Exported Google Docs")
    table.add_column("Doc ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Project", style="blue")
    table.add_column("GDoc ID", style="green")
    table.add_column("Created", style="dim")

    for row in rows:
        from datetime import datetime

        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_at_str = str(created_at)[:16]

        # Truncate GDoc ID for display
        gdoc_id = row["gdoc_id"]
        if len(gdoc_id) > 20:
            gdoc_id = gdoc_id[:17] + "..."

        table.add_row(
            str(row["document_id"]),
            row["title"][:40] + "..." if len(row["title"]) > 40 else row["title"],
            row["project"] or "-",
            gdoc_id,
            created_at_str,
        )

    console.print(table)


@app.command("gdoc-auth")
def auth():
    """Authenticate with Google (interactive OAuth flow)."""
    if not CREDENTIALS_FILE.exists():
        console.print("[red]Error: Google OAuth credentials not configured[/red]")
        console.print(f"\nPlease download OAuth credentials and save to:\n[cyan]{CREDENTIALS_FILE}[/cyan]")
        raise typer.Exit(1)

    console.print("[yellow]Starting Google OAuth flow...[/yellow]")
    console.print("A browser window will open for authentication.\n")

    creds = get_credentials()
    if creds:
        console.print("[green]✓ Successfully authenticated with Google[/green]")
    else:
        console.print("[red]Error: Authentication failed[/red]")
        raise typer.Exit(1)


# Register the create function as the default 'gdoc' command
app.command(name="gdoc")(create)
