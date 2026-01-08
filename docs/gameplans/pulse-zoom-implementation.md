# Gameplan: Pulse+Zoom TUI Implementation

**Status:** 🎯 🚀
**Created:** 2025-01-07
**Last Updated:** 2025-01-07 (Verification Pass #3)
**Related Docs:** #1981 (Initial Concepts), #2015 (Round 2), #2018 (Final Analysis)
**Spec:** `docs/pulse-zoom-tui-spec.md`

---

## Executive Summary

Replace the current `ControlCenterBrowser` (accessible via 'c' key) with a new `PulseBrowser` that implements a three-level semantic zoom interface for unified task, workflow, and execution management.

**Core Value:** See everything at a glance (Zoom 0), dive into specifics (Zoom 1), and get full details (Zoom 2) - with state preserved across transitions.

---

## Current State Analysis

### Verified Codebase Patterns (Verification Pass #3)

All patterns below have been verified against actual source code as of 2025-01-07.

#### Task Model (`emdx/models/tasks.py` - 217 lines)

```python
# Status values - USE THESE EXACTLY (line 8)
STATUSES = ('open', 'active', 'blocked', 'done', 'failed')

# Available functions (verified signatures):
create_task(title, description="", priority=3, gameplan_id=None, project=None, depends_on=None) -> int
get_task(task_id: int) -> Optional[dict[str, Any]]
list_tasks(status: Optional[list[str]] = None, gameplan_id=None, project=None, limit=50) -> list[dict[str, Any]]
update_task(task_id: int, **kwargs) -> bool
delete_task(task_id: int) -> bool
get_dependencies(task_id: int) -> list[dict[str, Any]]  # Tasks this depends ON
get_ready_tasks(gameplan_id: Optional[int] = None) -> list[dict[str, Any]]  # Open tasks with all deps done
add_dependency(task_id: int, depends_on: int) -> bool  # Returns False if would cycle
log_progress(task_id: int, message: str) -> int
get_task_log(task_id: int, limit=20) -> list[dict[str, Any]]
get_gameplan_stats(gameplan_id: int) -> dict[str, Any]  # {'total': N, 'done': N, 'by_status': {...}}

# NOTE: get_dependents() does NOT exist - must add in Phase 3
# Will need SQL: SELECT t.* FROM tasks t JOIN task_deps d ON t.id = d.task_id WHERE d.depends_on = ?
```

#### Tags Model (`emdx/models/tags.py` - 367 lines)

```python
# Key function for gameplan search:
search_by_tags(
    tag_names: list[str],
    mode: str = "all",  # "all" = must have all tags, "any" = has any
    project: Optional[str] = None,
    limit: int = 20
) -> list[dict[str, Any]]

# Returns: [{'id': int, 'title': str, 'project': str, 'created_at': datetime, 'access_count': int, 'tags': str}]
# Tags are comma-separated string

# Example usage for active gameplans:
gameplans = search_by_tags(["🎯", "🚀"], mode="all", limit=10)
```

#### Execution Model (`emdx/models/executions.py` - 350 lines)

```python
@dataclass
class Execution:
    id: int
    doc_id: int
    doc_title: str
    status: str  # 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: Optional[datetime] = None
    log_file: str = ""
    exit_code: Optional[int] = None
    working_dir: Optional[str] = None
    pid: Optional[int] = None

    @property
    def duration(self) -> Optional[float]: ...
    @property
    def is_running(self) -> bool: ...
    @property
    def is_zombie(self) -> bool: ...
    @property
    def log_path(self) -> Path: ...

# Available functions:
create_execution(doc_id: int, doc_title: str, log_file: str, working_dir=None, pid=None) -> int
get_execution(exec_id: str) -> Optional[Execution]
get_recent_executions(limit: int = 20) -> List[Execution]
get_running_executions() -> List[Execution]
update_execution_status(exec_id: int, status: str, exit_code: Optional[int] = None) -> None
get_execution_stats() -> dict  # {'total', 'recent_24h', 'running', 'completed', 'failed'}
```

#### LogStream Pattern (`emdx/services/log_stream.py` - 128 lines)

```python
class LogStreamSubscriber(ABC):
    """Interface for components that consume log updates."""

    @abstractmethod
    def on_log_content(self, new_content: str) -> None:
        """Called when new log content is available."""
        pass

    @abstractmethod
    def on_log_error(self, error: Exception) -> None:
        """Called when log reading encounters an error."""
        pass


class LogStream:
    """Event-driven log file streaming with file watching."""

    def __init__(self, log_file_path: Path): ...
    def subscribe(self, subscriber: LogStreamSubscriber) -> None: ...
    def unsubscribe(self, subscriber: LogStreamSubscriber) -> None: ...
    def get_initial_content(self) -> str: ...
```

#### BrowserContainer Integration (`emdx/ui/browser_container.py` - 258 lines)

```python
# Lines 157-159 - Current 'control' browser registration:
elif browser_type == "control":
    from .control_center import ControlCenterBrowser
    self.browsers[browser_type] = ControlCenterBrowser()

# Change to:
elif browser_type == "control":
    from .pulse_browser import PulseBrowser
    self.browsers[browser_type] = PulseBrowser()

# Key routing (lines 220-223):
elif key == "c" and self.current_browser == "document":
    await self.switch_browser("control")
    event.stop()
    return
```

#### Display Toggle Pattern (verified in `document_browser.py`)

```python
# CORRECT - Use display property directly
widget.display = False  # Hide
widget.display = True   # Show

# NOT CSS classes - Textual uses display property
```

#### Reactive Variables with Watchers (standard Textual pattern)

```python
from textual.reactive import reactive

class MyWidget(Widget):
    zoom_level = reactive(0)

    def watch_zoom_level(self, old_value: int, new_value: int) -> None:
        """Called automatically when zoom_level changes."""
        pass
```

#### CSS Variables (verified from existing browsers)

```python
DEFAULT_CSS = """
MyWidget {
    layout: vertical;
    height: 100%;
}

.header {
    height: 1;
    background: $boost;
    padding: 0 1;
    text-style: bold;
}

.muted {
    color: $text-muted;
}

.status {
    dock: bottom;
    height: 1;
    background: $surface;
    padding: 0 1;
}
"""
```

### Existing UI Files (38 total in `emdx/ui/`)

Key files to reference:
- `browser_container.py` - Main container, browser switching
- `control_center.py` - Current implementation (271 lines, to be replaced)
- `document_browser.py` - DataTable patterns, vim bindings, search toggle
- `log_browser.py` - LogStream integration, RichLog display (625 lines)
- `stages/base.py` - OverlayStage pattern for modals

Services to use:
- `emdx/services/log_stream.py` - Event-driven log streaming
- `emdx/services/file_watcher.py` - OS-level file watching

---

## Architecture

```
BrowserContainer
├── DocumentBrowser (existing)
├── FileBrowser (existing)
├── GitBrowser (existing)
├── LogBrowser (existing)
├── AgentBrowser (existing)
└── PulseBrowser (NEW - replaces ControlCenterBrowser)
    │
    ├── ZoomState (dataclass - preserves state across zoom transitions)
    │
    ├── Zoom0Container (Overview)
    │   ├── PulseView (default) - real-time dashboard
    │   ├── KanbanView - column-based board
    │   └── TimelineView - horizontal time axis
    │
    ├── Zoom1Container (Focus)
    │   ├── TaskDetailPanel (left 50%)
    │   └── SmartListPanel (right 50%) - with dep glyphs
    │
    ├── Zoom2Container (Deep)
    │   └── LogViewer - full-screen log with streaming
    │
    ├── AssistantPanel (slide-in overlay, 40% width)
    │
    └── StatusBar (context-aware shortcuts)
```

---

## Phase 1: Foundation (3-4 days)

### Goal
Create PulseBrowser shell that replaces ControlCenterBrowser with basic zoom switching.

### Tasks

#### 1.1 Create PulseBrowser Shell
**File:** `emdx/ui/pulse_browser.py`

```python
"""Pulse+Zoom browser - unified task/workflow/execution view."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from emdx.models import tasks
from emdx.models.executions import get_running_executions, get_execution_stats

logger = logging.getLogger(__name__)

# Reuse existing icons from control_center.py
ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


class PulseBrowser(Widget):
    """Three-level zoom browser for tasks and workflows."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("z", "zoom_in", "Zoom In"),
        Binding("Z", "zoom_out", "Zoom Out"),
        Binding("enter", "zoom_in", "Select"),
        Binding("escape", "zoom_out", "Back"),
        Binding("0", "goto_zoom0", "Overview"),
        Binding("1", "goto_zoom1", "Focus"),
        Binding("2", "goto_zoom2", "Deep"),
        Binding("v", "toggle_view", "View Mode"),
        Binding("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    PulseBrowser {
        layout: vertical;
        height: 100%;
    }

    .zoom-container {
        height: 1fr;
    }

    #pulse-status {
        dock: bottom;
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    """

    zoom_level = reactive(0)
    view_mode = reactive("pulse")  # pulse, kanban, timeline

    def __init__(self):
        super().__init__()
        self.state = None  # Will hold ZoomState

    def compose(self) -> ComposeResult:
        yield Vertical(id="zoom0", classes="zoom-container")
        yield Vertical(id="zoom1", classes="zoom-container")
        yield Vertical(id="zoom2", classes="zoom-container")
        yield Static("", id="pulse-status")

    async def on_mount(self) -> None:
        """Initialize the browser."""
        logger.info("PulseBrowser mounted")

        # Hide zoom 1 and 2 initially
        self.query_one("#zoom1").display = False
        self.query_one("#zoom2").display = False

        # Initialize state
        from .pulse.state import ZoomState
        self.state = ZoomState()

        # Load initial data
        await self._load_zoom0_data()
        self._update_status()

    def watch_zoom_level(self, old_level: int, new_level: int) -> None:
        """React to zoom level changes."""
        logger.info(f"Zoom level changed: {old_level} -> {new_level}")

        # Hide all containers, show only current
        for i in range(3):
            container = self.query_one(f"#zoom{i}")
            container.display = (i == new_level)

        self._update_status()

    def watch_view_mode(self, old_mode: str, new_mode: str) -> None:
        """React to view mode changes."""
        logger.info(f"View mode changed: {old_mode} -> {new_mode}")
        self._update_status()

    async def _load_zoom0_data(self) -> None:
        """Load data for zoom 0 views."""
        # Placeholder - will be implemented in 1.4
        pass

    def _update_status(self) -> None:
        """Update status bar with context-aware shortcuts."""
        zoom_names = ["Overview", "Focus", "Deep"]
        view_text = f"[{self.view_mode}]" if self.zoom_level == 0 else ""

        status_text = (
            f"Zoom {self.zoom_level}: {zoom_names[self.zoom_level]} {view_text} | "
            "z/Z=zoom | v=view | r=refresh | q=back"
        )

        try:
            status = self.query_one("#pulse-status", Static)
            status.update(status_text)
        except Exception:
            pass

    def action_cursor_down(self) -> None:
        """Move cursor down - delegate to current zoom view."""
        pass

    def action_cursor_up(self) -> None:
        """Move cursor up - delegate to current zoom view."""
        pass

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        pass

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        pass

    def action_zoom_in(self) -> None:
        """Zoom in to more detail."""
        if self.zoom_level < 2:
            self.zoom_level += 1

    def action_zoom_out(self) -> None:
        """Zoom out to less detail."""
        if self.zoom_level > 0:
            self.zoom_level -= 1

    def action_goto_zoom0(self) -> None:
        """Jump to zoom level 0."""
        self.zoom_level = 0

    def action_goto_zoom1(self) -> None:
        """Jump to zoom level 1."""
        self.zoom_level = 1

    def action_goto_zoom2(self) -> None:
        """Jump to zoom level 2."""
        self.zoom_level = 2

    def action_toggle_view(self) -> None:
        """Cycle through view modes at zoom 0."""
        if self.zoom_level == 0:
            modes = ["pulse", "kanban", "timeline"]
            current_idx = modes.index(self.view_mode)
            self.view_mode = modes[(current_idx + 1) % len(modes)]

    async def action_refresh(self) -> None:
        """Refresh current view."""
        if self.zoom_level == 0:
            await self._load_zoom0_data()
```

#### 1.2 Register in BrowserContainer
**File:** `emdx/ui/browser_container.py`

Change lines 157-159 from:
```python
elif browser_type == "control":
    from .control_center import ControlCenterBrowser
    self.browsers[browser_type] = ControlCenterBrowser()
```

To:
```python
elif browser_type == "control":
    from .pulse_browser import PulseBrowser
    self.browsers[browser_type] = PulseBrowser()
```

#### 1.3 Create ZoomState Dataclass
**File:** `emdx/ui/pulse/__init__.py`
```python
"""Pulse+Zoom TUI components."""
```

**File:** `emdx/ui/pulse/state.py`

```python
"""State management for Pulse+Zoom browser."""

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class ZoomState:
    """State preserved across zoom transitions."""

    # Zoom 0 state
    zoom0_view: str = "pulse"  # pulse, kanban, timeline
    zoom0_selected_id: Optional[int] = None  # Task or gameplan ID
    zoom0_scroll_position: int = 0
    zoom0_expanded_gameplans: Set[int] = field(default_factory=set)

    # Zoom 1 state
    zoom1_task_id: Optional[int] = None
    zoom1_scroll_position: int = 0
    zoom1_selected_related: Optional[int] = None

    # Zoom 2 state
    zoom2_execution_id: Optional[int] = None
    zoom2_scroll_position: int = 0
    zoom2_live_mode: bool = True
    zoom2_search_query: str = ""

    # Cross-cutting
    assistant_visible: bool = False
```

#### 1.4 Create Basic Zoom0 PulseView
**File:** `emdx/ui/pulse/zoom0/__init__.py`
```python
"""Zoom 0 overview views."""
```

**File:** `emdx/ui/pulse/zoom0/pulse_view.py`

```python
"""Pulse view - real-time dashboard for zoom 0."""

import logging
from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.models import tasks
from emdx.models.executions import get_running_executions, get_execution_stats
from emdx.models.tags import search_by_tags

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


class PulseView(Widget):
    """Real-time dashboard view for zoom 0."""

    DEFAULT_CSS = """
    PulseView {
        layout: horizontal;
        height: 100%;
    }

    .pulse-column {
        width: 1fr;
        padding: 0 1;
    }

    .pulse-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    DataTable {
        height: auto;
        max-height: 15;
    }
    """

    def __init__(self):
        super().__init__()
        self.active_tasks: List[Dict[str, Any]] = []
        self.gameplans: List[Dict[str, Any]] = []
        self.blocked_tasks: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left column - Active & Gameplans
            with Vertical(classes="pulse-column"):
                yield Static("● ACTIVE NOW", classes="pulse-header")
                yield DataTable(id="active-table", cursor_type="row")
                yield Static("🎯 GAMEPLANS", classes="pulse-header")
                yield DataTable(id="gameplan-table", cursor_type="row")

            # Right column - Health & Blocked
            with Vertical(classes="pulse-column"):
                yield Static("📊 SYSTEM HEALTH", classes="pulse-header")
                yield Static("", id="health-stats")
                yield Static("⚠ BLOCKED", classes="pulse-header")
                yield DataTable(id="blocked-table", cursor_type="row")

    async def on_mount(self) -> None:
        """Setup tables and load data."""
        # Setup active tasks table
        active_table = self.query_one("#active-table", DataTable)
        active_table.add_column("", width=2)
        active_table.add_column("Task", width=35)
        active_table.add_column("Time", width=6)

        # Setup gameplan table
        gp_table = self.query_one("#gameplan-table", DataTable)
        gp_table.add_column("", width=2)
        gp_table.add_column("Title", width=30)
        gp_table.add_column("Progress", width=10)

        # Setup blocked table
        blocked_table = self.query_one("#blocked-table", DataTable)
        blocked_table.add_column("", width=2)
        blocked_table.add_column("Task", width=30)
        blocked_table.add_column("Blocked By", width=10)

        await self.load_data()

    async def load_data(self) -> None:
        """Load all pulse view data."""
        try:
            # Load active tasks (status is a list)
            self.active_tasks = tasks.list_tasks(status=['active'], limit=10)
            await self._update_active_table()

            # Load gameplans (docs tagged with 🎯 and 🚀)
            self.gameplans = search_by_tags(["🎯", "🚀"], mode="all", limit=10)
            await self._update_gameplan_table()

            # Load blocked tasks
            self.blocked_tasks = tasks.list_tasks(status=['blocked'], limit=10)
            await self._update_blocked_table()

            # Update health stats
            await self._update_health_stats()

        except Exception as e:
            logger.error(f"Error loading pulse data: {e}", exc_info=True)

    async def _update_active_table(self) -> None:
        """Update the active tasks table."""
        table = self.query_one("#active-table", DataTable)
        table.clear()

        if not self.active_tasks:
            table.add_row("", "[dim]No active tasks[/dim]", "")
            return

        for task in self.active_tasks:
            title = task['title'][:35] if len(task['title']) > 35 else task['title']
            table.add_row(ICONS['active'], title, "—")

    async def _update_gameplan_table(self) -> None:
        """Update the gameplan table."""
        table = self.query_one("#gameplan-table", DataTable)
        table.clear()

        if not self.gameplans:
            table.add_row("", "[dim]No active gameplans[/dim]", "")
            return

        for gp in self.gameplans:
            stats = tasks.get_gameplan_stats(gp['id'])
            total = stats['total']
            done = stats['done']

            if total == 0:
                progress = "[dim]—[/dim]"
            else:
                pct = int((done / total) * 100)
                bars = "█" * (pct // 10) + "░" * (10 - pct // 10)
                progress = f"{bars} {pct}%"

            title = gp['title'][:30] if len(gp['title']) > 30 else gp['title']
            table.add_row("🎯", title, progress)

    async def _update_blocked_table(self) -> None:
        """Update the blocked tasks table."""
        table = self.query_one("#blocked-table", DataTable)
        table.clear()

        if not self.blocked_tasks:
            table.add_row("", "[dim]No blocked tasks[/dim]", "")
            return

        for task in self.blocked_tasks:
            title = task['title'][:30] if len(task['title']) > 30 else task['title']
            # Get what's blocking this task
            deps = tasks.get_dependencies(task['id'])
            blocking = [d for d in deps if d['status'] != 'done']
            blocked_by = f"← #{blocking[0]['id']}" if blocking else "?"
            table.add_row(ICONS['blocked'], title, blocked_by)

    async def _update_health_stats(self) -> None:
        """Update system health statistics."""
        try:
            stats = get_execution_stats()
            running = get_running_executions()

            health_text = (
                f"Running: {len(running)}  |  "
                f"Completed: {stats.get('completed', 0)}  |  "
                f"Failed: {stats.get('failed', 0)}  |  "
                f"Last 24h: {stats.get('recent_24h', 0)}"
            )

            health_widget = self.query_one("#health-stats", Static)
            health_widget.update(health_text)
        except Exception as e:
            logger.error(f"Error updating health stats: {e}")
```

### Phase 1 Deliverables
- [ ] 'c' key opens PulseBrowser instead of ControlCenterBrowser
- [ ] Basic task list visible at Zoom 0
- [ ] z/Z keys change zoom level (shows empty containers for zoom 1/2)
- [ ] Status bar shows current zoom level and shortcuts
- [ ] State dataclass defined

### Phase 1 Files
```
emdx/ui/pulse_browser.py         # Main browser widget
emdx/ui/pulse/__init__.py        # Package init
emdx/ui/pulse/state.py           # ZoomState dataclass
emdx/ui/pulse/zoom0/__init__.py  # Zoom 0 package
emdx/ui/pulse/zoom0/pulse_view.py # Dashboard view
```

---

## Phase 2: Complete Zoom Levels (4-5 days)

### Goal
Implement all three zoom levels with view toggles.

### Tasks

#### 2.1 Zoom0 View Modes

**KanbanView** (`zoom0/kanban_view.py`):
- 4 columns: Open, Active, Blocked, Done
- Cards show task ID, title, dependency counts
- h/l navigation between columns
- j/k navigation within column

**TimelineView** (`zoom0/timeline_view.py`):
- Horizontal time axis (configurable: 4h, 8h, 24h)
- Tasks as horizontal bars
- Running tasks extend to NOW marker
- Swimlanes by gameplan

#### 2.2 Zoom1 Focus View
**Files:** `zoom1/focus_view.py`, `zoom1/task_detail.py`, `zoom1/smart_list.py`

Split layout (use `Horizontal` container):
- Left 50%: TaskDetailPanel - full task info, description, current execution
- Right 50%: SmartListPanel - dependencies, dependents, same gameplan

#### 2.3 Zoom2 Log View
**File:** `zoom2/log_view.py`

Reuse `LogStream` pattern from `log_browser.py`:

```python
from pathlib import Path
from typing import Optional

from emdx.services.log_stream import LogStream, LogStreamSubscriber
from emdx.models.executions import Execution


class Zoom2Subscriber(LogStreamSubscriber):
    """Subscriber that forwards log content to the view."""

    def __init__(self, view: 'Zoom2LogView'):
        self.view = view

    def on_log_content(self, new_content: str) -> None:
        self.view._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        self.view._handle_log_error(error)


class Zoom2LogView(Widget):
    """Full-screen log viewer for zoom 2."""

    def __init__(self):
        super().__init__()
        self.current_stream: Optional[LogStream] = None
        self.is_live_mode = True
        self.stream_subscriber = Zoom2Subscriber(self)

    async def load_execution_log(self, execution: Execution) -> None:
        """Load and stream logs for an execution."""
        # Stop current stream if any
        if self.current_stream:
            self.current_stream.unsubscribe(self.stream_subscriber)

        # Create new stream
        self.current_stream = LogStream(execution.log_path)

        # Get initial content
        content = self.current_stream.get_initial_content()
        self._display_content(content)

        # Enable live streaming if in live mode
        if self.is_live_mode:
            self.current_stream.subscribe(self.stream_subscriber)

    def _handle_log_content(self, new_content: str) -> None:
        """Handle new content from stream."""
        # Append to RichLog widget
        pass

    def _handle_log_error(self, error: Exception) -> None:
        """Handle stream error."""
        pass

    def _display_content(self, content: str) -> None:
        """Display content in RichLog widget."""
        pass
```

#### 2.4 State Preservation
Implement save/restore in zoom transitions:
- Remember scroll position
- Remember selected item
- Remember view mode

### Phase 2 Files
```
emdx/ui/pulse/zoom0/kanban_view.py
emdx/ui/pulse/zoom0/timeline_view.py
emdx/ui/pulse/zoom1/__init__.py
emdx/ui/pulse/zoom1/focus_view.py
emdx/ui/pulse/zoom1/task_detail.py
emdx/ui/pulse/zoom1/smart_list.py
emdx/ui/pulse/zoom2/__init__.py
emdx/ui/pulse/zoom2/log_view.py
```

---

## Phase 3: Dependency Visualization (3-4 days)

### Goal
Add inline dependency glyphs and navigation.

### Tasks

#### 3.1 Add get_dependents() to tasks.py
**File:** `emdx/models/tasks.py`

Add after `get_dependencies()` function (around line 118):

```python
def get_dependents(task_id: int) -> list[dict[str, Any]]:
    """Get tasks that depend on this task (tasks this blocks)."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.* FROM tasks t
            JOIN task_deps d ON t.id = d.task_id
            WHERE d.depends_on = ?
        """, (task_id,))
        return [dict(row) for row in cursor.fetchall()]
```

#### 3.2 Dependency Glyph Model
**File:** `emdx/ui/pulse/widgets/dep_glyph.py`

```python
from dataclasses import dataclass


@dataclass
class DependencyGlyph:
    """Compact glyph for dependency display."""
    status_char: str      # ◆ ◇ ● ✓ ✗
    blocked_by: int       # Count of tasks this depends on
    blocks: int           # Count of tasks that depend on this
    is_critical: bool

    def render(self, max_width: int = 7) -> str:
        parts = [self.status_char]
        if self.blocked_by > 0:
            parts.append(f"{self.blocked_by}←")
        if self.blocks > 0:
            parts.append(f"→{self.blocks}")
        if self.is_critical:
            parts.append("!")
        return "".join(parts)[:max_width]
```

Glyph examples:
- `◆` - Ready, no deps
- `◆→2` - Ready, blocks 2 tasks
- `◇1←` - Waiting on 1 task
- `◇2←→3!` - Waiting on 2, blocks 3, critical path

#### 3.3 Dependency Service
**File:** `emdx/services/dependency_graph.py`

Functions:
- `get_task_neighborhood(task_id, depth=2)` - local subgraph
- `compute_critical_path(gameplan_id)` - longest path through DAG

#### 3.4 Navigation Shortcuts
- `b` - jump to first blocker
- `n` - jump to next task (or first blocked task from focus view)
- `g` - open focus graph overlay

### Phase 3 Files
```
emdx/models/tasks.py (modify - add get_dependents)
emdx/ui/pulse/widgets/__init__.py
emdx/ui/pulse/widgets/dep_glyph.py
emdx/services/dependency_graph.py
```

---

## Phase 4: Workflow Integration (3-4 days)

### Prerequisites
- PR #164 must be merged (workflow tables exist)

### Tasks
- Workflow display service
- Workflow grouping in PulseView
- Workflow swimlanes in KanbanView

### Phase 4 Files
```
emdx/services/workflow_display.py
emdx/ui/pulse/zoom0/pulse_view.py (modify)
emdx/ui/pulse/zoom0/kanban_view.py (modify)
```

---

## Phase 5: Real-time Updates (2-3 days)

### Tasks

#### 5.1 Activity Sparklines
**File:** `emdx/ui/pulse/widgets/sparkline.py`

5-char activity indicator: `▐▌▌▌░`
- `▐` = High activity (10+ lines/sec)
- `▌` = Medium (1-10 lines/sec)
- `░` = Low (< 1 line/sec)

#### 5.2 Toast Notifications
**File:** `emdx/ui/pulse/widgets/toast.py`

Show completion/error notifications:
- "✓ Task #142 completed - 3 tasks unblocked"
- "✗ Execution #847 failed"

### Phase 5 Files
```
emdx/ui/pulse/widgets/sparkline.py
emdx/ui/pulse/widgets/toast.py
```

---

## Phase 6: Claude Assistant Panel (3-4 days)

### Tasks

#### 6.1 Assistant Panel Widget
**File:** `emdx/ui/pulse/assistant_panel.py`

Slide-in panel (40% width) triggered by '?' key.

#### 6.2 Context Injection
**File:** `emdx/services/assistant_context.py`

Build context for Claude based on current zoom level and selection.

### Phase 6 Files
```
emdx/ui/pulse/assistant_panel.py
emdx/services/assistant_context.py
```

---

## Phase 7: Polish & Performance (2-3 days)

### Tasks
- Virtual scrolling for 100+ tasks
- Batch log updates (100ms windows)
- Empty states handling
- 80x24 minimum terminal support
- F1 help overlay

---

## Complete File Structure

```
emdx/ui/
├── pulse_browser.py                    # Main entry point
├── pulse/
│   ├── __init__.py
│   ├── state.py                        # ZoomState dataclass
│   │
│   ├── zoom0/                          # Overview level
│   │   ├── __init__.py
│   │   ├── pulse_view.py               # Dashboard (default)
│   │   ├── kanban_view.py              # Kanban board
│   │   └── timeline_view.py            # Timeline view
│   │
│   ├── zoom1/                          # Focus level
│   │   ├── __init__.py
│   │   ├── focus_view.py               # Split container
│   │   ├── task_detail.py              # Left panel
│   │   └── smart_list.py               # Right panel + glyphs
│   │
│   ├── zoom2/                          # Deep level
│   │   ├── __init__.py
│   │   └── log_view.py                 # Full-screen log
│   │
│   ├── widgets/                        # Shared widgets
│   │   ├── __init__.py
│   │   ├── dep_glyph.py                # Inline glyphs
│   │   ├── sparkline.py                # Activity indicator
│   │   └── toast.py                    # Notifications
│   │
│   └── assistant_panel.py              # Claude assistant

emdx/models/
├── tasks.py                            # (modify) add get_dependents()

emdx/services/
├── dependency_graph.py                 # Graph computation (Phase 3)
├── assistant_context.py                # Claude context (Phase 6)
```

**Total new files:** 18
**Modified files:** 2 (browser_container.py, tasks.py)

---

## Keyboard Shortcuts (Complete Reference)

### Global (All Zoom Levels)
| Key | Action |
|-----|--------|
| `q` | Back to document browser |
| `?` | Open Claude assistant |
| `Esc` | Zoom out / Cancel |
| `z` | Zoom in |
| `Z` | Zoom out |
| `0/1/2` | Jump to zoom level |
| `r` | Refresh |

### Zoom 0 (Overview)
| Key | Action |
|-----|--------|
| `j/k` | Navigate up/down |
| `Enter` | Zoom into selected |
| `v` | Toggle view (Pulse/Kanban/Timeline) |
| `n` | New task |
| `/` | Search |
| `g` | Open dependency graph |

### Zoom 1 (Focus)
| Key | Action |
|-----|--------|
| `j/k` | Navigate smart list |
| `Enter` | Zoom to selected task or logs |
| `Tab` | Switch between panels |
| `e` | Edit task |
| `b` | Jump to blocker |
| `d` | Toggle dependency view |

### Zoom 2 (Deep/Log)
| Key | Action |
|-----|--------|
| `j/k` | Scroll up/down |
| `g/G` | Top/Bottom |
| `l` | Toggle live mode |
| `/` | Search |
| `n/N` | Next/Prev match |
| `s` | Selection mode |
| `y` | Copy line |

---

## Success Criteria

### Minimum Viable Product (Phase 1-2)
- [ ] PulseBrowser opens on 'c' key
- [ ] Three zoom levels functional
- [ ] Basic task navigation works
- [ ] State preserved across zoom transitions

### Feature Complete (Phase 1-5)
- [ ] All three Zoom 0 view modes
- [ ] Dependency glyphs in all lists
- [ ] Real-time activity updates
- [ ] Workflow integration

### Fully Polished (Phase 1-7)
- [ ] Claude assistant panel
- [ ] Virtual scrolling for 100+ tasks
- [ ] Works at 80x24 minimum
- [ ] No edge case crashes
- [ ] Help overlay

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Textual performance with many widgets | Use `display = False` instead of mount/unmount |
| Complex state management | Single ZoomState dataclass, message-based events |
| Workflow tables not ready (PR #164) | Phase 4 is optional, can ship without |
| Claude latency for assistant | Async execution, show loading state |
| `get_dependents()` doesn't exist | Add to tasks.py in Phase 3 |

---

## Verification Checklist

All items verified against actual source code on 2025-01-07:

- [x] `STATUSES` tuple exists in `tasks.py` line 8
- [x] `list_tasks()` accepts `status` as list parameter
- [x] `search_by_tags()` exists in `tags.py` with correct signature
- [x] `get_execution_stats()` returns dict with 'total', 'recent_24h', 'running', 'completed', 'failed'
- [x] `get_running_executions()` returns `List[Execution]`
- [x] `Execution` dataclass has `log_path` property returning `Path`
- [x] `LogStream` and `LogStreamSubscriber` exist in `log_stream.py`
- [x] `BrowserContainer.switch_browser()` handles "control" at lines 157-159
- [x] 'c' key routes to "control" browser at lines 220-223
- [x] `display` property used for widget visibility (not CSS classes)
- [x] `$boost`, `$surface`, `$text-muted` CSS variables available

---

## Getting Started

1. Start with Phase 1, Task 1.1
2. Create `emdx/ui/pulse_browser.py` with starter template above
3. Test by running TUI and pressing 'c'
4. Iterate through phases sequentially

Each phase is designed to be shippable - you can stop after Phase 2 and have a functional TUI.
