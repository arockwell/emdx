"""Lazy loading and alias support for Typer CLI commands.

This module provides:
- LazyTyperGroup: Extends Typer's group with lazy loading of subcommands
  and command aliases. Heavy commands are only imported when invoked.
- AliasGroup: A lighter TyperGroup subclass that adds alias support
  without lazy loading, suitable for subcommand groups (e.g. task).

Heavy commands (gui, ai, etc.) are only imported
when actually invoked, not on every CLI call.
"""

from __future__ import annotations

import importlib
from typing import Any

import click
from typer.core import TyperGroup

# typer >= 0.26 vendors its own rewritten click under ``typer._click``, where
# ``Group`` no longer exists as a separate class — ``TyperGroup`` is itself the
# group implementation. Anything that has to live inside typer's parse tree must
# therefore derive from ``TyperGroup`` (not ``click.Group``), and cross-hierarchy
# ``isinstance`` checks must be duck-typed instead.
#
# For the same reason the ctx/formatter objects passed to the click hooks below
# are ``click.*`` types under typer < 0.26 and ``typer._click.*`` types from 0.26
# on, so they are annotated ``Any`` rather than pinned to one hierarchy.
ClickContext = Any
ClickFormatter = Any


def _is_command(obj: Any) -> bool:
    """True if ``obj`` is a click/typer command object."""
    return hasattr(obj, "invoke") and hasattr(obj, "make_context")


def _is_group(obj: Any) -> bool:
    """True if ``obj`` is a command that dispatches subcommands."""
    return hasattr(obj, "get_command") and hasattr(obj, "list_commands")


# Module-level registry for command aliases
# Maps alias name -> canonical command name
_ALIAS_REGISTRY: dict[str, str] = {}


def register_aliases(aliases: dict[str, str]) -> None:
    """Register command aliases in the global registry.

    Args:
        aliases: Dict mapping alias name to canonical command name.
            Example: {"show": "view"} means 'show' resolves to 'view'.
    """
    _ALIAS_REGISTRY.update(aliases)


def _build_reverse_alias_map(aliases: dict[str, str]) -> dict[str, list[str]]:
    """Build a reverse map from canonical name -> list of aliases."""
    reverse: dict[str, list[str]] = {}
    for alias, canonical in aliases.items():
        reverse.setdefault(canonical, []).append(alias)
    return reverse


class _AliasFormatMixin:
    """Mixin that annotates help output with alias info (e.g. 'view (show)')."""

    _aliases: dict[str, str]  # alias -> canonical

    def format_commands(self, ctx: ClickContext, formatter: ClickFormatter) -> None:
        """Override to append alias annotations to command names in help."""
        # Build reverse map: canonical -> [alias1, alias2, ...]
        reverse = _build_reverse_alias_map(self._aliases)

        commands: list[tuple[str, Any]] = []
        for subcommand in self.list_commands(ctx):  # type: ignore[attr-defined]
            cmd = self.get_command(ctx, subcommand)  # type: ignore[attr-defined]
            if cmd is not None and not cmd.hidden:
                commands.append((subcommand, cmd))

        if not commands:
            return

        limit = formatter.width - 6 - max(len(subcommand) for subcommand, _ in commands)
        rows: list[tuple[str, str]] = []
        for subcommand, cmd in commands:
            assert cmd is not None  # narrowing for mypy
            help_text = cmd.get_short_help_str(limit=limit)
            alias_list = reverse.get(subcommand)
            if alias_list:
                label = f"{subcommand} ({', '.join(sorted(alias_list))})"
            else:
                label = subcommand
            rows.append((label, help_text))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


class AliasGroup(_AliasFormatMixin, TyperGroup):
    """A TyperGroup with command alias support.

    Use this as cls= for Typer sub-apps that need aliases.
    Aliases are resolved in get_command() before falling back to super().
    """

    def __init__(
        self,
        *args: Any,
        aliases: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._aliases: dict[str, str] = aliases or {}

    def get_command(self, ctx: ClickContext, cmd_name: str) -> Any:
        """Resolve aliases before looking up the command."""
        canonical = self._aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, canonical)


def make_alias_group(aliases: dict[str, str]) -> type[AliasGroup]:
    """Create an AliasGroup subclass with aliases baked in.

    Typer instantiates ``cls`` without custom kwargs, so we use a factory
    to produce a class whose ``__init__`` injects the alias map automatically.

    Usage::

        app = typer.Typer(cls=make_alias_group({"create": "add"}))
    """

    class _BakedAliasGroup(AliasGroup):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("aliases", aliases)
            super().__init__(*args, **kwargs)

    _BakedAliasGroup.__qualname__ = f"AliasGroup[{','.join(aliases)}]"
    return _BakedAliasGroup


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


