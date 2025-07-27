# Gameplan: Log Browser Widget Refactoring

## Objective
Extract log browser functionality from DocumentBrowser into a standalone LogBrowser widget, following the architecture pattern of FileBrowser and GitBrowser.

## Success Criteria
- [ ] Log browser works as a separate widget
- [ ] No LOG_BROWSER mode checks remain in DocumentBrowser
- [ ] Clean switching via 'l' key from document browser
- [ ] All existing functionality preserved
- [ ] Tests pass and code is cleaner

## Phase 1: Create LogBrowser Widget [1.5 hours]

### 1.1 Create the new file structure
- [ ] Create `emdx/ui/log_browser.py`
- [ ] Import necessary dependencies from document_browser.py
- [ ] Define LogBrowser class extending Widget

### 1.2 Implement core layout
- [ ] Define compose() method with Horizontal layout
- [ ] Add DataTable for execution list (left pane)
- [ ] Add ScrollableContainer with RichLog for log content (right pane)
- [ ] Set up proper CSS styling for 50/50 split

### 1.3 Port execution listing functionality
- [ ] Copy get_recent_executions import
- [ ] Implement on_mount() to load executions
- [ ] Port table population logic from action_log_browser()
- [ ] Add proper column headers and formatting

### 1.4 Port log viewing functionality
- [ ] Copy load_execution_log() method
- [ ] Adapt for new widget structure
- [ ] Handle on_data_table_row_highlighted event
- [ ] Ensure log content displays properly

## Phase 2: Implement Selection Mode [1 hour]

### 2.1 Port selection mode
- [ ] Copy enter_log_selection_mode() logic
- [ ] Create LogSelectionTextArea class
- [ ] Handle 's' key binding
- [ ] Implement copy-to-clipboard functionality

### 2.2 Port preview restoration
- [ ] Copy restore_log_preview() logic
- [ ] Handle ESC key in selection mode
- [ ] Ensure smooth transition back to log view

### 2.3 Add key bindings
- [ ] Define BINDINGS list (j/k/s/r/q)
- [ ] Implement refresh functionality
- [ ] Handle 'q' to return to document browser

## Phase 3: Wire Up Container [30 minutes]

### 3.1 Update BrowserContainer
- [ ] Import LogBrowser in switch_browser()
- [ ] Add "log" case to browser creation
- [ ] Update status bar text for log browser

### 3.2 Update key handling
- [ ] Add 'l' key handler when current_browser == "document"
- [ ] Add 'q' key handler when current_browser == "log"
- [ ] Ensure proper event stopping

### 3.3 Test browser switching
- [ ] Verify 'l' switches to log browser
- [ ] Verify 'q' returns to document browser
- [ ] Check status bar updates correctly

## Phase 4: Remove Old Code [30 minutes]

### 4.1 Clean DocumentBrowser
- [ ] Remove action_log_browser() method
- [ ] Remove exit_log_browser() method
- [ ] Remove load_execution_log() method
- [ ] Remove enter_log_selection_mode() method
- [ ] Remove restore_log_preview() method

### 4.2 Remove mode checks
- [ ] Remove all `if mode == "LOG_BROWSER"` checks
- [ ] Remove LOG_BROWSER from mode handling
- [ ] Remove self.executions state variable
- [ ] Remove 'l' key binding from DocumentBrowser

### 4.3 Clean up imports
- [ ] Remove execution-related imports
- [ ] Remove unused log-related imports
- [ ] Verify no orphaned code remains

## Phase 5: Testing & Polish [1 hour]

### 5.1 Manual testing checklist
- [ ] Launch emdx gui
- [ ] Press 'l' - verify log browser opens
- [ ] Navigate with j/k - verify log content updates
- [ ] Press 's' - verify selection mode works
- [ ] Copy text and verify clipboard
- [ ] Press 'q' - verify return to documents
- [ ] Test with no executions (empty state)

### 5.2 Edge cases
- [ ] Test with very long log files
- [ ] Test with missing log files
- [ ] Test with corrupted log files
- [ ] Test rapid switching between browsers
- [ ] Test all keybindings work correctly

### 5.3 Code quality
- [ ] Add proper docstrings
- [ ] Add type hints
- [ ] Run linters (ruff, mypy if configured)
- [ ] Ensure consistent code style

## Phase 6: Documentation & Commit [30 minutes]

### 6.1 Update documentation
- [ ] Update CLAUDE.md if needed
- [ ] Add LogBrowser to architecture docs
- [ ] Document any new keybindings

### 6.2 Create atomic commits
- [ ] Commit 1: Add LogBrowser widget
- [ ] Commit 2: Wire up container switching
- [ ] Commit 3: Remove old log browser mode
- [ ] Commit 4: Clean up and polish

### 6.3 Create PR
- [ ] Write comprehensive PR description
- [ ] Include before/after architecture
- [ ] List all functionality preserved
- [ ] Note any behavior changes

## Risk Mitigation

### Parallel Development
- Keep old code working while building new
- Test both implementations side-by-side
- Only remove old code after new is verified

### Rollback Strategy
- Each phase is a separate commit
- Can revert individual commits if needed
- Old code removal is the final step

### Testing Strategy
- Manual testing after each phase
- Compare behavior with current implementation
- Get user feedback before removing old code

## Notes

### Key Architecture Decisions
1. **50/50 split layout** - Unlike DocumentBrowser's complex layout
2. **No details panel** - Logs don't need metadata display
3. **Direct widget switching** - No mode management
4. **Self-contained state** - Executions list lives in LogBrowser

### Future Enhancements (out of scope)
- Filter logs by date/status
- Search within logs
- Export logs functionality
- Log file management (delete old logs)

## Timeline
- **Total estimate**: 4 hours
- **With testing/polish**: 5-6 hours
- **Suggested approach**: Complete over 2 sessions
  - Session 1: Phases 1-3 (create and wire up)
  - Session 2: Phases 4-6 (remove old and polish)