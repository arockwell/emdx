# Markdown Rendering Improvements for emdx

## Summary of Research and Improvements

### 1. Fixed Auto-Scrolling Issue ✅

The preview pane was scrolling to the bottom when content was loaded due to RichLog's default `auto_scroll=True` behavior.

**Fix applied:**
- Set `auto_scroll=False` when creating the RichLog widget
- Added `scroll_end=False` when writing content
- Kept the `scroll_home()` call to ensure we start at the top

### 2. Better Markdown Rendering Options

#### Option A: Rich Markdown with Enhanced Configuration (Implemented)
Created `markdown_config.py` to provide:
- Automatic theme detection based on terminal background
- Code syntax highlighting with Pygments themes
- Environment variable support (`EMDX_CODE_THEME`)
- Popular themes for dark terminals: monokai, dracula, nord, one-dark
- Popular themes for light terminals: manni, tango, perldoc, friendly

#### Option B: Textual MarkdownViewer Widget (Alternative Implementation)
Created `textual_browser_improved.py` using MarkdownViewer which provides:
- Native Textual widget with better integration
- Built-in syntax highlighting for code blocks
- Scrollable code fences and tables
- Table of Contents support (disabled for preview)
- Separate theme configuration for light/dark terminals

#### Option C: mdcat Integration (Proof of Concept)
Created `mdcat_renderer.py` to explore using mdcat for superior rendering:
- Better code syntax highlighting
- Image support in compatible terminals (iTerm2, Kitty, WezTerm)
- Superior table formatting
- Proper link handling

**Note:** mdcat integration is complex because it outputs ANSI codes that need special handling in Textual.

### 3. Code Changes Made

1. **Fixed scrolling in `textual_browser.py`:**
   - Added `auto_scroll=False` to RichLog creation
   - Added `scroll_end=False` to write method
   - Integrated `MarkdownConfig` for better theme support

2. **Created `markdown_config.py`:**
   - Centralized markdown rendering configuration
   - Theme detection and selection logic
   - Helper functions for creating configured Markdown objects

3. **Created `textual_browser_improved.py`:**
   - Alternative implementation using MarkdownViewer
   - Better native Textual integration
   - Configurable code themes

4. **Created `mdcat_renderer.py`:**
   - Proof of concept for mdcat integration
   - Helper functions to check availability
   - Methods to capture mdcat output

5. **Updated `pyproject.toml`:**
   - Added `textual>=0.40.0` dependency

### 4. Recommendations

1. **Immediate Fix:** The scrolling issue is now fixed in the current implementation.

2. **Short Term:** Consider using the enhanced Rich configuration with theme support for better code highlighting.

3. **Medium Term:** Evaluate switching to MarkdownViewer widget (textual_browser_improved.py) for better native integration.

4. **Long Term:** Explore full mdcat integration for the best terminal markdown rendering, especially if image support is desired.

### 5. Usage Examples

#### Set a custom code theme:
```bash
export EMDX_CODE_THEME=monokai
emdx browse
```

#### List available themes:
```python
from emdx.markdown_config import list_available_themes
list_available_themes()
```

#### Use the improved browser:
```python
python -m emdx.textual_browser_improved
```

### 6. Testing Notes

- The scrolling fix has been applied to the main textual_browser.py
- The improved version with MarkdownViewer is available as a separate file
- All implementations support vim-style navigation and search modes
- Code syntax highlighting will automatically adapt to terminal background