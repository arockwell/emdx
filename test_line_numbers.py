#!/usr/bin/env python3
"""
Unit test for vim line numbers logic.
Run with: python test_line_numbers.py
"""

def calculate_vim_line_numbers(current_line, total_lines):
    """Pure function to calculate vim-style line numbers."""
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

def test_basic_cases():
    print("Testing basic vim line number cases...")
    
    # Test case 1: Cursor on first line of 3-line file
    result = calculate_vim_line_numbers(current_line=0, total_lines=3)
    expected = ["  1", "  1", "  2"]  # Current=1, then distances 1,2
    print(f"Test 1: {result} == {expected} ? {result == expected}")
    
    # Test case 2: Cursor on middle line of 3-line file  
    result = calculate_vim_line_numbers(current_line=1, total_lines=3)
    expected = ["  1", "  2", "  1"]  # Distance 1, Current=2, Distance 1
    print(f"Test 2: {result} == {expected} ? {result == expected}")
    
    # Test case 3: Cursor on last line of 3-line file
    result = calculate_vim_line_numbers(current_line=2, total_lines=3)
    expected = ["  2", "  1", "  3"]  # Distance 2, Distance 1, Current=3
    print(f"Test 3: {result} == {expected} ? {result == expected}")
    
    # Test case 4: Single line file
    result = calculate_vim_line_numbers(current_line=0, total_lines=1)
    expected = ["  1"]  # Just current line
    print(f"Test 4: {result} == {expected} ? {result == expected}")

def test_small_file_issue():
    print("\nTesting small file cases that showed problems...")
    
    # The exact case from the user's screenshot
    # File with ~4 lines, cursor somewhere
    for cursor_pos in range(4):
        result = calculate_vim_line_numbers(current_line=cursor_pos, total_lines=4)
        print(f"4-line file, cursor on line {cursor_pos}: {result}")
        
        # Verify no duplicates except distance=0 (which should be current line)
        unique_non_current = set()
        current_count = 0
        for i, line_num in enumerate(result):
            if i == cursor_pos:
                # This should be the absolute line number
                expected_abs = f"{i+1:>3}"
                if line_num != expected_abs:
                    print(f"  ERROR: Current line {i} should show '{expected_abs}', got '{line_num}'")
                current_count += 1
            else:
                # This should be a distance
                expected_dist = abs(i - cursor_pos)
                if line_num.strip() != str(expected_dist):
                    print(f"  ERROR: Line {i} should show distance {expected_dist}, got '{line_num}'")
                unique_non_current.add(line_num)
        
        if current_count != 1:
            print(f"  ERROR: Should have exactly 1 current line marker, got {current_count}")

if __name__ == "__main__":
    test_basic_cases()
    test_small_file_issue()
    print("\nDone! Check for any ERROR messages above.")