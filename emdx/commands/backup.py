"""CLI commands for cloud backup under `emdx maintain backup`."""

from __future__ import annotations

import logging

import typer
from rich.table import Table

from ..utils.output import console

logger = logging.getLogger(__name__)

app = typer.Typer(help="Cloud backup and restore")

DEFAULT_PROVIDER = "google_drive"


@app.callback(invoke_without_command=True)
def backup_callback(
    ctx: typer.Context,
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider", "-p",
        help="Backup provider (google_drive, github)",
    ),
) -> None:
    """Back up your knowledge base to cloud storage.

    Run with no subcommand to create a backup using the default provider.

    Examples:
        emdx maintain backup                        # Back up to Google Drive
        emdx maintain backup --provider github      # Back up to GitHub Gist
        emdx maintain backup list                   # Show previous backups
        emdx maintain backup restore                # Restore latest backup
        emdx maintain backup auth                   # Set up authentication
    """
    if ctx.invoked_subcommand is not None:
        # Store provider in context for subcommands
        ctx.ensure_object(dict)
        ctx.obj["provider"] = provider
        return

    # No subcommand — run backup
    _run_backup(provider)


def _run_backup(provider_name: str) -> None:
    """Execute a backup with the given provider."""
    from ..services.backup_providers import get_provider
    from ..services.backup_service import backup

    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"Backing up to {provider_name}...")

    try:
        record = backup(provider)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]Backup complete:[/green] {record['description']}")
    console.print(f"  ID: {record['id']}")
    console.print(f"  SHA-256: {record['sha256'][:16]}...")


@app.command(name="list")
def list_backups(
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider", "-p",
        help="Backup provider (google_drive, github)",
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
) -> None:
    """List available backups."""
    from ..services.backup_providers import get_provider
    from ..services.backup_service import list_backups as svc_list

    try:
        provider_obj = get_provider(provider)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        records = svc_list(provider_obj)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not records:
        console.print(f"No backups found on {provider}.")
        return

    if json_output:
        import json

        print(json.dumps(records, indent=2))
        return

    table = Table(title=f"Backups on {provider}")
    table.add_column("ID", style="cyan", max_width=20)
    table.add_column("Timestamp")
    table.add_column("Size", justify="right")
    table.add_column("Description")

    for r in records:
        size = _format_size(r["file_size_bytes"]) if r["file_size_bytes"] else "?"
        table.add_row(
            r["id"][:16] + "..." if len(r["id"]) > 16 else r["id"],
            r["timestamp"][:19] if r["timestamp"] else "?",
            size,
            r["description"],
        )

    console.print(table)


@app.command()
def restore(
    backup_id: str = typer.Argument(
        None, help="Backup ID to restore (latest if omitted)"
    ),
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider", "-p",
        help="Backup provider (google_drive, github)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Restore your knowledge base from a cloud backup.

    Creates a .db.bak of the current database before overwriting.
    Verifies SHA-256 integrity after download.
    """
    from rich.prompt import Confirm

    from ..services.backup_providers import get_provider
    from ..services.backup_service import restore as svc_restore

    try:
        provider_obj = get_provider(provider)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    if not force:
        msg = (
            "This will replace your current database"
            " (a .db.bak backup will be created). Continue?"
        )
        if not Confirm.ask(msg, default=False):
            console.print("Restore cancelled.")
            raise typer.Exit(0)

    console.print(f"Restoring from {provider}...")

    try:
        db_path = svc_restore(provider_obj, backup_id)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]Database restored successfully:[/green] {db_path}")


@app.command()
def auth(
    provider: str = typer.Option(
        DEFAULT_PROVIDER,
        "--provider", "-p",
        help="Backup provider to authenticate",
    ),
    client_secrets: str = typer.Option(
        None,
        "--client-secrets",
        help="Path to Google OAuth client secrets JSON (for google_drive)",
    ),
) -> None:
    """Set up authentication for a backup provider.

    For Google Drive:
        1. Create a project at https://console.cloud.google.com
        2. Enable the Google Drive API
        3. Create OAuth 2.0 credentials (Desktop app)
        4. Download the client secrets JSON
        5. Run: emdx maintain backup auth --client-secrets path/to/secrets.json

    For GitHub:
        Just ensure `gh auth login` is complete.
    """
    if provider == "google_drive":
        if client_secrets is None:
            console.print(
                "[yellow]Google Drive requires --client-secrets path/to/file.json[/yellow]\n"
                "Download from Google Cloud Console > APIs & Services > Credentials"
            )
            raise typer.Exit(1)

        from ..services.backup_providers.google_drive import GoogleDriveProvider

        gdrive = GoogleDriveProvider()
        try:
            if gdrive.setup_auth(client_secrets):
                console.print("[green]Google Drive authentication successful![/green]")
            else:
                console.print("[red]Google Drive authentication failed.[/red]")
                raise typer.Exit(1)
        except FileNotFoundError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from None

    elif provider == "github":
        from ..services.backup_providers.github import GitHubProvider

        gh = GitHubProvider()
        if gh.authenticate():
            console.print("[green]GitHub CLI is authenticated and ready![/green]")
        else:
            console.print(
                "[red]GitHub CLI not authenticated.[/red]\n"
                "Run: gh auth login"
            )
            raise typer.Exit(1)

    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)


def _format_size(size_bytes: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes_f = size_bytes / 1024
        size_bytes = int(size_bytes_f)
    return f"{size_bytes:.1f} TB"
