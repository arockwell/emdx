#!/usr/bin/env python3
"""
Apply the mode router refactoring to main_browser.py
"""

import re
from pathlib import Path

def apply_refactoring():
    """Apply the mode router refactoring."""
    
    main_browser = Path("emdx/ui/main_browser.py")
    content = main_browser.read_text()
    
    # Read the new on_key method
    new_on_key = Path("emdx/ui/new_on_key_method.py").read_text()
    
    # Find and replace the on_key method
    # Match from "def on_key" to the next "def" at the same indentation
    pattern = r'(    def on_key\(self, event: events\.Key\) -> None:.*?)(    def )'
    
    # Find the match
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # Replace with new on_key method + the next def
        new_content = content[:match.start(1)] + new_on_key + "\n" + match.group(2) + content[match.end():]
        
        # Write back
        main_browser.write_text(new_content)
        print("✅ Replaced on_key method")
        
        # Count lines saved
        old_lines = match.group(1).count('\n')
        new_lines = new_on_key.count('\n')
        print(f"📉 Reduced from {old_lines} to {new_lines} lines (saved {old_lines - new_lines} lines)")
    else:
        print("❌ Could not find on_key method")
        
    # Now let's also update the action methods to use mode router
    print("\n🔄 Updating action methods to use mode_router...")
    
    # Replace mode transitions
    replacements = [
        ('self.mode = "NORMAL"', 'self.mode_router.transition_to(BrowserMode.NORMAL)'),
        ('self.mode = "SEARCH"', 'self.mode_router.transition_to(BrowserMode.SEARCH)'),
        ('self.mode = "TAG"', 'self.mode_router.transition_to(BrowserMode.TAG)'),
        ('self.mode = "FILE_BROWSER"', 'self.mode_router.transition_to(BrowserMode.FILE_BROWSER)'),
        ('self.mode = "GIT_DIFF_BROWSER"', 'self.mode_router.transition_to(BrowserMode.GIT_DIFF_BROWSER)'),
        ('self.mode = "LOG_BROWSER"', 'self.mode_router.transition_to(BrowserMode.LOG_BROWSER)'),
    ]
    
    content = main_browser.read_text()
    for old, new in replacements:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            print(f"  ✓ Replaced {count} occurrences of {old}")
    
    main_browser.write_text(content)
    print("\n✅ Mode router refactoring applied!")

if __name__ == "__main__":
    apply_refactoring()