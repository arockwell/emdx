#!/usr/bin/env python3
"""
Fix the indentation issues caused by commenting out if statements
"""

from pathlib import Path
import re

def fix_indentation():
    main_browser = Path("emdx/ui/main_browser.py")
    content = main_browser.read_text()
    lines = content.splitlines()
    
    # Fix the broken if/elif chains
    fixes = [
        # Fix action_cursor_down
        (1174, "# MODE_ROUTER:         if self.mode == \"NORMAL\":  # TODO: Remove after testing",
               "        if self.mode == \"NORMAL\":"),
        (1176, "        elif self.mode == \"LOG_BROWSER\":",
               "        elif self.mode == \"LOG_BROWSER\":"),
        
        # Fix action_cursor_up  
        (1180, "# MODE_ROUTER:         if self.mode == \"NORMAL\":  # TODO: Remove after testing",
               "        if self.mode == \"NORMAL\":"),
        (1182, "        elif self.mode == \"LOG_BROWSER\":",
               "        elif self.mode == \"LOG_BROWSER\":"),
               
        # Fix action_cursor_top
        (1186, "# MODE_ROUTER:         if self.mode == \"NORMAL\":  # TODO: Remove after testing",
               "        if self.mode == \"NORMAL\":"),
               
        # Fix action_cursor_bottom
        (1192, "# MODE_ROUTER:         if self.mode == \"NORMAL\":  # TODO: Remove after testing",
               "        if self.mode == \"NORMAL\":"),
    ]
    
    # Apply fixes
    for line_num, old_text, new_text in fixes:
        if line_num <= len(lines):
            # Adjust for 0-based indexing
            idx = line_num - 1
            if lines[idx].strip() == old_text.strip():
                lines[idx] = new_text
                print(f"✓ Fixed line {line_num}")
            else:
                print(f"⚠️  Line {line_num} doesn't match expected content")
                print(f"   Expected: {old_text.strip()}")
                print(f"   Found: {lines[idx].strip()}")
    
    # Write back
    main_browser.write_text('\n'.join(lines))
    print("\n✅ Indentation fixes applied")

if __name__ == "__main__":
    fix_indentation()