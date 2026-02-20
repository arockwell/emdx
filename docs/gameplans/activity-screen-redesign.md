# Gameplan: Activity Screen Redesign — Flat Table View

## Goal

Replace the current hierarchical Tree-based Activity screen with a flat DataTable
(or OptionList + detail pane). Remove grouping concepts (document groups, group
picker, parent-child nesting) from the Activity view entirely. The result is a
simple, scannable table of recent activity — documents and agent executions — with
a detail/preview pane.

## Current State

The Activity screen (`emdx/ui/activity/`) uses Textual's `Tree` widget to display:

1. **Document groups** (batches, rounds, initiatives) — expandable nodes with child
   documents, child groups, role icons, cost/token summaries
2. **Standalone documents** — leaf nodes (but expandable if they have child docs via
   `parent_doc_id` lineage)
3. **Agent executions** — running/failed/completed delegate runs

Groups are loaded via `group_service` → `database/groups.py`. Documents not in any
group appear as "direct saves." The data loader (`activity_data.py`) first loads
groups, then loads ungrouped docs, then agent executions, and merges them.

The Tree widget (`activity_tree.py`) handles expand/collapse, cursor tracking,
diff-based refresh, and column-aligned rendering via `render_label()`.

The view (`activity_view.py`) has a 3-pane layout: left-top (tree), left-bottom
(context/details), right (preview). It also embeds a `GroupPicker` widget at the
bottom for adding items to groups.

### Key files involved

| File | Lines | Role |
|------|-------|------|
| `ui/activity/activity_view.py` | ~1326 | Main view widget, all actions, preview |
| `ui/activity/activity_tree.py` | ~404 | Tree widget with render_label, diff refresh |
| `ui/activity/activity_items.py` | ~344 | ActivityItem ABC + DocumentItem, GroupItem, AgentExecutionItem |
| `ui/activity/activity_data.py` | ~217 | Data loader — DB queries, typed item construction |
| `ui/activity/group_picker.py` | ~310 | Inline group picker widget |
| `ui/activity/sparkline.py` | small | Sparkline for status bar |
| `ui/activity_browser.py` | ~87 | Thin wrapper for BrowserContainer |
| `ui/browser_container.py` | ~481 | App shell, screen switching |

### Group-related bindings in ActivityView

- `g` → `action_add_to_group` — show group picker
- `G` → `action_create_group` — create group from selected doc
- `u` → `action_ungroup` — remove from parent group

### Group-related actions/methods in ActivityView

- `action_add_to_group()`, `action_create_group()`, `action_ungroup()`
- `_show_group_summary()`, `_show_group_context()`
- `on_group_picker_group_selected()`, `on_group_picker_group_created()`,
  `on_group_picker_cancelled()`

### Data loading (activity_data.py)

- `_load_groups()` — queries `group_service.list_top_groups_with_counts()`,
  creates `GroupItem` instances
- `_load_direct_saves()` — queries recent docs, skips any in
  `group_service.get_all_grouped_document_ids()`
- `_load_agent_executions()` — queries execution_service

### What stays vs. what goes

**Stays (core value):**
- Status bar (active count, docs today, cost, sparkline, time)
- Document preview pane (right side)
- Context/details pane (left bottom)
- Agent execution items (running, failed, completed)
- Live log streaming for running executions
- Document items
- Fullscreen preview (Enter/f)
- Copy mode (c)
- Refresh timer
- Kill/dismiss execution (x)
- Create gist (i)

**Goes (grouping/hierarchy):**
- `GroupItem` class and all group rendering
- `GroupPicker` widget
- Group-related keybindings (g, G, u)
- Group-related actions and message handlers
- `_load_groups()` in data loader
- Filtering of grouped doc IDs in `_load_direct_saves()`
- `_show_group_summary()`, `_show_group_context()`
- Tree widget's expand/collapse for hierarchy
- Document parent-child expand in the activity view
- `activity_tree.py` (replaced by DataTable)

**Goes from ActivityItem hierarchy:**
- `GroupItem` class entirely
- `can_expand()` / `load_children()` abstract methods (no longer needed)
- `DocumentItem.has_children` field
- `DocumentItem.load_children()` implementation

## Implementation Plan

### Phase 1: Replace Tree with DataTable (core UI change)

**1a. Create new `ActivityTable` widget**

Replace `activity_tree.py` with `activity_table.py`. Use Textual's `DataTable`
widget (or `OptionList` if column alignment is easier — DataTable is preferred for
the table feel).

