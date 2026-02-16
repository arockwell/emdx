#!/usr/bin/env python3
"""
Protocols for UI callback typing.

These protocols define the interface that host applications must implement
to work with vim editor components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from textual.widgets import Input


@runtime_checkable
class SelectionModeHost(Protocol):
    """Protocol for hosts that support selection mode toggle."""

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode on/off."""
        ...


@runtime_checkable
class VimEditorHost(Protocol):
    """
    Protocol for hosts that support vim editor callbacks.

    This is the minimal interface that a host application must implement
    to work with VimEditTextArea and VimEditor components.
    """

    new_document_mode: bool
    """Whether the host is in new document creation mode."""

    def _update_vim_status(self, status: str) -> None:
        """Update the vim status line display."""
        ...

    def action_save_and_exit_edit(self) -> None:
        """Save the document and exit edit mode."""
        ...

    def call_after_refresh(self, callback: Any) -> None:
        """Schedule a callback to run after the next refresh."""
        ...

    def query_one(self, selector: str) -> Input:
        """Query for a single widget matching the selector."""
        ...


@runtime_checkable
class ExtendedVimEditorHost(VimEditorHost, Protocol):
    """
    Extended vim editor host with optional methods.

    These methods may or may not be present on the host,
    so callers should check with hasattr before calling.
    """

    def save_document_without_exit(self) -> None:
        """Save without exiting edit mode (optional)."""
        ...

    def action_save_document(self) -> None:
        """Save the current document (optional)."""
        ...

    def action_save(self) -> None:
        """Alternative save method (optional)."""
        ...

    async def exit_edit_mode(self) -> None:
        """Exit edit mode without saving (optional, async)."""
        ...
