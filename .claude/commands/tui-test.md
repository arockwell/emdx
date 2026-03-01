# TUI Testing Checklist

Generate a manual testing checklist for TUI changes.

## Process

1. Run `git diff main --name-only` (or diff against the branch in $ARGUMENTS) to find changed UI files
2. Based on which files changed, generate a targeted testing checklist

## File-to-Test Mapping

### activity_tree.py / activity_view.py
- [ ] Open GUI, switch to Activity tab — items load without error
- [ ] Scroll down in activity list, wait 5s — list should NOT jump to top on auto-refresh
- [ ] Expand a workflow execution — children load correctly
- [ ] Select an item — RHS preview panel shows correct content
- [ ] Trigger a background task in another terminal — new entry appears without disrupting scroll
- [ ] Check column alignment — time and ID columns are right-aligned and consistent

### cascade_browser.py
- [ ] Press `4` to open Cascade browser
- [ ] Navigate stages with `h`/`l`
- [ ] Navigate docs with `j`/`k`
- [ ] Advance a doc with `a`
- [ ] Activity feed in cascade shows entries without duplicates

### browser_container.py / main layout
- [ ] Switch between all tabs (1-4) — no crashes
- [ ] Resize terminal — layout adapts without breaking
- [ ] Keybindings work in all views

### Any DB-touching UI changes
- [ ] Fresh database — GUI opens without migration errors
- [ ] Large dataset (100+ items) — no performance degradation

## Output

Print ONLY the relevant checklist items based on which files actually changed. Don't include sections for unchanged files.
