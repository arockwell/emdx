"""Tests for lazy loading CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Generator

import click
import pytest
from typer.testing import CliRunner

from emdx.utils.lazy_group import (
    _LAZY_REGISTRY,
    LazyCommand,
    LazyTyperGroup,
    register_lazy_commands,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _restore_lazy_registry() -> Generator[None, None, None]:
    """Save and restore the global lazy registry around each test.

    Tests that call register_lazy_commands() replace the global registry,
    which corrupts state for later tests that rely on it (e.g. maintain
    subcommand tests). This fixture ensures the registry is always restored.
    """
    saved_subcommands = _LAZY_REGISTRY["subcommands"].copy()
    saved_help = _LAZY_REGISTRY["help"].copy()
    yield
    _LAZY_REGISTRY["subcommands"] = saved_subcommands
    _LAZY_REGISTRY["help"] = saved_help


class TestLazyTyperGroup:
    """Test the LazyTyperGroup class."""

    def test_list_commands_includes_lazy(self) -> None:
        """Test that list_commands returns both eager and lazy commands."""

        # Create a group with one eager command
        @click.command()
        def eager() -> None:
            pass

        group = LazyTyperGroup(
            commands={"eager": eager},
            lazy_subcommands={"lazy1": "some.module:cmd", "lazy2": "another.module:cmd"},
            lazy_help={"lazy1": "Help for lazy1", "lazy2": "Help for lazy2"},
        )

        ctx = click.Context(group)
        commands = group.list_commands(ctx)

        assert "eager" in commands
        assert "lazy1" in commands
        assert "lazy2" in commands
        assert len(commands) == 3

    def test_get_command_returns_placeholder_for_lazy(self) -> None:
        """Test that get_command returns a LazyCommand placeholder for lazy commands."""
        group = LazyTyperGroup(
            lazy_subcommands={"lazy": "some.module:cmd"},
            lazy_help={"lazy": "Help for lazy"},
        )

        ctx = click.Context(group)
        cmd = group.get_command(ctx, "lazy")

        assert isinstance(cmd, LazyCommand)
        assert cmd.name == "lazy"
        assert cmd.help == "Help for lazy"

    def test_get_command_returns_eager_command(self) -> None:
        """Test that get_command returns eager commands directly."""

        @click.command()
        def eager() -> None:
            """Help for eager."""
            pass

        group = LazyTyperGroup(
            commands={"eager": eager},
            lazy_subcommands={},
            lazy_help={},
        )

        ctx = click.Context(group)
        cmd = group.get_command(ctx, "eager")

        assert cmd is eager
        assert not isinstance(cmd, LazyCommand)

    def test_lazy_command_not_loaded_until_invoked(self) -> None:
        """Test that lazy commands don't import their modules until invoked."""
        group = LazyTyperGroup(
            lazy_subcommands={"test_cmd": "emdx.commands.explore:app"},
            lazy_help={"test_cmd": "Test help"},
        )

        ctx = click.Context(group)

        # Getting the command should NOT load the module
        cmd = group.get_command(ctx, "test_cmd")
        assert isinstance(cmd, LazyCommand)
        assert cmd._real_command is None

    def test_uses_global_registry_by_default(self) -> None:
        """Test that LazyTyperGroup uses the global registry by default."""
        # Register some commands
        register_lazy_commands(
            {"registered": "some.module:cmd"},
            {"registered": "Registered help"},
        )

        group = LazyTyperGroup()

        assert "registered" in group.lazy_subcommands
        assert group.lazy_help.get("registered") == "Registered help"

    def test_explicit_config_overrides_registry(self) -> None:
        """Test that explicit config overrides the global registry."""
        register_lazy_commands(
            {"registered": "some.module:cmd"},
            {"registered": "Registered help"},
        )

        group = LazyTyperGroup(
            lazy_subcommands={"explicit": "other.module:cmd"},
            lazy_help={"explicit": "Explicit help"},
        )

        assert "explicit" in group.lazy_subcommands
        assert "registered" not in group.lazy_subcommands


