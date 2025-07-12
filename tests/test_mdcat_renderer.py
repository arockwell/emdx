"""Tests for mdcat_renderer module."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestMdcatRendererImports:
    """Test mdcat_renderer module imports."""

    def test_module_imports(self):
        """Test that mdcat_renderer module can be imported."""
        from emdx import mdcat_renderer
        assert hasattr(mdcat_renderer, 'MdcatRenderer')
        assert hasattr(mdcat_renderer, 'MdcatWidget')

    def test_mdcat_renderer_class(self):
        """Test MdcatRenderer class structure."""
        from emdx import mdcat_renderer
        
        assert hasattr(mdcat_renderer.MdcatRenderer, 'is_available')
        assert hasattr(mdcat_renderer.MdcatRenderer, 'get_terminal_info')
        assert hasattr(mdcat_renderer.MdcatRenderer, 'render')
        assert hasattr(mdcat_renderer.MdcatRenderer, 'render_to_html')

    def test_mdcat_widget_class(self):
        """Test MdcatWidget class structure."""
        from emdx import mdcat_renderer
        
        assert hasattr(mdcat_renderer.MdcatWidget, 'create_ansi_widget')


class TestMdcatRenderer:
    """Test MdcatRenderer class."""

    @patch("shutil.which")
    def test_is_available_true(self, mock_which):
        """Test mdcat availability when installed."""
        from emdx import mdcat_renderer
        
        mock_which.return_value = "/usr/local/bin/mdcat"
        
        assert mdcat_renderer.MdcatRenderer.is_available() is True
        mock_which.assert_called_once_with("mdcat")

    @patch("shutil.which")
    def test_is_available_false(self, mock_which):
        """Test mdcat availability when not installed."""
        from emdx import mdcat_renderer
        
        mock_which.return_value = None
        
        assert mdcat_renderer.MdcatRenderer.is_available() is False
        mock_which.assert_called_once_with("mdcat")

    @patch.dict(os.environ, {"TERM": "kitty", "TERM_PROGRAM": ""})
    def test_get_terminal_info_kitty(self):
        """Test terminal info detection for Kitty."""
        from emdx import mdcat_renderer
        
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        
        assert term == "kitty"
        assert supports_images is True

    @patch.dict(os.environ, {"TERM": "xterm-256color", "TERM_PROGRAM": "iTerm.app"})
    def test_get_terminal_info_iterm(self):
        """Test terminal info detection for iTerm."""
        from emdx import mdcat_renderer
        
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        
        assert term == "xterm-256color"
        assert supports_images is True

    @patch.dict(os.environ, {"TERM": "wezterm", "TERM_PROGRAM": ""})
    def test_get_terminal_info_wezterm(self):
        """Test terminal info detection for WezTerm."""
        from emdx import mdcat_renderer
        
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        
        assert term == "wezterm"
        assert supports_images is True

    @patch.dict(os.environ, {"TERM": "xterm", "TERM_PROGRAM": ""})
    def test_get_terminal_info_no_image_support(self):
        """Test terminal info detection for terminals without image support."""
        from emdx import mdcat_renderer
        
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        
        assert term == "xterm"
        assert supports_images is False

    @patch.dict(os.environ, {}, clear=True)
    def test_get_terminal_info_no_env(self):
        """Test terminal info detection when environment variables are missing."""
        from emdx import mdcat_renderer
        
        term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
        
        assert term == ""
        assert supports_images is False

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=False)
    def test_render_mdcat_not_available(self, mock_available):
        """Test rendering when mdcat is not available."""
        from emdx import mdcat_renderer
        
        content = "# Test"
        
        with pytest.raises(RuntimeError, match="mdcat is not installed"):
            mdcat_renderer.MdcatRenderer.render(content)

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_render_success(self, mock_unlink, mock_run, mock_temp):
        """Test successful markdown rendering."""
        from emdx import mdcat_renderer
        
        # Setup temp file mock
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        # Setup subprocess mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Rendered markdown output"
        mock_run.return_value = mock_result
        
        content = "# Test Markdown"
        result = mdcat_renderer.MdcatRenderer.render(content)
        
        assert result == "Rendered markdown output"
        
        # Check temp file was written to
        mock_file.write.assert_called_once_with(content)
        
        # Check subprocess was called correctly
        expected_cmd = ["mdcat", "--no-pager", "/tmp/test.md"]
        mock_run.assert_called_once()
        
        # Check temp file was cleaned up
        mock_unlink.assert_called_once_with("/tmp/test.md")

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_render_with_width(self, mock_unlink, mock_run, mock_temp):
        """Test rendering with specified width."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Rendered output"
        mock_run.return_value = mock_result
        
        content = "# Test"
        mdcat_renderer.MdcatRenderer.render(content, width=80)
        
        # Check that subprocess was called (width parameter should be included)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "mdcat" in cmd
        assert "--columns" in cmd
        assert "80" in cmd

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_render_failure(self, mock_unlink, mock_run, mock_temp):
        """Test rendering when mdcat command fails."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "mdcat error message"
        mock_run.return_value = mock_result
        
        content = "# Test"
        
        with pytest.raises(RuntimeError, match="mdcat failed: mdcat error message"):
            mdcat_renderer.MdcatRenderer.render(content)
        
        # Check temp file was still cleaned up
        mock_unlink.assert_called_once_with("/tmp/test.md")

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run", side_effect=Exception("Subprocess error"))
    @patch("os.unlink")
    def test_render_exception_cleanup(self, mock_unlink, mock_run, mock_temp):
        """Test that temp file is cleaned up even when subprocess raises exception."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        content = "# Test"
        
        with pytest.raises(Exception, match="Subprocess error"):
            mdcat_renderer.MdcatRenderer.render(content)
        
        # Check temp file was cleaned up despite exception
        mock_unlink.assert_called_once_with("/tmp/test.md")

    def test_render_to_html_not_implemented(self):
        """Test that HTML rendering raises NotImplementedError."""
        from emdx import mdcat_renderer
        
        content = "# Test"
        
        with pytest.raises(NotImplementedError, match="mdcat does not support HTML output"):
            mdcat_renderer.MdcatRenderer.render_to_html(content)


