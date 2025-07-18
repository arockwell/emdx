"""
Browser Mode Router - Handles mode switching and routing for the EMDX browser.

This module consolidates all the mode-based switching logic that was previously
scattered throughout main_browser.py with if/elif chains.
"""

import logging
from typing import Callable, Dict, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from textual.events import Key
    from .main_browser import MinimalDocumentBrowser

logger = logging.getLogger(__name__)


class BrowserMode(Enum):
    """All possible browser modes."""
    NORMAL = "NORMAL"
    SEARCH = "SEARCH"
    TAG = "TAG"
    SELECTION = "SELECTION"
    EDIT = "EDIT"
    FILE_BROWSER = "FILE_BROWSER"
    GIT_DIFF_BROWSER = "GIT_DIFF_BROWSER"
    LOG_BROWSER = "LOG_BROWSER"


@dataclass
class ModeConfig:
    """Configuration for a browser mode."""
    name: str
    enter_handler: Optional[Callable] = None
    exit_handler: Optional[Callable] = None
    key_handlers: Dict[str, Callable] = None
    status_text: Optional[Callable] = None
    allowed_transitions: Optional[list[BrowserMode]] = None
    
    def __post_init__(self):
        if self.key_handlers is None:
            self.key_handlers = {}
        if self.allowed_transitions is None:
            self.allowed_transitions = list(BrowserMode)


