"""Work Browser - TUI for the Unified Work System with stage-based navigation."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, RichLog, Static

from emdx.work import WorkService, WorkItem, Cascade, WorkTransition

logger = logging.getLogger(__name__)

# Priority colors
PRIORITY_COLORS = {
    0: "red bold",      # P0 Critical
    1: "yellow",        # P1 High
    2: "cyan",          # P2 Medium
    3: "dim",           # P3 Low
    4: "dim italic",    # P4 Backlog
}

# Type icons
TYPE_ICONS = {
    "task": "📋",
    "bug": "🐛",
    "feature": "✨",
    "epic": "🎯",
    "research": "🔍",
    "review": "👀",
}


class NewWorkItemScreen(ModalScreen):
    """Modal screen for creating a new work item."""

    CSS = """
    NewWorkItemScreen {
        align: center middle;
    }
    #work-dialog {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #work-label {
        width: 100%;
        padding-bottom: 1;
    }
    #work-title-input {
        width: 100%;
        margin-bottom: 1;
    }
    #work-content-input {
        width: 100%;
        height: 5;
        margin-bottom: 1;
    }
    #work-options {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #work-options Label {
        width: auto;
        margin-right: 1;
    }
    #work-options Input {
        width: 15;
        margin-right: 2;
    }
    #work-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    #work-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, cascade: str = "default", stage: Optional[str] = None):
        super().__init__()
        self.cascade_name = cascade
        self.initial_stage = stage
        self.result: Optional[Dict[str, Any]] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="work-dialog"):
            yield Label("📋 Create new work item:", id="work-label")
            yield Input(placeholder="Title (required)", id="work-title-input")
            yield Input(placeholder="Content/description (optional)", id="work-content-input")
            with Horizontal(id="work-options"):
                yield Label("Priority:")
                yield Input(value="3", placeholder="0-4", id="priority-input")
                yield Label("Type:")
                yield Input(value="task", placeholder="task/bug/feature", id="type-input")
            with Horizontal(id="work-buttons"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-btn":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key."""
        if event.input.id == "work-title-input":
            self._submit()

    def _submit(self) -> None:
        title_input = self.query_one("#work-title-input", Input)
        content_input = self.query_one("#work-content-input", Input)
        priority_input = self.query_one("#priority-input", Input)
        type_input = self.query_one("#type-input", Input)

        title = title_input.value.strip()
        if not title:
            label = self.query_one("#work-label", Label)
            label.update("[red]⚠️ Title is required[/red]")
            return

        try:
            priority = int(priority_input.value.strip() or "3")
            priority = max(0, min(4, priority))
        except ValueError:
            priority = 3

        self.result = {
            "title": title,
            "content": content_input.value.strip() or None,
            "cascade": self.cascade_name,
            "stage": self.initial_stage,
            "priority": priority,
            "type": type_input.value.strip() or "task",
        }
        self.dismiss(self.result)

    def on_mount(self) -> None:
        self.query_one("#work-title-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorkItemDetails(Widget):
    """Details panel for a selected work item."""

    DEFAULT_CSS = """
    WorkItemDetails {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    WorkItemDetails #details-content {
        height: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.item: Optional[WorkItem] = None

    def compose(self) -> ComposeResult:
        yield RichLog(id="details-content", highlight=True, markup=True)

    def show_item(self, item: Optional[WorkItem]) -> None:
        """Display work item details."""
        self.item = item
        log = self.query_one("#details-content", RichLog)
        log.clear()

        if not item:
            log.write("[dim]No item selected[/dim]")
            return

        # Header
        type_icon = TYPE_ICONS.get(item.type, "📋")
        log.write(f"[bold]{type_icon} {item.id}[/bold]")
        log.write(f"[bold cyan]{item.title}[/bold cyan]")
        log.write("")

        # Status line
        priority_style = PRIORITY_COLORS.get(item.priority, "")
        log.write(f"[{priority_style}]{item.priority_label}[/{priority_style}] | {item.cascade}/{item.stage}")

        # Blocked status
        if item.is_blocked:
            blockers = ", ".join(item.blocked_by)
            log.write(f"[red]⛔ BLOCKED by: {blockers}[/red]")
        elif item.claimed_by:
            log.write(f"[yellow]⚡ Claimed by: {item.claimed_by}[/yellow]")

        # Timestamps
        log.write("")
        if item.created_at:
            log.write(f"[dim]Created: {item.created_at.strftime('%Y-%m-%d %H:%M')}[/dim]")
        if item.started_at:
            log.write(f"[dim]Started: {item.started_at.strftime('%Y-%m-%d %H:%M')}[/dim]")
        if item.completed_at:
            log.write(f"[dim]Completed: {item.completed_at.strftime('%Y-%m-%d %H:%M')}[/dim]")

        # Content
        if item.content:
            log.write("")
            log.write("[bold]Content:[/bold]")
            log.write(item.content[:500] + ("..." if len(item.content) > 500 else ""))

        # Links
        if item.pr_number:
            log.write("")
            log.write(f"[green]🔗 PR #{item.pr_number}[/green]")
        if item.output_doc_id:
            log.write(f"[blue]📄 Output: #{item.output_doc_id}[/blue]")


class WorkActivityFeed(Widget):
    """Activity feed showing recent work transitions."""

    DEFAULT_CSS = """
    WorkActivityFeed {
        height: 10;
        border: solid $primary;
    }
    WorkActivityFeed #activity-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    WorkActivityFeed #activity-table {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = WorkService()

    def compose(self) -> ComposeResult:
        yield Static("[bold]Recent Activity[/bold]", id="activity-header")
        table = DataTable(id="activity-table")
        table.add_column("Time", width=8)
        table.add_column("Item", width=12)
        table.add_column("Transition", width=25)
        table.add_column("By", width=12)
        table.add_column("Title", width=30)
        table.cursor_type = "row"
        yield table

    def refresh_activity(self) -> None:
        """Refresh the activity feed."""
        table = self.query_one("#activity-table", DataTable)
        table.clear()

        # Get recent transitions
        transitions = self.service.get_recent_transitions(limit=15)

        for trans in transitions:
            # Time
            time_str = ""
            if trans.created_at:
                time_str = trans.created_at.strftime("%H:%M:%S")

            # Transition display
            from_stage = trans.from_stage or "(new)"
            transition = f"{from_stage} → [bold]{trans.to_stage}[/bold]"

            # By (transitioned_by)
            by = trans.transitioned_by or "manual"
            if len(by) > 10:
                by = by[:10] + "…"

            # Get work item title
            item = self.service.get(trans.work_id)
            title = item.title[:28] + "…" if item and len(item.title) > 28 else (item.title if item else "")

            table.add_row(time_str, trans.work_id, transition, by, title)

        if not transitions:
            table.add_row("", "", "[dim]No activity yet[/dim]", "", "")


class StagePipeline(Widget):
    """Horizontal pipeline showing all stages with counts."""

    DEFAULT_CSS = """
    StagePipeline {
        height: 3;
        background: $surface;
        padding: 0 1;
    }
    StagePipeline #pipeline-bar {
        height: 1;
        text-align: center;
    }
    StagePipeline #pipeline-help {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    current_stage = reactive("")
    current_cascade = reactive("default")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stages: List[str] = []
        self.counts: Dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="pipeline-bar")
        yield Static("", id="pipeline-help")

    def set_cascade(self, cascade: Cascade, counts: Dict[str, int]) -> None:
        """Update the pipeline for a cascade."""
        self.stages = cascade.stages
        self.counts = counts
        self.current_cascade = cascade.name
        if self.stages and not self.current_stage:
            self.current_stage = self.stages[0]
        self._update_display()

    def watch_current_stage(self, stage: str) -> None:
        """React to stage changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the pipeline display."""
        if not self.stages:
            return

        bar = self.query_one("#pipeline-bar", Static)
        help_bar = self.query_one("#pipeline-help", Static)

        parts = []
        for stage in self.stages:
            count = self.counts.get(stage, 0)
            if stage == self.current_stage:
                parts.append(f"[bold reverse] {stage.upper()} ({count}) [/]")
            elif count > 0:
                parts.append(f"[bold]{stage}[/bold] ({count})")
            else:
                parts.append(f"[dim]{stage} (0)[/dim]")

        bar.update(" → ".join(parts))

        count = self.counts.get(self.current_stage, 0)
        help_bar.update(
            f"[bold]← h[/bold] prev | [bold]l →[/bold] next | "
            f"{count} item{'s' if count != 1 else ''} at [bold]{self.current_stage}[/bold]"
        )

    def prev_stage(self) -> Optional[str]:
        """Move to previous stage."""
        if not self.stages:
            return None
        try:
            idx = self.stages.index(self.current_stage)
            if idx > 0:
                self.current_stage = self.stages[idx - 1]
                return self.current_stage
        except ValueError:
            pass
        return None

    def next_stage(self) -> Optional[str]:
        """Move to next stage."""
        if not self.stages:
            return None
        try:
            idx = self.stages.index(self.current_stage)
            if idx < len(self.stages) - 1:
                self.current_stage = self.stages[idx + 1]
                return self.current_stage
        except ValueError:
            pass
        return None


class WorkItemList(Widget):
    """List of work items at the current stage."""

    DEFAULT_CSS = """
    WorkItemList {
        height: 100%;
        border: solid $primary;
    }
    WorkItemList #work-table {
        height: 100%;
    }
    WorkItemList.focused {
        border: double $accent;
    }
    """

    class ItemSelected(Message):
        """Fired when an item is selected."""
        def __init__(self, item: WorkItem):
            self.item = item
            super().__init__()

    class ItemActivated(Message):
        """Fired when an item is activated (Enter)."""
        def __init__(self, item: WorkItem):
            self.item = item
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items: List[WorkItem] = []
        self.current_cascade = "default"
        self.current_stage = "idea"

    def compose(self) -> ComposeResult:
        table = DataTable(id="work-table")
        table.add_column("P", width=2)
        table.add_column("ID", width=12)
        table.add_column("Title", width=40)
        table.add_column("Type", width=8)
        table.add_column("Status", width=10)
        table.cursor_type = "row"
        yield table

    def load_items(self, items: List[WorkItem]) -> None:
        """Load work items into the list."""
        self.items = items
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        table = self.query_one("#work-table", DataTable)
        table.clear()

        for item in self.items:
            # Priority indicator
            priority_colors = ["🔴", "🟡", "🔵", "⚪", "⬜"]
            p_indicator = priority_colors[min(item.priority, 4)]

            # Type icon
            type_icon = TYPE_ICONS.get(item.type, "📋")

            # Title (truncate if needed)
            title = item.title
            if len(title) > 38:
                title = title[:35] + "..."

            # Status
            if item.is_done:
                status = "[green]✓ done[/green]"
            elif item.is_blocked:
                status = "[red]⛔ blocked[/red]"
            elif item.claimed_by:
                status = f"[yellow]⚡ {item.claimed_by[:6]}[/yellow]"
            else:
                status = "[dim]ready[/dim]"

            table.add_row(
                p_indicator,
                item.id,
                title,
                f"{type_icon} {item.type}",
                status,
                key=item.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        if event.row_key:
            for item in self.items:
                if item.id == str(event.row_key.value):
                    self.post_message(self.ItemSelected(item))
                    break

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight (cursor movement)."""
        if event.row_key:
            for item in self.items:
                if item.id == str(event.row_key.value):
                    self.post_message(self.ItemSelected(item))
                    break

    def get_selected_item(self) -> Optional[WorkItem]:
        """Get the currently selected work item."""
        table = self.query_one("#work-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.items):
            return self.items[table.cursor_row]
        return None


class CascadeTabs(Widget):
    """Horizontal tabs for switching between cascades."""

    DEFAULT_CSS = """
    CascadeTabs {
        height: 1;
        background: $boost;
        padding: 0 1;
    }
    """

    current_cascade = reactive("default")

    class CascadeChanged(Message):
        def __init__(self, cascade_name: str):
            self.cascade_name = cascade_name
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cascades: List[str] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="cascade-tabs")

    def set_cascades(self, cascades: List[str]) -> None:
        """Set available cascades."""
        self.cascades = cascades
        self._update_display()

    def watch_current_cascade(self, cascade: str) -> None:
        """React to cascade changes."""
        self._update_display()
        self.post_message(self.CascadeChanged(cascade))

    def _update_display(self) -> None:
        """Update tab display."""
        tabs = self.query_one("#cascade-tabs", Static)
        parts = []
        for name in self.cascades:
            if name == self.current_cascade:
                parts.append(f"[bold reverse] {name} [/]")
            else:
                parts.append(f" {name} ")
        tabs.update(" | ".join(parts) + "  [dim](Tab to switch)[/dim]")

    def next_cascade(self) -> None:
        """Switch to next cascade."""
        if not self.cascades:
            return
        try:
            idx = self.cascades.index(self.current_cascade)
            self.current_cascade = self.cascades[(idx + 1) % len(self.cascades)]
        except ValueError:
            self.current_cascade = self.cascades[0]

    def prev_cascade(self) -> None:
        """Switch to previous cascade."""
        if not self.cascades:
            return
        try:
            idx = self.cascades.index(self.current_cascade)
            self.current_cascade = self.cascades[(idx - 1) % len(self.cascades)]
        except ValueError:
            self.current_cascade = self.cascades[0]


class WorkView(Widget):
    """Main work view combining pipeline, list, details, and activity feed."""

    DEFAULT_CSS = """
    WorkView {
        layout: vertical;
        height: 100%;
    }
    WorkView #cascade-tabs-widget {
        height: 1;
    }
    WorkView #pipeline {
        height: 3;
    }
    WorkView #main-area {
        height: 1fr;
    }
    WorkView #list-panel {
        width: 55%;
    }
    WorkView #details-panel {
        width: 45%;
    }
    WorkView #activity-feed {
        height: 10;
    }
    """

    BINDINGS = [
        Binding("h", "prev_stage", "Prev Stage"),
        Binding("l", "next_stage", "Next Stage"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("enter", "select_item", "Select"),
        Binding("a", "advance_item", "Advance"),
        Binding("s", "start_item", "Start"),
        Binding("d", "done_item", "Done"),
        Binding("n", "new_item", "New"),
        Binding("tab", "next_cascade", "Next Cascade"),
        Binding("shift+tab", "prev_cascade", "Prev Cascade"),
        Binding("r", "refresh", "Refresh"),
    ]

    class ViewDocument(Message):
        """Request to view a document."""
        def __init__(self, doc_id: int):
            self.doc_id = doc_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = WorkService()
        self.current_cascade: Optional[Cascade] = None
        self.activity_feed: Optional[WorkActivityFeed] = None

    def compose(self) -> ComposeResult:
        yield CascadeTabs(id="cascade-tabs-widget")
        yield StagePipeline(id="pipeline")
        with Horizontal(id="main-area"):
            yield WorkItemList(id="list-panel")
            yield WorkItemDetails(id="details-panel")
        self.activity_feed = WorkActivityFeed(id="activity-feed")
        yield self.activity_feed

    async def on_mount(self) -> None:
        """Initialize on mount."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh all data."""
        # Load cascades
        cascades = self.service.list_cascades()
        cascade_names = [c.name for c in cascades]

        tabs = self.query_one("#cascade-tabs-widget", CascadeTabs)
        tabs.set_cascades(cascade_names)

        # Set initial cascade if not set
        if not tabs.current_cascade and cascade_names:
            tabs.current_cascade = cascade_names[0]

        await self._load_cascade(tabs.current_cascade)

        # Refresh activity feed
        if self.activity_feed:
            self.activity_feed.refresh_activity()

    async def _load_cascade(self, cascade_name: str) -> None:
        """Load a specific cascade."""
        cascade = self.service.get_cascade(cascade_name)
        if not cascade:
            return

        self.current_cascade = cascade

        # Get stage counts - extract inner dict for this cascade
        all_counts = self.service.get_stage_counts(cascade_name)
        counts = all_counts.get(cascade_name, {})

        # Update pipeline
        pipeline = self.query_one("#pipeline", StagePipeline)
        pipeline.set_cascade(cascade, counts)

        # Load items for current stage
        await self._load_stage_items(pipeline.current_stage)

    async def _load_stage_items(self, stage: str) -> None:
        """Load items for a stage."""
        if not self.current_cascade:
            return

        items = self.service.list(
            cascade=self.current_cascade.name,
            stage=stage,
            include_done=(stage in ["done", "merged", "conclusion", "deployed", "completed"]),
        )

        item_list = self.query_one("#list-panel", WorkItemList)
        item_list.load_items(items)

        # Clear details if no items
        details = self.query_one("#details-panel", WorkItemDetails)
        if items:
            details.show_item(items[0])
        else:
            details.show_item(None)

    def on_work_item_list_item_selected(self, event: WorkItemList.ItemSelected) -> None:
        """Handle item selection."""
        details = self.query_one("#details-panel", WorkItemDetails)
        details.show_item(event.item)

    async def on_cascade_tabs_cascade_changed(self, event: CascadeTabs.CascadeChanged) -> None:
        """Handle cascade tab change."""
        await self._load_cascade(event.cascade_name)

    async def action_prev_stage(self) -> None:
        """Move to previous stage."""
        pipeline = self.query_one("#pipeline", StagePipeline)
        if pipeline.prev_stage():
            await self._load_stage_items(pipeline.current_stage)

    async def action_next_stage(self) -> None:
        """Move to next stage."""
        pipeline = self.query_one("#pipeline", StagePipeline)
        if pipeline.next_stage():
            await self._load_stage_items(pipeline.current_stage)

    def action_cursor_down(self) -> None:
        """Move cursor down in list."""
        table = self.query_one("#work-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in list."""
        table = self.query_one("#work-table", DataTable)
        table.action_cursor_up()

    def action_select_item(self) -> None:
        """Select current item (view output doc if available)."""
        item_list = self.query_one("#list-panel", WorkItemList)
        item = item_list.get_selected_item()
        if item and item.output_doc_id:
            self.post_message(self.ViewDocument(item.output_doc_id))

    async def action_advance_item(self) -> None:
        """Advance selected item to next stage."""
        item_list = self.query_one("#list-panel", WorkItemList)
        item = item_list.get_selected_item()
        if not item:
            return

        try:
            self.service.advance(item.id, transitioned_by="tui")
            await self.refresh_data()
        except ValueError as e:
            logger.error(f"Failed to advance: {e}")

    async def action_start_item(self) -> None:
        """Start working on selected item."""
        item_list = self.query_one("#list-panel", WorkItemList)
        item = item_list.get_selected_item()
        if not item:
            return

        # Move to implementing stage
        cascade = self.service.get_cascade(item.cascade)
        if cascade:
            implementing_stages = ["implementing", "draft", "fixing", "working"]
            for stage in implementing_stages:
                if stage in cascade.stages:
                    self.service.set_stage(item.id, stage, "tui:start")
                    await self.refresh_data()
                    break

    async def action_done_item(self) -> None:
        """Mark selected item as done."""
        item_list = self.query_one("#list-panel", WorkItemList)
        item = item_list.get_selected_item()
        if not item:
            return

        try:
            self.service.done(item.id)
            await self.refresh_data()
        except ValueError as e:
            logger.error(f"Failed to mark done: {e}")

    async def action_new_item(self) -> None:
        """Create a new work item."""
        if not self.current_cascade:
            return

        pipeline = self.query_one("#pipeline", StagePipeline)

        def on_dismiss(result: Optional[Dict[str, Any]]) -> None:
            if result:
                try:
                    self.service.add(
                        title=result["title"],
                        content=result.get("content"),
                        cascade=result.get("cascade", self.current_cascade.name),
                        stage=result.get("stage"),
                        priority=result.get("priority", 3),
                        type_=result.get("type", "task"),
                    )
                    self.call_later(self.refresh_data)
                except Exception as e:
                    logger.error(f"Failed to create item: {e}")

        screen = NewWorkItemScreen(
            cascade=self.current_cascade.name,
            stage=pipeline.current_stage,
        )
        self.app.push_screen(screen, on_dismiss)

    def action_next_cascade(self) -> None:
        """Switch to next cascade."""
        tabs = self.query_one("#cascade-tabs-widget", CascadeTabs)
        tabs.next_cascade()

    def action_prev_cascade(self) -> None:
        """Switch to previous cascade."""
        tabs = self.query_one("#cascade-tabs-widget", CascadeTabs)
        tabs.prev_cascade()

    async def action_refresh(self) -> None:
        """Refresh all data."""
        await self.refresh_data()


class WorkBrowser(Widget):
    """Top-level Work Browser widget for the unified work system."""

    BINDINGS = [
        Binding("1", "switch_activity", "Activity", show=False),
        Binding("3", "switch_documents", "Documents", show=False),
        Binding("4", "switch_search", "Search", show=False),
        Binding("5", "switch_old_cascade", "Old Cascade", show=False),
    ]

    DEFAULT_CSS = """
    WorkBrowser {
        layout: vertical;
        height: 100%;
    }
    WorkBrowser #work-view {
        height: 1fr;
    }
    WorkBrowser #help-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield WorkView(id="work-view")
        yield Static(
            "[bold]h/l[/bold] stages │ [bold]j/k[/bold] items │ "
            "[bold]a[/bold] advance │ [bold]s[/bold] start │ [bold]d[/bold] done │ "
            "[bold]n[/bold] new │ [bold]Tab[/bold] cascade │ "
            "[bold]1[/bold] Activity │ [bold]3[/bold] Docs │ [bold]q[/bold] quit",
            id="help-bar"
        )

    def on_work_view_view_document(self, event: WorkView.ViewDocument) -> None:
        """Handle request to view a document."""
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    async def action_switch_activity(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    async def action_switch_documents(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")

    async def action_switch_search(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("search")

    async def action_switch_old_cascade(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("cascade")

    async def action_switch_work(self) -> None:
        # Already on work browser
        pass