Table columns:
```
| Status | Title                        | Time  |   ID |
|--------|------------------------------|-------|------|
| 🔄     | analyzing auth module        |   2m  | #523 |
| ✅     | Security audit results       |   1h  | #521 |
| ❌     | check XSS vulnerabilities    |   3h  | #519 |
| 📄     | Architecture overview        |   1d  | #515 |
```

- Status column: icon based on item type + status (running agent = 🔄, completed
  doc = 📄, failed = ❌)
- Title column: fills remaining width
- Time column: compact relative time (2m, 1h, 3d)
- ID column: right-aligned doc/execution ID

Key behaviors:
- Cursor row highlighting (native DataTable behavior)
- Row selection triggers preview update
- No expand/collapse — purely flat
- Diff-based refresh to preserve cursor position (reuse the key-based approach
  from `refresh_from_items` but simpler — just update cell values)

**1b. Simplify `ActivityItem` hierarchy**

- Remove `GroupItem` entirely
- Remove `can_expand()`, `load_children()` abstract methods
- Keep `get_preview_content()` for the preview pane
- Remove `DocumentItem.has_children`, `DocumentItem.load_children()`
- Simplify `AgentExecutionItem` (already doesn't expand)
- Consider flattening to just `DocumentItem` and `AgentExecutionItem`

**1c. Simplify data loader**

- Remove `_load_groups()` entirely
- In `_load_direct_saves()`, remove the grouped-doc-ID filtering — just load
  all recent documents regardless of group membership
- Keep `_load_agent_executions()` as-is (already flat)
- Result: flat list of documents + agent executions, sorted by timestamp

**1d. Simplify `ActivityView`**

- Replace `ActivityTree` reference with `ActivityTable`
- Remove all group-related bindings (g, G, u)
- Remove all group-related actions and handlers
- Remove `GroupPicker` from compose()
- Remove `_show_group_summary()`, `_show_group_context()`
- Remove group-picker message handlers
- Simplify `_update_preview()` — remove group branch
- Simplify `_update_context_panel()` — remove group branch
- Remove expand/collapse actions (l, h) — no hierarchy
- Remove `on_tree_node_expanded`, `on_tree_node_collapsed` handlers
- Update `action_select` to just navigate (no expand/collapse logic)
- Update compose() to yield `ActivityTable` instead of `ActivityTree`

### Phase 2: Clean up dead code

**2a. Remove `group_picker.py`**

Delete `emdx/ui/activity/group_picker.py` entirely.

**2b. Remove `activity_tree.py`**

Delete `emdx/ui/activity/activity_tree.py` (replaced by `activity_table.py`).

**2c. Update `__init__.py`**

Update `emdx/ui/activity/__init__.py` if it exports anything group-related.

**2d. Update `activity_browser.py`**

Minor — update the help bar text to remove "Enter expand" since there's nothing
to expand.

**2e. Update `browser_container.py`**

No changes needed — it just mounts `ActivityBrowser`.

### Phase 3: Update tests

- Update or remove any tests that reference `GroupItem`, `ActivityTree`,
  `GroupPicker`, or group-related actions
- Add basic tests for the new `ActivityTable` widget

### Phase 4: Optional cleanup (separate PR)

These are NOT required for the redesign but could be done later:

- **CLI `emdx groups` command**: Still functional, still useful for CLI users.
  Leave it. The groups concept survives in the database and CLI — we're just
  removing it from the TUI Activity screen.
- **`database/groups.py`**: Keep. The DB layer is independent.
- **`services/group_service.py`**: Keep. Other code may use it.
- **Document parent-child lineage**: Keep in DB. Just don't render it
  hierarchically in the Activity screen.

## Risks and Considerations

1. **Information loss**: Documents that were previously grouped will now appear as
   individual items. Users who relied on groups to organize batches of delegate
   results will see a flat list. Mitigation: tags and search still work for
   finding related docs.

2. **DataTable refresh stability**: DataTable can be trickier than Tree for
   preserving cursor position during periodic refresh. May need to track the
   current row key and re-select after update.

3. **Scope creep**: The groups CLI commands, database tables, and service layer
   should NOT be removed in this PR. That's a separate conversation.

4. **The context panel**: With groups gone, the context panel (left-bottom) will
   only show document metadata. May want to repurpose it or remove it to give
   more space to the table.

## Out of Scope

- Removing `emdx groups` CLI command
- Removing groups database tables or service layer
- Changes to the Task browser (screen 2)
- Changes to the Q&A screen (screen 3)
- Adding new features (filtering, sorting options, etc.) — save for follow-up
