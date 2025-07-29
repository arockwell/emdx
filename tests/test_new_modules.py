"""Tests for newly added modules.

Covering: gist, tag_commands, textual_browser_minimal, nvim_wrapper,
markdown_config, mdcat_renderer, gui.
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

    def test_textual_browser_minimal_import(self):
        """Test that textual_browser_minimal module can be imported."""
        from emdx.ui import textual_browser as textual_browser_minimal

        assert hasattr(textual_browser_minimal, "FullScreenView")
        assert hasattr(textual_browser_minimal, "MinimalDocumentBrowser")

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

    def test_mdcat_renderer_import(self):
        """Test that mdcat_renderer module can be imported."""
        from emdx.ui import mdcat_renderer

        assert hasattr(mdcat_renderer, "MdcatRenderer")
        assert hasattr(mdcat_renderer, "MdcatWidget")

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


class TestMdcatRendererBasicFunctionality:
    """Test basic mdcat renderer functionality."""

    def test_is_available_callable(self):
        """Test that is_available method is callable."""
        from emdx.ui import mdcat_renderer

        # Should be callable without errors
        result = mdcat_renderer.MdcatRenderer.is_available()
        assert isinstance(result, bool)

    def test_get_terminal_info_callable(self):
        """Test that get_terminal_info method is callable."""
        from emdx.ui import mdcat_renderer

        # Should be callable without errors
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        assert isinstance(term, str)
        assert isinstance(supports_images, bool)
