"""Configuration commands for emdx."""

import json

import typer

from ..config.app_config import (
    KNOWN_SETTINGS,
    get_config_file_path,
    get_config_value,
    load_config,
    parse_config_value,
    set_config_value,
    unset_config_value,
)

app = typer.Typer(help="Manage emdx settings")


def _format_value(value: object) -> str:
    """Render a config value the same way `config set` parses it."""
    return json.dumps(value)


@app.command(name="get")
def get_cmd(key: str = typer.Argument(..., help="Setting key, e.g. maintain.auto_link_on_save")):
    """Print a setting's effective value (set value or default)."""
    value = get_config_value(key)
    if value is None and key not in load_config() and key not in KNOWN_SETTINGS:
        typer.echo(f"Unknown setting: {key}", err=True)
        raise typer.Exit(1)
    print(_format_value(value))


@app.command(name="set")
def set_cmd(
    key: str = typer.Argument(..., help="Setting key, e.g. maintain.auto_link_on_save"),
    value: str = typer.Argument(..., help="Value (true/false, number, or string)"),
) -> None:
    """Set a setting. Values parse as bool/number when they look like one."""
    parsed = parse_config_value(value)
    set_config_value(key, parsed)
    print(f"{key} = {_format_value(parsed)}")


@app.command(name="unset")
def unset_cmd(key: str = typer.Argument(..., help="Setting key to remove")) -> None:
    """Remove a setting, reverting to its default."""
    if unset_config_value(key):
        default = KNOWN_SETTINGS.get(key)
        print(f"{key} unset (default: {_format_value(default)})")
    else:
        print(f"{key} was not set")


@app.command(name="list")
def list_cmd() -> None:
    """Show all settings: known defaults plus anything explicitly set."""
    config = load_config()
    keys = sorted(set(KNOWN_SETTINGS) | set(config))
    if not keys:
        print("No settings.")
        return
    for key in keys:
        if key in config:
            print(f"{key} = {_format_value(config[key])}")
        else:
            print(f"{key} = {_format_value(KNOWN_SETTINGS[key])} (default)")
    print(f"\nConfig file: {get_config_file_path()}")
