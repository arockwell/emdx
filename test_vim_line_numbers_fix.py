#!/usr/bin/env python3
"""
Test script to verify vim line numbers fix.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'emdx'))

from emdx.ui.text_areas import VimEditTextArea


class TestVimLineNumbers(unittest.TestCase):
    """Test vim line numbers functionality."""

    def setUp(self):
        """Set up test environment."""
        self.app_mock = Mock()
        self.line_numbers_widget = Mock()
        
    def test_get_current_line(self):
        """Test get_current_line method returns correct line number."""
        # Create vim text area with mock cursor position
        vim_area = VimEditTextArea(self.app_mock, text="line 1\nline 2\nline 3")
        vim_area.cursor_location = (1, 0)  # Second line, first column
        
        result = vim_area.get_current_line()
        self.assertEqual(result, 1)
    
    def test_get_current_line_bounds_checking(self):
        """Test get_current_line handles invalid cursor positions."""
        vim_area = VimEditTextArea(self.app_mock, text="line 1\nline 2")
        
        # Test negative cursor position
        vim_area.cursor_location = (-1, 0)
        result = vim_area.get_current_line()
        self.assertEqual(result, -1)  # Should return the raw value
        
        # Test cursor beyond text length
        vim_area.cursor_location = (10, 0)
        result = vim_area.get_current_line()
        self.assertEqual(result, 10)  # Should return the raw value
    
    def test_get_current_line_exception_handling(self):
        """Test get_current_line handles exceptions gracefully."""
        vim_area = VimEditTextArea(self.app_mock, text="test")
        
        # Remove cursor_location to force exception
        del vim_area.cursor_location
        
        result = vim_area.get_current_line()
        self.assertEqual(result, 0)  # Should return safe fallback
    
    def test_update_line_numbers_with_bounds_checking(self):
        """Test _update_line_numbers performs bounds checking."""
        vim_area = VimEditTextArea(self.app_mock, text="line 1\nline 2\nline 3")
        vim_area.line_numbers_widget = self.line_numbers_widget
        vim_area.cursor_location = (5, 0)  # Beyond text bounds
        
        # Call _update_line_numbers
        vim_area._update_line_numbers()
        
        # Verify bounds checking occurred and widget was called with corrected values
        self.line_numbers_widget.set_line_numbers.assert_called_once()
        args = self.line_numbers_widget.set_line_numbers.call_args[0]
        current_line, total_lines = args[0], args[1]
        
        # Should have clamped the line number
        self.assertTrue(current_line < total_lines)
        self.assertEqual(total_lines, 3)
    
    def test_update_line_numbers_no_widget(self):
        """Test _update_line_numbers handles missing widget gracefully."""
        vim_area = VimEditTextArea(self.app_mock, text="test")
        vim_area.cursor_location = (0, 0)
        # No line_numbers_widget set
        
        # Should not crash
        vim_area._update_line_numbers()
    
    def test_update_line_numbers_none_text(self):
        """Test _update_line_numbers handles None text gracefully."""
        vim_area = VimEditTextArea(self.app_mock, text="")
        vim_area.line_numbers_widget = self.line_numbers_widget
        vim_area.cursor_location = (0, 0)
        vim_area.text = None
        
        # Should not crash and should default to 1 line
        vim_area._update_line_numbers()
        
        self.line_numbers_widget.set_line_numbers.assert_called_once()
        args = self.line_numbers_widget.set_line_numbers.call_args[0]
        total_lines = args[1]
        self.assertEqual(total_lines, 1)
    
    def test_cursor_to_end_bounds_checking(self):
        """Test _cursor_to_end handles various text lengths."""
        vim_area = VimEditTextArea(self.app_mock, text="line 1\nline 2\nline 3")
        
        vim_area._cursor_to_end()
        
        # Should move to last line
        self.assertEqual(vim_area.cursor_location[0], 2)  # 0-based, last line is 2
        
        # Test with empty text
        vim_area.text = ""
        vim_area._cursor_to_end()
        self.assertEqual(vim_area.cursor_location, (0, 0))
    
    def test_cursor_watchers_trigger_updates(self):
        """Test that cursor watchers trigger line number updates."""
        vim_area = VimEditTextArea(self.app_mock, text="line 1\nline 2")
        vim_area.line_numbers_widget = self.line_numbers_widget
        
        # Simulate cursor change
        vim_area._on_cursor_changed((0, 0), (1, 0))
        
        # Should have triggered line number update
        self.line_numbers_widget.set_line_numbers.assert_called_once()
        
        # Test text change
        self.line_numbers_widget.reset_mock()
        vim_area._on_text_changed("line 1", "line 1\nline 2")
        
        # Should have triggered line number update
        self.line_numbers_widget.set_line_numbers.assert_called_once()


if __name__ == '__main__':
    unittest.main()