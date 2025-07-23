"""Test markdown rendering functionality in EMDX."""

import os
from unittest.mock import Mock, patch

import pytest
from rich.console import Console
from rich.markdown import Markdown

from emdx.ui.markdown_config import MarkdownConfig, render_enhanced_markdown


class TestMarkdownConfig:
    """Test markdown configuration and theme selection."""

    def test_get_code_theme_from_env(self):
        """Test getting code theme from environment variable."""
        with patch.dict(os.environ, {"EMDX_CODE_THEME": "monokai"}):
            assert MarkdownConfig.get_code_theme() == "monokai"

    def test_get_code_theme_dark_terminal(self):
        """Test theme selection for dark terminal."""
        with patch.dict(os.environ, {"COLORFGBG": "15;0"}, clear=True):
            # Background is 0 (black), so should get dark theme
            theme = MarkdownConfig.get_code_theme()
            assert theme in MarkdownConfig.THEMES["dark"]["alternatives"] + [
                MarkdownConfig.THEMES["dark"]["default"]
            ]

    def test_get_code_theme_light_terminal(self):
        """Test theme selection for light terminal."""
        with patch.dict(os.environ, {"COLORFGBG": "0;15"}, clear=True):
            # Background is 15 (white), so should get light theme
            assert MarkdownConfig.get_code_theme() == MarkdownConfig.THEMES["light"]["default"]

    def test_get_code_theme_no_env(self):
        """Test theme selection with no environment info."""
        with patch.dict(os.environ, {}, clear=True):
            # Should default to dark theme
            assert MarkdownConfig.get_code_theme() == MarkdownConfig.THEMES["dark"]["default"]

    def test_create_markdown_default_theme(self):
        """Test creating markdown object with default theme."""
        content = "# Test"
        md = MarkdownConfig.create_markdown(content)
        assert isinstance(md, Markdown)
        assert md.markup == content

    def test_create_markdown_custom_theme(self):
        """Test creating markdown object with custom theme."""
        content = "# Test"
        md = MarkdownConfig.create_markdown(content, code_theme="dracula")
        assert isinstance(md, Markdown)
        assert md.code_theme == "dracula"

    def test_render_markdown_default_console(self):
        """Test rendering markdown with default console."""
        content = "# Test"
        with patch("emdx.ui.markdown_config.Console") as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            result = MarkdownConfig.render_markdown(content)

            mock_console.print.assert_called_once()
            assert result == mock_console

    def test_render_markdown_custom_console(self):
        """Test rendering markdown with custom console."""
        content = "# Test"
        mock_console = Mock()

        result = MarkdownConfig.render_markdown(content, console=mock_console)

        mock_console.print.assert_called_once()
        assert result == mock_console


class TestEnhancedMarkdownRendering:
    """Test enhanced markdown rendering function."""

    def test_render_enhanced_markdown_basic(self):
        """Test basic enhanced markdown rendering."""
        content = "# Test Header"
        with patch("emdx.ui.markdown_config.Console") as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            render_enhanced_markdown(content)

            # Verify console was created with correct options
            mock_console_class.assert_called_once_with(
                force_terminal=True, width=None, highlight=True, markup=True
            )
            # Verify markdown was printed
            mock_console.print.assert_called_once()

    def test_render_enhanced_markdown_with_theme(self):
        """Test enhanced markdown rendering with custom theme."""
        content = "```python\nprint('hello')\n```"
        with patch("emdx.ui.markdown_config.Console") as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            render_enhanced_markdown(content, code_theme="dracula")

            mock_console.print.assert_called_once()
            # Verify the Markdown object was created with the theme
            call_args = mock_console.print.call_args[0][0]
            assert isinstance(call_args, Markdown)
            assert call_args.code_theme == "dracula"


class TestMarkdownContentRendering:
    """Test rendering of various markdown content types."""

    @pytest.fixture
    def console(self):
        """Create a test console."""
        return Console(force_terminal=True, width=80, file=Mock())

    def test_render_headers(self, console):
        """Test rendering headers."""
        content = """# Header 1
## Header 2
### Header 3"""
        md = MarkdownConfig.create_markdown(content)
        # Ensure no exceptions during rendering
        console.print(md)

    def test_render_code_blocks(self, console):
        """Test rendering code blocks."""
        content = """```python
def hello():
    print("Hello, World!")
```

```javascript
console.log("Test");
```"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_lists(self, console):
        """Test rendering lists."""
        content = """- Item 1
- Item 2
  - Nested item

1. First
2. Second"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_emphasis(self, console):
        """Test rendering emphasis."""
        content = """**Bold text**
*Italic text*
***Bold and italic***
`inline code`"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_links(self, console):
        """Test rendering links."""
        content = """[Link text](https://example.com)
https://auto-link.com
<email@example.com>"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_tables(self, console):
        """Test rendering tables."""
        content = """| Col1 | Col2 |
|------|------|
| A    | B    |
| C    | D    |"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_blockquotes(self, console):
        """Test rendering blockquotes."""
        content = """> This is a quote
> With multiple lines
>
> > Nested quote"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_mixed_content(self, console):
        """Test rendering mixed content."""
        content = """# Mixed Content Test

This has **bold** and *italic* text.

```python
# Code block
x = 42
```

> A quote with `code`

- List item with [link](https://example.com)"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_unicode_content(self, console):
        """Test rendering unicode content."""
        content = """# Unicode Test

Emojis: 🎯 🚀 ✅ 🏗️
Math: π ≈ ∑
Arrows: → ← ↑ ↓
Languages: 中文 日本語 한국어"""
        md = MarkdownConfig.create_markdown(content)
        console.print(md)

    def test_render_edge_cases(self, console):
        """Test rendering edge cases."""
        # Empty content
        md = MarkdownConfig.create_markdown("")
        console.print(md)

        # Very long line
        long_line = "x" * 200
        md = MarkdownConfig.create_markdown(long_line)
        console.print(md)

        # Malformed markdown
        malformed = "**Unclosed bold"
        md = MarkdownConfig.create_markdown(malformed)
        console.print(md)


class TestThemeAvailability:
    """Test theme availability and listing."""

    def test_themes_structure(self):
        """Test that theme structure is properly defined."""
        assert "dark" in MarkdownConfig.THEMES
        assert "light" in MarkdownConfig.THEMES
        assert "default" in MarkdownConfig.THEMES["dark"]
        assert "alternatives" in MarkdownConfig.THEMES["dark"]
        assert "default" in MarkdownConfig.THEMES["light"]
        assert "alternatives" in MarkdownConfig.THEMES["light"]

    def test_dark_themes(self):
        """Test dark theme availability."""
        dark_themes = MarkdownConfig.THEMES["dark"]
        assert dark_themes["default"] == "monokai"
        assert "dracula" in dark_themes["alternatives"]
        assert "nord" in dark_themes["alternatives"]

    def test_light_themes(self):
        """Test light theme availability."""
        light_themes = MarkdownConfig.THEMES["light"]
        assert light_themes["default"] == "manni"
        assert "tango" in light_themes["alternatives"]
        assert "friendly" in light_themes["alternatives"]

    @patch("builtins.print")
    def test_list_available_themes(self, mock_print):
        """Test listing available themes."""
        from emdx.ui.markdown_config import list_available_themes

        list_available_themes()

        # Verify output structure
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Available code themes:" in call for call in print_calls)
        assert any("For dark terminals:" in call for call in print_calls)
        assert any("For light terminals:" in call for call in print_calls)
        assert any("EMDX_CODE_THEME" in call for call in print_calls)
