"""Unit tests for vim-style relative line numbers logic."""

import pytest


def calculate_vim_line_numbers(current_line, total_lines):
    """Pure function to calculate vim-style line numbers.
    
    This matches the logic in SimpleVimLineNumbers.set_line_numbers()
    """
    lines = []
    for i in range(total_lines):
        if i == current_line:
            # Current line shows absolute number (1-based)
            lines.append(f"{i+1:>3}")
        else:
            # Other lines show distance from current line
            distance = abs(i - current_line)
            lines.append(f"{distance:>3}")
    return lines


class TestVimLineNumbers:
    """Test vim-style relative line number calculation."""
    
    def test_cursor_on_first_line(self):
        """Test cursor on first line of a 3-line file."""
        result = calculate_vim_line_numbers(current_line=0, total_lines=3)
        expected = ["  1", "  1", "  2"]  # Current=1, then distances 1,2
        assert result == expected
    
    def test_cursor_on_middle_line(self):
        """Test cursor on middle line of a 3-line file."""
        result = calculate_vim_line_numbers(current_line=1, total_lines=3)
        expected = ["  1", "  2", "  1"]  # Distance 1, Current=2, Distance 1
        assert result == expected
    
    def test_cursor_on_last_line(self):
        """Test cursor on last line of a 3-line file."""
        result = calculate_vim_line_numbers(current_line=2, total_lines=3)
        expected = ["  2", "  1", "  3"]  # Distance 2, Distance 1, Current=3
        assert result == expected
    
    def test_single_line_file(self):
        """Test single line file."""
        result = calculate_vim_line_numbers(current_line=0, total_lines=1)
        expected = ["  1"]  # Just current line
        assert result == expected
    
    def test_empty_file(self):
        """Test edge case of empty file."""
        result = calculate_vim_line_numbers(current_line=0, total_lines=0)
        expected = []
        assert result == expected
    
    def test_four_line_file_all_positions(self):
        """Test all cursor positions in a 4-line file (matches user's issue)."""
        expected_results = {
            0: ["  1", "  1", "  2", "  3"],  # Cursor on line 0
            1: ["  1", "  2", "  1", "  2"],  # Cursor on line 1
            2: ["  2", "  1", "  3", "  1"],  # Cursor on line 2
            3: ["  3", "  2", "  1", "  4"],  # Cursor on line 3
        }
        
        for cursor_pos in range(4):
            result = calculate_vim_line_numbers(current_line=cursor_pos, total_lines=4)
            expected = expected_results[cursor_pos]
            assert result == expected, f"Failed for cursor position {cursor_pos}"
    
    def test_current_line_uniqueness(self):
        """Test that exactly one line shows the current line's absolute number."""
        for total_lines in range(1, 10):
            for cursor_pos in range(total_lines):
                result = calculate_vim_line_numbers(current_line=cursor_pos, total_lines=total_lines)
                
                # The current line should show its absolute number
                expected_current_line_number = f"{cursor_pos+1:>3}"
                current_line_display = result[cursor_pos]
                
                assert current_line_display == expected_current_line_number, \
                    f"Line {cursor_pos} should show '{expected_current_line_number}', got '{current_line_display}'"
                
                # All other lines should show distances (not their absolute numbers)
                for i in range(total_lines):
                    if i != cursor_pos:
                        line_display = result[i]
                        expected_distance = abs(i - cursor_pos)
                        expected_distance_str = f"{expected_distance:>3}"
                        
                        assert line_display == expected_distance_str, \
                            f"Line {i} should show distance '{expected_distance_str}', got '{line_display}'"
    
    def test_distance_calculation(self):
        """Test that distances are calculated correctly."""
        cursor_pos = 2  # Middle of 5-line file
        result = calculate_vim_line_numbers(current_line=cursor_pos, total_lines=5)
        
        for i, line_num in enumerate(result):
            if i == cursor_pos:
                # Current line should show absolute number
                expected = f"{i+1:>3}"
                assert line_num == expected
            else:
                # Other lines should show distance
                expected_distance = abs(i - cursor_pos)
                assert line_num.strip() == str(expected_distance), \
                    f"Line {i}: expected distance {expected_distance}, got '{line_num.strip()}'"
    
    def test_formatting_consistency(self):
        """Test that all line numbers have consistent formatting."""
        result = calculate_vim_line_numbers(current_line=5, total_lines=10)
        
        for line_num in result:
            # All should be exactly 3 characters (right-aligned)
            assert len(line_num) == 3, f"Line number '{line_num}' should be 3 chars"
            # Should be right-aligned (spaces on left if needed)
            assert line_num.isdigit() or line_num.startswith(" "), \
                f"Line number '{line_num}' should be right-aligned"


if __name__ == "__main__":
    # Allow running directly for quick testing
    pytest.main([__file__, "-v"])