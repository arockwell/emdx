"""Tests for gui module."""

from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestGuiImports:
    """Test GUI module imports."""

    def test_module_imports(self):
        """Test that gui module can be imported."""
        from emdx import gui
        assert hasattr(gui, 'app')
        assert hasattr(gui, 'console')
        assert hasattr(gui, 'gui')

    def test_typer_app_structure(self):
        """Test that Typer app is properly set up."""
        from emdx import gui
        import typer
        
        assert isinstance(gui.app, typer.Typer)

    def test_console_structure(self):
        """Test that Rich console is properly set up."""
        from emdx import gui
        from rich.console import Console
        
        assert isinstance(gui.console, Console)


class TestGuiApp:
    """Test GUI application setup."""

    def test_gui_function_is_callable(self):
        """Test that gui function is callable."""
        from emdx import gui
        
        assert callable(gui.gui)

    def test_gui_function_has_docstring(self):
        """Test that gui function has proper docstring."""
        from emdx import gui
        
        assert gui.gui.__doc__ is not None
        assert "Seamless TUI browser with zero-flash nvim integration." in gui.gui.__doc__

    def test_module_docstring(self):
        """Test that module has proper docstring."""
        from emdx import gui
        
        assert gui.__doc__ is not None
        assert "GUI interface for emdx" in gui.__doc__


class TestGuiCommand:
    """Test GUI command function."""

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    def test_gui_command_success(self, mock_wrapper):
        """Test successful GUI command execution."""
        from emdx import gui
        
        mock_wrapper.return_value = None
        
        # Call the gui function directly
        gui.gui()
        
        mock_wrapper.assert_called_once()

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    def test_gui_command_keyboard_interrupt(self, mock_wrapper):
        """Test GUI command handling KeyboardInterrupt."""
        from emdx import gui
        
        mock_wrapper.side_effect = KeyboardInterrupt()
        
        # Should not raise an exception
        gui.gui()
        
        mock_wrapper.assert_called_once()

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_gui_command_exception(self, mock_console, mock_wrapper):
        """Test GUI command handling general exceptions."""
        from emdx import gui
        
        mock_wrapper.side_effect = Exception("Test error")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_wrapper.assert_called_once()
            mock_console.print.assert_called_once_with("❌ Error: Test error", style="red")
            mock_exit.assert_called_once_with(1)

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_gui_command_runtime_error(self, mock_console, mock_wrapper):
        """Test GUI command handling RuntimeError."""
        from emdx import gui
        
        mock_wrapper.side_effect = RuntimeError("Runtime test error")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once_with("❌ Error: Runtime test error", style="red")
            mock_exit.assert_called_once_with(1)

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_gui_command_value_error(self, mock_console, mock_wrapper):
        """Test GUI command handling ValueError."""
        from emdx import gui
        
        mock_wrapper.side_effect = ValueError("Value test error")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once_with("❌ Error: Value test error", style="red")
            mock_exit.assert_called_once_with(1)


class TestImportHandling:
    """Test import handling in GUI module."""

    def test_import_nvim_wrapper(self):
        """Test that nvim_wrapper can be imported."""
        # This tests that the import in the gui function works
        from emdx.nvim_wrapper import run_textual_with_nvim_wrapper
        assert callable(run_textual_with_nvim_wrapper)

    @patch("emdx.gui.run_textual_with_nvim_wrapper", side_effect=ImportError("Module not found"))
    def test_gui_import_error(self, mock_wrapper):
        """Test GUI command handling import errors."""
        from emdx import gui
        
        with patch("emdx.gui.console") as mock_console:
            with patch("typer.Exit") as mock_exit:
                gui.gui()
                
                mock_console.print.assert_called_once()
                error_message = str(mock_console.print.call_args[0][0])
                assert "Module not found" in error_message
                mock_exit.assert_called_once_with(1)


class TestCommandDecorator:
    """Test command decorator usage."""

    def test_gui_function_has_typer_decorator(self):
        """Test that gui function is properly decorated."""
        from emdx import gui
        
        # Check if the function has been wrapped by typer
        assert hasattr(gui.gui, '__call__')

    def test_typer_app_configuration(self):
        """Test that Typer app is properly configured."""
        from emdx import gui
        
        # Check that the gui function is registered as a command
        commands = gui.app.registered_commands
        assert len(commands) > 0


class TestErrorMessageFormatting:
    """Test error message formatting."""

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_error_message_format(self, mock_console, mock_wrapper):
        """Test that error messages are properly formatted."""
        from emdx import gui
        
        test_error = "This is a test error message"
        mock_wrapper.side_effect = Exception(test_error)
        
        with patch("typer.Exit"):
            gui.gui()
        
        # Check that the error message includes the emoji and styling
        mock_console.print.assert_called_once_with(f"❌ Error: {test_error}", style="red")

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_error_message_with_special_characters(self, mock_console, mock_wrapper):
        """Test error message handling with special characters."""
        from emdx import gui
        
        test_error = "Error with special chars: àáâãäå"
        mock_wrapper.side_effect = Exception(test_error)
        
        with patch("typer.Exit"):
            gui.gui()
        
        expected_message = f"❌ Error: {test_error}"
        mock_console.print.assert_called_once_with(expected_message, style="red")

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_error_message_multiline(self, mock_console, mock_wrapper):
        """Test error message handling with multiline errors."""
        from emdx import gui
        
        test_error = "Line 1\nLine 2\nLine 3"
        mock_wrapper.side_effect = Exception(test_error)
        
        with patch("typer.Exit"):
            gui.gui()
        
        expected_message = f"❌ Error: {test_error}"
        mock_console.print.assert_called_once_with(expected_message, style="red")


class TestModuleStructure:
    """Test module structure and components."""

    def test_module_has_required_attributes(self):
        """Test that module has all required attributes."""
        from emdx import gui
        
        required_attributes = ['app', 'console', 'gui']
        for attr in required_attributes:
            assert hasattr(gui, attr)

    def test_imports_are_correct(self):
        """Test that all imports are working correctly."""
        from emdx import gui
        
        # Test that typer import works
        import typer
        assert isinstance(gui.app, typer.Typer)
        
        # Test that rich console import works
        from rich.console import Console
        assert isinstance(gui.console, Console)

    def test_function_signature(self):
        """Test that gui function has correct signature."""
        from emdx import gui
        import inspect
        
        sig = inspect.signature(gui.gui)
        # Should have no required parameters
        assert len(sig.parameters) == 0


class TestExceptionTypes:
    """Test handling of different exception types."""

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_os_error_handling(self, mock_console, mock_wrapper):
        """Test handling of OS errors."""
        from emdx import gui
        
        mock_wrapper.side_effect = OSError("OS level error")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once()
            error_msg = mock_console.print.call_args[0][0]
            assert "❌ Error: OS level error" == error_msg
            mock_exit.assert_called_once_with(1)

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_file_not_found_error_handling(self, mock_console, mock_wrapper):
        """Test handling of FileNotFoundError."""
        from emdx import gui
        
        mock_wrapper.side_effect = FileNotFoundError("File not found")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once()
            error_msg = mock_console.print.call_args[0][0]
            assert "❌ Error: File not found" == error_msg
            mock_exit.assert_called_once_with(1)

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_permission_error_handling(self, mock_console, mock_wrapper):
        """Test handling of PermissionError."""
        from emdx import gui
        
        mock_wrapper.side_effect = PermissionError("Permission denied")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once()
            error_msg = mock_console.print.call_args[0][0]
            assert "❌ Error: Permission denied" == error_msg
            mock_exit.assert_called_once_with(1)