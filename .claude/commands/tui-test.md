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
- [ ] Run `emdx delegate "test"` in another terminal — new entry appears without disrupting scroll
- [ ] Check column alignment — time and ID columns are right-aligned and consistent

### cascade_browser.py
- [ ] Press `4` to open Cascade browser
- [ ] Navigate stages with `h`/`l`
- [ ] Navigate docs with `j`/`k`
- [ ] Advance a doc with `a`
- [ ] Activity feed in cascade shows entries without duplicates

### modals.py (DocumentPreviewScreen)
- [ ] Press `f`/`Enter` on a document — fullscreen preview opens with rendered markdown
- [ ] Press `c` in fullscreen preview — switches to copy mode (raw selectable text)
- [ ] Press `c` again — switches back to rendered preview
- [ ] Select text with mouse in copy mode — text is selectable
- [ ] Press `Esc`/`q` — closes preview, returns to previous screen

### activity_view.py (preview panel copy mode)
- [ ] Select a document — RHS preview shows rendered markdown
- [ ] Press `c` — RHS switches to raw selectable text
- [ ] Press `c` again — back to rendered markdown
- [ ] Switch documents while in copy mode — content updates correctly

### qa/qa_screen.py
- [ ] Press `3` from any screen — Q&A screen opens
- [ ] Type a question and press Enter — animated spinner appears
- [ ] Spinner label updates: Thinking → Retrieving context → Generating answer
- [ ] Answer renders as formatted markdown (headings, code blocks, lists)
- [ ] Sources listed below answer
- [ ] Press `s` — saves exchange to knowledge base
- [ ] Press `c` — clears conversation history

### browser_container.py / main layout
- [ ] Switch between all tabs (1–3) — no crashes
- [ ] Resize terminal — layout adapts without breaking
- [ ] Keybindings work in all views

### Any DB-touching UI changes
- [ ] Fresh database — GUI opens without migration errors
- [ ] Large dataset (100+ items) — no performance degradation

## Output

Print ONLY the relevant checklist items based on which files actually changed. Don't include sections for unchanged files.
