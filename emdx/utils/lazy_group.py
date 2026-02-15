"""Lazy loading support for Typer CLI commands.

This module provides a LazyTyperGroup class that extends Typer's group
to support lazy loading of subcommands. This significantly improves
startup performance for CLI applications with many heavy dependencies.

Heavy commands (cascade, delegate, ai, etc.) are only imported
when actually invoked, not on every CLI call.
"""

import importlib
from typing import Any

import click
from typer.core import TyperGroup

# Module-level registry for lazy commands
# This is populated by the main module and read by LazyTyperGroup instances
_LAZY_REGISTRY: dict[str, dict[str, str]] = {
    "subcommands": {},
    "help": {},
}


def register_lazy_commands(
    subcommands: dict[str, str],
    help_strings: dict[str, str],
) -> None:
    """Register lazy commands in the global registry.

    This should be called once at module load time by the main CLI module.

    Args:
        subcommands: Dict mapping command name to import path.
            Format: "module.path:object_name"
        help_strings: Dict mapping command name to help text.
    """
    _LAZY_REGISTRY["subcommands"] = subcommands
    _LAZY_REGISTRY["help"] = help_strings


class LazyCommand(click.MultiCommand):
    """A placeholder command that loads the real command on invocation.

    This command appears in help listings with pre-defined help text,
    but only loads the actual module when the command is invoked.
    """

    def __init__(
        self,
        name: str,
        import_path: str,
        help_text: str,
        parent_group: "LazyTyperGroup",
    ) -> None:
        super().__init__(name=name, help=help_text)
        self.import_path = import_path
        self.help_text = help_text
        self.short_help = help_text  # For --help listings
        self.parent_group = parent_group
        self._real_command: click.BaseCommand | None = None

    def _load_real_command(self) -> click.BaseCommand:
        """Load the actual command."""
        if self._real_command is not None:
            return self._real_command

        # Parse import path: "module.path:object_name"
        if ":" in self.import_path:
            modname, obj_name = self.import_path.rsplit(":", 1)
        else:
            # Legacy format: "module.path.object_name"
            modname, obj_name = self.import_path.rsplit(".", 1)

        try:
            mod = importlib.import_module(modname)
            cmd_object = getattr(mod, obj_name)
            self._real_command = self._convert_to_click_command(cmd_object)
            return self._real_command
        except ImportError as e:
            # Create an error command
            import_err = str(e)
            @click.command(name=self.name)
            def error_cmd() -> None:
                click.echo(f"Command '{self.name}' is not available: {import_err}", err=True)
                click.echo(
                    "This might be due to missing optional dependencies.",
                    err=True,
                )
                raise SystemExit(1)

            self._real_command = error_cmd
            return self._real_command
        except Exception as e:
            load_err = str(e)
            @click.command(name=self.name)
            def error_cmd() -> None:
                click.echo(f"Command '{self.name}' failed to load: {load_err}", err=True)
                raise SystemExit(1)

            self._real_command = error_cmd
            return self._real_command

    def _convert_to_click_command(self, cmd_object: Any) -> click.BaseCommand:
        """Convert a command object to a Click command."""
        import typer

        # Check if it's a Typer app
        if isinstance(cmd_object, typer.Typer):
            from typer.main import get_command, get_group

            # Check if it has multiple commands (use group) or single (use command)
            if (
                len(cmd_object.registered_commands) > 1
                or cmd_object.registered_groups
            ):
                cmd = get_group(cmd_object)
            else:
                cmd = get_command(cmd_object)
            cmd.name = self.name
            return cmd

        # Check if it's already a Click command
        if isinstance(cmd_object, click.BaseCommand):
            cmd_object.name = self.name
            return cmd_object

        # Check if it's a callable (function decorated for Typer)
        if callable(cmd_object):
            # Wrap the function in a Typer command
            temp_app = typer.Typer()
            temp_app.command(name=self.name)(cmd_object)
            from typer.main import get_command

            return get_command(temp_app)

        raise ValueError(
            f"Cannot convert {type(cmd_object)} to Click command. "
            f"Expected Typer app, Click command, or callable."
        )

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List subcommands (delegates to real command if it's a group)."""
        real_cmd = self._load_real_command()
        if isinstance(real_cmd, click.MultiCommand):
            return real_cmd.list_commands(ctx)
        return []

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get a subcommand (delegates to real command if it's a group)."""
        real_cmd = self._load_real_command()
        if isinstance(real_cmd, click.MultiCommand):
            return real_cmd.get_command(ctx, cmd_name)
        return None

    def invoke(self, ctx: click.Context) -> Any:
        """Invoke the command (loads the real command first)."""
        real_cmd = self._load_real_command()
        # Update the parent group's cache
        self.parent_group._loaded_commands[self.name or ""] = real_cmd
        # Delegate to the real command
        return real_cmd.invoke(ctx)

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        """Get parameters (loads the real command first for accurate params)."""
        real_cmd = self._load_real_command()
        return real_cmd.get_params(ctx)

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Run as main entry point."""
        real_cmd = self._load_real_command()
        return real_cmd.main(*args, **kwargs)


class LazyTyperGroup(TyperGroup):
    """A Typer-compatible Group with lazy subcommand loading.

    This class allows subcommands to be specified as import paths rather than
    actual command objects. The commands are only imported when they are
    invoked, not when the CLI is started.

    The lazy commands are registered via the module-level registry using
    `register_lazy_commands()`.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        lazy_help: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the lazy group.

        Args:
            lazy_subcommands: Dict mapping command name to import path.
                If not provided, uses the global registry.
            lazy_help: Dict mapping command name to help text.
                If not provided, uses the global registry.
        """
        super().__init__(*args, **kwargs)

        # Use provided values or fall back to global registry
        if lazy_subcommands is not None:
            self.lazy_subcommands = lazy_subcommands
        else:
            self.lazy_subcommands = _LAZY_REGISTRY["subcommands"].copy()

        if lazy_help is not None:
            self.lazy_help = lazy_help
        else:
            self.lazy_help = _LAZY_REGISTRY["help"].copy()

        self._loaded_commands: dict[str, click.BaseCommand] = {}
        self._lazy_placeholders: dict[str, LazyCommand] = {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return list of all commands (eager + lazy)."""
        base = super().list_commands(ctx)
        lazy = sorted(self.lazy_subcommands.keys())
        # Remove duplicates while preserving order
        all_commands = base + [cmd for cmd in lazy if cmd not in base]
        return sorted(all_commands)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.BaseCommand | None:
        """Get command, returning a lazy placeholder if needed.

        For lazy commands, this returns a LazyCommand placeholder that:
        - Has the correct help text (for --help listings)
        - Only loads the actual module when invoked
        """
        # Check if we've already loaded the real command
        if cmd_name in self._loaded_commands:
            return self._loaded_commands[cmd_name]

        # Check if this is a lazy command
        if cmd_name in self.lazy_subcommands:
            # Return or create a placeholder
            if cmd_name not in self._lazy_placeholders:
                self._lazy_placeholders[cmd_name] = LazyCommand(
                    name=cmd_name,
                    import_path=self.lazy_subcommands[cmd_name],
                    help_text=self.lazy_help.get(cmd_name, ""),
                    parent_group=self,
                )
            return self._lazy_placeholders[cmd_name]

        return super().get_command(ctx, cmd_name)
