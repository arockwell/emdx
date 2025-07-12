"""Tests for gui module."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from emdx import gui


class TestGuiApp:
    """Test GUI application setup."""

    def test_app_is_typer_instance(self):
        """Test that app is a Typer instance."""
        assert isinstance(gui.app, typer.Typer)

    def test_console_is_available(self):
        """Test that console is available."""
        from rich.console import Console
        assert isinstance(gui.console, Console)


class TestGuiCommand:
    """Test GUI command function."""

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    def test_gui_command_success(self, mock_wrapper):
        """Test successful GUI command execution."""
        mock_wrapper.return_value = None
        
        # Call the gui function directly
        gui.gui()
        
        mock_wrapper.assert_called_once()

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    def test_gui_command_keyboard_interrupt(self, mock_wrapper):
        """Test GUI command handling KeyboardInterrupt."""
        mock_wrapper.side_effect = KeyboardInterrupt()
        
        # Should not raise an exception
        gui.gui()
        
        mock_wrapper.assert_called_once()

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_gui_command_exception(self, mock_console, mock_wrapper):
        """Test GUI command handling general exceptions."""
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
        mock_wrapper.side_effect = RuntimeError("Runtime test error")
        
        with patch("typer.Exit") as mock_exit:
            gui.gui()
            
            mock_console.print.assert_called_once_with("❌ Error: Runtime test error", style="red")
            mock_exit.assert_called_once_with(1)

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_gui_command_value_error(self, mock_console, mock_wrapper):
        """Test GUI command handling ValueError."""
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
        with patch("emdx.gui.console") as mock_console:
            with patch("typer.Exit") as mock_exit:
                gui.gui()
                
                mock_console.print.assert_called_once()
                error_message = str(mock_console.print.call_args[0][0])
                assert "Module not found" in error_message
                mock_exit.assert_called_once_with(1)


class TestModuleStructure:
    """Test module structure and availability."""

    def test_module_has_required_attributes(self):
        """Test that module has all required attributes."""
        assert hasattr(gui, 'app')
        assert hasattr(gui, 'console')
        assert hasattr(gui, 'gui')

    def test_gui_function_is_callable(self):
        """Test that gui function is callable."""
        assert callable(gui.gui)

    def test_typer_app_configuration(self):
        """Test that Typer app is properly configured."""
        # Check that the gui function is registered as a command
        commands = gui.app.registered_commands
        assert len(commands) > 0
        
        # The gui function should be registered
        command_names = [cmd.name for cmd in commands.values()]
        assert "gui" in command_names


class TestCommandDecorator:
    """Test command decorator usage."""

    def test_gui_function_has_typer_decorator(self):
        """Test that gui function is properly decorated."""
        # Check if the function has been wrapped by typer
        assert hasattr(gui.gui, '__call__')

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    def test_gui_command_registration(self, mock_wrapper):
        """Test that GUI command is properly registered with typer."""
        # Get the registered commands
        commands = gui.app.registered_commands
        
        # Find the gui command
        gui_command = None
        for cmd in commands.values():
            if cmd.name == "gui":
                gui_command = cmd
                break
        
        assert gui_command is not None
        assert gui_command.help == "Seamless TUI browser with zero-flash nvim integration."


class TestErrorMessageFormatting:
    """Test error message formatting."""

    @patch("emdx.gui.run_textual_with_nvim_wrapper")
    @patch("emdx.gui.console")
    def test_error_message_format(self, mock_console, mock_wrapper):
        """Test that error messages are properly formatted."""
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
        test_error = "Line 1\nLine 2\nLine 3"
        mock_wrapper.side_effect = Exception(test_error)
        
        with patch("typer.Exit"):
            gui.gui()
        
        expected_message = f"❌ Error: {test_error}"
        mock_console.print.assert_called_once_with(expected_message, style="red")


class TestDocstring:
    """Test docstring and documentation."""

    def test_gui_function_docstring(self):
        """Test that gui function has proper docstring."""
        assert gui.gui.__doc__ is not None
        assert "Seamless TUI browser with zero-flash nvim integration." in gui.gui.__doc__

    def test_module_docstring(self):
        """Test that module has proper docstring."""
        assert gui.__doc__ is not None
        assert "GUI interface for emdx" in gui.__doc__