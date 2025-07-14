# Test Git Diff Browser

This is a test file to create some git changes for testing the git diff browser functionality.

## Features to Test

1. **Git Diff Browser ('d' key)**
   - Press 'd' in the TUI to enter git diff browser mode
   - Should show this file and other modified files

2. **Worktree Switching ('w' key)**
   - Press 'w' while in git diff mode to switch worktrees
   - Should show an interactive picker with all available worktrees

3. **File Navigation (j/k keys)**
   - Use j/k to navigate between changed files
   - Preview pane should show the actual git diff

4. **Status Display**
   - Status bar should show current worktree and branch
   - Should display file count and navigation instructions

## Test Scenarios

- Modified files (like this one)
- New untracked files
- Staged changes
- Multiple worktrees

This file will appear as a new untracked file when you test the git diff browser.