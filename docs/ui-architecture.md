# EMDX UI Architecture

## TUI Framework: Textual

EMDX uses the [Textual](https://textual.textualize.io/) framework for its terminal user interface, providing a rich, responsive experience with modern terminal features.

### Why Textual?
- **Modern TUI** - Rich widgets, CSS styling, smooth animations
- **Reactive Design** - Automatic UI updates when data changes
- **Cross-platform** - Works consistently across different terminals
- **Developer-friendly** - Hot reload, debugging tools, comprehensive docs

## UI Component Hierarchy

```
BrowserContainer (App — top-level)
├── BrowserContainerWidget (mount point)
│   └── Container#browser-mount
│       ├── ActivityBrowser (press '1' — default)
│       │   ├── ActivityView#activity-view
│       │   │   ├── Static#status-bar
│       │   │   ├── Horizontal#activity-panel
│       │   │   │   ├── Vertical#activity-list-section
│       │   │   │   │   ├── Static#activity-header ("DOCUMENTS")
│       │   │   │   │   └── ActivityTable#activity-table
│       │   │   │   └── Vertical#context-section
│       │   │   │       ├── Static#context-header ("DETAILS")
│       │   │   │       └── RichLog#context-content
│       │   │   └── Vertical#preview-panel
│       │   │       ├── Static#preview-header ("PREVIEW")
│       │   │       ├── RichLog#preview-content
│       │   │       └── Log#preview-copy (hidden, for copy mode)
│       │   └── Static#help-bar
│       └── TaskBrowser (press '2')
│           ├── TaskView#task-view
│           └── Static#task-help-bar
├── CommandPaletteScreen (modal, ctrl+k / ctrl+p)
├── ThemeSelectorScreen (modal, backslash)
└── DocumentPreviewScreen (modal, fullscreen doc view)
```

Only **two browser modes** exist: ActivityBrowser (documents) and TaskBrowser (tasks). The container swaps between them.

## Core UI Components

### 1. BrowserContainer — App Shell

```python
class BrowserContainer(App[None]):
    """Top-level app that swaps browser widgets."""

    BINDINGS = [
        Binding("1", "switch_activity", "Docs"),
        Binding("2", "switch_tasks", "Tasks"),
        Binding("backslash", "cycle_theme", "Theme"),
        Binding("ctrl+k", "open_command_palette", "Search"),
        Binding("ctrl+p", "open_command_palette", "Search"),
        Binding("ctrl+t", "toggle_theme", "Toggle Dark/Light"),
    ]
```

**Key Features:**
- **Modal switching** — One browser visible at a time, mounted into `#browser-mount`
- **State preservation** — `save_state()` / `restore_state()` when switching browsers
- **Theme management** — Persists theme selection, supports dark/light toggle
- **Command palette** — `ctrl+k` opens fuzzy search for documents and commands
- **Document navigation** — `action_select_doc()` handles cross-browser doc links via `@click` meta

### 2. ActivityBrowser — Document Browser (press '1')

The default view. Wraps `ActivityView` with a help bar.

```python
class ActivityBrowser(Widget):
    """Browser wrapper for ActivityView — Mission Control."""
```

#### ActivityView — The Core Document Interface

A flat table of recent documents with a preview pane. No hierarchy or tree — just a scannable list sorted by time.

**Layout (wide terminal, ≥120 cols):**
```
┌─────────────────────────────────┬──────────────┐
│ DOCUMENTS (ActivityTable)       │ DETAILS      │
│ (activity-list-section, 70%)    │ (context,30%)│
├─────────────────────────────────┴──────────────┤
│ PREVIEW (preview-panel, 60% height)            │
│ Document content rendered as markdown          │
└────────────────────────────────────────────────┘
```

On narrow terminals (<120 cols), the context sidebar hides and the table fills the full width.

**Bindings:**
| Key | Action | Description |
|-----|--------|-------------|
| `j` / `k` | cursor_down / cursor_up | Navigate documents |
| `Enter` / `f` | fullscreen | Open document fullscreen |
| `r` | refresh | Refresh document list |
| `i` | create_gist | Create a new document |
| `Tab` / `Shift+Tab` | focus_next / focus_prev | Switch panes |
| `?` | show_help | Show keybinding help |
| `c` | toggle_copy_mode | Toggle copy-friendly mode |
| `w` | cycle_doc_type_filter | Cycle: User Docs → Wiki → All |
| `z` | toggle_zoom | Zoom current pane |

**Components:**
- **ActivityTable** — DataTable showing documents with columns for time, title, project, tags
- **Context Panel** — RichLog showing metadata for the selected document (right sidebar)
- **Preview Panel** — RichLog rendering document content as markdown (bottom pane)
- **ActivityDataLoader** — Loads document data from the database

**Reactive features:**
- Auto-refresh every 1 second via `set_interval`
- Responsive sidebar: hides/shows based on terminal width
- Doc type filtering: cycle between user docs, wiki articles, and all
- Zoom mode: expand table or preview to full screen

### 3. TaskBrowser — Task Management (press '2')

Wraps `TaskView` with a help bar and status actions.

```python
class TaskBrowser(HelpMixin, Widget):
    """Browser wrapper for TaskView."""
```

**Task action bindings:**
| Key | Action | Description |
|-----|--------|-------------|
| `d` | mark_done | Mark task as done |
| `a` | mark_active | Mark task as active |
| `b` | mark_blocked | Mark task as blocked |
| `w` | mark_wontdo | Mark task as won't do |
| `u` | mark_open | Reopen task |
| `/` | filter | Filter tasks |
| `?` | show_help | Show keybinding help |

### 4. Command Palette (ctrl+k / ctrl+p)

Modal search interface for quick navigation:
- **Document search** — Fuzzy search across all document titles
- **Command execution** — Navigate to browsers, change theme, refresh, quit
- Located in `emdx/ui/command_palette/`

### 5. Theme System

- **Multiple themes** — emdx-dark, emdx-light, emdx-nord, emdx-solarized-dark, emdx-solarized-light
- **Quick toggle** — `ctrl+t` switches between dark/light variants
- **Theme selector** — `backslash` opens a theme picker modal
- **Persistent** — Theme choice saved to config via `set_theme()`
- Located in `emdx/ui/themes.py` and `emdx/ui/theme_selector.py`

## Key Binding System

### Global Bindings (BrowserContainer)
| Key | Action | Description |
|-----|--------|-------------|
| `1` | switch_activity | Switch to document browser |
| `2` | switch_tasks | Switch to task browser |
| `\` | cycle_theme | Open theme selector |
| `ctrl+k` / `ctrl+p` | open_command_palette | Open command palette |
| `ctrl+t` | toggle_theme | Quick dark/light toggle |
| `q` | quit | Quit (context-sensitive — ignored in modals) |

### Keybinding Registry
The `emdx/ui/keybindings/` module provides conflict detection:
- **KeybindingRegistry** — Registers all bindings from all widgets
- **Conflict detection** — Warns about overlapping keys at different scopes
- **Extraction** — `extract_all_keybindings()` scans widget classes for bindings

## Styling & Theming

Textual CSS is used for all layout and styling. Each widget defines `DEFAULT_CSS` inline.

**Responsive design:**
- Sidebar hides at <120 columns (`sidebar-hidden` CSS class)
- Zoom mode toggles pane visibility via CSS classes (`zoom-content`, `zoom-list`)
- Panel borders adapt to theme variables (`$primary`, `$secondary`, `$surface`)

## Modals

Located in `emdx/ui/modals.py`:
- **DocumentPreviewScreen** — Fullscreen document viewer
- **HelpMixin** — Reusable help dialog showing categorized keybindings
- **ThemeSelectorScreen** — Theme picker
- **CommandPaletteScreen** — Fuzzy search + command execution

## Testing UI Components

See `tests/test_task_browser.py` for canonical patterns:

```python
class TaskTestApp(App):
    def compose(self):
        yield TaskBrowser()

@pytest.mark.asyncio
async def test_task_browser():
    app = TaskTestApp()
    async with app.run_test() as pilot:
        await pilot.press("j")  # Navigate down
        await pilot.press("d")  # Mark done
```

**Testing tips:**
- `Static.content` returns `VisualType` — wrap with `str()` for assertions
- `RichLog.lines` contains `Strip` objects — use `.text` property
- Mock `get_theme` to return `"textual-dark"` to avoid `InvalidThemeError`
- OptionList doesn't auto-fire `OptionHighlighted` on mount — press `j` then `k` to trigger
- Mouse clicks need explicit `offset=(x, y)` to hit specific rows

## Architecture Notes

- **`@click` meta actions** resolve only on the widget that received the click, not parent widgets. Use `app.action_name(...)` prefix to target the App.
- **DOM-mutating `@click` actions must be sync + `run_worker`** to avoid deadlocking the message loop. See `BrowserContainer.action_select_doc()`.
- **Terminal state corruption** can occur when background threads import heavy libraries (torch, sentence-transformers). Save/restore terminal state with `termios`.
- **Never add `on_click`/`on_mouse_down` to parent widgets** — it breaks all mouse interaction globally.
