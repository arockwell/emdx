"""Tests for newly added modules.

Covering: gist, tag_commands, nvim_wrapper, markdown_config, gui.
"""


class TestModuleImports:
    """Test that all the new modules can be imported without errors."""

    def test_gist_import(self):
        """Test that gist module can be imported."""
        from emdx.commands import gist

        assert hasattr(gist, "get_github_auth")
        assert hasattr(gist, "create_gist_with_gh")
        assert hasattr(gist, "sanitize_filename")

    def test_tag_commands_import(self):
        """Test that tag_commands module can be imported."""
        from emdx.commands import tags as tag_commands

        assert hasattr(tag_commands, "app")
        assert hasattr(tag_commands, "tag")
        assert hasattr(tag_commands, "untag")

    def test_nvim_wrapper_import(self):
        """Test that nvim_wrapper module can be imported."""
        from emdx.ui import nvim_wrapper

        assert hasattr(nvim_wrapper, "save_terminal_state")
        assert hasattr(nvim_wrapper, "restore_terminal_state")
        assert hasattr(nvim_wrapper, "run_textual_with_nvim_wrapper")

    def test_markdown_config_import(self):
        """Test that markdown_config module can be imported."""
        from emdx.ui import markdown_config

        assert hasattr(markdown_config, "MarkdownConfig")
        assert hasattr(markdown_config, "render_enhanced_markdown")

    def test_gui_import(self):
        """Test that gui module can be imported."""
        from emdx.ui import gui

        assert hasattr(gui, "app")
        assert hasattr(gui, "gui")


class TestGistBasicFunctionality:
    """Test basic gist functionality."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        from emdx.commands import gist

        # Test normal title
        assert gist.sanitize_filename("My Document") == "My Document.md"

        # Test title with invalid characters
        assert gist.sanitize_filename('File<>:"/\\|?*Name') == "File---------Name.md"


class TestMarkdownConfigBasicFunctionality:
    """Test basic markdown config functionality."""

    def test_themes_structure(self):
        """Test that themes are properly structured."""
        from emdx.ui import markdown_config

        themes = markdown_config.MarkdownConfig.THEMES

        assert "dark" in themes
        assert "light" in themes

        for theme_type in ["dark", "light"]:
            assert "default" in themes[theme_type]
            assert "alternatives" in themes[theme_type]
