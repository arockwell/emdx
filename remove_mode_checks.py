#!/usr/bin/env python3
"""
Remove if/elif mode checking chains from main_browser.py
"""

import re
from pathlib import Path

def remove_mode_checks():
    """Remove mode checking chains that are now handled by the router."""
    
    main_browser = Path("emdx/ui/main_browser.py")
    content = main_browser.read_text()
    lines = content.splitlines()
    
    # Patterns to identify mode checks that can be removed
    mode_check_patterns = [
        r'if self\.mode == "NORMAL".*:',
        r'elif self\.mode == "NORMAL".*:',
        r'if self\.mode == "SEARCH".*:',
        r'elif self\.mode == "SEARCH".*:',
        r'if self\.mode == "TAG".*:',
        r'elif self\.mode == "TAG".*:',
    ]
    
    # Find lines with mode checks
    mode_check_lines = []
    for i, line in enumerate(lines):
        for pattern in mode_check_patterns:
            if re.search(pattern, line):
                mode_check_lines.append(i)
                print(f"Found mode check at line {i+1}: {line.strip()}")
    
    print(f"\n📊 Found {len(mode_check_lines)} mode check lines")
    
    # For safety, let's just comment them out first rather than delete
    print("\n💡 Commenting out mode checks (safer than deletion)...")
    
    for line_num in reversed(mode_check_lines):  # Reverse to maintain line numbers
        # Skip if it's in a method we want to keep (like watch_mode)
        if line_num > 0 and "def watch_mode" in lines[line_num - 5:line_num]:
            print(f"  ⏭️  Skipping line {line_num+1} (in watch_mode)")
            continue
            
        # Comment out the line
        lines[line_num] = "# MODE_ROUTER: " + lines[line_num] + "  # TODO: Remove after testing"
    
    # Write back
    main_browser.write_text('\n'.join(lines))
    print(f"\n✅ Commented out {len(mode_check_lines)} mode check lines")
    print("   (Search for 'MODE_ROUTER:' to find them)")

if __name__ == "__main__":
    remove_mode_checks()