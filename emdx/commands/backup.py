"""CLI commands for cloud backup operations.

Registered as `emdx maintain cloud-backup` subcommand group.
"""

from __future__ import annotations

import json as json_mod

import typer

from ..config.settings import get_db_path
from ..services.cloud_backup_service import CloudBackupService

app = typer.Typer(help="Cloud backup operations (GitHub Gist, Google Drive)")


@app.command()
def upload(
    provider: str = typer.Option(
        "github",
        "--provider",
        "-p",
        help="Cloud provider: github or gdrive",
    ),
    description: str = typer.Option(
        "",
        "--description",
        "-d",
        help="Description for this backup",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Upload the current database as a cloud backup.

    Examples:
        emdx maintain cloud-backup upload
        emdx maintain cloud-backup upload --provider gdrive
        emdx maintain cloud-backup upload -d "Before migration"
    """
    db_path = get_db_path()
    if not db_path.exists():
        msg = f"Database not found: {db_path}"
        if json_output:
            print(json_mod.dumps({"success": False, "message": msg}))
        else:
            print(msg)
        raise typer.Exit(code=1)

    try:
        svc = CloudBackupService(provider_name=provider)  # type: ignore[arg-type]
    except (ValueError, RuntimeError) as e:
        if json_output:
            print(json_mod.dumps({"success": False, "message": str(e)}))
        else:
            print(f"Error: {e}")
        raise typer.Exit(code=1) from None

    result = svc.upload(str(db_path), description)

    if json_output:
        print(json_mod.dumps(result, indent=2))
    elif result["success"]:
        meta = result["metadata"]
        assert meta is not None
        print(f"Uploaded: {meta['filename']}")
        print(f"  ID: {meta['backup_id']}")
        print(f"  Size: {meta['size_bytes']} bytes")
        print(f"  Provider: {meta['provider']}")
    else:
        print(result["message"])
        raise typer.Exit(code=1)


@app.command(name="list")
def list_backups(
    provider: str = typer.Option(
        "github",
        "--provider",
        "-p",
        help="Cloud provider: github or gdrive",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List cloud backups.

    Examples:
        emdx maintain cloud-backup list
        emdx maintain cloud-backup list --provider gdrive
        emdx maintain cloud-backup list --json
    """
    try:
        svc = CloudBackupService(provider_name=provider)  # type: ignore[arg-type]
    except (ValueError, RuntimeError) as e:
        if json_output:
            print(json_mod.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}")
        raise typer.Exit(code=1) from None

    backups = svc.list_backups()

    if json_output:
        print(json_mod.dumps(backups, indent=2))
    elif backups:
        for b in backups:
            size_info = f"  {b['size_bytes']} bytes" if b["size_bytes"] else ""
            print(f"{b['backup_id']}  {b['filename']}{size_info}  {b['created_at']}")
    else:
        print("No cloud backups found.")


@app.command()
def download(
    backup_id: str = typer.Argument(help="Backup ID to download"),
    provider: str = typer.Option(
        "github",
        "--provider",
        "-p",
        help="Cloud provider: github or gdrive",
    ),
    target_dir: str | None = typer.Option(
        None,
        "--target",
        "-t",
        help="Directory to download into (default: current directory)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Download a cloud backup by ID.

    Examples:
        emdx maintain cloud-backup download abc123
        emdx maintain cloud-backup download abc123 --provider gdrive
        emdx maintain cloud-backup download abc123 --target /tmp/restore
    """
    dest = target_dir or "."

    try:
        svc = CloudBackupService(provider_name=provider)  # type: ignore[arg-type]
    except (ValueError, RuntimeError) as e:
        if json_output:
            print(json_mod.dumps({"success": False, "message": str(e)}))
        else:
            print(f"Error: {e}")
        raise typer.Exit(code=1) from None

    result = svc.download(backup_id, dest)

    if json_output:
        print(json_mod.dumps(result, indent=2))
    elif result["success"]:
        print(f"Downloaded: {result['path']}")
    else:
        print(result["message"])
        raise typer.Exit(code=1)


@app.command()
def auth(
    provider: str = typer.Argument(help="Provider to authenticate: github or gdrive"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Set up authentication for a cloud backup provider.

    Examples:
        emdx maintain cloud-backup auth github
        emdx maintain cloud-backup auth gdrive
    """
    if provider == "github":
        _auth_github(json_output)
    elif provider == "gdrive":
        _auth_gdrive(json_output)
    else:
        msg = f"Unknown provider: {provider}. Use 'github' or 'gdrive'."
        if json_output:
            print(json_mod.dumps({"success": False, "message": msg}))
        else:
            print(msg)
        raise typer.Exit(code=1)


def _auth_github(json_output: bool) -> None:
    """Check GitHub CLI auth status."""
    from ..services.backup_providers.github import GitHubGistProvider

    provider = GitHubGistProvider()
    status = provider.check_auth()

    if json_output:
        print(json_mod.dumps(status, indent=2))
    elif status["authenticated"]:
        print("GitHub CLI is authenticated.")
        print("Cloud backups via GitHub Gist are ready to use.")
    else:
        print("GitHub CLI is not authenticated.")
        print("Run: gh auth login")


def _auth_gdrive(json_output: bool) -> None:
    """Run Google Drive OAuth flow."""
    try:
        from ..services.backup_providers.google_drive import (
            run_gdrive_auth_flow,
        )
    except ImportError:
        msg = (
            "Google Drive support requires google-api-python-client and "
            "google-auth-oauthlib.\n"
            "Install with: pip install google-api-python-client "
            "google-auth-oauthlib"
        )
        if json_output:
            print(json_mod.dumps({"success": False, "message": msg}))
        else:
            print(msg)
        raise typer.Exit(code=1) from None

    status = run_gdrive_auth_flow()

    if json_output:
        print(json_mod.dumps(status, indent=2))
    elif status["authenticated"]:
        print("Google Drive authentication successful.")
        print("Cloud backups via Google Drive are ready to use.")
    else:
        print(status["message"])
        raise typer.Exit(code=1)
