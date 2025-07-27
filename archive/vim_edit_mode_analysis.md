# Vim-like Edit Mode Analysis for EMDX TUI

## Overview
This document analyzes how to implement vim-like keybindings in the EMDX TUI edit mode, building on the existing EditTextArea implementation.

## Current State

### Existing Foundation
1. **EditTextArea class** - Already handles ESC to save and exit
2. **Modal architecture** - App already uses modes (NORMAL, SEARCH, TAG)
3. **Vim navigation** - j/k/g/G already implemented in browser
4. **Key event handling** - Comprehensive logging and event control

### Key Strengths
- Clean separation of concerns with custom TextArea classes
- Existing modal state management
- Established key handling patterns
- Reactive state system for UI updates

## Proposed Vim Mode Implementation

### 1. Sub-Modal Architecture
Create vim modes within edit mode:

```python
class VimEditTextArea(TextArea):
    """TextArea with vim-like keybindings."""
    
    # Vim modes
    VIM_NORMAL = "NORMAL"
    VIM_INSERT = "INSERT"
    VIM_VISUAL = "VISUAL"
    VIM_VISUAL_LINE = "V-LINE"
    
    def __init__(self, app_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance
        self.vim_mode = self.VIM_INSERT  # Start in insert mode
        self.visual_start = None
        self.last_motion = None
        self.repeat_count = ""
```

### 2. Key Handling Strategy

#### Normal Mode Commands
```python
# Basic motions
'h' - Move left
'j' - Move down  
'k' - Move up
'l' - Move right
'w' - Next word
'b' - Previous word
'e' - End of word
'0' - Start of line
'$' - End of line
'gg' - Go to first line
'G' - Go to last line

# Mode changes
'i' - Insert before cursor
'a' - Insert after cursor
'I' - Insert at beginning of line
'A' - Insert at end of line
'o' - Open line below
'O' - Open line above
'v' - Visual mode
'V' - Visual line mode
'ESC' - Return to normal mode

# Editing
'x' - Delete character
'dd' - Delete line
'yy' - Yank line
'p' - Paste after
'P' - Paste before
'u' - Undo
'ctrl+r' - Redo

# Text objects (simplified)
'dw' - Delete word
'cw' - Change word
'ciw' - Change inner word
'di"' - Delete inside quotes
```

### 3. Implementation Approach

#### Phase 1: Basic Modal Editing
1. Add vim_mode state to EditTextArea
2. Implement mode switching (i, a, v, ESC)
3. Add basic motions (h, j, k, l)
4. Show mode in status bar

#### Phase 2: Core Vim Features
1. Word motions (w, b, e)
2. Line operations (dd, yy, p)
3. Basic visual mode
4. Undo/redo integration

#### Phase 3: Advanced Features
1. Text objects (iw, i", i(, etc.)
2. Repeat counts (3j, 5w)
3. Dot command (.)
4. Marks and jumps

### 4. Technical Considerations

#### Cursor Management
- Textual's TextArea has built-in cursor position tracking
- Need to translate vim motions to TextArea cursor movements
- Use `move_cursor_relative()` and `move_cursor()` methods

#### Visual Mode
- Track selection start/end positions
- Use TextArea's selection API
- Highlight selected text appropriately

#### Registers/Clipboard
- Integrate with system clipboard for yank/paste
- Consider vim-style registers for advanced users

#### Status Display
- Show current vim mode in edit mode status
- Display partial commands (e.g., "d" waiting for motion)
- Show visual selection size

### 5. Integration Points

#### With Existing Code
```python
def watch_edit_mode(self, edit_mode: bool) -> None:
    """React to edit mode changes."""
    if edit_mode:
        # Show vim mode in status
        self.update_status(f"Edit Mode - {self.edit_textarea.vim_mode}")
    else:
        # Clear vim state
        self.edit_textarea.vim_mode = VimEditTextArea.VIM_INSERT
```

#### Status Bar Updates
```python
# In _update_status_bar()
if self.edit_mode and hasattr(self, 'edit_textarea'):
    vim_mode = getattr(self.edit_textarea, 'vim_mode', 'INSERT')
    parts.append(f"[bold yellow]-- {vim_mode} --[/bold yellow]")
```

### 6. User Experience Considerations

#### Default Behavior
- Start in INSERT mode (user expects to type immediately)
- ESC always available to exit edit mode completely
- Clear visual indicators of current mode

#### Configuration Options
- Allow disabling vim mode for users who prefer standard editing
- Configurable key mappings
- Option to start in NORMAL vs INSERT mode

#### Learning Curve
- Implement subset of vim commands initially
- Focus on most common operations
- Provide help/cheatsheet in UI

### 7. Implementation Priority

1. **High Priority (Phase 1)**
   - Mode switching (i, a, ESC)
   - Basic navigation (h, j, k, l)
   - Visual mode indicator
   - Save on ESC from NORMAL mode

2. **Medium Priority (Phase 2)**
   - Word navigation (w, b, e)
   - Delete/change operations (x, dd, cc)
   - Yank/paste (yy, p)
   - Undo/redo

3. **Low Priority (Phase 3)**
   - Text objects
   - Advanced motions
   - Macros
   - Ex commands

### 8. Testing Strategy

1. **Unit Tests**
   - Test each vim command in isolation
   - Verify mode transitions
   - Test edge cases (empty document, single line)

2. **Integration Tests**
   - Test vim mode within full TUI
   - Verify status bar updates
   - Test save/cancel workflows

3. **User Testing**
   - Get feedback from vim users
   - Identify missing "must-have" commands
   - Refine UX based on usage

## Conclusion

The EMDX TUI is well-architected for adding vim mode to the edit functionality. The existing modal system, custom TextArea classes, and key handling infrastructure provide a solid foundation. 

A phased approach starting with basic modal editing and gradually adding more vim features would provide value quickly while maintaining code quality. The implementation should focus on the most commonly used vim commands and maintain the existing user-friendly design of EMDX.

Key success factors:
1. Clear mode indicators
2. Responsive key handling
3. Predictable vim-like behavior
4. Graceful degradation for non-vim users
5. Integration with existing EMDX workflows