"""Help command for emdx.

Provides `emdx help [command...]` as an alternative to `emdx [command...] --help`.
"""

from typing import List, Optional

import click
import typer
from typer.main import get_command


def help_command(
    ctx: typer.Context,
    commands: Optional[List[str]] = typer.Argument(
        None,
        help="Command(s) to show help for (e.g., 'task create')",
    ),
) -> None:
    """Show help for emdx commands.

    Examples:
        emdx help              Show main help
        emdx help save         Show help for save command
        emdx help task         Show help for task command group
        emdx help task create  Show help for task create subcommand
    """
    # Import here to avoid circular imports
    from emdx.main import app

    # Get the Click command from the Typer app
    click_app = get_command(app)

    # If no commands specified, show main help
    if not commands:
        with click.Context(click_app) as click_ctx:
            typer.echo(click_app.get_help(click_ctx))
        return

    # Navigate to the target command
    current_cmd = click_app
    current_ctx = click.Context(current_cmd)

    for cmd_name in commands:
        if isinstance(current_cmd, click.MultiCommand):
            next_cmd = current_cmd.get_command(current_ctx, cmd_name)
            if next_cmd is None:
                typer.echo(f"Error: No such command '{cmd_name}'.", err=True)
                raise typer.Exit(2)
            current_cmd = next_cmd
            current_ctx = click.Context(current_cmd, parent=current_ctx)
        else:
            typer.echo(f"Error: '{commands[0]}' has no subcommands.", err=True)
            raise typer.Exit(2)

    # Show help for the target command
    typer.echo(current_cmd.get_help(current_ctx))
