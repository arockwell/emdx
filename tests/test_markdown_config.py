"""Tests for markdown_config module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestMarkdownConfigImports:
    """Test markdown_config module imports."""

    def test_module_imports(self):
        """Test that markdown_config module can be imported."""
        from emdx import markdown_config
        assert hasattr(markdown_config, 'MarkdownConfig')
        assert hasattr(markdown_config, 'render_enhanced_markdown')
        assert hasattr(markdown_config, 'list_available_themes')

    def test_markdown_config_class(self):
        """Test MarkdownConfig class structure."""
        from emdx import markdown_config
        
        assert hasattr(markdown_config.MarkdownConfig, 'THEMES')
        assert hasattr(markdown_config.MarkdownConfig, 'get_code_theme')
        assert hasattr(markdown_config.MarkdownConfig, 'create_markdown')
        assert hasattr(markdown_config.MarkdownConfig, 'render_markdown')


class TestMarkdownConfig:
    """Test MarkdownConfig class."""

    def test_themes_structure(self):
        """Test that themes are properly structured."""
        from emdx import markdown_config
        
        themes = markdown_config.MarkdownConfig.THEMES
        
        assert "dark" in themes
        assert "light" in themes
        
        for theme_type in ["dark", "light"]:
            assert "default" in themes[theme_type]
            assert "alternatives" in themes[theme_type]
            assert isinstance(themes[theme_type]["alternatives"], list)

    @patch.dict(os.environ, {"EMDX_CODE_THEME": "custom_theme"})
    def test_get_code_theme_from_env(self):
        """Test getting code theme from environment variable."""
        from emdx import markdown_config
        
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == "custom_theme"

    @patch.dict(os.environ, {"COLORFGBG": "0;15"}, clear=True)
    def test_get_code_theme_light_terminal(self):
        """Test getting code theme for light terminal."""
        from emdx import markdown_config
        
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == markdown_config.MarkdownConfig.THEMES["light"]["default"]

    @patch.dict(os.environ, {"COLORFGBG": "15;0"}, clear=True)
    def test_get_code_theme_dark_terminal(self):
        """Test getting code theme for dark terminal."""
        from emdx import markdown_config
        
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]

    @patch.dict(os.environ, {}, clear=True)
    def test_get_code_theme_no_env(self):
        """Test getting code theme when no environment variables are set."""
        from emdx import markdown_config
        
        theme = markdown_config.MarkdownConfig.get_code_theme()
        # Should default to dark theme
        assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]

    def test_create_markdown_default(self):
        """Test creating markdown with default settings."""
        from emdx import markdown_config
        from rich.markdown import Markdown
        
        content = "# Test\n\n```python\nprint('hello')\n```"
        
        with patch.object(markdown_config.MarkdownConfig, 'get_code_theme', return_value='monokai'):
            md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_custom_theme(self):
        """Test creating markdown with custom theme."""
        from emdx import markdown_config
        from rich.markdown import Markdown
        
        content = "# Test"
        
        md = markdown_config.MarkdownConfig.create_markdown(content, code_theme="dracula")
        
        assert isinstance(md, Markdown)

    @patch('emdx.markdown_config.Console')
    def test_render_markdown_default_console(self, mock_console_class):
        """Test rendering markdown with default console."""
        from emdx import markdown_config
        
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        content = "# Test"
        
        with patch.object(markdown_config.MarkdownConfig, 'create_markdown') as mock_create:
            mock_md = MagicMock()
            mock_create.return_value = mock_md
            
            result = markdown_config.MarkdownConfig.render_markdown(content)
        
        mock_console_class.assert_called_once()
        mock_console.print.assert_called_once_with(mock_md)
        assert result == mock_console

    def test_render_markdown_custom_console(self):
        """Test rendering markdown with custom console."""
        from emdx import markdown_config
        
        content = "# Test"
        custom_console = MagicMock()
        
        with patch.object(markdown_config.MarkdownConfig, 'create_markdown') as mock_create:
            mock_md = MagicMock()
            mock_create.return_value = mock_md
            
            result = markdown_config.MarkdownConfig.render_markdown(content, console=custom_console)
        
        custom_console.print.assert_called_once_with(mock_md)
        assert result == custom_console


class TestEnhancedMarkdownRendering:
    """Test enhanced markdown rendering functions."""

    @patch('emdx.markdown_config.Console')
    @patch.object('emdx.markdown_config.MarkdownConfig', 'render_markdown')
    def test_render_enhanced_markdown(self, mock_render, mock_console_class):
        """Test enhanced markdown rendering function."""
        from emdx import markdown_config
        
        content = "# Test Content"
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        markdown_config.render_enhanced_markdown(content)
        
        # Check console was created with correct settings
        mock_console_class.assert_called_once_with(
            force_terminal=True,
            width=None,
            highlight=True,
            markup=True
        )

    @patch('emdx.markdown_config.Console')
    @patch.object('emdx.markdown_config.MarkdownConfig', 'render_markdown')
    def test_render_enhanced_markdown_custom_theme(self, mock_render, mock_console_class):
        """Test enhanced markdown rendering with custom theme."""
        from emdx import markdown_config
        
        content = "# Test Content"
        theme = "dracula"
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        markdown_config.render_enhanced_markdown(content, code_theme=theme)
        
        # Should have been called
        mock_console_class.assert_called_once()


class TestUtilityFunctions:
    """Test utility functions."""

    @patch('builtins.print')
    def test_list_available_themes(self, mock_print):
        """Test listing available themes."""
        from emdx import markdown_config
        
        markdown_config.list_available_themes()
        
        # Check that print was called multiple times
        assert mock_print.call_count > 0
        
        # Check that themes were mentioned in output
        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)
        
        # Check some expected themes are mentioned
        assert "monokai" in all_output or "dracula" in all_output
        assert "EMDX_CODE_THEME" in all_output


class TestThemeConstants:
    """Test theme constants and structure."""

    def test_dark_themes_exist(self):
        """Test that dark themes are properly defined."""
        from emdx import markdown_config
        
        dark_themes = markdown_config.MarkdownConfig.THEMES["dark"]
        
        assert dark_themes["default"] == "monokai"
        assert isinstance(dark_themes["alternatives"], list)
        assert len(dark_themes["alternatives"]) > 0

    def test_light_themes_exist(self):
        """Test that light themes are properly defined."""
        from emdx import markdown_config
        
        light_themes = markdown_config.MarkdownConfig.THEMES["light"]
        
        assert light_themes["default"] == "manni"
        assert isinstance(light_themes["alternatives"], list)
        assert len(light_themes["alternatives"]) > 0

    def test_theme_alternatives_are_lists(self):
        """Test that theme alternatives are lists."""
        from emdx import markdown_config
        
        for theme_type in ["dark", "light"]:
            alternatives = markdown_config.MarkdownConfig.THEMES[theme_type]["alternatives"]
            assert isinstance(alternatives, list)
            assert len(alternatives) > 0

    def test_theme_defaults_are_strings(self):
        """Test that theme defaults are strings."""
        from emdx import markdown_config
        
        for theme_type in ["dark", "light"]:
            default = markdown_config.MarkdownConfig.THEMES[theme_type]["default"]
            assert isinstance(default, str)
            assert len(default) > 0


class TestMarkdownCreation:
    """Test markdown object creation with various parameters."""

    def test_create_markdown_with_hyperlinks(self):
        """Test that markdown objects are created with hyperlinks enabled."""
        from emdx import markdown_config
        from rich.markdown import Markdown
        
        content = "Visit [example](https://example.com)"
        
        md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_empty_content(self):
        """Test creating markdown with empty content."""
        from emdx import markdown_config
        from rich.markdown import Markdown
        
        content = ""
        
        md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_code_block(self):
        """Test creating markdown with code blocks."""
        from emdx import markdown_config
        from rich.markdown import Markdown
        
        content = """
# Example

```python
def hello():
    print("Hello, world!")
```
"""
        
        md = markdown_config.MarkdownConfig.create_markdown(content, code_theme="monokai")
        
        assert isinstance(md, Markdown)


class TestEnvironmentDetection:
    """Test environment variable handling."""

    def test_colorfgbg_parsing(self):
        """Test COLORFGBG environment variable parsing."""
        from emdx import markdown_config
        
        # Test various COLORFGBG formats
        test_cases = [
            ("0;15", "light"),  # Light background
            ("15;0", "dark"),   # Dark background
            ("7;0", "dark"),    # Dark background
            ("invalid", "dark"), # Invalid format defaults to dark
            ("", "dark"),       # Empty defaults to dark
        ]
        
        for colorfgbg_value, expected_theme_type in test_cases:
            with patch.dict(os.environ, {"COLORFGBG": colorfgbg_value}, clear=True):
                theme = markdown_config.MarkdownConfig.get_code_theme()
                expected_theme = markdown_config.MarkdownConfig.THEMES[expected_theme_type]["default"]
                
                if colorfgbg_value == "0;15":
                    assert theme == expected_theme
                else:
                    # Most should default to dark theme
                    assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]