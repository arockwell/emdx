"""
Unified Work System for EMDX.

This module provides the core work item management with:
- Work items that flow through configurable cascade stages
- Dependencies between work items (blocks, related, discovered-from)
- Automatic stage advancement via processors
- Integration with patrols for automated execution
"""

from .models import WorkItem, WorkDep, Cascade, WorkTransition
from .service import WorkService

__all__ = [
    "WorkItem",
    "WorkDep",
    "Cascade",
    "WorkTransition",
    "WorkService",
]
