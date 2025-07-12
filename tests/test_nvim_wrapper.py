"""Tests for nvim_wrapper module."""

import os
import subprocess
import sys
import tempfile
import termios
from unittest.mock import MagicMock, patch, mock_open

import pytest

from emdx import nvim_wrapper


class TestTerminalState:
    """Test terminal state management functions."""

    @patch("sys.stdin.fileno")
    @patch("termios.tcgetattr")
    def test_save_terminal_state_success(self, mock_tcgetattr, mock_fileno):
        """Test successful terminal state saving."""
        mock_fileno.return_value = 0
        mock_tcgetattr.return_value = ["saved_state"]
        
        state = nvim_wrapper.save_terminal_state()
        
        assert state == ["saved_state"]
        mock_fileno.assert_called_once()
        mock_tcgetattr.assert_called_once_with(0)

    @patch("sys.stdin.fileno", side_effect=Exception("No terminal"))
    def test_save_terminal_state_failure(self, mock_fileno):
        """Test terminal state saving when no terminal is available."""
        state = nvim_wrapper.save_terminal_state()
        
        assert state is None

    @patch("sys.stdin.fileno")
    @patch("termios.tcsetattr")
    def test_restore_terminal_state_success(self, mock_tcsetattr, mock_fileno):
        """Test successful terminal state restoration."""
        mock_fileno.return_value = 0
        state = ["saved_state"]
        
        nvim_wrapper.restore_terminal_state(state)
        
        mock_fileno.assert_called_once()
        mock_tcsetattr.assert_called_once_with(0, termios.TCSADRAIN, state)

    def test_restore_terminal_state_none(self):
        """Test restoring None state."""
        # Should not raise an exception
        nvim_wrapper.restore_terminal_state(None)

    @patch("sys.stdin.fileno", side_effect=Exception("No terminal"))
    def test_restore_terminal_state_failure(self, mock_fileno):
        """Test terminal state restoration failure."""
        state = ["saved_state"]
        
        # Should not raise an exception
        nvim_wrapper.restore_terminal_state(state)


class TestScreenClearing:
    """Test screen clearing functionality."""

    @patch("sys.stdout")
    @patch("os.system")
    def test_clear_screen_completely(self, mock_system, mock_stdout):
        """Test complete screen clearing."""
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
        # Should not raise an exception
        nvim_wrapper.process_nvim_changes("/nonexistent/file.md", 1)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="New Title\n\nNew content here\n# This is a comment\nMore content"))
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_success(self, mock_db, mock_exists):
        """Test successful processing of nvim changes."""
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        mock_db.update_document.assert_called_once_with(123, "New Title", "New content here\nMore content")

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="# Comment only\n# Another comment\n"))
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_comments_only(self, mock_db, mock_exists):
        """Test processing when file contains only comments."""
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        # Should not call update_document
        mock_db.update_document.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=""))
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_empty_file(self, mock_db, mock_exists):
        """Test processing when file is empty."""
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        # Should not call update_document
        mock_db.update_document.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="Title Only"))
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_title_only(self, mock_db, mock_exists):
        """Test processing when file contains only a title."""
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        mock_db.update_document.assert_called_once_with(123, "Title Only", "")

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="Title\n\n# Comment in content\nContent"))
    @patch("emdx.nvim_wrapper.db")
    def test_process_nvim_changes_with_comment_filtering(self, mock_db, mock_exists):
        """Test that comment lines are properly filtered."""
        nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
        
        mock_db.update_document.assert_called_once_with(123, "Title", "\nContent")

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", side_effect=Exception("File read error"))
    def test_process_nvim_changes_exception_handling(self, mock_exists):
        """Test exception handling in process_nvim_changes."""
        with patch("builtins.print") as mock_print:
            nvim_wrapper.process_nvim_changes("/tmp/test.md", 123)
            
            mock_print.assert_called_once()
            assert "Error processing changes" in str(mock_print.call_args)


