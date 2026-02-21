# Task TUI Research: Patterns & Recommendations for emdx

Research into popular terminal task management TUIs to inform improvements to emdx's task browser.

## Tools Surveyed

| Tool | Language | Layout | Stars |
|------|----------|--------|-------|
| [taskwarrior-tui](https://github.com/kdheepak/taskwarrior-tui) | Rust | List + detail split | ~4k |
| [Dooit](https://github.com/dooit-org/dooit) | Python (Textual) | Tree + list two-pane | ~2.7k |
| [Taskell](https://github.com/smallhadroncollider/taskell) | Haskell | Kanban columns | ~1.7k |
| [kanban-tui](https://github.com/Zaloog/kanban-tui) | Python (Textual) | Kanban + analytics | growing |
| [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) | Go (Bubble Tea) | Split + dependency graph | newer |
| [calcure](https://github.com/anufrievroman/calcure) | Python | Calendar + tasks | ~2.2k |
| [Todoman](https://github.com/pimutils/todoman) | Python | CLI + REPL | mature |
| [Ultralist](https://github.com/gammons/ultralist) | Go | CLI with agenda | mature |
| [jira-cli](https://github.com/ankitpokhrel/jira-cli) | Go | Hybrid CLI+TUI | ~4k |
| [linear-term](https://tylerjamesburch.com/blog/misc/linear-term) | Python (Textual) | Three-panel | newer |

## Layout Patterns

| Pattern | Used By | Best For |
|---------|---------|----------|
| **List + detail split** | taskwarrior-tui, beads_viewer, linear-term | General task management (most versatile) |
| **Tree + list two-pane** | Dooit | Hierarchical/categorized work |
| **Kanban columns** | Taskell, kanban-tui | Workflow-stage-based management |
| **Table (spreadsheet-like)** | taskwarrior-tui, Jira TUIs | High-density data, many attributes |
| **Three-panel (filter/list/detail)** | linear-term | Complex filtering with detail view |

**The dominant pattern is list + detail split pane** -- what emdx already uses. Most successful
TUIs show a summary list on one side and full details on the other. This is the same pattern
lazygit popularized.

## Information Density: What to Show at a Glance vs. on Demand

### List Row (at a glance -- universally shown)

- Task title/description (truncated to fit)
- Status indicator (color + symbol: `[x]`, `[>]`, `[ ]`, `[!]`)
- Priority (color-coded: red/yellow/green, or symbols: `!!!`, `!!`, `!`)
- Due date or relative time ("today", "overdue", "3d")
- Project/workspace/category (short label)

### Detail View (on selection -- revealed on demand)

- Full description/notes (rendered as markdown where supported)
- All metadata: tags, created/modified dates, assignee, effort estimate
- Sub-tasks/checklists
- Comments/annotations
- Dependencies (blocked by / blocking)
- Activity history/changelog
- Links and attachments

**Key principle: Progressive disclosure with exactly 2 levels.** Show 4-6 fields at the list
level. Reveal everything else in the detail pane. Don't add a third level.

## Navigation: The Universal Standard

Vim-style keybindings are universal across every tool surveyed:

| Key | Action | Notes |
|-----|--------|-------|
| `j`/`k` | Up/down within list | Universal |
| `h`/`l` | Left/right between panels or columns | Universal |
| `g`/`G` | Top/bottom | Universal |
| `J`/`K` or `Ctrl-d`/`Ctrl-u` | Page up/down | Common |
| `/` | Search/filter | Universal |
| `?` | Help | Universal |
| `a` | Add/create | Very common |
| `d` | Done/delete (varies) | Common |
| `e` | Edit | Common |
| `m` | Modify/move | Common |
| `q` | Quit | Universal |
| `Enter` | Open/select/confirm | Universal |
| `Esc` | Cancel/back | Universal |
| `Tab` | Switch panes/panels | Common |

## Filtering & Sorting Approaches

| Capability | Tools | Notes |
|-----------|-------|-------|
| **Live filter bar** (type to narrow) | taskwarrior-tui, beads_viewer | Most immediate UX |
| **Structured filters** (`field:value`) | Ultralist, jira-tui (JQL) | Most powerful |
| **Sort menus** | Dooit, Todoman | Simple and effective |
| **Negation filters** (`-project:X`) | Ultralist | Nice for exclusion |
| **Quick filter keys** (`o`/`c`/`r`) | beads_viewer | Zero-latency status filters |
| **Saved filter tabs** | jira-tui, JiraTUI | For recurring queries |
| **Tag-based filtering** | taskwarrior-tui, Dooit | Good for cross-cutting concerns |

## Status Visualization

- **Color is king.** Every tool uses color to indicate status. Overdue = red, active =
  green/cyan, blocked = gray/dim, completed = strikethrough or muted.
- **Unicode symbols** are widely used: checkmarks, dots, arrows, warning triangles.
- **Urgency scores** (taskwarrior-tui) combine priority, due date, and other factors into a
  single sortable number.

## Standout Innovations

### Graph Intelligence (beads_viewer)

Uses PageRank and dependency graph analysis to surface bottlenecks and suggest task priority.
Robot mode (`--robot-insights`, `--robot-plan`, `--robot-priority`) outputs JSON for AI agents.
Relevant to emdx's "agents populate, humans curate" philosophy.

### AI Agent Integration (kanban-tui, beads_viewer)

kanban-tui has a Claude backend and MCP server mode. beads_viewer has `--robot-*` JSON APIs.
Emerging pattern: task TUIs designed for both human and AI consumption.

### Python Extensibility (Dooit)

Config file is Python -- users can script custom bar widgets, automate workflows, and integrate
with external services. Community themes and utility extensions ecosystem.

### Standards-Based Storage (Todoman, Taskell)

Todoman uses iCalendar for CalDAV sync. Taskell uses Markdown for clean git diffs. Both make
data portable without the tool.

### Background Sync (taskwarrior-tui, Ultralist)

Automatic periodic syncing with offline buffering keeps the local view fresh.

### Mouse + Keyboard Hybrid (kanban-tui)

Both drag-and-drop mouse interaction AND full vim-style keyboard navigation.

### Custom Shell Scripts (taskwarrior-tui)

Shortcut keys 1-9 bound to arbitrary shell scripts -- simple but powerful extensibility.

### Privacy Mode (calcure)

Toggle all content to dots for screen sharing.

### Dependency Management (kanban-tui, beads_viewer)

Task dependencies with blocking prevention, circular dependency detection. beads_viewer adds
critical path analysis.

## Design Principles (Distilled Across All Tools)

1. **State-Action-State visibility** (lazygit philosophy): Show current state, available
   actions, and how state changed after an action. The TUI advantage over CLI is that all three
   are always visible.

2. **Progressive disclosure with exactly 2 levels:** List row (4-6 fields) and detail view
   (everything). Don't add a third level.

3. **Fewer keystrokes wins:** If an action can be done in fewer keypresses, it should be.
   Single-key actions for common operations.

4. **Discoverability through `?` help:** Every successful TUI offers a `?` key that shows
   available keybindings in context.

5. **Consistency with vim conventions:** j/k/h/l/g/G// are expected. Tools that deviate
   frustrate experienced terminal users.

6. **Color as semantic encoding:** Red = urgent/overdue, green = done/active, dim =
   blocked/inactive, yellow = warning. Users should never have to read text to understand
   status.

7. **Dual output modes:** A good terminal tool works both as an interactive TUI and a CLI with
   `--json` output. This serves both humans and agents.

8. **Data portability:** Store data in open, human-readable formats (Markdown, iCalendar, JSON,
   SQLite) so users are never locked in.

## Current emdx Task Browser: Gaps Identified

The current task browser (`emdx/ui/task_view.py`) has a solid two-pane foundation but several
gaps compared to the surveyed tools:

| Gap | Impact | Priority |
|-----|--------|----------|
| **No filtering UI** | All 200 tasks shown; no way to filter by epic, project, priority, or search | High |
| **No sorting options** | Always status-order then insertion-order; can't sort by priority/date | High |
| **Help (`?`) unimplemented** | Users can't discover keybindings | High |
| **Tab/focus navigation stubbed** | Can't keyboard-navigate between panes | Medium |
| **No live filter bar (`/`)** | Can't quickly narrow task list by typing | Medium |
| **No quick status actions** | Can't mark tasks done/active from TUI (must use CLI) | Medium |
| **Limited list info density** | Only shows icon + title; no priority, epic, or age | Medium |
| **Task keybinding context missing** | `context.py` lacks `TASK_NORMAL`; can't register task-specific bindings | Low |
| **No quick-filter keys** | No single-key toggles for status groups (e.g., `o` for open only) | Low |
| **Static detail rendering** | Detail pane doesn't auto-refresh; requires manual `r` | Low |

## Recommended Improvements (Priority Order)

### 1. Live Filter Bar (`/` key)

Add a text input that filters the task list in real-time as the user types. This is the single
highest-impact improvement across all surveyed tools.

### 2. Richer List Items

Show more info per task row: priority indicator, epic short label, relative age. Target 4-5
fields per row like taskwarrior-tui.

### 3. Quick Status Actions

Add keybindings to change task status directly: `d` for done, `a` for active, `b` for blocked.
Eliminates the round-trip to CLI.

### 4. Implement `?` Help Overlay

Show a keybinding reference card. Every successful TUI has this.

### 5. Sort Controls

Add a sort menu or cycle-sort keybinding (e.g., `s` cycles through priority, created, updated).

### 6. Quick Filter Keys

Single-key toggles for status groups: `o` (open/ready only), `a` (active only), `*` (all).
Inspired by beads_viewer's zero-latency filtering.

### 7. Focus Navigation Between Panes

Implement `Tab`/`Shift+Tab` to move focus between list and detail panes, enabling keyboard
scrolling of the detail view.

### 8. Epic/Category Grouping Toggle

Option to group tasks by epic instead of status. Useful when working across multiple epics.
