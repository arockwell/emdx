# Vim Line Numbers Analysis

## Current State

The vim line numbers feature has been successfully re-enabled and fixed.

### Key Findings

1. **Implementation exists** in `/emdx/ui/vim_line_numbers.py`
   - `SimpleVimLineNumbers` widget provides vim-style relative line numbering
   - Shows current line number and relative distances for other lines
   - Supports focus/unfocus styling

2. **Integration points**:
   - `VimEditor` class (`/emdx/ui/vim_editor.py`) - Main orchestrator
   - `VimEditTextArea` class (`/emdx/ui/text_areas.py`) - Has `_update_line_numbers()` method
   - Line numbers are now ENABLED and working properly

3. **Previously disabled reason** (commit 4d7e455):
   - Line numbers were causing width calculation problems
   - Layout issues with the horizontal container
   - Text area couldn't take full container width properly

## Solution Implemented

The layout issues have been resolved by:

1. **Fixed width for line numbers**: Set to 4 characters (configurable based on document size)
2. **Fraction unit for text area**: Uses `1fr` to fill remaining space
3. **Proper CSS styling**: Added horizontal layout rules and styling
4. **Correct mounting order**: Line numbers mount before text area

### Key Changes

1. **In `vim_editor.py`**:
   - Re-enabled line numbers mounting in `on_mount()`
   - Added CSS with proper layout rules
   - Fixed width calculation for both widgets

2. **Layout CSS**:
   ```css
   #vim-edit-container {
       layout: horizontal;
   }
   
   #vim-line-numbers {
       width: 4;
       min-width: 4;
       max-width: 4;
   }
   
   #vim-text-area {
       width: 1fr;
   }
   ```

4. **Where line numbers should appear**:
   - Main document browser edit mode (press 'e')
   - File browser vim edit mode (press 'f' then edit)
   - Any VimEditTextArea instance


## Test Points

Line numbers are now working. To verify:
1. Launch TUI: `emdx gui`
2. Press 'e' on a document - line numbers should appear
3. Move cursor with j/k - relative numbers should update
4. Check layout doesn't break when:
   - Terminal is resized
   - Documents have 100+ lines
   - Switching between documents
5. Test in file browser (press 'f')