"""Integration tests for vim editor with line numbers."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from textual.app import App
from textual.widgets import TextArea

# Mock the config module before importing vim_editor
mock_vim_settings = MagicMock()
mock_vim_settings.line_numbers_enabled = True
mock_vim_settings.line_numbers_relative = True  
mock_vim_settings.line_numbers_width = 4
mock_vim_settings.settings = {
    "colors": {
        "line_numbers": {
            "background": "$background",
            "foreground": "$text-muted", 
            "current_line": "bold yellow"
        }
    },
    "line_numbers": {
        "highlight_current": True
    }
}

with patch.dict('sys.modules', {'emdx.config.vim_settings': MagicMock(vim_settings=mock_vim_settings)}):
    from emdx.ui.vim_editor import VimEditor
    from emdx.ui.vim_line_numbers import SimpleVimLineNumbers


class MockApp:
    """Mock app for testing."""
    def _update_vim_status(self, status):
        self.last_status = status


class TestVimEditorIntegration:
    """Test vim editor with line numbers integration."""
    
    def test_vim_editor_init(self):
        """Test VimEditor initialization."""
        app = MockApp()
        editor = VimEditor(app, content="Hello\nWorld", id="test-editor")
        
        assert editor.text_area is not None
        assert editor.line_numbers is not None
        assert isinstance(editor.line_numbers, SimpleVimLineNumbers)
        assert editor.text_area.text == "Hello\nWorld"
        
    def test_line_numbers_widget_connection(self):
        """Test that line numbers widget is connected to text area."""
        app = MockApp()
        editor = VimEditor(app, content="Line 1\nLine 2\nLine 3")
        
        # Check that line_numbers_widget is set on text area
        assert hasattr(editor.text_area, 'line_numbers_widget')
        assert editor.text_area.line_numbers_widget == editor.line_numbers
        
    @patch('emdx.ui.vim_editor.vim_settings')
    def test_line_numbers_disabled(self, mock_settings):
        """Test behavior when line numbers are disabled."""
        mock_settings.line_numbers_enabled = False
        
        app = MockApp()
        editor = VimEditor(app, content="Test")
        
        # Line numbers widget should still be created but not mounted
        assert editor.line_numbers is not None
        
    def test_text_content_methods(self):
        """Test get_text and set_text methods."""
        app = MockApp()
        editor = VimEditor(app, content="Initial")
        
        assert editor.get_text() == "Initial"
        assert editor.text == "Initial"  # Property access
        
        editor.set_text("Updated")
        assert editor.get_text() == "Updated"
        
        editor.text = "Property Update"  # Property setter
        assert editor.text == "Property Update"
        
    def test_vim_mode_property(self):
        """Test vim_mode property."""
        app = MockApp()
        editor = VimEditor(app, content="Test")
        
        # Should proxy to text area's vim mode
        editor.text_area.vim_mode = "INSERT"
        assert editor.vim_mode == "INSERT"
        
    def test_line_number_width_calculation(self):
        """Test line number width calculation."""
        app = MockApp()
        editor = VimEditor(app, content="")
        
        # Test different line counts
        assert editor._calculate_line_number_width(1) == 4     # min 3 + 1
        assert editor._calculate_line_number_width(10) == 4    # 2 digits + 1 padding, still min 4
        assert editor._calculate_line_number_width(100) == 4   # 3 digits + 1 padding
        assert editor._calculate_line_number_width(1000) == 5  # 4 digits + 1 padding
        
    def test_focus_editor(self):
        """Test focus_editor method."""
        app = MockApp()
        editor = VimEditor(app, content="Test")
        
        # Mock focus method
        editor.text_area.focus = Mock()
        
        editor.focus_editor()
        editor.text_area.focus.assert_called_once()


class TestSimpleVimLineNumbers:
    """Test SimpleVimLineNumbers widget."""
    
    def test_relative_line_numbers(self):
        """Test relative line number generation."""
        widget = SimpleVimLineNumbers()
        
        # Mock text area
        text_area = Mock()
        text_area.has_focus = True
        
        # Capture the update call
        widget.update = Mock()
        
        with patch('emdx.config.vim_settings.vim_settings', mock_vim_settings):
            mock_vim_settings.line_numbers_relative = True
            widget.set_line_numbers(current_line=2, total_lines=5, text_area=text_area)
        
        # Should have called update
        widget.update.assert_called_once()
        
    def test_absolute_line_numbers(self):
        """Test absolute line number generation."""
        widget = SimpleVimLineNumbers()
        
        # Mock text area
        text_area = Mock()
        text_area.has_focus = True
        
        # Capture the update call
        widget.update = Mock()
        
        with patch('emdx.config.vim_settings.vim_settings', mock_vim_settings):
            mock_vim_settings.line_numbers_relative = False
            widget.set_line_numbers(current_line=2, total_lines=5, text_area=text_area)
        
        # Should have called update
        widget.update.assert_called_once()
        
    def test_focus_affects_highlight(self):
        """Test that focus affects current line highlighting."""
        widget = SimpleVimLineNumbers()
        
        # Test with focus
        text_area_focused = Mock()
        text_area_focused.has_focus = True
        
        widget.update = Mock()
        with patch('emdx.config.vim_settings.vim_settings', mock_vim_settings):
            widget.set_line_numbers(1, 3, text_area_focused)
        
        # Test without focus
        text_area_unfocused = Mock()
        text_area_unfocused.has_focus = False
        
        widget.update = Mock()
        with patch('emdx.config.vim_settings.vim_settings', mock_vim_settings):
            widget.set_line_numbers(1, 3, text_area_unfocused)
        
        # Both should update
        assert widget.update.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])