class TestLazyCommand:
    """Test the LazyCommand class."""

    def test_help_text_without_loading(self) -> None:
        """Test that LazyCommand has help text without loading the real command."""
        group = LazyTyperGroup()
        cmd = LazyCommand(
            name="test",
            import_path="some.fake.module:cmd",
            help_text="Test help text",
            parent_group=group,
        )

        assert cmd.help == "Test help text"
        assert cmd._real_command is None

    def test_short_help_matches_help(self) -> None:
        """Test that short_help matches the provided help text."""
        group = LazyTyperGroup()
        cmd = LazyCommand(
            name="test",
            import_path="some.fake.module:cmd",
            help_text="Test help text",
            parent_group=group,
        )

        # short_help should use the help text
        assert cmd.short_help == "Test help text"

    def test_load_real_command_on_invoke(self) -> None:
        """Test that invoke loads the real command."""
        group = LazyTyperGroup()
        cmd = LazyCommand(
            name="explore",
            import_path="emdx.commands.explore:app",
            help_text="Test help",
            parent_group=group,
        )

        # Before invoke, real command is not loaded
        assert cmd._real_command is None

        # Load the real command
        real = cmd._load_real_command()

        # After loading, real command exists
        assert cmd._real_command is not None
        assert real is not None

    def test_graceful_degradation_on_import_error(self) -> None:
        """Test that import errors create an error command."""
        group = LazyTyperGroup()
        cmd = LazyCommand(
            name="broken",
            import_path="nonexistent.module:cmd",
            help_text="Test help",
            parent_group=group,
        )

        # Loading should not raise, should return error command
        real = cmd._load_real_command()

        assert real is not None
        assert cmd._real_command is not None


class TestCLIIntegration:
    """Test lazy loading in the actual CLI."""

    def test_help_does_not_load_lazy_modules(self) -> None:
        """Test that --help doesn't load lazy modules."""
        # Track which modules are loaded
        lazy_modules = [
            "emdx.commands.explore",
            "emdx.commands.distill",
        ]

        # Clear any cached imports
        for mod in lazy_modules:
            if mod in sys.modules:
                del sys.modules[mod]

        before = set(sys.modules.keys())

        # Import and run help - reimport to ensure fresh registry
        import importlib

        import emdx.main

        importlib.reload(emdx.main)
        from emdx.main import app

        result = runner.invoke(app, ["--help"])

        after = set(sys.modules.keys())
        loaded = after - before

        # None of the lazy modules should be loaded
        loaded_lazy = [m for m in lazy_modules if m in loaded]
        assert loaded_lazy == [], f"Lazy modules were loaded: {loaded_lazy}"
        assert result.exit_code == 0

    def test_lazy_commands_appear_in_help(self) -> None:
        """Test that lazy commands appear in --help output."""
        # Reimport to ensure fresh registry
        import importlib

        import emdx.main

        importlib.reload(emdx.main)
        from emdx.main import app

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "gui" in result.output

    def test_lazy_help_text_in_output(self) -> None:
        """Test that lazy commands show their pre-defined help text."""
        import importlib

        import emdx.main

        importlib.reload(emdx.main)
        from emdx.main import app

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Check that lazy commands appear in help
        assert "maintain" in result.output
        assert "labs" in result.output

    def test_core_commands_still_work(self) -> None:
        """Test that core (eager) commands still work."""
        from emdx.main import app

        result = runner.invoke(app, ["save", "--help"])

        assert result.exit_code == 0
        assert "Save content" in result.output

    def test_find_command_still_works(self) -> None:
        """Test that find command works."""
        from emdx.main import app

        result = runner.invoke(app, ["find", "--help"])

        assert result.exit_code == 0
        assert "Search" in result.output or "find" in result.output.lower()

    def test_list_is_an_alias_for_find(self) -> None:
        """GH #1104: `emdx list` should resolve to `emdx find`."""
        from emdx.main import app

        result = runner.invoke(app, ["list", "--help"])
        find_result = runner.invoke(app, ["find", "--help"])

        assert result.exit_code == 0
        # Usage line echoes the invoked name ("list" vs "find"); everything
        # else (options, help text) comes from the same underlying command.
        result_lines = [line for line in result.output.splitlines() if "Usage:" not in line]
        find_lines = [line for line in find_result.output.splitlines() if "Usage:" not in line]
        assert result_lines == find_lines

    def test_recent_is_an_alias_for_find(self) -> None:
        """GH #1104: `emdx recent` should resolve to `emdx find`."""
        from emdx.main import app

        result = runner.invoke(app, ["recent", "--help"])
        find_result = runner.invoke(app, ["find", "--help"])

        assert result.exit_code == 0
        result_lines = [line for line in result.output.splitlines() if "Usage:" not in line]
        find_lines = [line for line in find_result.output.splitlines() if "Usage:" not in line]
        assert result_lines == find_lines

    def test_epic_is_a_top_level_command(self) -> None:
        """GH #1104: `emdx epic` should forward into `emdx task epic`."""
        import importlib

        import emdx.main

        importlib.reload(emdx.main)
        from emdx.main import app

        result = runner.invoke(app, ["epic", "--help"])

        assert result.exit_code == 0
        assert "epic" in result.output.lower()


