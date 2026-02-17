#!/usr/bin/env python3
"""
Protocols for UI callback typing.

These protocols define the interface that host applications must implement
to work with UI components.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SelectionModeHost(Protocol):
    """Protocol for hosts that support selection mode toggle."""

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode on/off."""
        ...
