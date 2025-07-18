# EMDX TUI Comprehensive Test Plan

## Overview
This test plan covers all functionality after the refactoring, with special focus on:
- VimEditor integration and text visibility
- Mode routing and transitions
- Document table operations
- State persistence across modes

## 1. VimEditor Integration Tests 🎯

### Basic Edit Mode
- [ ] Press 'e' on a document - should enter edit mode
- [ ] **Text should be visible** (white text on dark background)
- [ ] Cursor should be visible and blinking
- [ ] Line numbers should display correctly on the left
- [ ] Status bar should show "EDIT MODE"

### Vim Modal Behavior
- [ ] Should start in INSERT mode (can type immediately)
- [ ] ESC once: INSERT → NORMAL mode
- [ ] ESC twice: Exit edit mode completely
- [ ] Status bar updates with current vim mode

### Vim Commands (NORMAL mode)
- [ ] **Movement**: h/j/k/l navigation
- [ ] **Word motion**: w/b/e movement
- [ ] **Line motion**: 0/$ for start/end of line
- [ ] **Document motion**: gg/G for top/bottom
- [ ] **Deletion**: x (char), dd (line)
- [ ] **Copy/paste**: yy (yank line), p (paste)
- [ ] **Mode changes**: i/a/I/A/o/O to enter INSERT

### Vim with Counts
- [ ] 3j - move down 3 lines
- [ ] 5w - move forward 5 words
- [ ] 2dd - delete 2 lines
- [ ] 10x - delete 10 characters

### Visual Mode
- [ ] v - enter VISUAL mode
- [ ] V - enter VISUAL LINE mode
- [ ] Selection highlighting works
- [ ] d/y operations on selection

### Save/Cancel
- [ ] Ctrl+S saves changes and exits
- [ ] ESC ESC cancels without saving
- [ ] Changes persist after save
- [ ] Document reloads in table after edit

## 2. Mode Routing Tests 🔀

### Mode Transitions
- [ ] BROWSER → SEARCH (/)
- [ ] SEARCH → BROWSER (ESC)
- [ ] BROWSER → TAG_MODE (t)
- [ ] TAG_MODE → BROWSER (ESC)
- [ ] BROWSER → EDIT (e)
- [ ] EDIT → BROWSER (ESC ESC)
- [ ] BROWSER → FILE_BROWSER (b)
- [ ] FILE_BROWSER → BROWSER (ESC)

### Key Routing
- [ ] Mode-specific keys only work in correct mode
- [ ] Global keys (q, ?) work in all modes
- [ ] Invalid keys are ignored gracefully
- [ ] No key conflicts between modes

## 3. Document Table Operations 📊

### Navigation
- [ ] j/k - move selection up/down
- [ ] g - jump to first document
- [ ] G - jump to last document
- [ ] Page Up/Down - scroll table
- [ ] Mouse click selects document

### Selection
- [ ] Space - toggle document selection
- [ ] Selected documents show checkmark
- [ ] Selection persists during navigation
- [ ] Clear selection works

### Sorting
- [ ] Sort by title
- [ ] Sort by date
- [ ] Sort by access count
- [ ] Sort direction toggles

### Filtering
- [ ] Project filter dropdown works
- [ ] Tag filter applies correctly
- [ ] Search filter updates table
- [ ] Multiple filters combine properly

## 4. Search Functionality 🔍

### Basic Search
- [ ] / enters search mode
- [ ] Type search terms
- [ ] ENTER executes search
- [ ] Results update in real-time
- [ ] ESC cancels search

### Search Features
- [ ] Case-insensitive search
- [ ] Partial word matching
- [ ] Multi-word search
- [ ] Empty search shows all docs
- [ ] Search status shows result count

## 5. Tag Management 🏷️

### Tag Mode
- [ ] t enters tag mode
- [ ] Shows current document tags
- [ ] Add tag with ENTER
- [ ] Remove tag with selection
- [ ] Tag autocomplete works

### Tag Display
- [ ] Emoji tags display correctly
- [ ] Text aliases work (gameplan → 🎯)
- [ ] Tag counts update
- [ ] Tag filter in sidebar

## 6. State Management 💾

### Document State
- [ ] Current document persists across modes
- [ ] Scroll position maintained
- [ ] Selection state preserved
- [ ] Filter state retained

### Cross-Mode State
- [ ] Edit changes reflect immediately
- [ ] Tag changes update everywhere
- [ ] Delete/restore updates table
- [ ] Project changes update filters

## 7. Special Features 🌟

### Trash Management
- [ ] View deleted documents
- [ ] Restore from trash
- [ ] Permanent delete warning
- [ ] Trash count updates

### Status Bar
- [ ] Shows current mode
- [ ] Document count accurate
- [ ] Keyboard hints update
- [ ] Error messages display

### Preview Panel
- [ ] Markdown renders correctly
- [ ] Code syntax highlighting
- [ ] Scrollable content
- [ ] Updates on selection change

## 8. Edge Cases 🔧

### Empty States
- [ ] No documents - helpful message
- [ ] No search results - clear feedback
- [ ] No tags - appropriate UI
- [ ] Empty document - handles gracefully

### Large Data
- [ ] 1000+ documents - performance acceptable
- [ ] Long documents - preview scrolls
- [ ] Many tags - UI remains usable
- [ ] Long titles - truncate properly

### Error Handling
- [ ] Database errors - user-friendly message
- [ ] Save failures - clear notification
- [ ] Invalid input - appropriate feedback
- [ ] Network issues - graceful degradation

## 9. CSS and Visual Tests 🎨

### Text Visibility
- [ ] All text readable (no invisible text)
- [ ] Proper contrast ratios
- [ ] Consistent color scheme
- [ ] Focus indicators visible

### Layout
- [ ] No overlapping elements
- [ ] Responsive to terminal size
- [ ] Panels resize correctly
- [ ] Scrollbars appear when needed

## 10. Performance Tests ⚡

### Responsiveness
- [ ] Key presses register immediately
- [ ] Mode switches are instant
- [ ] Search updates quickly
- [ ] No lag during navigation

### Memory
- [ ] Long sessions stable
- [ ] No memory leaks
- [ ] Large documents handled
- [ ] Multiple operations smooth

## Test Execution Commands

```bash
# Start the TUI
emdx gui

# Test with specific scenarios
emdx gui --project myproject  # Test project filtering
emdx gui --tags "gameplan"    # Test tag filtering

# Create test data if needed
echo "Test gameplan content" | emdx save --title "Test Gameplan" --tags "gameplan,active"
echo "Test analysis" | emdx save --title "Test Analysis" --tags "analysis,done"
```

## Regression Tests

Based on recent fixes, ensure:
1. ✅ Text is ALWAYS visible in edit mode
2. ✅ VimEditor CSS styles apply correctly
3. ✅ Mode transitions don't break UI state
4. ✅ Widget IDs remain consistent
5. ✅ Panel refresh works properly

## Notes
- Test in different terminal emulators
- Try various terminal sizes
- Test with both light and dark themes
- Verify with screen readers if possible