class TestListRecentShorthand:
    """GH #1130: `list`/`recent` are registered as top-level *name* aliases
    for `find`, but aliasing only renames the resolved command — it doesn't
    imply a flag. Bare `emdx list`/`emdx recent` used to still hit find's
    "provide search terms, tags, or date filters" error. The
    `_rewrite_list_recent_shorthand` argv rewrite (applied in `run()`,
    mirroring the existing `_rewrite_tag_shorthand` pattern) fixes that by
    injecting the flag the alias name implies.
    """

    def test_bare_list_gets_all_flag(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "list"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "list", "--all"]

    def test_bare_recent_gets_default_recent_flag(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "recent"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "recent", "--recent", "10"]

    def test_recent_with_numeric_positional_becomes_recent_flag(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "recent", "20"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "recent", "--recent", "20"]

    def test_list_help_is_not_rewritten(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "list", "--help"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "list", "--help"]

    def test_list_with_explicit_all_is_unchanged(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "list", "--all"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "list", "--all"]

    def test_list_with_tags_is_unchanged(self) -> None:
        """Already-valid find criteria (--tags) is left alone — no --all injected."""
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "list", "--tags", "python"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "list", "--tags", "python"]

    def test_list_with_search_query_is_unchanged(self) -> None:
        """A real search query after `list` is left as a plain find alias."""
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "list", "docker"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "list", "docker"]

    def test_recent_with_other_flags_gets_default_recent_flag(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "recent", "--json"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "recent", "--recent", "10", "--json"]

    def test_no_list_or_recent_token_is_unchanged(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "find", "docker"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "find", "docker"]

    def test_subcommand_list_is_not_rewritten(self) -> None:
        """`emdx task list` is `task`'s own `list` verb, not the top-level
        `list` alias for `find` — it must never get `--all` injected.
        """
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "task", "list"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "task", "list"]

    def test_nested_dep_list_is_not_rewritten(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "task", "dep", "list", "42"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "task", "dep", "list", "42"]

    def test_tag_list_subcommand_is_not_rewritten(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "tag", "list"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "tag", "list"]

    def test_top_level_list_after_global_flag_is_still_rewritten(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand

        argv = ["emdx", "--verbose", "list"]
        _rewrite_list_recent_shorthand(argv)
        assert argv == ["emdx", "--verbose", "list", "--all"]

    def test_bare_list_end_to_end(self) -> None:
        """The rewritten argv actually resolves through `find --all`, not
        find's "provide search terms..." error (the bug reported in #1130).
        """
        from emdx.main import _rewrite_list_recent_shorthand, app

        argv = ["emdx", "list"]
        _rewrite_list_recent_shorthand(argv)
        result = runner.invoke(app, argv[1:])

        assert result.exit_code == 0
        assert "Provide search terms" not in result.output

    def test_bare_recent_end_to_end(self) -> None:
        from emdx.main import _rewrite_list_recent_shorthand, app

        argv = ["emdx", "recent"]
        _rewrite_list_recent_shorthand(argv)
        result = runner.invoke(app, argv[1:])

        assert result.exit_code == 0
        assert "Provide search terms" not in result.output


class TestLazyRegistry:
    """Test the lazy command registry."""

    def test_register_and_get(self) -> None:
        """Test registering and getting lazy commands."""
        register_lazy_commands(
            {"cmd1": "mod1:app", "cmd2": "mod2:app"},
            {"cmd1": "Help 1", "cmd2": "Help 2"},
        )

        subcommands = _LAZY_REGISTRY["subcommands"]
        help_strings = _LAZY_REGISTRY["help"]

        assert "cmd1" in subcommands
        assert "cmd2" in subcommands
        assert help_strings["cmd1"] == "Help 1"
        assert help_strings["cmd2"] == "Help 2"

    def test_registry_is_global(self) -> None:
        """Test that the registry is global."""
        register_lazy_commands(
            {"global_cmd": "mod:app"},
            {"global_cmd": "Global help"},
        )

        # Create a new group - should pick up global registry
        group = LazyTyperGroup()

        assert "global_cmd" in group.lazy_subcommands
