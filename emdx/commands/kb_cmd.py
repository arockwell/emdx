"""Named knowledge bases — isolated databases selected by name."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

import typer

from ..config.app_config import (
    get_config_value,
    load_config,
    set_config_value,
    unset_config_value,
)
from ..config.knowledge_bases import (
    DEFAULT_KB,
    KB_DEFAULT_SETTING,
    KB_DIRS_PREFIX,
    KnowledgeBaseError,
    dir_mappings,
    kb_db_path,
    kb_exists,
    list_kbs,
    validate_kb_name,
)
from ..config.settings import resolve_database

app = typer.Typer(help="Named knowledge bases (isolated databases)")


class KBRow(TypedDict):
    name: str
    path: str
    active: bool
    exists: bool
    size: str
    dirs: list[str]


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _name_or_fail(name: str) -> str:
    try:
        return validate_kb_name(name)
    except KnowledgeBaseError as e:
        _fail(str(e))
        raise  # unreachable, keeps mypy happy


def _size(path: Path) -> str:
    if not path.exists():
        return "-"
    mb = path.stat().st_size / (1024 * 1024)
    return f"{mb:.1f} MB"


@app.command(name="list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List knowledge bases and which one is active."""
    try:
        active = resolve_database(require_exists=False)
    except KnowledgeBaseError as e:
        _fail(str(e))
        raise
    mappings = dir_mappings()
    rows: list[KBRow] = []
    for name in list_kbs():
        path = kb_db_path(name)
        rows.append(
            {
                "name": name,
                "path": str(path),
                "active": path.resolve() == active.path.resolve(),
                "exists": path.exists(),
                "size": _size(path),
                "dirs": [str(d) for d in mappings.get(name, [])],
            }
        )
    if json_output:
        print(json.dumps(rows, indent=2))
        return
    for r in rows:
        marker = "*" if r["active"] else " "
        line = f"{marker} {r['name']:<20} {r['size']:>9}  {r['path']}"
        if r["dirs"]:
            line += f"  [{', '.join(r['dirs'])}]"
        print(line)
    if active.name is None:
        print(f"\nActive database: {active.path} ({active.reason})")
    elif not active.path.exists() and active.name != DEFAULT_KB:
        print(f"\nActive KB '{active.name}' does not exist yet — run: emdx kb create {active.name}")


@app.command()
def current(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show the active knowledge base and why it was chosen."""
    try:
        sel = resolve_database(require_exists=False)
    except KnowledgeBaseError as e:
        _fail(str(e))
        raise
    if json_output:
        print(
            json.dumps(
                {
                    "name": sel.name,
                    "path": str(sel.path),
                    "reason": sel.reason,
                    "exists": sel.path.exists(),
                }
            )
        )
        return
    print(f"Knowledge base: {sel.name or '(database override)'}")
    print(f"Path:           {sel.path}")
    print(f"Reason:         {sel.reason}")
    if not sel.path.exists():
        print("Exists:         no")


@app.command()
def create(name: str = typer.Argument(..., help="Name (lowercase, digits, - or _)")) -> None:
    """Create a new, empty knowledge base."""
    name = _name_or_fail(name)
    path = kb_db_path(name)
    if path.exists():
        _fail(f"Knowledge base '{name}' already exists at {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    from ..database import migrations

    migrations.run_migrations(path)
    print(f"✅ Created knowledge base '{name}' at {path}")
    print(f"   Use it with: emdx --kb {name} ...   or   emdx kb use {name}")


@app.command()
def use(
    name: str | None = typer.Argument(None, help="Knowledge base to make the default"),
    clear: bool = typer.Option(False, "--clear", help="Revert to the built-in default"),
) -> None:
    """Set the default knowledge base (persisted as the kb.default setting)."""
    if clear:
        unset_config_value(KB_DEFAULT_SETTING)
        print(f"Default knowledge base reset to '{DEFAULT_KB}'")
        return
    if not name:
        current_default = get_config_value(KB_DEFAULT_SETTING)
        print(f"Default knowledge base: {current_default}")
        return
    name = _name_or_fail(name)
    if not kb_exists(name):
        _fail(f"Knowledge base '{name}' does not exist. Create it with: emdx kb create {name}")
    set_config_value(KB_DEFAULT_SETTING, name)
    print(f"Default knowledge base set to '{name}'")


@app.command(name="map")
def map_cmd(
    name: str = typer.Argument(..., help="Knowledge base name"),
    directories: list[Path] | None = typer.Argument(
        None, help="Directories to map (default: current directory)"
    ),
    remove: bool = typer.Option(False, "--remove", help="Remove the mapping instead"),
) -> None:
    """Use a knowledge base automatically when running inside given directories."""
    name = _name_or_fail(name)
    if not remove and not kb_exists(name):
        _fail(f"Knowledge base '{name}' does not exist. Create it with: emdx kb create {name}")

    dirs = [d.expanduser().resolve() for d in (directories or [Path(os.getcwd())])]
    key = f"{KB_DIRS_PREFIX}{name}"
    existing = [str(d) for d in dir_mappings(load_config()).get(name, [])]

    if remove:
        remaining = [d for d in existing if Path(d).resolve() not in dirs]
        if remaining:
            set_config_value(key, ":".join(remaining))
        else:
            unset_config_value(key)
        print(f"Removed {len(existing) - len(remaining)} mapping(s) for '{name}'")
        return

    merged = existing + [str(d) for d in dirs if str(d) not in existing]
    set_config_value(key, ":".join(merged))
    for d in dirs:
        print(f"{d} → {name}")