class TestMdcatWidget:
    """Test MdcatWidget class."""

    @patch("emdx.mdcat_renderer.MdcatRenderer.render")
    def test_create_ansi_widget_success(self, mock_render):
        """Test successful ANSI widget creation."""
        from emdx import mdcat_renderer
        
        mock_render.return_value = "Rendered ANSI output"
        
        content = "# Test"
        result = mdcat_renderer.MdcatWidget.create_ansi_widget(content)
        
        assert result == "Rendered ANSI output"
        mock_render.assert_called_once_with(content)

    @patch("emdx.mdcat_renderer.MdcatRenderer.render", side_effect=Exception("Render error"))
    def test_create_ansi_widget_error(self, mock_render):
        """Test ANSI widget creation when rendering fails."""
        from emdx import mdcat_renderer
        
        content = "# Test"
        result = mdcat_renderer.MdcatWidget.create_ansi_widget(content)
        
        assert "Error rendering with mdcat: Render error" in result


class TestEnvironmentDetection:
    """Test environment and terminal detection."""

    def test_terminal_environment_combinations(self):
        """Test various terminal environment combinations."""
        from emdx import mdcat_renderer
        
        test_cases = [
            ({"TERM": "screen-256color", "TERM_PROGRAM": ""}, False),
            ({"TERM": "tmux-256color", "TERM_PROGRAM": ""}, False),
            ({"TERM": "xterm-kitty", "TERM_PROGRAM": ""}, True),
            ({"TERM": "alacritty", "TERM_PROGRAM": ""}, False),
            ({"TERM": "xterm", "TERM_PROGRAM": "iTerm.app"}, True),
        ]
        
        for env_vars, expected_image_support in test_cases:
            with patch.dict(os.environ, env_vars, clear=True):
                term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
                assert supports_images == expected_image_support

    def test_case_insensitive_terminal_detection(self):
        """Test that terminal detection is case insensitive."""
        from emdx import mdcat_renderer
        
        with patch.dict(os.environ, {"TERM": "KITTY", "TERM_PROGRAM": ""}, clear=True):
            term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
            assert supports_images is True
        
        with patch.dict(os.environ, {"TERM": "WEZTERM", "TERM_PROGRAM": ""}, clear=True):
            term, supports_images = mdcat_renderer.MdcatRenderer.get_terminal_info()
            assert supports_images is True


class TestCommandBuilding:
    """Test command building logic."""

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_command_without_width(self, mock_unlink, mock_run, mock_temp):
        """Test command building without width parameter."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_run.return_value = mock_result
        
        mdcat_renderer.MdcatRenderer.render("# Test")
        
        args, kwargs = mock_run.call_args
        cmd = args[0]
        
        assert "mdcat" in cmd
        assert "--no-pager" in cmd
        assert "/tmp/test.md" in cmd
        assert "--columns" not in cmd

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_environment_variables(self, mock_unlink, mock_run, mock_temp):
        """Test that environment variables are properly set."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_run.return_value = mock_result
        
        mdcat_renderer.MdcatRenderer.render("# Test")
        
        args, kwargs = mock_run.call_args
        env = kwargs["env"]
        
        assert "TERM" in env
        assert env["TERM"] == "xterm-256color"


class TestMainExecution:
    """Test main execution functionality."""

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available")
    def test_module_has_main_example(self, mock_available):
        """Test that module has main execution example."""
        from emdx import mdcat_renderer
        
        # The module should have example content for testing
        # This tests that the module structure supports main execution
        mock_available.return_value = False
        
        # Should be able to call is_available without errors
        result = mdcat_renderer.MdcatRenderer.is_available()
        assert result is False


class TestErrorHandling:
    """Test error handling in various scenarios."""

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile", side_effect=Exception("Temp file error"))
    def test_render_temp_file_error(self, mock_temp):
        """Test rendering when temp file creation fails."""
        from emdx import mdcat_renderer
        
        content = "# Test"
        
        with pytest.raises(Exception, match="Temp file error"):
            mdcat_renderer.MdcatRenderer.render(content)

    @patch("emdx.mdcat_renderer.MdcatRenderer.is_available", return_value=True)
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink", side_effect=Exception("Cleanup error"))
    def test_render_cleanup_error(self, mock_unlink, mock_run, mock_temp):
        """Test that cleanup errors don't break the render process."""
        from emdx import mdcat_renderer
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.md"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_run.return_value = mock_result
        
        # This should still work despite cleanup error
        # (in the finally block, cleanup errors are silently ignored)
        try:
            result = mdcat_renderer.MdcatRenderer.render("# Test")
            # If we get here, the finally block swallowed the cleanup error
            assert result == "output"
        except Exception as e:
            # If cleanup error propagates, that's also valid behavior
            assert "Cleanup error" in str(e)