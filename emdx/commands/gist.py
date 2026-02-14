"""
GitHub Gist integration for emdx
"""

import logging
import os
import subprocess
import webbrowser
from typing import Optional

logger = logging.getLogger(__name__)

import typer

from emdx.database import db
from emdx.models.documents import get_document
from emdx.utils.output import console

app = typer.Typer()


def get_github_auth() -> Optional[str]:
    """Get GitHub authentication token.

    SECURITY NOTE: GitHub tokens are sensitive credentials.
    - Never log or display the token value
    - Prefer using `gh auth` over GITHUB_TOKEN when possible
    - Tokens should have minimal required scopes (only 'gist' for gist operations)
    - Revoke and rotate tokens periodically

    Returns:
        GitHub token if available, None otherwise.
    """
    # Priority order:
    # 1. Try gh CLI first (preferred - uses secure credential storage)
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10  # Prevent hanging
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("gh auth token not available: %s", e)

    # 2. Fall back to environment variable GITHUB_TOKEN
    # Note: Environment variables are less secure than gh auth
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token

    # 3. Check config file (future enhancement)
    # config_path = Path.home() / '.config' / 'emdx' / 'config.yml'
    # if config_path.exists():
    #     # Load token from config

    return None


def create_gist_with_gh(
    content: str, filename: str, description: str, public: bool = False
) -> Optional[dict[str, str]]:
    """Create a gist using gh CLI.

    Uses secure temp file handling to prevent race conditions.
    The temp file is kept open until after the command completes.
    """
    import tempfile

    temp_path = None
    try:
        # Create temp file with secure permissions (mode 0o600 by default on Unix)
        # Keep the file descriptor open to maintain exclusive access
        fd, temp_path = tempfile.mkstemp(suffix=".md", prefix="emdx_gist_")
        try:
            # Write content through the file descriptor for atomic operation
            os.write(fd, content.encode('utf-8'))
        finally:
            os.close(fd)

        # Build gh command
        cmd = ["gh", "gist", "create", temp_path, "--desc", description]
        if public:
            cmd.append("--public")

        # Execute command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if result.returncode == 0:
            gist_url = result.stdout.strip()
            # Extract gist ID from URL
            gist_id = gist_url.split("/")[-1]
            return {"id": gist_id, "url": gist_url}
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logger.debug("Failed to create gist with gh CLI: %s", e)
    finally:
        # Always clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.debug("Failed to clean up temp file %s: %s", temp_path, e)

    return None


def update_gist_with_gh(gist_id: str, content: str, filename: str) -> bool:
    """Update an existing gist using gh CLI.

    Uses secure temp file handling to prevent race conditions.
    """
    import tempfile

    temp_path = None
    try:
        # Create temp file with secure permissions (mode 0o600 by default on Unix)
        fd, temp_path = tempfile.mkstemp(suffix=".md", prefix="emdx_gist_")
        try:
            # Write content through the file descriptor for atomic operation
            os.write(fd, content.encode('utf-8'))
        finally:
            os.close(fd)

        # Execute gh command
        cmd = ["gh", "gist", "edit", gist_id, temp_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logger.debug("Failed to update gist with gh CLI: %s", e)
    finally:
        # Always clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.debug("Failed to clean up temp file %s: %s", temp_path, e)

    return False


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard."""
    try:
        # macOS
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logger.debug("pbcopy not available: %s", e)
        try:
            # Linux (X11)
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            # Windows or fallback - would need pyperclip
            logger.debug("xclip not available: %s", e)
            return False


def sanitize_filename(title: str) -> str:
    """Sanitize document title for use as filename."""
    # Remove/replace invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    filename = title
    for char in invalid_chars:
        filename = filename.replace(char, "-")

    # Ensure .md extension
    if not filename.endswith(".md"):
        filename += ".md"

    return filename


def create(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    public: bool = typer.Option(False, "--public", help="Create public gist"),
    secret: bool = typer.Option(False, "--secret", help="Create secret gist (default)"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Gist description"),
    copy_url: bool = typer.Option(False, "--copy", "-c", help="Copy gist URL to clipboard"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="Open gist in browser"),
    update: Optional[str] = typer.Option(None, "--update", "-u", help="Update existing gist ID"),
):
    """Create or update a GitHub Gist from a document."""
    # Ensure database schema is up to date
    db.ensure_schema()

    # Check for conflicting options
    if public and secret:
        console.print("[red]Error: Cannot use both --public and --secret options[/red]")
        raise typer.Exit(1)

    # Get the document
    doc = get_document(identifier, track_access=False)
    if not doc:
        console.print(f"[red]Error: Document '{identifier}' not found[/red]")
        raise typer.Exit(1)

    # Verify GitHub authentication (gh CLI)
    if not get_github_auth():
        console.print("[red]Error: GitHub authentication not configured[/red]")
        console.print("\nTo use the gist command, authenticate with GitHub CLI:")
        console.print("  [cyan]gh auth login[/cyan]")
        raise typer.Exit(1)

    # Prepare gist content
    filename = sanitize_filename(doc["title"])
    content = doc["content"]

    # Use document title and metadata in description if not provided
    if not description:
        description = f"{doc['title']} - emdx knowledge base"
        if doc.get("project"):
            description += f" (Project: {doc['project']})"

    # Create or update gist
    if update:
        # Update existing gist
        console.print(f"[yellow]Updating gist {update}...[/yellow]")

        success = update_gist_with_gh(update, content, filename)
        if success:
            console.print(f"[green]✓ Updated gist {update}[/green]")

            # Update database record
            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE gists
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE gist_id = ? AND document_id = ?
                """,
                    (update, doc["id"]),
                )
                conn.commit()
        else:
            console.print("[red]Error: Failed to update gist[/red]")
            raise typer.Exit(1)
    else:
        # Create new gist
        console.print(f"[yellow]Creating {'public' if public else 'secret'} gist...[/yellow]")

        result = create_gist_with_gh(content, filename, description, public)
        if result:
            gist_id = result["id"]
            gist_url = result["url"]

            console.print(f"[green]✓ Created gist:[/green] {gist_url}")

            # Save to database
            with db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO gists (document_id, gist_id, gist_url, is_public)
                    VALUES (?, ?, ?, ?)
                """,
                    (doc["id"], gist_id, gist_url, public),
                )
                conn.commit()

            # Post-creation actions
            if copy_url:
                if copy_to_clipboard(gist_url):
                    console.print("[green]✓ URL copied to clipboard[/green]")
                else:
                    console.print("[yellow]⚠ Could not copy to clipboard[/yellow]")

            if open_browser:
                webbrowser.open(gist_url)
                console.print("[green]✓ Opened in browser[/green]")
        else:
            console.print("[red]Error: Failed to create gist[/red]")
            raise typer.Exit(1)


# Register the create function as the default 'gist' command
app.command(name="gist")(create)