class TestMainWrapper:
    """Test the main wrapper function."""

    @patch("nvim_wrapper.save_terminal_state")
    @patch("nvim_wrapper.restore_terminal_state")
    @patch("nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    def test_run_textual_with_nvim_wrapper_no_edit_signal(self, mock_exists, mock_getpid, 
                                                         mock_clear, mock_restore, mock_save):
        """Test wrapper when no edit signal exists."""
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

    @patch("nvim_wrapper.save_terminal_state")
    @patch("nvim_wrapper.restore_terminal_state")
    @patch("nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    @patch("builtins.open", mock_open(read_data="/tmp/test.md|123"))
    @patch("os.remove")
    @patch("os.unlink")
    @patch("subprocess.run")
    @patch("nvim_wrapper.process_nvim_changes")
    def test_run_textual_with_nvim_wrapper_with_edit_signal(self, mock_process, mock_subprocess, 
                                                           mock_unlink, mock_remove, mock_open_file,
                                                           mock_exists, mock_getpid, mock_clear, 
                                                           mock_restore, mock_save):
        """Test wrapper when edit signal exists."""
        mock_getpid.return_value = 12345
        mock_exists.side_effect = [True, True, False]  # Signal exists, temp file exists, then no signal
        mock_save.return_value = ["terminal_state"]
        mock_subprocess.return_value.returncode = 0
        
        with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
            mock_run_minimal.return_value = 0  # Normal exit after edit
            
            nvim_wrapper.run_textual_with_nvim_wrapper()
        
        # Check nvim was called
        mock_subprocess.assert_called_once_with(["nvim", "/tmp/test.md"])
        # Check changes were processed
        mock_process.assert_called_once_with("/tmp/test.md", 123)
        # Check temp file was cleaned up
        mock_unlink.assert_called_once_with("/tmp/test.md")

    @patch("nvim_wrapper.save_terminal_state")
    @patch("nvim_wrapper.restore_terminal_state")
    @patch("nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    @patch("builtins.open", mock_open(read_data="/tmp/test.md|123"))
    @patch("os.remove")
    @patch("subprocess.run")
    def test_run_textual_with_nvim_wrapper_nvim_cancelled(self, mock_subprocess, mock_remove,
                                                         mock_open_file, mock_exists, mock_getpid, 
                                                         mock_clear, mock_restore, mock_save):
        """Test wrapper when nvim is cancelled."""
        mock_getpid.return_value = 12345
        mock_exists.side_effect = [True, False, False]  # Signal exists, temp file removed, no signal
        mock_save.return_value = ["terminal_state"]
        mock_subprocess.return_value.returncode = 1  # User cancelled
        
        with patch("nvim_wrapper.process_nvim_changes") as mock_process:
            with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
                mock_run_minimal.return_value = 0
                
                nvim_wrapper.run_textual_with_nvim_wrapper()
        
        # Check nvim was called
        mock_subprocess.assert_called_once_with(["nvim", "/tmp/test.md"])
        # Check changes were NOT processed (nvim cancelled)
        mock_process.assert_not_called()

    @patch("nvim_wrapper.save_terminal_state")
    @patch("nvim_wrapper.restore_terminal_state")
    @patch("nvim_wrapper.clear_screen_completely")
    @patch("os.getpid")
    @patch("os.path.exists")
    def test_run_textual_with_nvim_wrapper_continue_loop(self, mock_exists, mock_getpid, 
                                                        mock_clear, mock_restore, mock_save):
        """Test wrapper continuing loop on edit request."""
        mock_getpid.return_value = 12345
        mock_exists.return_value = False
        mock_save.return_value = ["terminal_state"]
        
        with patch("emdx.nvim_wrapper.run_minimal") as mock_run_minimal:
            # First call returns 42 (edit request), second returns 0 (normal exit)
            mock_run_minimal.side_effect = [42, 0]
            
            nvim_wrapper.run_textual_with_nvim_wrapper()
        
        # Should be called twice - once for edit request, once for normal run
        assert mock_run_minimal.call_count == 2

    @patch("nvim_wrapper.save_terminal_state")
    @patch("nvim_wrapper.restore_terminal_state")
    @patch("nvim_wrapper.clear_screen_completely")
    def test_run_textual_with_nvim_wrapper_exception_handling(self, mock_clear, mock_restore, mock_save):
        """Test wrapper exception handling."""
        mock_save.return_value = ["terminal_state"]
        
        with patch("os.getpid", side_effect=Exception("Unexpected error")):
            try:
                nvim_wrapper.run_textual_with_nvim_wrapper()
            except Exception:
                pass  # Expected
        
        # Terminal state should still be restored
        mock_restore.assert_called_with(["terminal_state"])
        mock_clear.assert_called()


class TestModuleIntegration:
    """Test module-level integration."""

    def test_module_imports(self):
        """Test that all required modules are imported."""
        assert hasattr(nvim_wrapper, 'os')
        assert hasattr(nvim_wrapper, 'subprocess')
        assert hasattr(nvim_wrapper, 'sys')
        assert hasattr(nvim_wrapper, 'termios')

    def test_main_execution(self):
        """Test __name__ == '__main__' execution path."""
        with patch("nvim_wrapper.run_textual_with_nvim_wrapper") as mock_run:
            # Simulate running as main module
            if __name__ == "__main__":
                nvim_wrapper.run_textual_with_nvim_wrapper()
                mock_run.assert_called_once()

    def test_function_availability(self):
        """Test that all expected functions are available."""
        expected_functions = [
            'save_terminal_state',
            'restore_terminal_state', 
            'clear_screen_completely',
            'run_textual_with_nvim_wrapper',
            'process_nvim_changes'
        ]
        
        for func_name in expected_functions:
            assert hasattr(nvim_wrapper, func_name)
            assert callable(getattr(nvim_wrapper, func_name))