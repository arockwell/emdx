"""Tests for nvim_wrapper module."""

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestNvimWrapperImports:
    """Test nvim_wrapper module imports."""

    def test_module_imports(self):
        """Test that nvim_wrapper module can be imported."""
        from emdx import nvim_wrapper
        assert hasattr(nvim_wrapper, 'save_terminal_state')
        assert hasattr(nvim_wrapper, 'restore_terminal_state')
        assert hasattr(nvim_wrapper, 'clear_screen_completely')
        assert hasattr(nvim_wrapper, 'run_textual_with_nvim_wrapper')
        assert hasattr(nvim_wrapper, 'process_nvim_changes')

    def test_all_functions_callable(self):
        """Test that all functions are callable."""
        from emdx import nvim_wrapper
        
        functions = [
            'save_terminal_state',
            'restore_terminal_state', 
            'clear_screen_completely',
            'run_textual_with_nvim_wrapper',
            'process_nvim_changes'
        ]
        
        for func_name in functions:
            assert hasattr(nvim_wrapper, func_name)
            assert callable(getattr(nvim_wrapper, func_name))


class TestTerminalState:
    """Test terminal state management."""

    @patch("sys.stdin.fileno")
    @patch("termios.tcgetattr")
    def test_save_terminal_state_success(self, mock_tcgetattr, mock_fileno):
        """Test successful terminal state saving."""
        from emdx import nvim_wrapper
        
        mock_fileno.return_value = 0
        mock_tcgetattr.return_value = ["saved_state"]
        
        state = nvim_wrapper.save_terminal_state()
        
        assert state == ["saved_state"]
        mock_fileno.assert_called_once()
        mock_tcgetattr.assert_called_once_with(0)

    @patch("sys.stdin.fileno", side_effect=Exception("No terminal"))
    def test_save_terminal_state_failure(self, mock_fileno):
        """Test terminal state saving failure."""
        from emdx import nvim_wrapper
        
        state = nvim_wrapper.save_terminal_state()
        
        assert state is None

    @patch("sys.stdin.fileno")
    @patch("termios.tcsetattr")
    def test_restore_terminal_state_success(self, mock_tcsetattr, mock_fileno):
        """Test successful terminal state restoration."""
        from emdx import nvim_wrapper
        import termios
        
        mock_fileno.return_value = 0
        state = ["saved_state"]
        
        nvim_wrapper.restore_terminal_state(state)
        
        mock_fileno.assert_called_once()
        mock_tcsetattr.assert_called_once_with(0, termios.TCSADRAIN, state)

    def test_restore_terminal_state_none(self):
        """Test restoring None state."""
        from emdx import nvim_wrapper
        
        # Should not raise an exception
        nvim_wrapper.restore_terminal_state(None)

    @patch("sys.stdin.fileno", side_effect=Exception("No terminal"))
    def test_restore_terminal_state_failure(self, mock_fileno):
        """Test terminal state restoration failure."""
        from emdx import nvim_wrapper
        
        state = ["saved_state"]
        
        # Should not raise an exception
        nvim_wrapper.restore_terminal_state(state)


class TestScreenClearing:
    """Test screen clearing functionality."""

    @patch("sys.stdout")
    @patch("os.system")
    def test_clear_screen_completely(self, mock_system, mock_stdout):
        """Test complete screen clearing."""
        from emdx import nvim_wrapper
        
        nvim_wrapper.clear_screen_completely()
        
        # Check ANSI escape sequences were written
        mock_stdout.write.assert_any_call("\033[2J")  # Clear entire screen
        mock_stdout.write.assert_any_call("\033[H")   # Move cursor to home
        mock_stdout.write.assert_any_call("\033[3J")  # Clear scrollback
        mock_stdout.flush.assert_called_once()
        
        # Check system clear was called
        mock_system.assert_called_once_with("clear")


class TestNvimChangesProcessing:
    """Test processing of nvim editing changes."""

    def test_process_nvim_changes_nonexistent_file(self):
        """Test processing when temp file doesn't exist."""
        from emdx import nvim_wrapper
        
        # Should not raise an exception
        nvim_wrapper.process_nvim_changes("/nonexistent/file.md", 1)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open")
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_success(self, mock_db, mock_open, mock_exists):
        """Test successful processing of nvim changes."""
        from emdx import nvim_wrapper
        
        # Mock file content
        mock_open.return_value.__enter__.return_value.readlines.return_value = [
            "New Title\n",
            "\n",
            "New content here\n",
            "# This is a comment\n",
            "More content\n"
        ]
        
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        mock_db.update_document.assert_called_once_with(123, "New Title", "\nNew content here\nMore content")

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open")
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_comments_only(self, mock_db, mock_open, mock_exists):
        """Test processing when file contains only comments."""
        from emdx import nvim_wrapper
        
        mock_open.return_value.__enter__.return_value.readlines.return_value = [
            "# Comment only\n",
            "# Another comment\n"
        ]
        
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        # Should not call update_document
        mock_db.update_document.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open")
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_empty_file(self, mock_db, mock_open, mock_exists):
        """Test processing when file is empty."""
        from emdx import nvim_wrapper
        
        mock_open.return_value.__enter__.return_value.readlines.return_value = []
        
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        # Should not call update_document
        mock_db.update_document.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", side_effect=Exception("File read error"))
    def test_process_nvim_changes_exception_handling(self, mock_open, mock_exists):
        """Test exception handling in process_nvim_changes."""
        from emdx import nvim_wrapper
        
        with patch("builtins.print") as mock_print:
            nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
            
            mock_print.assert_called_once()
            assert "Error processing changes" in str(mock_print.call_args)


