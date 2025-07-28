#!/usr/bin/env python3
"""
Base class and interface for overlay stages.
"""

from abc import abstractmethod
from typing import Dict, Any, Optional, Protocol

from textual.widget import Widget
from textual.message import Message


class OverlayStageHost(Protocol):
    """Protocol defining what overlay stages expect from their host."""
    
    def set_document_selection(self, document_id: int) -> None:
        """Set selected document ID."""
        ...
    
    def set_agent_selection(self, agent_id: int) -> None:
        """Set selected agent ID."""
        ...
    
    def set_worktree_selection(self, worktree_index: int) -> None:
        """Set selected worktree index."""
        ...
    
    def set_execution_config(self, config: Dict[str, Any]) -> None:
        """Set execution configuration."""
        ...
    
    def get_selection_summary(self) -> Dict[str, Any]:
        """Get summary of current selections."""
        ...


class OverlayStage(Widget):
    """Base class for overlay stages."""
    
    class SelectionChanged(Message):
        """Message sent when stage selection changes."""
        def __init__(self, stage_name: str, selection_data: Dict[str, Any]) -> None:
            self.stage_name = stage_name
            self.selection_data = selection_data
            super().__init__()
    
    class StageCompleted(Message):
        """Message sent when stage is completed."""
        def __init__(self, stage_name: str) -> None:
            self.stage_name = stage_name
            super().__init__()
    
    class NavigationRequested(Message):
        """Message sent when stage requests navigation."""
        def __init__(self, direction: str) -> None:
            self.direction = direction  # "next", "prev", "execute"
            super().__init__()
    
    def __init__(self, host: OverlayStageHost, stage_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = host
        self.stage_name = stage_name
        self._is_valid = False
        self._selection_data: Dict[str, Any] = {}
    
    @abstractmethod
    def validate_selection(self) -> bool:
        """Check if current selection is valid."""
        pass
    
    @abstractmethod
    def get_selection_data(self) -> Dict[str, Any]:
        """Return current selection data."""
        pass
    
    @abstractmethod
    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the primary input element."""
        pass
    
    @abstractmethod
    async def load_stage_data(self) -> None:
        """Load any data needed for this stage."""
        pass
    
    def mark_completed(self) -> None:
        """Mark this stage as completed."""
        if self.validate_selection():
            self._is_valid = True
            self.post_message(self.StageCompleted(self.stage_name))
    
    def update_selection(self, data: Dict[str, Any]) -> None:
        """Update selection data and notify host."""
        self._selection_data.update(data)
        self.post_message(self.SelectionChanged(self.stage_name, data))
    
    def request_navigation(self, direction: str) -> None:
        """Request navigation to next/prev stage or execution."""
        self.post_message(self.NavigationRequested(direction))
    
    def is_valid(self) -> bool:
        """Check if stage has valid selection."""
        return self._is_valid and self.validate_selection()
    
    def get_help_text(self) -> str:
        """Get help text for this stage."""
        return "Use Tab/Shift+Tab to navigate stages, Enter to proceed"
    
    async def on_mount(self) -> None:
        """Called when stage is mounted."""
        await self.load_stage_data()
        await self.set_focus_to_primary_input()


class PlaceholderStage(OverlayStage):
    """Placeholder stage implementation for testing."""
    
    def __init__(self, host: OverlayStageHost, stage_name: str, content: str = ""):
        super().__init__(host, stage_name)
        self.content = content or f"Placeholder for {stage_name} stage"
    
    def validate_selection(self) -> bool:
        """Placeholder validation - always valid."""
        return True
    
    def get_selection_data(self) -> Dict[str, Any]:
        """Return placeholder selection data."""
        return {"stage": self.stage_name, "placeholder": True}
    
    async def set_focus_to_primary_input(self) -> None:
        """No input to focus in placeholder."""
        pass
    
    async def load_stage_data(self) -> None:
        """No data to load in placeholder."""
        pass
    
    def compose(self):
        """Simple composition for placeholder."""
        from textual.widgets import Static
        yield Static(self.content)