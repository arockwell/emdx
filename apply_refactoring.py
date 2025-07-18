#!/usr/bin/env python3
"""
Apply the refactoring to main_browser.py

This script shows what changes to make to integrate the new components.
"""

import re
from pathlib import Path

def show_refactoring_plan():
    """Show the refactoring plan and impact."""
    
    main_browser = Path("emdx/ui/main_browser.py")
    content = main_browser.read_text()
    
    # Count mode checks
    mode_checks = len(re.findall(r'if.*self\.mode.*==', content))
    elif_chains = len(re.findall(r'elif.*self\.mode.*==', content))
    
    # Count large methods
    large_methods = []
    for match in re.finditer(r'def (\w+)\(self.*?\):', content):
        method_name = match.group(1)
        if any(prefix in method_name for prefix in ['setup_', 'load_', 'update_', 'handle_']):
            large_methods.append(method_name)
    
    print("🔍 REFACTORING ANALYSIS")
    print("=" * 50)
    print(f"File: {main_browser}")
    print(f"Current size: {len(content.splitlines())} lines")
    print()
    
    print("📊 MODE SWITCHING CHAOS:")
    print(f"  - if self.mode == ...: {mode_checks} occurrences")
    print(f"  - elif self.mode == ...: {elif_chains} occurrences")
    print(f"  - Total mode checks: {mode_checks + elif_chains}")
    print()
    
    print("🎯 EXTRACTABLE METHODS:")
    for method in large_methods:
        print(f"  - {method}()")
    print(f"  Total: {len(large_methods)} methods")
    print()
    
    print("✨ IMPACT OF REFACTORING:")
    print(f"  - Mode Router eliminates: ~{(mode_checks + elif_chains) * 10} lines")
    print(f"  - Table Manager extracts: ~200 lines")
    print(f"  - State Manager extracts: ~150 lines")
    print(f"  - Method extractions: ~{len(large_methods) * 50} lines")
    print()
    
    estimated_reduction = ((mode_checks + elif_chains) * 10 + 200 + 150 + len(large_methods) * 50)
    new_size = len(content.splitlines()) - estimated_reduction
    
    print(f"📉 ESTIMATED RESULT:")
    print(f"  - Current: {len(content.splitlines())} lines")
    print(f"  - After refactoring: ~{new_size} lines")
    print(f"  - Reduction: {estimated_reduction} lines ({estimated_reduction / len(content.splitlines()) * 100:.1f}%)")
    print()
    
    print("🚀 NEXT STEPS:")
    print("1. Add to imports:")
    print("   from .browser_mode_router import BrowserModeRouter, BrowserMode")
    print("   from .browser_state import BrowserStateManager")
    print("   from .document_table_manager import DocumentTableManager")
    print()
    print("2. In __init__, add:")
    print("   self.mode_router = BrowserModeRouter(self)")
    print("   self.state = BrowserStateManager()")
    print()
    print("3. In compose(), initialize:")
    print("   self.table_manager = DocumentTableManager(table)")
    print()
    print("4. Replace on_key() with the simplified version")
    print("5. Remove all if/elif self.mode chains")
    print("6. Replace table operations with table_manager calls")
    print()
    
    # Show example transformations
    print("📝 EXAMPLE TRANSFORMATIONS:")
    print()
    print("BEFORE:")
    print('  if self.mode == "NORMAL":'
          '\n      # handle normal mode'
          '\n  elif self.mode == "SEARCH":'
          '\n      # handle search mode')
    print()
    print("AFTER:")
    print('  # All handled by: self.mode_router.handle_key(event)')
    print()
    
    print("BEFORE:")
    print('  table.add_row(...)'
          '\n  table.clear()'
          '\n  # 50+ lines of table manipulation')
    print()
    print("AFTER:")
    print('  self.table_manager.populate_table(documents)')
    print()

if __name__ == "__main__":
    show_refactoring_plan()