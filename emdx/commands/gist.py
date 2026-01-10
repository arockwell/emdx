"""
GitHub Gist integration for emdx

Security Note:
    This module handles GitHub authentication tokens. When using environment
    variables for tokens (GITHUB_TOKEN), be aware that these can be exposed
    in process listings and may be inherited by child processes. For better
    security, prefer using `gh auth login` which stores credentials securely.
"""

import os
import subprocess
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from github import Github, GithubException
from rich.console import Console
from rich.table import Table

from emdx.database import db
from emdx.models.documents import get_document

app = typer.Typer()
console = Console()


def get_github_auth() -> Optional[str]:
    """Get GitHub authentication token.

    Security Note:
        This function retrieves GitHub tokens from environment variables or
        the gh CLI. Using `gh auth login` is preferred over environment
        variables as it stores credentials more securely and handles token
        refresh automatically.

    Returns:
        GitHub token string if found, None otherwise.
    """
    # Priority order:
    # 1. Try to get token from gh CLI if available (more secure)
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5  # Prevent hanging
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. Environment variable GITHUB_TOKEN (less secure fallback)
    token = os.getenv("GITHUB_TOKEN")
    if token:
        # Warn about environment variable usage in debug scenarios
        # Note: We don't warn every time to avoid noise, but the security
        # note in the module docstring covers this
        return token

    return None


def create_gist_with_gh(
    content: str, filename: str, description: str, public: bool = False
) -> Optional[dict[str, str]]:
    """Create a gist using gh CLI.

    Uses secure temp file handling to prevent race conditions.
    """
    temp_path = None
    try:
        # Create a secure temporary file with restricted permissions
        # Using mkstemp for atomic creation with secure permissions
        fd, temp_path = tempfile.mkstemp(suffix=".md", prefix="emdx_gist_")
        try:
            # Write content using the file descriptor for atomicity
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)

        # Build gh command
        cmd = ["gh", "gist", "create", temp_path, "--desc", description]
        if public:
            cmd.append("--public")

        # Execute command with timeout to prevent hanging
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        if result.returncode == 0:
            gist_url = result.stdout.strip()
            # Extract gist ID from URL
            gist_id = gist_url.split("/")[-1]
            return {"id": gist_id, "url": gist_url}
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    finally:
        # Ensure temp file is always cleaned up
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass  # Ignore cleanup errors

    return None


def create_gist_with_api(
    content: str, filename: str, description: str, public: bool = False, token: Optional[str] = None
) -> Optional[dict[str, str]]:
    """Create a gist using GitHub API."""
    if not token:
        return None

    try:
        g = Github(token)
        user = g.get_user()

        # Create gist
        gist = user.create_gist(
            public=public, files={filename: {"content": content}}, description=description
        )

        return {"id": gist.id, "url": gist.html_url}
    except GithubException as e:
        console.print(f"[red]GitHub API error: {e}[/red]")
        return None


def update_gist_with_gh(gist_id: str, content: str, filename: str) -> bool:
    """Update an existing gist using gh CLI.

    Uses secure temp file handling to prevent race conditions.
    """
    temp_path = None
    try:
        # Create a secure temporary file with restricted permissions
        fd, temp_path = tempfile.mkstemp(suffix=".md", prefix="emdx_gist_")
        try:
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)

        # Execute gh command with timeout
        cmd = ["gh", "gist", "edit", gist_id, temp_path]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    finally:
        # Ensure temp file is always cleaned up
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    return False


def update_gist_with_api(
    gist_id: str, content: str, filename: str, token: Optional[str] = None
) -> bool:
    """Update an existing gist using GitHub API."""
    if not token:
        return False

    try:
        g = Github(token)
        gist = g.get_gist(gist_id)

        # Update gist
        gist.edit(files={filename: {"content": content}})
        return True
    except GithubException as e:
        console.print(f"[red]GitHub API error: {e}[/red]")
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard."""
    try:
        # macOS
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        try:
            # Linux (X11)
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            # Windows or fallback - would need pyperclip
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
    doc = get_document(identifier)
    if not doc:
        console.print(f"[red]Error: Document '{identifier}' not found[/red]")
        raise typer.Exit(1)

    # Get GitHub authentication
    token = get_github_auth()
    if not token:
        console.print("[red]Error: GitHub authentication not configured[/red]")
        console.print("\nTo use the gist command, you need to:")
        console.print("1. Set the GITHUB_TOKEN environment variable, or")
        console.print("2. Install and authenticate with GitHub CLI: [cyan]gh auth login[/cyan]")
        console.print("\nTo create a GitHub token:")
        console.print("1. Go to https://github.com/settings/tokens/new")
        console.print("2. Select 'gist' scope")
        console.print("3. Set: [cyan]export GITHUB_TOKEN=your_token[/cyan]")
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

        # Try gh CLI first
        success = update_gist_with_gh(update, content, filename)
        if not success:
            # Fallback to API
            success = update_gist_with_api(update, content, filename, token)

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

        # Try gh CLI first
        result = create_gist_with_gh(content, filename, description, public)
        if not result:
            # Fallback to API
            result = create_gist_with_api(content, filename, description, public, token)

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


@app.command("gist-list")
def list_gists(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
):
    """List all gists created from documents."""
    db.ensure_schema()

    with db.get_connection() as conn:
        if project:
            cursor = conn.execute(
                """
                SELECT g.*, d.title, d.project
                FROM gists g
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
                FROM gists g
                JOIN documents d ON g.document_id = d.id
                ORDER BY g.created_at DESC
            """
            )

        rows = cursor.fetchall()

    if not rows:
        console.print("[yellow]No gists found[/yellow]")
        return

    # Create table
    table = Table(title="Created Gists")
    table.add_column("Doc ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Project", style="blue")
    table.add_column("Gist ID", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Created", style="dim")

    for row in rows:
        # Handle datetime formatting
        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_at_str = str(created_at)[:16]

        table.add_row(
            str(row["document_id"]),
            row["title"],
            row["project"] or "-",
            row["gist_id"],
            "Public" if row["is_public"] else "Secret",
            created_at_str,
        )

    console.print(table)


# Register the create function as the default 'gist' command
app.command(name="gist")(create)
