# Manual Testing Script for Vim Line Numbers

## Test Scenarios

### 1. Document Browser Edit Mode
- [ ] Launch EMDX TUI: `emdx gui`
- [ ] Select a document and press 'e' to enter edit mode
- [ ] Verify line numbers appear within 100ms
- [ ] Check that current line is highlighted in bold yellow
- [ ] Move cursor up/down with j/k - verify line numbers update
- [ ] Switch between INSERT and NORMAL modes - verify line numbers persist
- [ ] Press ESC twice to exit - verify line numbers disappear

### 2. File Browser Edit Mode  
- [ ] In TUI, press 'f' to enter file browser
- [ ] Select a file and press 'e' to edit
- [ ] Verify line numbers appear immediately
- [ ] Test cursor movement - line numbers should update
- [ ] Test with files of different sizes (5, 50, 500+ lines)

### 3. Configuration Testing
- [ ] Create/edit `~/.config/emdx/vim_settings.json`:
```json
{
  "line_numbers": {
    "enabled": false
  }
}
```
- [ ] Restart TUI and enter edit mode - no line numbers should appear
- [ ] Change to `"enabled": true, "relative": false` - absolute line numbers
- [ ] Test different width values (3, 5, 6)

### 4. Terminal Resize
- [ ] Enter edit mode with line numbers visible
- [ ] Resize terminal window horizontally and vertically
- [ ] Line numbers should maintain proper layout
- [ ] Text should not overlap with line numbers

### 5. Performance Testing
- [ ] Open a large document (500+ lines)
- [ ] Enter edit mode and move cursor rapidly (hold j/k)
- [ ] Line numbers should update smoothly without lag
- [ ] No flicker or visual artifacts

### 6. Edge Cases
- [ ] Empty document - should show single line number "1"
- [ ] Single line document - proper display
- [ ] Very long lines (200+ chars) - no overlap
- [ ] Documents with 1000+ lines - width adjusts properly

## Expected Results
- Line numbers appear instantly (no timing delays)
- Consistent display across all vim-enabled editors
- Proper visual separation from content
- Smooth updates during cursor movement
- Settings persist across sessions

## Known Issues Fixed
- ✅ Line numbers not appearing consistently
- ✅ Timing workarounds removed
- ✅ CSS layout stabilized
- ✅ Configuration support added
- ✅ Visual feedback enhanced