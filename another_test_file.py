#!/usr/bin/env python3
"""
Another test file to create more git changes for testing.
"""

def test_git_diff_browser():
    """Test function for git diff browser functionality."""
    print("Testing git diff browser!")
    print("This file should appear in the git diff browser")
    
    # Test different types of changes
    changes = [
        "New file",
        "Modified content", 
        "Staged changes",
        "Unstaged changes"
    ]
    
    for change in changes:
        print(f"Testing: {change}")

if __name__ == "__main__":
    test_git_diff_browser()
