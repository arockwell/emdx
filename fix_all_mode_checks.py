#!/usr/bin/env python3
"""
Fix all the mode checks properly - either remove them or fix indentation
"""

from pathlib import Path

def fix_mode_checks():
    main_browser = Path("emdx/ui/main_browser.py")
    content = main_browser.read_text()
    
    # For now, let's just uncomment all the MODE_ROUTER lines to restore functionality
    content = content.replace("# MODE_ROUTER: ", "")
    content = content.replace("  # TODO: Remove after testing", "")
    
    # Write back
    main_browser.write_text(content)
    print("✅ Restored all mode checks to working state")
    print("   (They still need to be properly refactored later)")

if __name__ == "__main__":
    fix_mode_checks()