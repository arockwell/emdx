#!/usr/bin/env python3
"""
Unit tests for VimEditor component integration.
"""

import pytest
from unittest.mock import Mock, MagicMock

from emdx.ui.vim_editor import VimEditor
from emdx.ui.vim_line_numbers import SimpleVimLineNumbers
from emdx.ui.text_areas import VimEditTextArea


class TestVimEditorUnit:
    """Unit tests for VimEditor component."""
    
    def test_vim_editor_initialization(self):
        """Test that VimEditor initializes with correct components."""
        # Create mock app instance
        mock_app = Mock()
        mock_app.action_save_and_exit_edit = Mock()
        mock_app._update_vim_status = Mock()
        
        # Create vim editor
        editor = VimEditor(mock_app, content="Test content")
        
        # Check basic attributes
        assert editor.app_instance == mock_app
        assert hasattr(editor, 'text_area')
        assert hasattr(editor, 'line_numbers')
        assert hasattr(editor, 'edit_container')
        
        # Check types
        assert isinstance(editor.text_area, VimEditTextArea)
        assert isinstance(editor.line_numbers, SimpleVimLineNumbers)
        
        # Check text area configuration
        assert editor.text_area.show_line_numbers is False  # Using custom vim numbers
        assert editor.text_area.word_wrap is False
        
        # Check that line numbers widget is linked to text area
        assert editor.text_area.line_numbers_widget == editor.line_numbers
    
    def test_vim_editor_text_operations(self):
        """Test text getter/setter methods."""
        mock_app = Mock()
        editor = VimEditor(mock_app, content="Initial text")
        
        # Test getter
        assert editor.get_text() == "Initial text"
        assert editor.text == "Initial text"
        
        # Test setter through method
        editor.set_text("New text")
        assert editor.get_text() == "New text"
        
        # Test setter through property
        editor.text = "Property text"
        assert editor.text == "Property text"
    
    def test_vim_editor_css_defined(self):
        """Test that CSS is properly defined."""
        # Check that CSS class variable exists
        assert hasattr(VimEditor, 'CSS')
        css = VimEditor.CSS
        
        # Check key CSS rules are present
        assert "#vim-edit-container" in css
        assert "layout: horizontal" in css
        assert "#vim-line-numbers" in css
        assert "width: 4" in css
        assert "#vim-text-area" in css
        assert "width: 1fr" in css
    
    def test_line_number_width_calculation(self):
        """Test line number width calculation for different document sizes."""
        mock_app = Mock()
        editor = VimEditor(mock_app, content="")
        
        # Test with different line counts
        # Width = max(3, digits) + 1 for padding
        assert editor._calculate_line_number_width(1) == 4     # 1 digit, min 3 + 1 = 4
        assert editor._calculate_line_number_width(9) == 4     # 1 digit, min 3 + 1 = 4
        assert editor._calculate_line_number_width(10) == 4    # 2 digits, min 3 + 1 = 4
        assert editor._calculate_line_number_width(99) == 4    # 2 digits, min 3 + 1 = 4
        assert editor._calculate_line_number_width(100) == 4   # 3 digits, 3 + 1 = 4
        assert editor._calculate_line_number_width(999) == 4   # 3 digits, 3 + 1 = 4
        assert editor._calculate_line_number_width(1000) == 5  # 4 digits, 4 + 1 = 5
    
    def test_vim_editor_compose_yields_container(self):
        """Test that compose method yields the edit container."""
        mock_app = Mock()
        editor = VimEditor(mock_app)
        
        # Get composed widgets
        composed = list(editor.compose())
        
        # Should yield exactly one widget - the edit container
        assert len(composed) == 1
        assert composed[0] == editor.edit_container