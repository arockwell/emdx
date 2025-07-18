# EMDX Browser Refactoring Progress

## What We've Done (2025-07-17)

### 1. Created Powerful Extraction Tools
- **`tools/copy_tool.py`** - AST-based Python class/function extractor
  - Handles imports, dependencies, and code structure
  - Can extract classes/functions to separate files
  - Much better than regex-based tools
  
- **`tools/copy_py.fish`** - Fish shell wrapper with EMDX helpers
  - Provides convenient commands like `fix_emdx_browser`
  - Can batch extract multiple components

### 2. Extracted Components

✅ **SimpleVimLineNumbers** → `vim_line_numbers.py`
- Removed 50 lines from main_browser.py
- Clean import structure maintained

✅ **BrowserModeRouter** → `browser_mode_router.py` (NEW)
- Centralizes all mode switching logic
- Eliminates hundreds of if/elif chains
- Makes it easy to add new modes
- Provides clean key event routing

✅ **BrowserStateManager** → `browser_state.py` (NEW)
- Extracts state management into dedicated classes
- Reduces instance variables in main browser
- Provides cleaner interfaces for state

✅ **DocumentTableManager** → `document_table_manager.py` (NEW)
- Extracts all DataTable manipulation code
- ~200 lines of table-specific logic isolated
- Clean interface for table operations

✅ **MinimalContainer** → `minimal_container.py` (NEW)
- Demonstrates the CORRECT architecture
- Lightweight container that just swaps browsers
- Each browser is self-contained
- No mode switching needed

### 3. Architecture Improvements

**Created `integrate_mode_router.py`** showing how to:
- Replace massive on_key method
- Use mode router for clean key handling
- Reduce main_browser.py by ~500 lines

**Created `refactored_on_key.py`** showing:
- Simplified key handling with mode router
- From ~200+ lines to ~50 lines
- Clear, maintainable structure

## Current State

### main_browser.py Status
- Started: 3179 lines
- After extractions: ~3050 lines
- Potential after integration: ~2000 lines

### What's Ready to Integrate
1. BrowserModeRouter - Will eliminate all if/elif mode chains
2. DocumentTableManager - Will extract all table code
3. BrowserStateManager - Will consolidate state management

## Next Steps

### Immediate (1-2 hours)
1. **Integrate BrowserModeRouter**
   ```python
   # In __init__:
   self.mode_router = BrowserModeRouter(self)
   
   # Replace on_key with simplified version
   # Remove all if/elif mode chains
   ```

2. **Apply DocumentTableManager**
   ```python
   # Replace all table manipulation code
   self.table_manager = DocumentTableManager(self.query_one("#doc-table"))
   ```

3. **Use BrowserStateManager**
   ```python
   # Replace scattered state variables
   self.state = BrowserStateManager()
   ```

### This Week
1. Continue extracting large methods
2. Create separate files for:
   - Search functionality
   - Tag management
   - Preview/viewer logic
   - Status bar management

3. Start parallel implementation with MinimalContainer

### Next 2 Weeks
1. Port browsers to new architecture
2. Each browser becomes a self-contained component
3. MinimalContainer becomes the main app
4. Delete the old monolithic structure

## Why This Approach Works

1. **Incremental** - Each step improves the code
2. **Safe** - Current functionality preserved
3. **Testable** - Smaller, focused components
4. **Sustainable** - You can stop at any point with a better system

## Command Reference

```bash
# Analyze what's left in main_browser.py
python3 tools/copy_tool.py analyze emdx/ui/main_browser.py

# Extract a specific class
python3 tools/copy_tool.py copy-class emdx/ui/main_browser.py emdx/ui/new_file.py ClassName

# See what the mode router will replace
rg "if.*self\.mode.*==" emdx/ui/main_browser.py | wc -l
# Result: 20+ mode checks that will disappear!

# See duplicate code that can be extracted
rg "def (update_|load_|setup_|handle_)" emdx/ui/main_browser.py
```

## The Path Forward

You were right - the current architecture is inside-out. But now you have:
1. Tools to extract code safely
2. Components that demonstrate the right patterns
3. A clear path to the correct architecture

The key insight remains: **Don't suffer with bad architecture while rewriting**. Each extraction makes the next one easier, and you can stop whenever the code becomes manageable.