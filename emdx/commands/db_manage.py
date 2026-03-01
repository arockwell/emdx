"""Database management commands for emdx."""

import shutil

import typer

from ..config.constants import EMDX_CONFIG_DIR
from ..config.settings import _is_dev_checkout, get_db_path

app = typer.Typer(help="Database management")


@app.command()
def status() -> None:
    """Show which database is active and why."""
    import os

    db_path = get_db_path()
    prod_path = EMDX_CONFIG_DIR / "knowledge.db"

    # Determine reason
    if os.environ.get("EMDX_TEST_DB"):
        reason = "EMDX_TEST_DB environment variable"
    elif os.environ.get("EMDX_DB"):
        reason = "EMDX_DB environment variable"
    elif _is_dev_checkout():
        reason = "dev checkout detected (editable install)"
    else:
        reason = "production default"

    print(f"Active DB:    {db_path}")
    print(f"Reason:       {reason}")
    print(f"Production:   {prod_path}")
    if db_path != prod_path:
        print(f"Exists:       {'yes' if db_path.exists() else 'no'}")


@app.command()
def path() -> None:
    """Print the active database path (for scripts)."""
    print(get_db_path())


@app.command(name="copy-from-prod")
def copy_from_prod() -> None:
    """Copy the production database to the dev database.

    Useful for working with real data locally during development.
    """
    prod_path = EMDX_CONFIG_DIR / "knowledge.db"
    dev_path = get_db_path()

    if dev_path == prod_path:
        typer.echo("Already using the production database — nothing to copy.", err=True)
        raise typer.Exit(1)

    if not prod_path.exists():
        typer.echo(f"Production database not found at {prod_path}", err=True)
        raise typer.Exit(1)

    dev_path.parent.mkdir(parents=True, exist_ok=True)

    if dev_path.exists():
        confirm = typer.confirm(f"Overwrite existing dev DB at {dev_path}?")
        if not confirm:
            raise typer.Abort()

    shutil.copy2(prod_path, dev_path)
    print(f"Copied {prod_path} -> {dev_path}")