class TestMainWrapper:
    """Test the main wrapper function."""

    @patch("emdx.nvim_wrapper.save_terminal_state")
    @patch("emdx.nvim_wrapper.restore_terminal_state")
    @patch("emdx.nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    def test_run_textual_with_nvim_wrapper_no_edit_signal(self, mock_exists, mock_getpid, 
                                                         mock_clear, mock_restore, mock_save):
        """Test wrapper when no edit signal exists."""
        from emdx import nvim_wrapper
        
        mock_getpid.return_value = 12345
        mock_exists.return_value = False
        mock_save.return_value = ["terminal_state"]
        
        with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
            mock_run_minimal.return_value = 0  # Normal exit
            
            nvim_wrapper.run_textual_with_nvim_wrapper()
        
        mock_save.assert_called_once()
        mock_clear.assert_called()
        mock_run_minimal.assert_called_once()
        mock_restore.assert_called()

    @patch("emdx.nvim_wrapper.save_terminal_state")
    @patch("emdx.nvim_wrapper.restore_terminal_state")
    @patch("emdx.nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    def test_run_textual_with_nvim_wrapper_continue_loop(self, mock_exists, mock_getpid, 
                                                        mock_clear, mock_restore, mock_save):
        """Test wrapper continuing loop on edit request."""
        from emdx import nvim_wrapper
        
        mock_getpid.return_value = 12345
        mock_exists.return_value = False
        mock_save.return_value = ["terminal_state"]
        
        with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
            # First call returns 42 (edit request), second returns 0 (normal exit)
            mock_run_minimal.side_effect = [42, 0]
            
            nvim_wrapper.run_textual_with_nvim_wrapper()
        
        # Should be called twice
        assert mock_run_minimal.call_count == 2

    @patch("emdx.nvim_wrapper.save_terminal_state")
    @patch("emdx.nvim_wrapper.restore_terminal_state")
    @patch("emdx.nvim_wrapper.clear_screen_completely")
    def test_run_textual_with_nvim_wrapper_exception_handling(self, mock_clear, mock_restore, mock_save):
        """Test wrapper exception handling."""
        from emdx import nvim_wrapper
        
        mock_save.return_value = ["terminal_state"]
        
        with patch("os.getpid", side_effect=Exception("Unexpected error")):
            try:
                nvim_wrapper.run_textual_with_nvim_wrapper()
            except Exception:
                pass  # Expected
        
        # Terminal state should still be restored
        mock_restore.assert_called_with(["terminal_state"])
        mock_clear.assert_called()


class TestEditSignalHandling:
    """Test edit signal file handling."""

    @patch("emdx.nvim_wrapper.save_terminal_state")
    @patch("emdx.nvim_wrapper.restore_terminal_state")
    @patch("emdx.nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("os.remove")
    @patch("subprocess.run")
    @patch("emdx.nvim_wrapper.process_nvim_changes")
    @patch("os.unlink")
    def test_edit_signal_processing(self, mock_unlink, mock_process, mock_subprocess,
                                   mock_remove, mock_open, mock_exists, mock_getpid,
                                   mock_clear, mock_restore, mock_save):
        """Test processing of edit signal."""
        from emdx import nvim_wrapper
        
        mock_getpid.return_value = 12345
        mock_exists.side_effect = [True, True, False]  # Signal exists, file exists, then no signal
        mock_save.return_value = ["terminal_state"]
        mock_subprocess.return_value.returncode = 0
        
        # Mock file content
        mock_open.return_value.__enter__.return_value.read.return_value = "/tmp/test.md|123"
        
        with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
            mock_run_minimal.return_value = 0
            
            nvim_wrapper.run_textual_with_nvim_wrapper()
        
        # Check edit signal was processed
        mock_remove.assert_called()
        mock_subprocess.assert_called_with(["nvim", "/tmp/test.md"])
        mock_process.assert_called_with("/tmp/test.md", 123)
        mock_unlink.assert_called_with("/tmp/test.md")


class TestModuleStructure:
    """Test module structure and constants."""

    def test_required_imports(self):
        """Test that required modules are imported."""
        from emdx import nvim_wrapper
        
        assert hasattr(nvim_wrapper, 'os')
        assert hasattr(nvim_wrapper, 'subprocess')
        assert hasattr(nvim_wrapper, 'sys')
        assert hasattr(nvim_wrapper, 'termios')

    def test_function_docstrings(self):
        """Test that functions have docstrings."""
        from emdx import nvim_wrapper
        
        functions = [
            'save_terminal_state',
            'restore_terminal_state',
            'clear_screen_completely',
            'run_textual_with_nvim_wrapper',
            'process_nvim_changes'
        ]
        
        for func_name in functions:
            func = getattr(nvim_wrapper, func_name)
            assert func.__doc__ is not None, f"{func_name} should have a docstring"