class BrowserModeRouter:
    """
    Centralized mode routing for the EMDX browser.
    
    This class handles:
    - Mode transitions and validation
    - Key event routing based on current mode
    - Status bar updates for each mode
    - Mode-specific setup and teardown
    """
    
    def __init__(self, browser: 'MinimalDocumentBrowser'):
        self.browser = browser
        self.mode_configs: Dict[BrowserMode, ModeConfig] = {}
        self._setup_modes()
        
    def _setup_modes(self):
        """Configure all browser modes."""
        
        # NORMAL mode - default document browsing
        self.mode_configs[BrowserMode.NORMAL] = ModeConfig(
            name="NORMAL",
            key_handlers={
                "/": lambda: self.browser.action_search_mode(),
                "t": lambda: self.browser.action_tag_mode(),
                "T": lambda: self.browser.action_untag_mode(),
                "s": lambda: self.browser.action_toggle_selection_mode(),
                "e": lambda: self.browser.action_enter_edit_mode(),
                "f": lambda: self.browser.action_open_file_browser(),
                "d": lambda: self.browser.action_git_diff_browser(),
                "l": lambda: self.browser.action_log_browser(),
                "n": lambda: self.browser.action_new_note(),
                "v": lambda: self.browser.action_view(),
                "g": lambda: self.browser.action_create_gist(),
                "x": lambda: self.browser.action_claude_execute(),
                "X": lambda: self.browser.action_mark_execution_complete(),
                "delete": lambda: self.browser.action_delete(),
                "D": lambda: self.browser.action_delete(),
                "c": lambda: self.browser.action_copy_content(),
                "C": lambda: self.browser.action_copy_selected(),
            },
            status_text=lambda: "NORMAL - j/k:nav /:search t:tag e:edit f:files d:git n:new",
        )
        
        # SEARCH mode
        self.mode_configs[BrowserMode.SEARCH] = ModeConfig(
            name="SEARCH",
            enter_handler=self._enter_search_mode,
            exit_handler=self._exit_search_mode,
            key_handlers={
                "escape": lambda: self.transition_to(BrowserMode.NORMAL),
                "enter": lambda: self._submit_search(),
            },
            status_text=lambda: f"SEARCH - Query: {self.browser.search_query}",
        )
        
        # TAG mode
        self.mode_configs[BrowserMode.TAG] = ModeConfig(
            name="TAG",
            enter_handler=self._enter_tag_mode,
            exit_handler=self._exit_tag_mode,
            key_handlers={
                "escape": lambda: self.transition_to(BrowserMode.NORMAL),
                "enter": lambda: self._submit_tag(),
                "tab": lambda: self.browser.update_tag_selector(direction=1),
                "shift+tab": lambda: self.browser.update_tag_selector(direction=-1),
            },
            status_text=lambda: f"TAG - Action: {self.browser.tag_action or 'Type tag'}",
        )
        
        # SELECTION mode
        self.mode_configs[BrowserMode.SELECTION] = ModeConfig(
            name="SELECTION",
            enter_handler=self._enter_selection_mode,
            exit_handler=self._exit_selection_mode,
            key_handlers={
                "escape": lambda: self.browser.action_toggle_selection_mode(),
                "s": lambda: self.browser.action_toggle_selection_mode(),
                "space": lambda: self._toggle_selection(),
                "a": lambda: self._select_all(),
                "A": lambda: self._deselect_all(),
            },
            status_text=lambda: f"SELECTION - {len(self.browser.selected_docs)} selected",
        )
        
        # EDIT mode
        self.mode_configs[BrowserMode.EDIT] = ModeConfig(
            name="EDIT",
            enter_handler=self._enter_edit_mode,
            exit_handler=self._exit_edit_mode,
            key_handlers={
                # Edit mode keys handled by the text area widget
            },
            status_text=lambda: "EDIT - ESC to exit, Ctrl+S to save",
        )
        
        # FILE_BROWSER mode
        self.mode_configs[BrowserMode.FILE_BROWSER] = ModeConfig(
            name="FILE_BROWSER",
            enter_handler=self._enter_file_browser,
            exit_handler=self._exit_file_browser,
            key_handlers={
                "q": lambda: self.browser.exit_file_browser(),
                "escape": lambda: self.browser.exit_file_browser(),
            },
            status_text=lambda: "FILE BROWSER - q/ESC to return",
        )
        
        # GIT_DIFF_BROWSER mode
        self.mode_configs[BrowserMode.GIT_DIFF_BROWSER] = ModeConfig(
            name="GIT_DIFF_BROWSER",
            enter_handler=self._enter_git_browser,
            exit_handler=self._exit_git_browser,
            key_handlers={
                "q": lambda: self.transition_to(BrowserMode.NORMAL),
                "escape": lambda: self.transition_to(BrowserMode.NORMAL),
                "w": lambda: self.browser.action_switch_worktree(),
                "r": lambda: self.browser.refresh_files(),
                "s": lambda: self.browser.action_git_stage_file(),
                "u": lambda: self.browser.action_git_unstage_file(),
                "D": lambda: self.browser.action_git_discard_changes(),
                "c": lambda: self.browser.action_git_commit(),
                "j": lambda: self.browser.action_git_diff_next(),
                "k": lambda: self.browser.action_git_diff_prev(),
            },
            status_text=lambda: "GIT DIFF - w:worktree s:stage u:unstage c:commit",
        )
        
        # LOG_BROWSER mode
        self.mode_configs[BrowserMode.LOG_BROWSER] = ModeConfig(
            name="LOG_BROWSER",
            enter_handler=self._enter_log_browser,
            exit_handler=self._exit_log_browser,
            key_handlers={
                "q": lambda: self.browser.restore_normal_status(),
                "escape": lambda: self.browser.restore_normal_status(),
                "j": lambda: self.browser.action_next_log(),
                "k": lambda: self.browser.action_prev_log(),
                "r": lambda: self.browser.refresh_execution_list(),
                "x": lambda: self.browser.action_mark_execution_complete(),
            },
            status_text=lambda: "LOG BROWSER - j/k:navigate r:refresh x:complete",
        )
    
    def get_current_mode(self) -> BrowserMode:
        """Get the current browser mode."""
        try:
            return BrowserMode(self.browser.mode)
        except ValueError:
            logger.warning(f"Unknown mode: {self.browser.mode}, defaulting to NORMAL")
            return BrowserMode.NORMAL
    
    def transition_to(self, new_mode: BrowserMode) -> bool:
        """
        Transition to a new mode.
        
        Returns True if transition was successful, False otherwise.
        """
        current_mode = self.get_current_mode()
        
        # Check if transition is allowed
        current_config = self.mode_configs.get(current_mode)
        if current_config and new_mode not in current_config.allowed_transitions:
            logger.warning(f"Transition from {current_mode} to {new_mode} not allowed")
            return False
        
        # Exit current mode
        if current_config and current_config.exit_handler:
            try:
                current_config.exit_handler()
            except Exception as e:
                logger.error(f"Error exiting {current_mode}: {e}")
                
        # Enter new mode
        new_config = self.mode_configs.get(new_mode)
        if new_config and new_config.enter_handler:
            try:
                new_config.enter_handler()
            except Exception as e:
                logger.error(f"Error entering {new_mode}: {e}")
                return False
        
        # Update browser mode
        self.browser.mode = new_mode.value
        
        # Update status
        self.update_status()
        
        return True
    
    def handle_key(self, event: 'Key') -> bool:
        """
        Route key events based on current mode.
        
        Returns True if key was handled, False otherwise.
        """
        current_mode = self.get_current_mode()
        config = self.mode_configs.get(current_mode)
        
        if not config:
            return False
            
        # Check if this key has a handler in current mode
        handler = config.key_handlers.get(event.key)
        if handler:
            try:
                handler()
                return True
            except Exception as e:
                logger.error(f"Error handling key {event.key} in {current_mode}: {e}")
                return False
        
        return False
    
    def update_status(self):
        """Update status bar based on current mode."""
        current_mode = self.get_current_mode()
        config = self.mode_configs.get(current_mode)
        
        if config and config.status_text:
            try:
                status = config.status_text()
                self.browser.update_status(status)
            except Exception as e:
                logger.error(f"Error updating status for {current_mode}: {e}")
    
    # Mode-specific handlers
    
    def _enter_search_mode(self):
        """Enter search mode."""
        self.browser.search_query = ""
        search_input = self.browser.query_one("#search-input", Input)
        search_input.value = ""
        search_input.focus()
        
    def _exit_search_mode(self):
        """Exit search mode."""
        # Clear search UI
        pass
        
    def _submit_search(self):
        """Submit search query."""
        # Implement search submission
        self.browser.filter_documents()
        self.transition_to(BrowserMode.NORMAL)
        
    def _enter_tag_mode(self):
        """Enter tag mode."""
        self.browser.tag_action = ""
        tag_input = self.browser.query_one("#tag-input", Input)
        tag_input.value = ""
        tag_input.focus()
        
    def _exit_tag_mode(self):
        """Exit tag mode."""
        # Clear tag UI
        pass
        
    def _submit_tag(self):
        """Submit tag action."""
        # Implement tag submission
        self.transition_to(BrowserMode.NORMAL)
        
    def _enter_selection_mode(self):
        """Enter selection mode."""
        # Initialize selection state
        pass
        
    def _exit_selection_mode(self):
        """Exit selection mode."""
        # Clear selections
        self.browser.selected_docs.clear()
        
    def _toggle_selection(self):
        """Toggle selection of current item."""
        # Implement selection toggle
        pass
        
    def _select_all(self):
        """Select all items."""
        # Implement select all
        pass
        
    def _deselect_all(self):
        """Deselect all items."""
        self.browser.selected_docs.clear()
        
    def _enter_edit_mode(self):
        """Enter edit mode."""
        # Setup edit UI
        pass
        
    def _exit_edit_mode(self):
        """Exit edit mode."""
        # Cleanup edit UI
        pass
        
    def _enter_file_browser(self):
        """Enter file browser mode."""
        self.browser.setup_file_browser()
        
    def _exit_file_browser(self):
        """Exit file browser mode."""
        # Cleanup file browser
        pass
        
    def _enter_git_browser(self):
        """Enter git browser mode."""
        self.browser.setup_git_diff_browser()
        
    def _exit_git_browser(self):
        """Exit git browser mode."""
        # Cleanup git browser
        pass
        
    def _enter_log_browser(self):
        """Enter log browser mode."""
        self.browser.setup_log_browser()
        
    def _exit_log_browser(self):
        """Exit log browser mode."""
        self.browser.restore_normal_status()