#!/usr/bin/env python3
"""
Worktree picker modal for EMDX TUI.
"""

from typing import Callable, List

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, Static

from emdx.utils.git_ops import GitWorktree


class WorktreePickerScreen(ModalScreen):
    """Modal screen for selecting a git worktree."""
    
    CSS = """
    WorktreePickerScreen {
        align: center middle;
    }
    
    #worktree-picker-container {
        width: 80%;
        height: 70%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #worktree-search {
        margin-bottom: 1;
        border: solid $primary;
        background: black;
        color: white;
        height: 3;
        padding: 1;
    }
    
    #worktree-search:focus {
        border: solid yellow;
        background: black;
        color: white;
    }
    
    /* Make sure the input text is visible */
    Input {
        background: black;
        color: white;
    }
    
    Input:focus {
        background: black;
        color: white;
        border: solid yellow;
    }
    
    #worktree-table {
        height: 1fr;
    }
    
    #worktree-instructions {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    """
    
    def __init__(self, worktrees: List[GitWorktree], current_index: int, callback: Callable[[int], None]):
        super().__init__()
        self.worktrees = worktrees
        self.current_index = current_index
        self.callback = callback
        self.filtered_worktrees = worktrees.copy()
        self.search_query = ""
        
    def compose(self) -> ComposeResult:
        with Vertical(id="worktree-picker-container"):
            yield Label("🌳 Select Worktree", classes="title")
            yield Input(
                placeholder="🔍 Type to filter worktrees...",
                id="worktree-search",
                value=""
            )
            yield DataTable(id="worktree-table", cursor_type="row")
            yield Static(
                "↑↓ Navigate | Enter Select | Esc Cancel | / Search",
                id="worktree-instructions"
            )
    
    def on_mount(self) -> None:
        """Set up the worktree table."""
        table = self.query_one("#worktree-table", DataTable)
        table.add_columns("#", "Name", "Branch", "Status", "Path")
        self.populate_table()
        
        # Move cursor to current worktree
        if 0 <= self.current_index < len(self.filtered_worktrees):
            table.move_cursor(row=self.current_index)
        
        # Focus the search input immediately for typing
        search_input = self.query_one("#worktree-search", Input)
        search_input.focus()
    
    def populate_table(self):
        """Populate the table with filtered worktrees."""
        table = self.query_one("#worktree-table", DataTable)
        table.clear()
        
        for i, worktree in enumerate(self.filtered_worktrees):
            # Status indicators
            current_indicator = "👉" if worktree.is_current else "  "
            
            # Truncate long names for display
            name = worktree.name[:25]
            branch_name = worktree.branch.replace("refs/heads/", "")[:30]
            path_display = worktree.path.replace("/Users/alexrockwell/dev/worktrees/", "")[:40]
            
            table.add_row(
                str(i + 1),
                f"{current_indicator} {name}",
                branch_name,
                "current" if worktree.is_current else "other",
                path_display,
                key=str(i)  # Use index as key for selection
            )
    
    def filter_worktrees(self, query: str):
        """Filter worktrees based on search query."""
        if not query:
            self.filtered_worktrees = self.worktrees.copy()
        else:
            query_lower = query.lower()
            self.filtered_worktrees = [
                wt for wt in self.worktrees
                if (query_lower in wt.name.lower() or 
                    query_lower in wt.branch.lower() or
                    query_lower in wt.path.lower())
            ]
        
        self.populate_table()
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "worktree-search":
            self.search_query = event.value
            
            # Update title to show current search query for debugging
            title = self.query_one(Label)
            if event.value:
                title.update(f"🌳 Select Worktree - Search: '{event.value}'")
            else:
                title.update("🌳 Select Worktree")
            
            self.filter_worktrees(event.value)
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission (Enter key)."""
        if event.input.id == "worktree-search":
            # Select first filtered result
            table = self.query_one("#worktree-table", DataTable)
            if table.row_count > 0:
                self.select_worktree(0)
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle worktree selection."""
        if event.data_table.id == "worktree-table":
            # Get the index from the filtered list
            filtered_index = event.cursor_row
            self.select_worktree(filtered_index)
    
    def select_worktree(self, filtered_index: int):
        """Select a worktree and close the modal."""
        if 0 <= filtered_index < len(self.filtered_worktrees):
            selected_worktree = self.filtered_worktrees[filtered_index]
            
            # Find the original index in the full worktree list
            original_index = self.worktrees.index(selected_worktree)
            
            # Call the callback with the original index
            self.callback(original_index)
            self.dismiss()
    
    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss()
        elif event.key == "enter":
            # Select current row
            table = self.query_one("#worktree-table", DataTable)
            if table.cursor_row is not None:
                self.select_worktree(table.cursor_row)
        elif event.key == "/":
            # Focus search input
            search_input = self.query_one("#worktree-search", Input)
            search_input.focus()
        elif event.key in ("j", "down"):
            # Move down in table
            table = self.query_one("#worktree-table", DataTable)
            table.action_cursor_down()
        elif event.key in ("k", "up"):
            # Move up in table
            table = self.query_one("#worktree-table", DataTable)
            table.action_cursor_up()
        elif event.key == "g":
            # Go to top
            table = self.query_one("#worktree-table", DataTable)
            table.action_cursor_top()
        elif event.key == "G":
            # Go to bottom
            table = self.query_one("#worktree-table", DataTable)
            table.action_cursor_bottom()
