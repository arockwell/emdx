#!/usr/bin/env python3
"""Navigation mixin for browser widgets."""

import logging
from textual.binding import Binding

logger = logging.getLogger(__name__)


class NavigationMixin:
    """Mixin that provides vim-style navigation for DataTable widgets."""
    
    NAVIGATION_BINDINGS: list[Binding] = [
        Binding("j", "cursor_down", "Down", key_display="j"),
        Binding("k", "cursor_up", "Up", key_display="k"),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]
    
    def get_primary_table(self):
        """Return the primary table for navigation. Override in subclass."""
        raise NotImplementedError("Subclass must implement get_primary_table()")
    
    def action_cursor_down(self) -> None:
        """Move cursor down."""
        self.get_primary_table().action_cursor_down()
        
    def action_cursor_up(self) -> None:
        """Move cursor up."""
        self.get_primary_table().action_cursor_up()
        
    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.get_primary_table()
        if table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            
    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.get_primary_table()
        if table.row_count > 0:
            table.cursor_coordinate = (table.row_count - 1, 0)