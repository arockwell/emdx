"""EMDX UI widgets package."""

from .processing_progress import ProcessingProgress
from .stuck_indicator import StuckBadge, StuckIndicator

# Timeline widgets are optional - import conditionally to handle missing dependencies
try:
    from .timeline_axis import TimelineAxis
    from .timeline_detail import TimelineDetail
    _TIMELINE_AVAILABLE = True
except ImportError:
    _TIMELINE_AVAILABLE = False
    TimelineAxis = None
    TimelineDetail = None

__all__ = [
    "ProcessingProgress",
    "StuckIndicator",
    "StuckBadge",
]

# Only export timeline widgets if they loaded successfully
if _TIMELINE_AVAILABLE:
    __all__.extend(["TimelineAxis", "TimelineDetail"])
