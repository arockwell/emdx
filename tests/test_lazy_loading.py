"""Tests for lazy loading CLI commands."""

import sys

import click
from typer.testing import CliRunner

from emdx.utils.lazy_group import (
    LazyCommand,
    LazyTyperGroup,
    register_lazy_commands,
    _LAZY_REGISTRY,
)


runner = CliRunner()


class TestLazyTyperGroup:
    """Test the LazyTyperGroup class."""

    def test_list_commands_includes_lazy(self):
        """Test that list_commands returns both eager and lazy commands."""
        # Create a group with one eager command
        @click.command()
        def eager():
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

    def test_get_command_returns_placeholder_for_lazy(self):
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

    def test_get_command_returns_eager_command(self):
        """Test that get_command returns eager commands directly."""
        @click.command()
        def eager():
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

    def test_lazy_command_not_loaded_until_invoked(self):
        """Test that lazy commands don't import their modules until invoked."""
        group = LazyTyperGroup(
            lazy_subcommands={"test_cmd": "emdx.commands.recipe:app"},
            lazy_help={"test_cmd": "Test help"},
        )

        ctx = click.Context(group)

        # Getting the command should NOT load the module
        cmd = group.get_command(ctx, "test_cmd")
        assert isinstance(cmd, LazyCommand)
        assert cmd._real_command is None

    def test_uses_global_registry_by_default(self):
        """Test that LazyTyperGroup uses the global registry by default."""
        # Register some commands
        register_lazy_commands(
            {"registered": "some.module:cmd"},
            {"registered": "Registered help"},
        )

        group = LazyTyperGroup()

        assert "registered" in group.lazy_subcommands
        assert group.lazy_help.get("registered") == "Registered help"

    def test_explicit_config_overrides_registry(self):
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

    def test_help_text_without_loading(self):
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

    def test_short_help_matches_help(self):
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

    def test_load_real_command_on_invoke(self):
        """Test that invoke loads the real command."""
        group = LazyTyperGroup()
        cmd = LazyCommand(
            name="recipe",
            import_path="emdx.commands.recipe:app",
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

    def test_graceful_degradation_on_import_error(self):
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

    def test_help_does_not_load_lazy_modules(self):
        """Test that --help doesn't load lazy modules."""
        # Track which modules are loaded
        lazy_modules = [
            'emdx.commands.recipe',
            'emdx.commands.cascade',
            'emdx.commands.delegate',
            'emdx.commands.claude_execute',
            'emdx.commands.ask',
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

    def test_lazy_commands_appear_in_help(self):
        """Test that lazy commands appear in --help output."""
        # Reimport to ensure fresh registry
        import importlib
        import emdx.main
        importlib.reload(emdx.main)
        from emdx.main import app

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "recipe" in result.output
        assert "cascade" in result.output
        assert "ai" in result.output
        assert "gui" in result.output

    def test_lazy_help_text_in_output(self):
        """Test that lazy commands show their pre-defined help text."""
        from emdx.main import app

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Check that our lazy help text appears (not the actual module help)
        assert "Manage and run EMDX recipes" in result.output
        assert "Cascade ideas through stages" in result.output

    def test_lazy_command_works_when_invoked(self):
        """Test that lazy commands work when actually invoked."""
        from emdx.main import app

        result = runner.invoke(app, ["recipe", "--help"])

        assert result.exit_code == 0
        # Should show the actual recipe subcommands
        assert "run" in result.output.lower()
        assert "list" in result.output.lower()

    def test_core_commands_still_work(self):
        """Test that core (eager) commands still work."""
        from emdx.main import app

        result = runner.invoke(app, ["save", "--help"])

        assert result.exit_code == 0
        assert "Save content" in result.output

    def test_find_command_still_works(self):
        """Test that find command works."""
        from emdx.main import app

        result = runner.invoke(app, ["find", "--help"])

        assert result.exit_code == 0
        assert "Search" in result.output or "find" in result.output.lower()


class TestLazyRegistry:
    """Test the lazy command registry."""

    def test_register_and_get(self):
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

    def test_registry_is_global(self):
        """Test that the registry is global."""
        register_lazy_commands(
            {"global_cmd": "mod:app"},
            {"global_cmd": "Global help"},
        )

        # Create a new group - should pick up global registry
        group = LazyTyperGroup()

        assert "global_cmd" in group.lazy_subcommands
