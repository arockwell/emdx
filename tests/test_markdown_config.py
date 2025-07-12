"""Tests for markdown_config module."""

import os
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.markdown import Markdown

from emdx import markdown_config


class TestMarkdownConfig:
    """Test MarkdownConfig class."""

    def test_themes_structure(self):
        """Test that themes are properly structured."""
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
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == "custom_theme"

    @patch.dict(os.environ, {"COLORFGBG": "0;15"}, clear=True)
    def test_get_code_theme_light_terminal(self):
        """Test getting code theme for light terminal."""
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == markdown_config.MarkdownConfig.THEMES["light"]["default"]

    @patch.dict(os.environ, {"COLORFGBG": "15;0"}, clear=True)
    def test_get_code_theme_dark_terminal(self):
        """Test getting code theme for dark terminal."""
        theme = markdown_config.MarkdownConfig.get_code_theme()
        assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]

    @patch.dict(os.environ, {}, clear=True)
    def test_get_code_theme_no_env(self):
        """Test getting code theme when no environment variables are set."""
        theme = markdown_config.MarkdownConfig.get_code_theme()
        # Should default to dark theme
        assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]

    @patch.dict(os.environ, {"COLORFGBG": "invalid"}, clear=True)
    def test_get_code_theme_invalid_colorfgbg(self):
        """Test getting code theme with invalid COLORFGBG."""
        theme = markdown_config.MarkdownConfig.get_code_theme()
        # Should default to dark theme
        assert theme == markdown_config.MarkdownConfig.THEMES["dark"]["default"]

    def test_create_markdown_default(self):
        """Test creating markdown with default settings."""
        content = "# Test\n\n```python\nprint('hello')\n```"
        
        with patch.object(markdown_config.MarkdownConfig, 'get_code_theme', return_value='monokai'):
            md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_custom_theme(self):
        """Test creating markdown with custom theme."""
        content = "# Test"
        
        md = markdown_config.MarkdownConfig.create_markdown(content, code_theme="dracula")
        
        assert isinstance(md, Markdown)

    @patch('markdown_config.Console')
    def test_render_markdown_default_console(self, mock_console_class):
        """Test rendering markdown with default console."""
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
        content = "# Test"
        custom_console = MagicMock()
        
        with patch.object(markdown_config.MarkdownConfig, 'create_markdown') as mock_create:
            mock_md = MagicMock()
            mock_create.return_value = mock_md
            
            result = markdown_config.MarkdownConfig.render_markdown(content, console=custom_console)
        
        custom_console.print.assert_called_once_with(mock_md)
        assert result == custom_console

    def test_render_markdown_custom_theme(self):
        """Test rendering markdown with custom theme."""
        content = "# Test"
        
        with patch.object(markdown_config.MarkdownConfig, 'create_markdown') as mock_create:
            mock_md = MagicMock()
            mock_create.return_value = mock_md
            
            markdown_config.MarkdownConfig.render_markdown(content, code_theme="nord")
        
        mock_create.assert_called_once_with(content, "nord")


class TestEnhancedMarkdownRendering:
    """Test enhanced markdown rendering functions."""

    @patch('markdown_config.Console')
    @patch.object(markdown_config.MarkdownConfig, 'render_markdown')
    def test_render_enhanced_markdown(self, mock_render, mock_console_class):
        """Test enhanced markdown rendering function."""
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
        
        # Check render_markdown was called
        mock_render.assert_called_once_with(content, mock_console, None)

    @patch('markdown_config.Console')
    @patch.object(markdown_config.MarkdownConfig, 'render_markdown')
    def test_render_enhanced_markdown_custom_theme(self, mock_render, mock_console_class):
        """Test enhanced markdown rendering with custom theme."""
        content = "# Test Content"
        theme = "dracula"
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        markdown_config.render_enhanced_markdown(content, code_theme=theme)
        
        mock_render.assert_called_once_with(content, mock_console, theme)


class TestUtilityFunctions:
    """Test utility functions."""

    @patch('builtins.print')
    def test_list_available_themes(self, mock_print):
        """Test listing available themes."""
        markdown_config.list_available_themes()
        
        # Check that print was called multiple times
        assert mock_print.call_count > 0
        
        # Check that themes were printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)
        
        # Check dark themes are mentioned
        for theme in markdown_config.MarkdownConfig.THEMES["dark"]["alternatives"]:
            assert theme in all_output
        
        # Check light themes are mentioned
        for theme in markdown_config.MarkdownConfig.THEMES["light"]["alternatives"]:
            assert theme in all_output
        
        # Check environment variable instruction is mentioned
        assert "EMDX_CODE_THEME" in all_output


class TestThemeConstants:
    """Test theme constants and structure."""

    def test_dark_themes_exist(self):
        """Test that dark themes are properly defined."""
        dark_themes = markdown_config.MarkdownConfig.THEMES["dark"]
        
        assert dark_themes["default"] == "monokai"
        assert "dracula" in dark_themes["alternatives"]
        assert "nord" in dark_themes["alternatives"]
        assert "one-dark" in dark_themes["alternatives"]
        assert "gruvbox-dark" in dark_themes["alternatives"]

    def test_light_themes_exist(self):
        """Test that light themes are properly defined."""
        light_themes = markdown_config.MarkdownConfig.THEMES["light"]
        
        assert light_themes["default"] == "manni"
        assert "tango" in light_themes["alternatives"]
        assert "perldoc" in light_themes["alternatives"]
        assert "friendly" in light_themes["alternatives"]
        assert "colorful" in light_themes["alternatives"]

    def test_theme_alternatives_are_lists(self):
        """Test that theme alternatives are lists."""
        for theme_type in ["dark", "light"]:
            alternatives = markdown_config.MarkdownConfig.THEMES[theme_type]["alternatives"]
            assert isinstance(alternatives, list)
            assert len(alternatives) > 0

    def test_theme_defaults_are_strings(self):
        """Test that theme defaults are strings."""
        for theme_type in ["dark", "light"]:
            default = markdown_config.MarkdownConfig.THEMES[theme_type]["default"]
            assert isinstance(default, str)
            assert len(default) > 0


class TestMarkdownCreation:
    """Test markdown object creation with various parameters."""

    def test_create_markdown_with_hyperlinks(self):
        """Test that markdown objects are created with hyperlinks enabled."""
        content = "Visit [example](https://example.com)"
        
        md = markdown_config.MarkdownConfig.create_markdown(content)
        
        # This tests that the markdown object is created successfully
        # Rich's Markdown class doesn't expose hyperlinks setting for inspection
        assert isinstance(md, Markdown)

    def test_create_markdown_with_inline_code_lexer(self):
        """Test that markdown objects are created with python inline code lexer."""
        content = "Use `print()` function"
        
        md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_empty_content(self):
        """Test creating markdown with empty content."""
        content = ""
        
        md = markdown_config.MarkdownConfig.create_markdown(content)
        
        assert isinstance(md, Markdown)

    def test_create_markdown_code_block(self):
        """Test creating markdown with code blocks."""
        content = """
# Example

```python
def hello():
    print("Hello, world!")
```
"""
        
        md = markdown_config.MarkdownConfig.create_markdown(content, code_theme="monokai")
        
        assert isinstance(md, Markdown)