class LazyCommand(TyperGroup):
    """A placeholder command that loads the real command on invocation.

    This command appears in help listings with pre-defined help text,
    but only loads the actual module when the command is invoked.

    Derives from ``TyperGroup`` rather than ``click.Group`` so the placeholder
    stays inside typer's own command hierarchy (see the compat note at the top
    of this module).
    """

    def __init__(
        self,
        name: str,
        import_path: str,
        help_text: str,
        parent_group: LazyTyperGroup,
    ) -> None:
        # invoke_without_command so bare invocation (e.g. `emdx trash`) parses
        # and reaches invoke(); the real group then applies its own
        # invoke_without_command semantics (default action or "Missing command").
        super().__init__(name=name, help=help_text, invoke_without_command=True)
        self.import_path = import_path
        self.help_text = help_text
        self.short_help = help_text  # For --help listings
        self.parent_group = parent_group
        self._real_command: Any = None

    def _load_real_command(self) -> Any:
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
            self._real_command = self._make_error_command(
                f"Command '{self.name}' is not available: {e}",
                "This might be due to missing optional dependencies.",
            )
            return self._real_command
        except Exception as e:
            self._real_command = self._make_error_command(
                f"Command '{self.name}' failed to load: {e}"
            )
            return self._real_command

    def _make_error_command(self, *messages: str) -> Any:
        """Build a stand-in command that reports a load failure and exits 1.

        Built through typer rather than the ``click`` decorator so the result
        belongs to whichever click hierarchy typer is using.
        """
        import typer
        from typer.main import get_command

        def error_cmd() -> None:
            for message in messages:
                click.echo(message, err=True)
            raise SystemExit(1)

        temp_app = typer.Typer()
        temp_app.command(name=self.name)(error_cmd)
        return get_command(temp_app)

    def _convert_to_click_command(self, cmd_object: Any) -> Any:
        """Convert a command object to a Click command."""
        import typer

        # Check if it's a Typer app
        if isinstance(cmd_object, typer.Typer):
            from typer.main import get_command, get_group

            # Check if it has multiple commands (use group) or single (use command)
            if len(cmd_object.registered_commands) > 1 or cmd_object.registered_groups:
                cmd: Any = get_group(cmd_object)
            else:
                cmd = get_command(cmd_object)
            cmd.name = self.name
            return cmd

        # Check if it's already a Click command
        if _is_command(cmd_object):
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

    def list_commands(self, ctx: ClickContext) -> list[str]:
        """List subcommands (delegates to real command if it's a group)."""
        real_cmd = self._load_real_command()
        if _is_group(real_cmd):
            return list(real_cmd.list_commands(ctx))
        return []

    def get_command(self, ctx: ClickContext, cmd_name: str) -> Any:
        """Get a subcommand (delegates to real command if it's a group)."""
        real_cmd = self._load_real_command()
        if _is_group(real_cmd):
            return real_cmd.get_command(ctx, cmd_name)
        return None

    def invoke(self, ctx: ClickContext) -> Any:
        """Invoke the command (loads the real command first)."""
        real_cmd = self._load_real_command()
        # Update the parent group's cache
        self.parent_group._loaded_commands[self.name or ""] = real_cmd
        # Bare invocation of a group that doesn't define a default action:
        # show its help (matching eager-group behavior) instead of delegating,
        # which would fail with a bare "Missing command." error.
        if (
            not ctx._protected_args
            and not ctx.args
            and _is_group(real_cmd)
            and not real_cmd.invoke_without_command
        ):
            click.echo(real_cmd.get_help(ctx))
            ctx.exit()
        # Delegate to the real command
        return real_cmd.invoke(ctx)

    def format_help(self, ctx: ClickContext, formatter: ClickFormatter) -> None:
        """Format help text (delegates to real command for full help)."""
        real_cmd = self._load_real_command()
        real_cmd.format_help(ctx, formatter)

    def get_params(self, ctx: ClickContext) -> list[Any]:
        """Get parameters (loads the real command first for accurate params)."""
        real_cmd = self._load_real_command()
        if hasattr(real_cmd, "get_params"):
            return list(real_cmd.get_params(ctx))
        return list(getattr(real_cmd, "params", []))

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Run as main entry point."""
        real_cmd = self._load_real_command()
        return real_cmd.main(*args, **kwargs)


class LazyTyperGroup(_AliasFormatMixin, TyperGroup):
    """A Typer-compatible Group with lazy subcommand loading and aliases.

    This class allows subcommands to be specified as import paths rather than
    actual command objects. The commands are only imported when they are
    invoked, not when the CLI is started.

    It also supports command aliases (e.g. 'show' → 'view') via the global
    alias registry or explicit ``aliases`` kwarg.

    The lazy commands are registered via the module-level registry using
    `register_lazy_commands()`.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        lazy_help: dict[str, str] | None = None,
        aliases: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the lazy group.

        Args:
            lazy_subcommands: Dict mapping command name to import path.
                If not provided, uses the global registry.
            lazy_help: Dict mapping command name to help text.
                If not provided, uses the global registry.
            aliases: Dict mapping alias name to canonical command name.
                If not provided, uses the global alias registry.
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

        if aliases is not None:
            self._aliases: dict[str, str] = aliases
        else:
            self._aliases = _ALIAS_REGISTRY.copy()

        self._loaded_commands: dict[str, Any] = {}
        self._lazy_placeholders: dict[str, LazyCommand] = {}

    def list_commands(self, ctx: ClickContext) -> list[str]:
        """Return list of all commands (eager + lazy)."""
        base = super().list_commands(ctx)
        lazy = sorted(self.lazy_subcommands.keys())
        # Remove duplicates while preserving order
        all_commands = base + [cmd for cmd in lazy if cmd not in base]
        return sorted(all_commands)

    def get_command(self, ctx: ClickContext, cmd_name: str) -> Any:
        """Get command, resolving aliases and returning a lazy placeholder if needed.

        For lazy commands, this returns a LazyCommand placeholder that:
        - Has the correct help text (for --help listings)
        - Only loads the actual module when invoked
        """
        # Resolve alias to canonical name
        cmd_name = self._aliases.get(cmd_name, cmd_name)

        # Check if we've already loaded the real command
        if cmd_name in self._loaded_commands:
            loaded = self._loaded_commands[cmd_name]
            if _is_command(loaded):
                return loaded
            return None

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
