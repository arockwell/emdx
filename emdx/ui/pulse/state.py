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
