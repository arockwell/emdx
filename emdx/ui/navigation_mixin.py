#!/usr/bin/env python3
"""
Common navigation functionality for browser widgets.

This mixin provides standard j/k/g/G navigation that works with DataTable widgets.
"""

import logging
from typing import Protocol, runtime_checkable
from textual.widgets import DataTable
from textual.binding import Binding

logger = logging.getLogger(__name__)


@runtime_checkable
class TableProvider(Protocol):
    """Protocol for widgets that provide a primary DataTable for navigation."""
    
    def get_primary_table(self) -> DataTable:
        """Return the primary DataTable widget for navigation."""
        ...


class NavigationMixin:
    """
    Mixin that provides common vim-style navigation for browser widgets.
    
    Classes using this mixin should implement TableProvider protocol.
    """
    
    # Standard navigation bindings that can be used by any browser
    NAVIGATION_BINDINGS: list[Binding] = [
        Binding("j", "cursor_down", "Down", key_display="j"),
        Binding("k", "cursor_up", "Up", key_display="k"), 
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]
    
    def get_primary_table(self) -> DataTable:
        """
        Return the primary DataTable widget for navigation.
        
        Subclasses must implement this method.
        
        Returns:
            DataTable: The primary table widget for navigation
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError("Subclasses must implement get_primary_table()")
    
    def action_cursor_down(self) -> None:
        """Move cursor down in the primary table."""
        try:
            table: DataTable = self.get_primary_table()
            table.action_cursor_down()
        except Exception as e:
            logger.debug(f"Error in cursor_down: {e}")
    
    def action_cursor_up(self) -> None:
        """Move cursor up in the primary table."""
        try:
            table: DataTable = self.get_primary_table()
            table.action_cursor_up()
        except Exception as e:
            logger.debug(f"Error in cursor_up: {e}")
    
    def action_cursor_top(self) -> None:
        """Move cursor to top of the primary table."""
        try:
            table: DataTable = self.get_primary_table()
            table.action_cursor_top()
        except Exception as e:
            logger.debug(f"Error in cursor_top: {e}")
    
    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom of the primary table."""
        try:
            table: DataTable = self.get_primary_table()
            table.action_cursor_bottom()
        except Exception as e:
            logger.debug(f"Error in cursor_bottom: {e}")
    
    def handle_navigation_key(self, key: str) -> bool:
        """
        Handle common navigation keys.
        
        Args:
            key: The key string to handle (e.g., "j", "k", "g", "G")
            
        Returns:
            bool: True if the key was handled, False otherwise
            
        Example:
            def on_key(self, event: events.Key) -> None:
                if self.handle_navigation_key(event.key):
                    event.stop()
                    return
                # Handle other keys...
        """
        if key == "j":
            self.action_cursor_down()
            return True
        elif key == "k":
            self.action_cursor_up()
            return True
        elif key == "g":
            self.action_cursor_top()
            return True
        elif key == "G":
            self.action_cursor_bottom()
            return True
        
        return False