# Gameplan: Fix Delete Modal Key Handling in EMDX TUI

## Overview

The delete functionality in EMDX TUI browser is broken because the main browser's key handler intercepts keyboard events before they reach the delete confirmation modal. We need to make the main browser modal-aware so it only processes keys when no modal is active.

## Step-by-Step Implementation Plan

### 1. Add Modal State Detection
- Modify `emdx/ui/main_browser.py`'s `on_key` method
- Add check for active modals using `self.screen_stack` length
- Skip key processing when modals are active (stack > 1)

### 2. Implement the Fix
```python
# At the start of on_key method:
if len(self.screen_stack) > 1:
    # Modal is active, let it handle keys
    return
```

### 3. Verify Modal Focus
- Ensure DeleteConfirmScreen has proper focus on mount
- Confirm modal CSS has correct z-index and overlay
- Check that modal bindings work when focused

### 4. Test Other Key Handlers
- Verify the fix doesn't break other functionality
- Check that vim mode still works properly
- Ensure tag management modals work correctly

### 5. Clean Up Debug Files
- Remove temporary test files after fix is verified:
  - `test_delete_debug.py`
  - `test_modal_keys.py`
  - `test_modal_fix.py`
  - `fix_delete_modal.patch`

## Testing Approach

### Manual Testing
1. Launch EMDX TUI: `emdx gui`
2. Navigate to any document
3. Press 'd' to open delete modal
4. Press 'y' to confirm - verify document is deleted
5. Repeat with 'n' to cancel - verify document remains

### Automated Testing
1. Run existing modal tests to verify baseline
2. Add test case for modal key interception
3. Test edge cases:
   - Multiple modals stacked
   - Modal opened during search
   - Modal with vim edit mode active

### Regression Testing
1. Verify all other key bindings still work:
   - Navigation (j/k, g/G)
   - Search (/)
   - Tag management (t)
   - Edit mode (e)
2. Test mouse interactions with modals
3. Verify no performance impact

## Success Criteria
- Delete modal responds to 'y'/'n' keypresses
- Main browser doesn't consume keys when modal is active
- No regression in other functionality
- Clean codebase without debug files