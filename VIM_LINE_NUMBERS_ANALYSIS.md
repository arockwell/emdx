# Vim Line Numbers Analysis

## Current State

The vim line numbers feature is implemented but currently disabled due to layout issues.

### Key Findings

1. **Implementation exists** in `/emdx/ui/vim_line_numbers.py`
   - `SimpleVimLineNumbers` widget provides vim-style relative line numbering
   - Shows current line number and relative distances for other lines
   - Supports focus/unfocus styling

2. **Integration points**:
   - `VimEditor` class (`/emdx/ui/vim_editor.py`) - Main orchestrator
   - `VimEditTextArea` class (`/emdx/ui/text_areas.py`) - Has `_update_line_numbers()` method
   - Line numbers are TEMPORARILY DISABLED (lines 69-77 in vim_editor.py)

3. **Disabled reason** (commit 4d7e455):
   - Line numbers were causing width calculation problems
   - Layout issues with the horizontal container
   - Text area couldn't take full container width properly

4. **Where line numbers should appear**:
   - Main document browser edit mode (press 'e')
   - File browser vim edit mode (press 'f' then edit)
   - Any VimEditTextArea instance

## Technical Issues

### 1. Layout Problems
- The horizontal container with line numbers + text area wasn't calculating widths properly
- Text area would get squashed or overflow
- CSS width settings conflicted

### 2. Mounting/Timing Issues
- Multiple workarounds exist for delayed initialization
- Race conditions between widget mounting and line number updates
- TextArea's internal positioning logic conflicts with line number updates

### 3. Architecture Fragmentation
- VimEditTextArea has line number logic but depends on external widget
- VimEditor creates the line numbers widget but mounting is disabled
- No clear owner of the line numbers lifecycle

## Re-enable Strategy

### Quick Fix (Phase 3 Priority)
1. Re-enable line numbers mounting in vim_editor.py
2. Fix the width calculation issues:
   - Set fixed width for line numbers (4-5 characters)
   - Ensure text area uses remaining space (flex or calc)
   - Test with different terminal widths

### Proper Fix
1. Move line numbers into VimEditTextArea as a composed child
2. Handle lifecycle internally within the text area
3. Use Textual's layout system properly (Grid or proper Horizontal constraints)
4. Remove all timing workarounds

## Test Points

When line numbers are re-enabled, test:
1. Launch TUI: `emdx gui`
2. Press 'e' on a document - line numbers should appear
3. Move cursor with j/k - relative numbers should update
4. Check layout doesn't break when:
   - Terminal is resized
   - Documents have 100+ lines
   - Switching between documents
5. Test in file browser (press 'f')