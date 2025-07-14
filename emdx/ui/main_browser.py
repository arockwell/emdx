#!/usr/bin/env python3
"""
Main browser application for EMDX TUI.
"""

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, RichLog, Static

from emdx.database import db
from emdx.models.documents import get_document
from emdx.models.executions import (
    get_recent_executions,
    update_execution_status,
)
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)
from emdx.ui.formatting import format_tags, truncate_emoji_safe
from emdx.utils.emoji_aliases import expand_aliases
from emdx.utils.git_ops import is_git_repository

from .document_viewer import FullScreenView
from .git_browser import GitBrowserMixin
from .inputs import TitleInput
from .modals import DeleteConfirmScreen
from .text_areas import EditTextArea, SelectionTextArea, VimEditTextArea
from .worktree_picker import WorktreePickerScreen

# Set up logging
log_dir = None
try:
    log_dir = Path.home() / ".config" / "emdx"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tui_debug.log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            # logging.StreamHandler()  # Uncomment for console output
        ],
    )

    # Also create a dedicated key events log
    key_log_file = log_dir / "key_events.log"
    key_logger = logging.getLogger("key_events")
    key_handler = logging.FileHandler(key_log_file)
    key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    key_logger.addHandler(key_handler)
    key_logger.setLevel(logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.info("EMDX TUI starting up")
except Exception:
    # Fallback if logging setup fails
    import logging
    key_logger = logging.getLogger("key_events")
    logger = logging.getLogger(__name__)


class SimpleVimLineNumbers(Static):
    """Dead simple vim-style line numbers widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("vim-line-numbers")
        self.text_area = None  # Reference to associated text area

    def set_line_numbers(self, current_line, total_lines, text_area=None):
        """Set line numbers given current line (0-based) and total lines."""
        logger.debug(f"🔢 set_line_numbers called: current={current_line}, total={total_lines}")
        
        # Store text area reference if provided
        if text_area:
            self.text_area = text_area
        
        from rich.text import Text
        
        # Check if text area has focus - only highlight current line if it does
        has_focus = self.text_area and self.text_area.has_focus if self.text_area else False
        logger.debug(f"🔢 Text area has focus: {has_focus}")
        
        lines = []
        for i in range(total_lines):
            if i == current_line:
                # Current line always shows absolute number (1-based)
                line_num = i + 1
                if has_focus:
                    line_text = Text(f"{line_num:>3}", style="bold yellow")
                    logger.debug(f"  Line {i}: CURRENT (focused) -> bold yellow '{line_num}'")
                else:
                    line_text = Text(f"{line_num:>3}", style="dim yellow")
                    logger.debug(f"  Line {i}: CURRENT (not focused) -> dim yellow '{line_num}'")
                lines.append(line_text)
            else:
                # Other lines show distance from current line
                distance = abs(i - current_line)
                line_text = Text(f"{distance:>3}", style="dim cyan")
                logger.debug(f"  Line {i}: distance {distance} -> dim cyan '{distance}'")
                lines.append(line_text)
        
        # Join with Rich Text newlines
        result = Text("\n").join(lines)
        logger.debug(f"🔢 Rich Text result created with {len(lines)} lines")
        logger.debug(f"🔢 Widget content BEFORE update: {repr(self.renderable)}")
        
        # Update widget content with Rich Text
        self.update(result)
        
        logger.debug(f"🔢 Widget content AFTER update: {repr(self.renderable)}")

class MinimalDocumentBrowser(GitBrowserMixin, App):
    """Minimal document browser that signals external wrapper for nvim."""

    ENABLE_COMMAND_PALETTE = False
    # Disable mouse support to prevent coordinate spam
    MOUSE_DISABLED = True
    # Enable text selection globally
    ALLOW_SELECT = True
    # Disable default Tab focus navigation
    AUTO_FOCUS = False

    CSS = """
    #sidebar {
        width: 50%;
        border-right: solid $primary;
    }

    #preview-container {
        width: 50%;
    }

    #vim-mode-indicator {
        height: 1;
        background: $primary;
        padding: 0 1;
        text-align: center;
        color: $text;
        display: none;
        border-bottom: solid $accent;
    }

    #vim-mode-indicator.visible {
        display: block;
    }

    #preview {
        width: 100%;
        padding: 0;
        overflow: hidden;
        border: none;
        scrollbar-size: 0 0;
    }
    
    ScrollableContainer {
        border: none;
        scrollbar-size: 0 0;
    }
    
    Horizontal {
        border: none;
        padding: 0;
        margin: 0;
    }

    #preview TextArea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
    }

    .constrained-textarea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
        box-sizing: border-box !important;
        padding: 0 1 !important;
    }

    #edit-wrapper {
        width: 100%;
        height: 100%;
        overflow: hidden;
        border: none;
        padding: 0;
        margin: 0;
    }
    
    #edit-container {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0;
        margin: 0;
    }
    
    #edit-container > * {
        padding: 0;
        margin: 0;
    }
    
    #line-numbers {
        border: none;
        scrollbar-size: 0 0;
        overflow: hidden;
        padding-top: 0;  /* Reset padding */
        padding-left: 0;
        padding-right: 1;
        padding-bottom: 0;
        margin-top: 0;  /* No margin adjustment */
        margin-left: 0;
        margin-right: 0;
        margin-bottom: 0;
        width: 4;
        min-width: 4;
        max-width: 4;
        height: 100%;
    }
    
    #preview-content {
        border: none !important;
        scrollbar-size: 0 0;
        overflow-x: hidden;
        overflow-y: auto;
        padding: 0;
        margin: 0;
    }
    
    #preview-content:focus {
        border: none !important;
    }
    .edit-title-input {
        width: 100%;
        margin-bottom: 1;
        background: $background;
        border: tall $primary;
    }
    .edit-title-input:focus {
        border: tall $accent;
    }

    /* Vim mode styling - using background colors instead of cursor */
    .vim-insert-mode {
        background: $background;
    }

    .vim-normal-mode {
        background: $background;
    }

    RichLog {
        width: 100%;
        height: 100%;
        padding: 0 1;
        background: $background;
    }

    RichLog:focus {
        border: thick $accent;
    }

    #preview-textarea {
        width: 100%;
        height: 100%;
        max-width: 100%;
        min-width: 0;
        padding: 0 1;
        background: $background;
        overflow-x: hidden;
        overflow-y: auto;
        box-sizing: border-box;
    }

    #preview-textarea:focus {
        border: thick $accent;
    }

    DataTable {
        height: 100%;
    }


    Input {
        dock: top;
        margin: 0 1;
        display: none;
    }

    Input.visible {
        display: block;
    }

    #tag-input {
        display: none;
    }

    #tag-input.visible {
        display: block;
    }

    #tag-selector {
        dock: top;
        display: none;
        height: 1;
        margin: 0 1;
        text-align: center;
    }

    #tag-selector.visible {
        display: block;
    }

    #status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    /* Vim relative line numbers */
    .vim-line-numbers {
        width: 4;
        background: $background;
        color: $text-muted;
        text-align: right;
        padding-right: 1;
        padding-top: 1;
        margin: 0;
        border: none;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }

    #edit-container {
        height: 100%;
        background: $background;
    }

    #edit-container TextArea {
        margin: 0;
        padding-left: 0;
        border-left: none;
        background: $background;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("escape", "quit", "Quit", show=False),
        Binding("j", "cursor_down", "Down", key_display="j"),
        Binding("k", "cursor_up", "Up", key_display="k"),
        Binding("ctrl+g", "cursor_top", "Top", show=False),
        Binding("shift+g", "cursor_bottom", "Bottom", show=False),
        Binding("/", "search_mode", "Search", key_display="/"),
        Binding("r", "refresh", "Refresh", key_display="r"),
        Binding("n", "new_note", "New Note", key_display="n"),
        Binding("e", "toggle_edit_mode", "Edit in place", key_display="e"),
        Binding("d", "git_diff_browser", "Git Diff", key_display="d"),
        Binding("a", "git_stage_file", "Stage File", show=False),
        Binding("u", "git_unstage_file", "Unstage File", show=False), 
        Binding("c", "git_commit", "Commit", show=False),
        Binding("R", "git_discard_changes", "Discard Changes", show=False),
        Binding("enter", "view", "View", show=False),
        Binding("t", "tag_mode", "Tag", key_display="t"),
        Binding("T", "untag_mode", "Untag", show=False),
        Binding("s", "toggle_selection_mode", "Select Text", key_display="s"),
        Binding("ctrl+c", "copy_selected", "Copy Selection", show=False),
        Binding("h", "tmux_split_horizontal", "Split →", key_display="h"),
        Binding("v", "tmux_split_vertical", "Split ↓", key_display="v"),
        Binding("x", "claude_execute", "Execute", key_display="x"),
        Binding("f", "open_file_browser", "Files", key_display="f"),
        Binding("g", "create_gist", "Gist", key_display="g"),
        Binding("l", "log_browser", "Log Browser", key_display="l"),
        Binding("m", "mark_execution_complete", "Kill Exec", key_display="m"),
        Binding("D", "delete", "Delete", key_display="D"),
        Binding("w", "switch_worktree", "Switch Worktree", show=False),
    ]

    mode = reactive("NORMAL")
    search_query = reactive("")
    tag_action = reactive("")  # "add" or "remove"
    current_tag_completion = reactive(0)  # Current completion index
    selection_mode = reactive(False)  # Text selection mode
    edit_mode = reactive(False)  # Edit mode for in-place editing
    editing_doc_id = None  # Track which document is being edited

    def __init__(self):
        super().__init__()
        self.documents = []
        self.filtered_docs = []
        self.current_doc_id = None
        self.refresh_timer = None  # Timer for auto-dismissing refresh status
        # Log browser state
        self.executions = []  # List of Execution objects
        self.current_execution_index = 0
        self.current_log_file = None

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input",
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")

        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with Vertical(id="preview-container"):
                yield Label("", id="vim-mode-indicator")
                with ScrollableContainer(id="preview"):
                    yield RichLog(
                        id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
                    )

        yield Label("", id="status")

    def on_mount(self) -> None:
        logger.info("on_mount called")
        try:
            # Disable focus on widgets to prevent Tab navigation
            preview_content = self.query_one("#preview-content")
            preview_content.can_focus = False
            
            # Also disable focus on input widgets when not in use
            search_input = self.query_one("#search-input")
            search_input.can_focus = False
            tag_input = self.query_one("#tag-input")
            tag_input.can_focus = False
            
            self.load_documents()
            logger.info("Documents loaded, scheduling delayed setup")
            # Delay table setup until after widgets are mounted
            self.call_after_refresh(self._delayed_setup)
        except Exception as e:
            # If there's any error during mount, ensure we have a usable state
            import traceback

            logger.error(f"Error during on_mount(): {e}")
            traceback.print_exc()
            self.exit(message=f"Error during startup: {e}")
    
    def _delayed_setup(self):
        """Setup table and UI after widgets are fully mounted."""
        logger.info("_delayed_setup called")
        try:
            self.setup_table()
            self.update_status()
            if self.filtered_docs:
                self.on_row_selected()
        except Exception as e:
            logger.error(f"Error in delayed setup: {e}", exc_info=True)
            self.exit(message=f"Error during startup: {e}")

    def load_documents(self):
        try:
            db.ensure_schema()
            docs = db.list_documents(limit=1000)

            # Add tags to each document
            for doc in docs:
                doc["tags"] = get_document_tags(doc["id"])

            self.documents = docs
            self.filtered_docs = docs
        except Exception as e:
            self.exit(message=f"Error loading documents: {e}")

    def setup_table(self):
        logger.info("setup_table called")
        try:
            table = self.query_one("#doc-table", DataTable)
            logger.info("Successfully found #doc-table")
        except Exception as e:
            logger.error(f"Failed to find #doc-table: {e}")
            raise
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Only add columns if they don't already exist
        if len(table.columns) == 0:
            table.add_columns("ID", "Title", "Tags")

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[: title_space - 3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars with emoji-safe truncation
            formatted_tags = format_tags(doc.get("tags", []))
            tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
            if was_truncated:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        table.focus()

    def on_row_selected(self):
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            self.current_doc_id = doc["id"]
            self.update_preview(doc["id"])

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        if message.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[message.cursor_row]

            # Don't allow switching documents while in edit mode
            if self.edit_mode:
                # Show warning and prevent switch
                status = self.query_one("#status", Label)
                self.cancel_refresh_timer()
                status.update("⚠️ Exit edit mode (ESC) before switching documents")
                # Move cursor back to editing document
                if self.editing_doc_id:
                    for i, d in enumerate(self.filtered_docs):
                        if d["id"] == self.editing_doc_id:
                            table = self.query_one("#doc-table", DataTable)
                            table.cursor_coordinate = (i, 0)
                            break
                return

            self.current_doc_id = doc["id"]
            self.update_preview(doc["id"])

    def get_execution_hint(self, tags: list[str]) -> str:
        """Get execution hint based on document tags."""
        from emdx.commands.claude_execute import ExecutionType, get_execution_context
        context = get_execution_context(tags)

        if context['type'] == ExecutionType.NOTE:
            return "→ Press 'x' to generate analysis"
        elif context['type'] == ExecutionType.ANALYSIS:
            return "→ Press 'x' to generate gameplan"
        elif context['type'] == ExecutionType.GAMEPLAN:
            return "→ Press 'x' to implement & create PR"
        else:
            return ""

    def get_related_documents(self, doc_id: int) -> str:
        """Find related documents and show the generation chain."""
        from emdx.models.documents import list_documents
        
        # Get current document to extract base title
        current_doc = get_document(str(doc_id))
        if not current_doc:
            return ""
            
        title = current_doc['title']
        current_tags = set(current_doc.get('tags', []))
        
        # Determine current document type
        if 'notes' in current_tags or '📝' in current_tags or title.startswith("New Note"):
            current_type = 'note'
        elif 'analysis' in current_tags or '🔍' in current_tags or title.startswith("Analysis:"):
            current_type = 'analysis'
        elif 'gameplan' in current_tags or '🎯' in current_tags or title.startswith("Gameplan:"):
            current_type = 'gameplan'
        else:
            current_type = 'unknown'
        
        base_title = (title
                     .replace("New Note - ", "")
                     .replace("Analysis: ", "")
                     .replace("Gameplan: ", "")
                     .split(" - ")[0])  # Remove timestamp if present
        
        # Find documents with similar base titles
        all_docs = list_documents(limit=1000)  # Get all docs
        related = {'note': [], 'analysis': [], 'gameplan': [], 'other': []}
        
        for doc in all_docs:
            if doc['id'] == doc_id:
                continue
                
            doc_title = doc['title']
            if base_title.lower() in doc_title.lower():
                # Determine document type by tags or title
                tags = set(doc.get('tags', []))
                if 'notes' in tags or '📝' in tags or doc_title.startswith("New Note"):
                    related['note'].append(doc['id'])
                elif 'analysis' in tags or '🔍' in tags or doc_title.startswith("Analysis:"):
                    related['analysis'].append(doc['id'])
                elif 'gameplan' in tags or '🎯' in tags or doc_title.startswith("Gameplan:"):
                    related['gameplan'].append(doc['id'])
                else:
                    related['other'].append(doc['id'])
        
        # Build the chain display
        result_lines = []
        
        # Show generation source (what created this)
        if current_type == 'analysis' and related['note']:
            result_lines.append(f"**Generated from:** 📝 #{related['note'][0]}")
        elif current_type == 'gameplan' and related['analysis']:
            result_lines.append(f"**Generated from:** 🔍 #{related['analysis'][0]}")
            if related['note']:
                result_lines.append(f"**Original note:** 📝 #{related['note'][0]}")
        
        # Show generation outputs (what this created)
        if current_type == 'note' and related['analysis']:
            result_lines.append(f"**Generated analysis:** 🔍 #{related['analysis'][0]}")
            if related['gameplan']:
                result_lines.append(f"**Generated gameplan:** 🎯 #{related['gameplan'][0]}")
        elif current_type == 'analysis' and related['gameplan']:
            result_lines.append(f"**Generated gameplan:** 🎯 #{related['gameplan'][0]}")
        
        # Show all related if there are multiple
        all_related = []
        for note_id in related['note']:
            all_related.append(f"📝 #{note_id}")
        for analysis_id in related['analysis']:
            all_related.append(f"🔍 #{analysis_id}")
        for gameplan_id in related['gameplan']:
            all_related.append(f"🎯 #{gameplan_id}")
        for other_id in related['other']:
            all_related.append(f"📄 #{other_id}")
        
        if len(all_related) > 1:  # More than just direct parent/child
            result_lines.append(f"**All related:** {', '.join(all_related)}")
        
        if result_lines:
            return "\n\n" + "\n".join(result_lines)
        return ""

    def update_preview(self, doc_id: int):
        try:
            doc = get_document(str(doc_id))
            if doc:
                # Check if we're in selection mode or formatted mode
                try:
                    preview_area = self.query_one("#preview-content", RichLog)
                    # We're in formatted mode
                    preview_area.clear()

                    # Add execution hint and related documents
                    hint = self.get_execution_hint(doc.get('tags', []))
                    related = self.get_related_documents(doc_id)

                    content = doc["content"].strip()
                    content_lines = content.split("\n")
                    first_line = content_lines[0].strip() if content_lines else ""

                    # Build the full content with hint and related docs
                    extra_content = ""
                    if hint:
                        extra_content += f"*{hint}*\n\n"
                    if related:
                        extra_content += related + "\n\n"

                    if first_line == f"# {doc['title']}":
                        if extra_content:
                            markdown_content = f"# {doc['title']}\n\n{extra_content}{content[len(first_line)+1:].strip()}"
                        else:
                            markdown_content = content
                    else:
                        if extra_content:
                            markdown_content = f"# {doc['title']}\n\n{extra_content}{content}"
                        else:
                            markdown_content = f"# {doc['title']}\n\n{content}"

                    from rich.markdown import Markdown

                    md = Markdown(markdown_content, code_theme="monokai")
                    preview_area.write(md)

                except Exception:
                    # Might be in selection mode with TextArea
                    try:
                        preview_area = self.query_one("#preview-content")
                        content = doc["content"].strip()
                        if not content.startswith(f"# {doc['title']}"):
                            plain_content = f"# {doc['title']}\n\n{content}"
                        else:
                            plain_content = content
                        preview_area.text = plain_content
                    except Exception:
                        pass

        except Exception as e:
            # Try to show error in whatever widget we have
            try:
                preview_area = self.query_one("#preview-content", RichLog)
                preview_area.clear()
                preview_area.write(f"[red]Error loading preview: {e}[/red]")
            except Exception:
                try:
                    preview_area = self.query_one("#preview-content")
                    preview_area.text = f"Error loading preview: {e}"
                except Exception:
                    pass

    def update_status(self, custom_message=None):
        # Cancel refresh timer, but preserve log monitoring in LOG_BROWSER mode
        if self.mode != "LOG_BROWSER":
            self.cancel_refresh_timer()
        else:
            # In log browser mode, only cancel the status refresh timer, not log monitoring
            if self.refresh_timer:
                self.refresh_timer.stop()
                self.refresh_timer = None

        status = self.query_one("#status", Label)
        
        # If custom message provided, use it directly
        if custom_message:
            status.update(custom_message)
            return
            
        search_input = self.query_one("#search-input", Input)

        # Build status with document count
        status_parts = []
        if search_input.value and search_input.value.startswith("tags:"):
            tag_query = search_input.value[5:].strip()
            status_parts.append(
                f"{len(self.filtered_docs)}/{len(self.documents)} docs (tag: {tag_query})"
            )
        elif search_input.value:
            status_parts.append(
                f"{len(self.filtered_docs)}/{len(self.documents)} docs (search: {search_input.value})"
            )
        else:
            status_parts.append(f"{len(self.filtered_docs)}/{len(self.documents)} docs")

        # Add key hints for normal mode
        if self.mode == "NORMAL":
            status_parts.append("n=new | e=edit | /=search | t=tag | q=quit")
        elif self.mode == "SEARCH":
            status_parts.append("Enter=apply | ESC=cancel")
        elif self.mode == "TAG":
            if self.tag_action == "add":
                status_parts.append("Enter=add tags | ESC=cancel")
            else:
                status_parts.append("Tab=select | Enter=remove | ESC=cancel")

        status.update(" | ".join(status_parts))

    def _update_vim_status(self, message=None):
        """Update status bar to show vim mode when in edit mode."""
        if self.edit_mode and hasattr(self, 'edit_textarea') and hasattr(self.edit_textarea, 'vim_mode'):
            vim_mode = self.edit_textarea.vim_mode
            pending = getattr(self.edit_textarea, 'pending_command', '')
            repeat = getattr(self.edit_textarea, 'repeat_count', '')
            command_buffer = getattr(self.edit_textarea, 'command_buffer', '')

            # Hide vim mode indicator in preview pane (use status bar instead)
            try:
                vim_indicator = self.query_one("#vim-mode-indicator", Label)
                vim_indicator.remove_class("visible")
            except Exception as e:
                logger.error(f"Failed to hide vim mode indicator: {e}")

            # Build mode indicator text with subtle cursor hints (vim-like)
            try:
                if vim_mode == "INSERT":
                    vim_indicator.update("[bold green]-- INSERT --[/bold green]")
                elif vim_mode == "NORMAL":
                    mode_text = "-- NORMAL --"
                    if repeat:
                        mode_text = f"-- NORMAL ({repeat}) --"
                    if pending:
                        mode_text = f"-- NORMAL ({pending}) --"
                    vim_indicator.update(f"[bold blue]{mode_text}[/bold blue]")
                elif vim_mode == "VISUAL":
                    vim_indicator.update("[bold yellow]-- VISUAL --[/bold yellow]")
                elif vim_mode == "V-LINE":
                    vim_indicator.update("[bold yellow]-- VISUAL LINE --[/bold yellow]")
                elif vim_mode == "COMMAND":
                    vim_indicator.update(f"[bold magenta]{command_buffer}[/bold magenta]")
            except Exception as e:
                logger.error(f"Failed to update vim indicator text: {e}")

            # Build status message
            status_parts = [f"EDIT MODE: #{self.editing_doc_id}"]

            # Add message if provided
            if message:
                status_parts.append(f"[red]{message}[/red]")
            else:
                # Add instructions
                if vim_mode == "INSERT":
                    status_parts.append("ESC=normal | Ctrl+S=save")
                elif vim_mode == "COMMAND":
                    status_parts.append("Enter=execute | ESC=cancel")
                elif vim_mode == "NORMAL":
                    status_parts.append("i=insert | :=command | ESC=exit | Tab=switch title/content")
                else:
                    status_parts.append("ESC=normal/exit")

            status = self.query_one("#status", Label)
            status.update(" | ".join(status_parts))
        else:
            # Hide vim mode indicator when not in edit mode
            try:
                vim_indicator = self.query_one("#vim-mode-indicator", Label)
                vim_indicator.remove_class("visible")
                vim_indicator.update("")
            except Exception:
                pass  # Indicator might not exist yet

    def watch_mode(self, old_mode: str, new_mode: str):
        try:
            # Check if we're mounted first
            if not self.is_mounted:
                return
                
            search = self.query_one("#search-input", Input)
            tag_input = self.query_one("#tag-input", Input)
            tag_selector = self.query_one("#tag-selector", Label)
            table = self.query_one("#doc-table", DataTable)
        except Exception:
            # Widgets don't exist yet (during initialization) - skip mode handling
            return

        if new_mode == "SEARCH":
            search.add_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.can_focus = True
            search.focus()
        elif new_mode == "TAG":
            search.remove_class("visible")

            # Show current tags in placeholder
            if self.current_doc_id:
                doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
                if doc:
                    current_tags = doc.get("tags", [])

                    if self.tag_action == "add":
                        # Show input for adding tags
                        tag_input.add_class("visible")
                        tag_selector.remove_class("visible")
                        if current_tags:
                            tag_input.placeholder = f"Add tags (current: {', '.join(current_tags)})"
                        else:
                            tag_input.placeholder = "Add tags (no current tags)"
                        tag_input.can_focus = True
                        tag_input.focus()
                    else:  # remove
                        # Show visual selector for removing tags
                        tag_input.remove_class("visible")
                        if current_tags:
                            tag_selector.add_class("visible")
                            self.current_tag_completion = 0  # Start with first tag
                            self.update_tag_selector()
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("Tab to navigate, Enter to remove tag, Esc to cancel")
                        else:
                            tag_selector.remove_class("visible")
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No tags to remove")
                            self.mode = "NORMAL"
                            return

                    # Only reset completion index for add mode
                    if self.tag_action == "add":
                        self.current_tag_completion = 0
        else:
            search.remove_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.value = ""
            tag_input.value = ""
            # Disable focus on inputs when not in use
            search.can_focus = False
            tag_input.can_focus = False
            self.current_tag_completion = 0  # Reset completion index
            table.focus()

    def action_search_mode(self):
        self.mode = "SEARCH"

    def action_tag_mode(self):
        if not self.current_doc_id:
            return
        self.tag_action = "add"
        self.mode = "TAG"

    def action_untag_mode(self):
        if not self.current_doc_id:
            logger.info("DEBUG: action_untag_mode called but no current_doc_id")
            return
        logger.info("DEBUG: action_untag_mode called, setting mode to TAG")
        self.tag_action = "remove"
        self.mode = "TAG"
        logger.info(f"DEBUG: mode set to {self.mode}, tag_action set to {self.tag_action}")

    def action_new_note(self):
        """Create a new note in the TUI."""
        try:
            # Generate title with timestamp
            from datetime import datetime
            title = f"New Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Detect project from current directory
            from pathlib import Path

            from emdx.utils.git import get_git_project
            project = get_git_project(Path.cwd())

            # Create new document in database
            from emdx.models.documents import save_document
            doc_id = save_document(title, "", project)
            
            # Add auto-tag after creation
            from emdx.models.tags import add_tags_to_document
            add_tags_to_document(str(doc_id), ['notes'])

            # Refresh documents list
            self.load_documents()
            self.filter_documents(self.search_query)

            # Find the new document in the list and select it
            for i, doc in enumerate(self.filtered_docs):
                if doc["id"] == doc_id:
                    table = self.query_one("#doc-table", DataTable)
                    table.cursor_coordinate = (i, 0)
                    self.on_row_selected()
                    break

            # Immediately enter edit mode
            self.action_toggle_edit_mode()

            # Update status to show user they're in new note (NORMAL mode)
            self._update_vim_status("New note created - press 'i' to insert")

        except Exception as e:
            logger.error(f"Error creating new note: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error creating new note: {str(e)[:50]}...")

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search-input":
            self.search_query = event.value
            self.filter_documents(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self.mode = "NORMAL"
        elif event.input.id == "tag-input":
            # Process tag input for both add and remove
            tags = [tag.strip() for tag in event.value.split() if tag.strip()]
            if tags and self.current_doc_id:
                # Save current position
                table = self.query_one("#doc-table", DataTable)
                current_row = table.cursor_row
                current_doc_id = self.current_doc_id

                try:
                    if self.tag_action == "add":
                        added_tags = add_tags_to_document(self.current_doc_id, tags)
                        if added_tags:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update(f"Added tags: {', '.join(added_tags)}")
                        else:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No new tags added (may already exist)")
                    else:  # remove
                        removed_tags = remove_tags_from_document(self.current_doc_id, tags)
                        if removed_tags:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update(f"Removed tags: {', '.join(removed_tags)}")
                        else:
                            self.cancel_refresh_timer()
                            status = self.query_one("#status", Label)
                            status.update("No tags removed (may not exist)")

                    # Refresh document data and restore position
                    self.load_documents()
                    self.filter_documents(self.search_query)
                    self.restore_table_position(current_doc_id, current_row)

                except Exception as e:
                    self.cancel_refresh_timer()
                    status = self.query_one("#status", Label)
                    status.update(f"Error: {e}")

            self.mode = "NORMAL"

    def on_key(self, event: events.Key) -> None:
        try:
            # Check if any modal or screen is active (screen stack > 1 means another screen is pushed)
            if len(self.screen_stack) > 1:
                # Another screen is active, let it handle the key event
                active_screen = self.screen_stack[-1]
                screen_type = type(active_screen).__name__
                key_logger.info(f"{screen_type} active, passing key event through: key={event.key}")
                return
            
            # Comprehensive logging of ALL key events
            event_attrs = {}
            for attr in ["key", "character", "name", "is_printable", "aliases"]:
                if hasattr(event, attr):
                    try:
                        event_attrs[attr] = getattr(event, attr)
                    except Exception as attr_error:
                        event_attrs[attr] = f"ERROR: {attr_error}"

            key_logger.info(f"App.on_key: {event_attrs}")
            logger.debug(f"Key event: key={event.key}")

            # Handle j/k keys for log switching in log browser mode
            if hasattr(self, 'mode') and self.mode == "LOG_BROWSER" and hasattr(self, 'executions'):
                if event.key == "j":
                    self.action_next_log()
                    event.stop()
                    event.prevent_default()
                    return
                elif event.key == "k":
                    self.action_prev_log()
                    event.stop()
                    event.prevent_default()
                    return

            # Globally handle Tab to prevent default focus behavior
            if event.key == "tab":
                logger.info(f"DEBUG: Global Tab handler, mode={self.mode}, tag_action={getattr(self, 'tag_action', 'None')}")
                # Only allow Tab in TAG mode for tag cycling
                if self.mode == "TAG" and self.tag_action == "remove":
                    logger.info(f"DEBUG: Allowing Tab to fall through to TAG handler")
                    # Let it fall through to the TAG mode handler below
                    pass
                else:
                    logger.info(f"DEBUG: Blocking Tab in non-untag mode")
                    # Block Tab in all other modes
                    event.prevent_default()
                    event.stop()
                    return

            # Handle global Escape key - quit from any mode
            if event.key == "escape":
                # Edit mode ESC is handled by VimEditTextArea - don't interfere
                if self.edit_mode:
                    # Let the edit widget handle ESC
                    return

                # Selection mode ESC is handled by SelectionTextArea

                # From any mode/state, ESC should quit
                if self.mode == "SEARCH":
                    self.mode = "NORMAL"
                    self.search_query = ""
                    self.filter_documents("")
                elif self.mode == "TAG":
                    self.mode = "NORMAL"
                else:
                    # From normal mode or preview focus, quit the app
                    self.action_quit()
                event.prevent_default()
                return

            if self.mode == "TAG":
                logger.info(f"DEBUG: In TAG mode, key={event.key}, tag_action={self.tag_action}")
                if event.key == "tab" and self.tag_action == "remove":
                    logger.info(f"DEBUG: Tab pressed in remove mode, calling complete_tag_removal")
                    # Tab cycling for tag removal
                    self.complete_tag_removal()
                    event.prevent_default()
                    event.stop()
                    return
                elif event.key == "enter" and self.tag_action == "remove":
                    logger.info(f"DEBUG: Enter pressed in remove mode, calling remove_highlighted_tag")
                    # Remove the highlighted tag
                    self.remove_highlighted_tag()
                    event.prevent_default()
                    event.stop()
                    return
                else:
                    logger.info(f"DEBUG: Other key in TAG mode, blocking")
                    # In TAG mode, block all other keys except ESC (handled above)
                    event.prevent_default()
                    event.stop()
                    return
            elif self.mode == "NORMAL":
                # Handle keys that don't require a document
                if event.character == "s":
                    event.prevent_default()
                    event.stop()
                    self.action_toggle_selection_mode()
                elif event.character == "n":
                    event.prevent_default()
                    event.stop()
                    self.action_new_note()
                # Handle keys that require a document
                elif self.current_doc_id:
                    if event.key == "enter":
                        event.prevent_default()
                        event.stop()
                        self.action_view()
                    elif event.character == "e":
                        event.prevent_default()
                        event.stop()
                        self.action_toggle_edit_mode()
                    elif event.character == "d":
                        event.prevent_default()
                        event.stop()
                        self.action_delete()
                    elif event.character == "t":
                        event.prevent_default()
                        event.stop()
                        self.action_tag_mode()
                    elif event.character == "T":
                        logger.info(f"DEBUG: Manual T character handler triggered")
                        event.prevent_default()
                        event.stop()
                        self.action_untag_mode()

        # Note: In Textual 4.0, we should NOT call super().on_key()
        # as Textual automatically handles event propagation

        except Exception as e:
            key_logger.error(f"CRASH in App.on_key: {e}")
            logger.error(f"Error in App.on_key: {e}", exc_info=True)
            # Don't re-raise here - let app continue

    def filter_documents(self, query: str):
        if not query:
            self.filtered_docs = self.documents
        elif query.startswith("tags:"):
            # Tag-based search mode: "tags:docker,kubernetes" or "tags:any:docker,python"
            tag_query = query[5:].strip()  # Remove "tags:" prefix

            if tag_query.startswith("any:"):
                # Search for documents with ANY of the specified tags
                tags = [tag.strip() for tag in tag_query[4:].split(",") if tag.strip()]
                mode = "any"
            else:
                # Default: search for documents with ALL specified tags
                tags = [tag.strip() for tag in tag_query.split(",") if tag.strip()]
                mode = "all"

            if tags:
                try:
                    # Expand aliases before searching
                    expanded_tags = expand_aliases(tags)
                    # Use the existing search_by_tags function
                    results = search_by_tags(expanded_tags, mode=mode, limit=1000)

                    # Convert results to match our document format
                    result_ids = {doc["id"] for doc in results}
                    self.filtered_docs = [doc for doc in self.documents if doc["id"] in result_ids]
                except Exception:
                    # Fall back to simple filtering if search_by_tags fails
                    self.filtered_docs = [
                        doc
                        for doc in self.documents
                        if any(
                            tag.lower() in [t.lower() for t in doc.get("tags", [])] for tag in tags
                        )
                    ]
            else:
                self.filtered_docs = self.documents
        else:
            # Regular search in title, project, and tags
            query_lower = query.lower()
            self.filtered_docs = [
                doc
                for doc in self.documents
                if query_lower in doc["title"].lower()
                or query_lower in (doc["project"] or "").lower()
                or any(query_lower in tag.lower() for tag in doc.get("tags", []))
            ]

        table = self.query_one("#doc-table", DataTable)
        table.clear()

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[: title_space - 3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars with emoji-safe truncation
            formatted_tags = format_tags(doc.get("tags", []))
            tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
            if was_truncated:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        self.update_status()

        if self.filtered_docs and table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_down(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_down()

    def action_cursor_up(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_up()

    def action_cursor_top(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_bottom(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            if table.row_count > 0:
                table.cursor_coordinate = (table.row_count - 1, 0)
                self.on_row_selected()


    def action_delete(self):
        logger.info(f"action_delete called, mode={self.mode}, current_doc_id={self.current_doc_id}")
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]

            def check_delete(should_delete: bool) -> None:
                logger.info(f"check_delete callback called with: {should_delete}")
                if should_delete:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "emdx.main",
                            "delete",
                            str(self.current_doc_id),
                            "--force",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        self.load_documents()
                        self.filter_documents(self.search_query)
                        status = self.query_one("#status", Label)
                        status.update(f"Document #{self.current_doc_id} deleted")
                else:
                    status = self.query_one("#status", Label)
                    status.update("Delete cancelled")

            logger.info(f"Pushing DeleteConfirmScreen for doc #{doc['id']}: {doc['title']}")
            self.push_screen(DeleteConfirmScreen(doc["id"], doc["title"]), check_delete)

    def action_view(self):
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        self.push_screen(FullScreenView(self.current_doc_id))

    def action_refresh(self):
        """Refresh the document list."""
        # Save current state
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = None

        # Get current document ID if a row is selected
        if current_row is not None and current_row < len(self.filtered_docs):
            current_doc_id = self.filtered_docs[current_row]["id"]

        # Save search state
        search_query = self.search_query if self.mode == "SEARCH" else None

        # Reload documents
        self.load_documents()

        # Clear and rebuild table
        table.clear()
        self.setup_table()

        # Restore search if it was active
        if search_query:
            self.search_query = search_query
            search_input = self.query_one("#search-input", Input)
            search_input.value = search_query
            self.filter_documents(search_query)

        # Restore selection
        if current_doc_id:
            # Try to find the same document
            for idx, doc in enumerate(self.filtered_docs):
                if doc["id"] == current_doc_id:
                    table.cursor_coordinate = (idx, 0)
                    self.on_row_selected()
                    break
            else:
                # Document not found, restore row position if valid
                if current_row is not None and current_row < len(self.filtered_docs):
                    table.cursor_coordinate = (current_row, 0)
                    self.on_row_selected()
                elif self.filtered_docs:
                    # Default to first row if available
                    table.cursor_coordinate = (0, 0)
                    self.on_row_selected()
        elif self.filtered_docs and current_row is not None:
            # No previous doc ID, just restore row position
            new_row = min(current_row, len(self.filtered_docs) - 1)
            table.cursor_coordinate = (new_row, 0)
            self.on_row_selected()

        # Show notification with auto-dismiss after 3 seconds
        status = self.query_one("#status", Label)
        status.update("Documents refreshed")

        # Cancel any existing timer
        if self.refresh_timer:
            self.refresh_timer.stop()

        # Set a timer to restore the normal status after 3 seconds
        self.refresh_timer = self.set_timer(3.0, self.restore_normal_status)

    def update_tag_selector(self):
        """Update the visual tag selector."""
        if not self.current_doc_id:
            return

        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        tag_selector = self.query_one("#tag-selector", Label)

        # Build visual representation: a  [b]  c
        visual_tags = []
        for i, tag in enumerate(current_tags):
            if i == self.current_tag_completion:
                visual_tags.append(f"[reverse]{tag}[/reverse]")
            else:
                visual_tags.append(tag)

        tag_selector.update("    ".join(visual_tags))

    def complete_tag_removal(self):
        """Handle tab cycling for tag removal."""
        if not self.current_doc_id:
            return

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        # Move to next tag
        self.current_tag_completion = (self.current_tag_completion + 1) % len(current_tags)

        # Update visual selector
        self.update_tag_selector()

    def remove_highlighted_tag(self):
        """Remove the currently highlighted tag."""
        if not self.current_doc_id:
            return

        # Save current table position
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = self.current_doc_id

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags or self.current_tag_completion >= len(current_tags):
            return

        # Get the tag to remove
        tag_to_remove = current_tags[self.current_tag_completion]

        try:
            # Remove the tag
            removed_tags = remove_tags_from_document(self.current_doc_id, [tag_to_remove])
            if removed_tags:
                # Show success message
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Removed tag: {tag_to_remove}")

                # Refresh document data but preserve position
                self.load_documents()
                self.filter_documents(self.search_query)

                # Restore table position
                self.restore_table_position(current_doc_id, current_row)

                # Exit tag mode
                self.mode = "NORMAL"
            else:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Failed to remove tag")
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error removing tag: {e}")

    def restore_table_position(self, target_doc_id: int, fallback_row: int):
        """Restore table position to specific document or row."""
        table = self.query_one("#doc-table", DataTable)

        # First try to find the same document
        for idx, doc in enumerate(self.filtered_docs):
            if doc["id"] == target_doc_id:
                table.cursor_coordinate = (idx, 0)
                self.on_row_selected()
                return

        # Document not found (maybe filtered out), restore row position if valid
        if fallback_row is not None and fallback_row < len(self.filtered_docs):
            table.cursor_coordinate = (fallback_row, 0)
            self.on_row_selected()
        elif self.filtered_docs:
            # Default to first row if available
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_copy_selected(self):
        """Copy selected text or full document when Ctrl+C is pressed."""
        logger.debug("action_copy_selected called")
        try:
            if self.selection_mode:
                logger.debug("In selection mode, trying to copy selected text")
                # Try to get selected text from TextArea
                try:
                    text_area = self.query_one("#preview-content", SelectionTextArea)
                    selected_text = text_area.selected_text

                    if selected_text:
                        logger.debug(f"Copying selected text: {len(selected_text)} characters")
                        self.copy_to_clipboard(selected_text)
                        status = self.query_one("#status", Label)
                        self.cancel_refresh_timer()
                        status.update("Selected text copied to clipboard!")
                    else:
                        logger.debug("No text selected, copying full document")
                        self.action_copy_content()
                except Exception as text_error:
                    logger.debug(
                        f"Could not get selected text: {text_error}, copying full document"
                    )
                    self.action_copy_content()
            else:
                logger.debug("Not in selection mode, copying full document")
                # Not in selection mode, copy full document
                self.action_copy_content()
        except Exception as e:
            logger.error(f"Error in action_copy_selected: {e}", exc_info=True)
            # Log error but don't crash
            try:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Copy error: {str(e)[:30]}...")
            except Exception:
                pass

    def action_copy_content(self):
        """Copy current document content to clipboard."""
        logger.debug(f"action_copy_content called, current_doc_id={self.current_doc_id}")
        if self.current_doc_id:
            try:
                doc = get_document(str(self.current_doc_id))
                if doc:
                    content = doc["content"].strip()
                    if not content.startswith(f"# {doc['title']}"):
                        content_to_copy = f"# {doc['title']}\n\n{content}"
                    else:
                        content_to_copy = content

                    logger.debug(f"Copying {len(content_to_copy)} characters to clipboard")
                    self.copy_to_clipboard(content_to_copy)
                    status = self.query_one("#status", Label)
                    self.cancel_refresh_timer()
                    status.update("Full document copied to clipboard!")

            except Exception as e:
                logger.error(f"Error in action_copy_content: {e}", exc_info=True)
                status = self.query_one("#status", Label)
                self.cancel_refresh_timer()
                status.update(f"Copy failed: {e}")

    def action_focus_preview(self):
        """Focus the preview pane."""
        try:
            # Try to get whatever widget is currently in the preview
            preview_area = self.query_one("#preview-content")
            preview_area.focus()
            status = self.query_one("#status", Label)

            if self.selection_mode:
                self.cancel_refresh_timer()
                status.update("TextArea focused - select text with mouse, Esc to return")
            else:
                self.cancel_refresh_timer()
                status.update("Preview focused - use 's' for text selection, Esc to return")
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Focus failed: {e}")

    def action_toggle_selection_mode(self):
        """Toggle between formatted view and text selection mode."""
        try:
            # Check if we're in the right screen/context
            try:
                container = self.query_one("#preview", ScrollableContainer)
                status = self.query_one("#status", Label)
            except Exception:
                # We're not in the main browser screen - selection mode not available
                return

            if not self.selection_mode:
                # Switch to selection mode - use TextArea for native selection support
                self.selection_mode = True

                # Get content based on current mode
                plain_content = "Select and copy text here..."

                if self.mode == "LOG_BROWSER":
                    # Extract log content from RichLog
                    plain_content = self._extract_log_content()
                elif self.current_doc_id:
                    doc = get_document(str(self.current_doc_id))
                    if doc:
                        content = doc["content"].strip()
                        if not content.startswith(f"# {doc['title']}"):
                            plain_content = f"# {doc['title']}\n\n{content}"
                        else:
                            plain_content = content

                # Remove old widgets explicitly and safely
                try:
                    # First try to remove by query
                    existing_widget = container.query_one("#preview-content")
                    if existing_widget:
                        existing_widget.remove()
                except Exception:
                    pass

                # Then remove all children as backup
                container.remove_children()

                # Refresh the container to ensure DOM is clean
                container.refresh(layout=True)

                # Use deferred mounting to avoid ID conflicts
                def mount_text_area():
                    try:
                        text_area = SelectionTextArea(
                            self,  # Pass app instance
                            plain_content,
                            id="preview-content"
                        )
                        # Make it read-only after creation
                        text_area.read_only = True
                        # Keep it focusable for selection
                        text_area.disabled = False
                        text_area.can_focus = True

                        # Apply the constrained-textarea CSS class
                        text_area.add_class("constrained-textarea")

                        # Try to enable word wrap if the property exists
                        if hasattr(text_area, 'word_wrap'):
                            text_area.word_wrap = True

                        # Mount the widget with constraints already applied
                        container.mount(text_area)
                        text_area.focus()

                        self.cancel_refresh_timer()
                        status.update(
                            "SELECTION MODE: Select text with mouse, Ctrl+C to copy, ESC or 's' to exit"
                        )
                    except Exception as mount_error:
                        self.cancel_refresh_timer()
                        status.update(f"Failed to create selection widget: {mount_error}")

                # Use call_after_refresh to ensure DOM is clean before mounting
                self.call_after_refresh(mount_text_area)

            else:
                # Switch back to formatted view
                self.selection_mode = False

                # Remove old widgets explicitly and safely
                try:
                    # First try to remove by query
                    existing_widget = container.query_one("#preview-content")
                    if existing_widget:
                        existing_widget.remove()
                except Exception:
                    pass

                # Then remove all children as backup
                container.remove_children()

                # Refresh the container to ensure DOM is clean
                container.refresh(layout=True)

                # Use deferred mounting to avoid ID conflicts
                def mount_richlog():
                    richlog = RichLog(
                        id="preview-content",
                        wrap=True,
                        highlight=True,
                        markup=True,
                        auto_scroll=False
                    )

                    # Mount the new widget
                    container.mount(richlog)

                    # Reset container scroll and refresh layout
                    container.scroll_to(0, 0, animate=False)
                    container.refresh(layout=True)

                    # Use deferred content restoration
                    self.call_after_refresh(self._restore_preview_content)

                # Use call_after_refresh to ensure DOM is clean before mounting
                self.call_after_refresh(mount_richlog)

                self.cancel_refresh_timer()
                if self.mode == "LOG_BROWSER":
                    status.update("LOG BROWSER: j/k to navigate logs, 'm' to kill exec, 's' for text selection, 'q' to exit")
                else:
                    status.update("FORMATTED MODE: Nice display, 's' for text selection, ESC to quit")

        except Exception as e:
            # Recovery: ensure we have a working widget
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Toggle failed: {e} - restoring view...")

            try:
                # Emergency recovery - ensure we have a preview widget
                container = self.query_one("#preview", ScrollableContainer)
                container.remove_children()
                # Clear artifacts before mounting
                container.refresh()

                richlog = RichLog(
                    id="preview-content",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False
                )
                container.mount(richlog)
                self.selection_mode = False

                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)

            except Exception as recovery_error:
                self.cancel_refresh_timer()
                status.update(f"Failed to recover preview: {recovery_error}")

    def _restore_preview_content(self):
        """Restore preview content after switching back from selection mode."""
        try:
            if self.mode == "LOG_BROWSER":
                # Restore log content
                if hasattr(self, 'current_execution_index') and self.executions:
                    self.load_execution_log(self.current_execution_index)
            elif self.current_doc_id:
                # Update the preview with current document
                self.update_preview(self.current_doc_id)

            # Return focus to table
            table = self.query_one("#doc-table", DataTable)
            table.focus()
        except Exception:
            import traceback

            traceback.print_exc()

    def action_toggle_edit_mode(self):
        """Toggle between view and edit modes for current document."""
        logger.info(f"action_toggle_edit_mode called, current_doc_id={self.current_doc_id}, edit_mode={self.edit_mode}")
        if not self.current_doc_id:
            status = self.query_one("#status", Label)
            self.cancel_refresh_timer()
            status.update("Select a document first")
            return

        if self.edit_mode:
            # Currently editing - save and exit
            self.action_save_and_exit_edit()
        else:
            # Enter edit mode
            self.action_enter_edit_mode()

    def action_enter_edit_mode(self):
        """Enter edit mode for current document."""
        try:
            logger.info(f"action_enter_edit_mode called, current_doc_id={self.current_doc_id}")
            if not self.current_doc_id:
                return

            # Exit selection mode if active
            if self.selection_mode:
                self.action_toggle_selection_mode()

            # Get document content
            doc = get_document(str(self.current_doc_id))
            if not doc:
                return

            # Get container and status
            container = self.query_one("#preview", ScrollableContainer)
            status = self.query_one("#status", Label)

            # Clear container with better timing to prevent artifacts
            container.remove_children()
            # Force immediate layout refresh to clear any artifacts
            container.refresh()

            # Create a wrapper container to enforce width constraints
            from textual.containers import Container
            edit_wrapper = Container(id="edit-wrapper")

            # Skip title input for now to simplify line number positioning
            # title_input = TitleInput(...)  # Commented out

            # Strip title from content for editing (user shouldn't edit the title inline)
            content = doc["content"].strip()
            title_header = f"# {doc['title']}"
            if content.startswith(title_header):
                # Remove title header and any following newlines
                content_without_title = content[len(title_header):].lstrip('\n')
            else:
                content_without_title = content
            
            # Create VimEditTextArea with title-stripped content
            edit_area = VimEditTextArea(self, text=content_without_title, id="preview-content")
            self.edit_textarea = edit_area  # Store reference for vim status updates
            # self.edit_title_input = title_input  # No title input anymore

            # Make it editable (not read-only like selection mode)
            edit_area.read_only = False
            edit_area.disabled = False
            edit_area.can_focus = True

            # Apply the constrained-textarea CSS class
            edit_area.add_class("constrained-textarea")

            # CRITICAL: Set word wrap BEFORE any other properties
            edit_area.word_wrap = True
            edit_area.show_line_numbers = False  # Disable built-in, using custom vim relative numbers

            # Try setting max line length if available
            if hasattr(edit_area, 'max_line_length'):
                edit_area.max_line_length = 80  # Enforce maximum line length

            # Mount wrapper in preview container
            container.mount(edit_wrapper)

            # Create simple line numbers widget
            line_numbers = SimpleVimLineNumbers(id="line-numbers")
            edit_area.line_numbers_widget = line_numbers

            # Create horizontal container for line numbers and text area
            edit_container = Horizontal(id="edit-container")

            # Mount only the edit container (no title)
            edit_wrapper.mount(edit_container)

            # Now mount widgets in the container after it's mounted
            edit_container.mount(line_numbers)
            edit_container.mount(edit_area)

            # Reset container scroll with single refresh to prevent artifacts
            container.scroll_to(0, 0, animate=False)
            # Single refresh call to reduce visual artifacts
            self.refresh(layout=True)

            # Focus the content editor first instead of title input
            edit_area.focus()

            # Initialize line numbers with current cursor position and text area reference
            current_line = edit_area.cursor_location[0] if hasattr(edit_area, 'cursor_location') else 0
            total_lines = len(edit_area.text.split('\n'))
            logger.info(f"📍 INITIAL SETUP: cursor_location={edit_area.cursor_location if hasattr(edit_area, 'cursor_location') else 'None'}")
            logger.info(f"📍 INITIAL SETUP: current_line={current_line}, total_lines={total_lines}")
            
            # Force cursor to start at beginning if needed
            if current_line == 0:
                edit_area.cursor_location = (0, 0)
                
            line_numbers.set_line_numbers(current_line, total_lines, edit_area)

            # Debug logging to understand width issues
            logger.info(f"EditTextArea mounted - container width: {container.size.width}")
            logger.info(f"EditTextArea classes: {edit_area.classes}")

            # Store current cursor position before entering edit mode
            table = self.query_one("#doc-table", DataTable)
            self.edit_mode_cursor_position = table.cursor_coordinate

            # Update state
            self.edit_mode = True
            self.editing_doc_id = self.current_doc_id

            # Update status with vim mode and tab hint
            self.cancel_refresh_timer()
            self._update_vim_status()

        except Exception as e:
            logger.error(f"Error entering edit mode: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Edit mode failed: {str(e)}")

    def action_save_and_exit_edit(self):
        """Save changes and exit edit mode."""
        try:
            if not self.edit_mode or not self.editing_doc_id:
                return

            # Get the container and edit area
            container = self.query_one("#preview", ScrollableContainer)
            status = self.query_one("#status", Label)

            # Find the edit area within the wrapper
            try:
                from textual.containers import Container
                edit_wrapper = self.query_one("#edit-wrapper", Container)
                edit_area = edit_wrapper.query_one("#preview-content", EditTextArea)
            except:
                # Fallback if wrapper doesn't exist
                edit_area = self.query_one("#preview-content", EditTextArea)

            # Get the edited content (no title editing for now)
            new_content = edit_area.text
            new_title = None  # Keep original title for now

            # Get current document for comparison
            doc = get_document(str(self.editing_doc_id))
            if not doc:
                return

            # Check if content or title changed
            content_changed = new_content != edit_area.original_content
            title_changed = new_title and new_title != doc["title"]

            if content_changed or title_changed:
                # Update document in database
                from emdx.models.documents import update_document

                # Use new title if provided, otherwise keep existing
                final_title = new_title if new_title else doc["title"]
                success = update_document(self.editing_doc_id, final_title, new_content)

                if success:
                    self.cancel_refresh_timer()
                    status.update(f"✅ Saved changes to #{self.editing_doc_id}")

                    # Refresh the document list to show updated timestamp
                    self.load_documents()
                    self.filter_documents(self.search_query)
                else:
                    self.cancel_refresh_timer()
                    status.update(f"❌ Failed to save changes to #{self.editing_doc_id}")
            else:
                self.cancel_refresh_timer()
                status.update("No changes made")

            # Exit edit mode
            self.edit_mode = False
            self.editing_doc_id = None

            # Hide vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.remove_class("visible")
            vim_indicator.update("")

            # Clear edit interface with better timing to prevent artifacts
            container.remove_children()
            # Force immediate refresh to clear artifacts
            container.refresh()

            # Create new RichLog for preview
            richlog = RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False
            )
            container.mount(richlog)

            # Reset container scroll with single refresh to prevent artifacts
            container.scroll_to(0, 0, animate=False)
            # Single refresh call to reduce visual artifacts
            self.refresh(layout=True)

            # Use deferred content restoration (SAME AS SELECTION MODE)
            self.call_after_refresh(self._restore_preview_content)

            # Restore cursor position to where it was before edit mode
            if hasattr(self, 'edit_mode_cursor_position'):
                table = self.query_one("#doc-table", DataTable)
                try:
                    table.cursor_coordinate = self.edit_mode_cursor_position
                except:
                    pass  # Position might be invalid after refresh
                delattr(self, 'edit_mode_cursor_position')

        except Exception as e:
            logger.error(f"Error saving and exiting edit mode: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Save failed: {str(e)}")

            # Try to recover
            try:
                self.edit_mode = False
                self.editing_doc_id = None
                container = self.query_one("#preview", ScrollableContainer)
                container.remove_children()
                # Clear artifacts before mounting
                container.refresh()

                richlog = RichLog(
                    id="preview-content",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False
                )
                container.mount(richlog)

                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)

                # Try to restore cursor position even in error recovery
                if hasattr(self, 'edit_mode_cursor_position'):
                    table = self.query_one("#doc-table", DataTable)
                    try:
                        table.cursor_coordinate = self.edit_mode_cursor_position
                    except:
                        pass
                    delattr(self, 'edit_mode_cursor_position')
            except Exception:
                pass  # Give up on recovery

    def action_save_preview(self):
        """Save is now handled by edit mode - show message."""
        self.cancel_refresh_timer()
        status = self.query_one("#status", Label)
        status.update("Use 'e' to edit document in place")

    def action_save_document(self):
        """Save the current document without exiting edit mode."""
        try:
            if not self.edit_mode or not self.editing_doc_id:
                return

            # Get the edit area
            try:
                from textual.containers import Container
                edit_wrapper = self.query_one("#edit-wrapper", Container)
                edit_area = edit_wrapper.query_one("#preview-content", EditTextArea)
            except:
                edit_area = self.query_one("#preview-content", EditTextArea)

            # Get the edited content (no title editing for now)
            new_content = edit_area.text
            new_title = None  # Keep original title

            # Update document in database
            from emdx.models.documents import update_document

            # Get current document for comparison
            doc = get_document(str(self.editing_doc_id))
            if doc:
                # Use new title if provided, otherwise keep existing
                final_title = new_title if new_title else doc["title"]
                success = update_document(self.editing_doc_id, final_title, new_content)

                if success:
                    # Update original content to mark as saved
                    edit_area.original_content = new_content
                    self._update_vim_status("Document saved")

                    # Refresh the document list to show updated timestamp
                    self.load_documents()
                    self.filter_documents(self.search_query)
                else:
                    self._update_vim_status("Failed to save document")
        except Exception as e:
            logger.error(f"Error saving document: {e}", exc_info=True)
            self._update_vim_status(f"Save failed: {str(e)[:30]}...")

    def action_cancel_edit(self):
        """Cancel edit mode without saving changes."""
        try:
            if not self.edit_mode:
                return

            # Exit edit mode
            self.edit_mode = False
            self.editing_doc_id = None

            # Hide vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.remove_class("visible")
            vim_indicator.update("")

            # Get container
            container = self.query_one("#preview", ScrollableContainer)

            # Remove edit area and restore preview
            container.remove_children()

            # Create new RichLog for preview
            richlog = RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False
            )
            container.mount(richlog)

            # Reset container scroll and refresh layout
            container.scroll_to(0, 0, animate=False)
            container.refresh(layout=True)

            # Use deferred content restoration
            self.call_after_refresh(self._restore_preview_content)

            # Update status
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Edit cancelled - changes discarded")

        except Exception as e:
            logger.error(f"Error cancelling edit: {e}", exc_info=True)
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Cancel failed: {str(e)}")

            # Try to recover
            try:
                self.edit_mode = False
                self.editing_doc_id = None
                if self.current_doc_id:
                    self.update_preview(self.current_doc_id)
            except Exception:
                pass


    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess

        success = False

        # Try pbcopy on macOS first
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            success = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"], input=text, text=True, check=True
                )
                success = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(
                        ["xsel", "--clipboard", "--input"], input=text, text=True, check=True
                    )
                    success = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        status = self.query_one("#status", Label)
        if success:
            self.cancel_refresh_timer()
            status.update("Content copied to clipboard!")
        else:
            self.cancel_refresh_timer()
            status.update("Clipboard not available - manual selection required")

    def restore_normal_status(self):
        """Restore the normal status display after temporary messages."""
        self.update_status()
        self.refresh_timer = None

    def restore_log_browser_status(self):
        """Restore the log browser status display after auto-refresh messages."""
        try:
            if hasattr(self, 'executions') and self.mode == "LOG_BROWSER":
                status = self.query_one("#status", Label)
                status.update(f"📋 LOG BROWSER: {len(self.executions)} executions (j/k to navigate, 'm' to mark complete, 'q' to exit, auto-refresh every 2s)")
        except Exception:
            pass

    def refresh_execution_list(self):
        """Refresh the execution list to catch status changes and new executions."""
        try:
            # Get current position and selected execution
            table = self.query_one("#doc-table", DataTable)
            old_row = table.cursor_row if hasattr(table, 'cursor_row') else 0
            old_execution_id = None
            if hasattr(self, 'current_execution_index') and hasattr(self, 'executions') and self.executions:
                if self.current_execution_index < len(self.executions):
                    old_execution_id = self.executions[self.current_execution_index].id
            
            # Get fresh executions
            old_count = len(self.executions) if hasattr(self, 'executions') else 0
            fresh_executions = get_recent_executions(limit=50)
            new_count = len(fresh_executions)
            
            # Only update if there are actual changes to avoid disrupting user interaction
            if old_count == new_count and hasattr(self, 'executions'):
                # Check if any status changed
                status_changed = False
                for i, (old_exec, new_exec) in enumerate(zip(self.executions, fresh_executions)):
                    if old_exec.id == new_exec.id and old_exec.status != new_exec.status:
                        status_changed = True
                        break
                
                if not status_changed:
                    logger.debug("No execution changes detected, skipping refresh")
                    return
            
            logger.debug(f"Refreshing executions: {old_count} -> {new_count}")
            self.executions = fresh_executions
            
            # Clear and repopulate table
            table.clear(columns=True)
            table.add_columns("Recent", "Status", "Document", "Started")
            
            # Populate executions table with fresh data
            for i, execution in enumerate(self.executions):
                status_icon = {
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌'
                }.get(execution.status, '❓')

                duration = ""
                if execution.duration:
                    if execution.duration < 60:
                        duration = f"{int(execution.duration)}s"
                    else:
                        mins = int(execution.duration // 60)
                        secs = int(execution.duration % 60)
                        duration = f"{mins}m{secs}s"
                elif execution.status == 'running':
                    duration = "running..."

                # Create recency indicator  
                if i == 0:
                    recency = "Latest"
                elif i == 1:
                    recency = "2nd"
                elif i == 2:
                    recency = "3rd"
                else:
                    recency = f"{i+1}th"
                
                table.add_row(
                    recency,
                    f"{status_icon} {execution.status}",
                    execution.doc_title[:30],
                    execution.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                )
            
            # Try to restore the same execution if it still exists
            new_row = 0
            if old_execution_id:
                for i, execution in enumerate(self.executions):
                    if execution.id == old_execution_id:
                        new_row = i
                        break
            else:
                new_row = min(old_row, len(self.executions) - 1) if self.executions else 0
            
            # Restore cursor position without changing the current log view
            if self.executions and new_row < len(self.executions):
                table.move_cursor(row=new_row)
                self.current_execution_index = new_row
                
        except Exception as e:
            logger.error(f"Error refreshing execution list: {e}", exc_info=True)

    def cancel_refresh_timer(self):
        """Cancel the refresh timer if it's active."""
        if self.refresh_timer:
            self.refresh_timer.stop()
            self.refresh_timer = None
    
    def cancel_log_monitor_timer(self):
        """Cancel the log monitor timer if it's active."""
        if hasattr(self, 'log_monitor_timer'):
            logger.debug("Stopping log monitor timer")
            self.log_monitor_timer.stop()
            delattr(self, 'log_monitor_timer')
        else:
            logger.debug("No log monitor timer to cancel")

    def action_tmux_split_horizontal(self):
        """Spawn a new tmux pane (horizontal split) with the current document."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for tmux split")
            return

        if not os.environ.get('TMUX'):
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Not running in tmux session")
            return

        self._spawn_tmux_pane(horizontal=True)

    def action_tmux_split_vertical(self):
        """Spawn a new tmux pane (vertical split) with the current document."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for tmux split")
            return

        if not os.environ.get('TMUX'):
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("Not running in tmux session")
            return

        self._spawn_tmux_pane(horizontal=False)

    def _spawn_tmux_pane(self, horizontal: bool = True):
        """Internal method to spawn tmux pane with current document."""
        try:
            from emdx.models.documents import get_document

            # Get the current document
            doc = get_document(str(self.current_doc_id))
            if not doc:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Document not found")
                return

            # Create a temporary file with the document content
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(f"# {doc['title']}\n\n")
                f.write(doc['content'])
                temp_path = f.name

            # Determine split direction
            split_flag = '-h' if horizontal else '-v'

            # For now, just spawn a shell that shows the document
            # You can replace this with your Claude command later
            tmux_command = f"cat {temp_path} && echo '\n\n--- Document loaded ---' && bash"

            # Spawn the tmux pane
            result = subprocess.run([
                'tmux', 'split-window', split_flag, tmux_command
            ], capture_output=True, text=True)

            if result.returncode == 0:
                direction = "right" if horizontal else "below"
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Spawned tmux pane {direction} with: {doc['title']}")
            else:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update(f"Failed to spawn tmux pane: {result.stderr}")

        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error spawning tmux pane: {e}")

    def action_claude_execute(self):
        """Execute the current document with Python claude execution system."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for execution")
            return

        try:
            import threading

            from emdx.commands.claude_execute import execute_document_smart, get_execution_context
            from emdx.models.documents import get_document

            # Get the current document
            doc = get_document(str(self.current_doc_id))
            if not doc:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Document not found")
                return

            # Get execution context to show what will happen
            context = get_execution_context(doc.get('tags', []))
            status = self.query_one("#status", Label)
            status.update(f"Executing {context['type'].value}: {context['description']}")

            # Create execution ID
            exec_id = f"claude-{self.current_doc_id}-{int(time.time())}"

            # Create logs directory
            log_dir = Path.home() / ".config/emdx/logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{exec_id}.log"

            # Use the new detached execution directly
            from emdx.commands.claude_execute import execute_document_smart_background
            execute_document_smart_background(
                doc_id=self.current_doc_id,
                execution_id=exec_id,
                log_file=log_path,
                allowed_tools=None,  # Use default tools
                use_stage_tools=True
            )

            # Show success message with worktree info
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"🚀 Claude executing in worktree: {doc['title'][:25]}... → {exec_id[:8]} (Press 'l' for logs)")

        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error starting Claude execution: {e}")

    def action_create_gist(self):
        """Create a GitHub Gist from the current document."""
        if not self.current_doc_id:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update("No document selected for gist creation")
            return
        
        try:
            from emdx.commands.gist import create_gist_with_gh, create_gist_with_api, get_github_auth, sanitize_filename
            from emdx.models.documents import get_document
            
            # Get the current document
            doc = get_document(str(self.current_doc_id))
            if not doc:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("Document not found")
                return
            
            # Check for GitHub authentication
            token = get_github_auth()
            if not token:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("GitHub auth required: Set GITHUB_TOKEN or run 'gh auth login'")
                return
            
            # Show creating status
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Creating gist for: {doc['title'][:30]}...")
            
            # Prepare gist content
            filename = sanitize_filename(doc["title"])
            content = doc["content"]
            description = f"{doc['title']} - emdx knowledge base"
            if doc.get("project"):
                description += f" (Project: {doc['project']})"
            
            # Create gist (try gh CLI first, fallback to API)
            result = create_gist_with_gh(content, filename, description, public=False)
            if not result:
                result = create_gist_with_api(content, filename, description, public=False, token=token)
            
            if result:
                gist_url = result["url"]
                
                # Save to database
                from emdx.database import db
                with db.get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO gists (document_id, gist_id, gist_url, is_public)
                        VALUES (?, ?, ?, ?)
                        """,
                        (doc["id"], result["id"], gist_url, False),
                    )
                    conn.commit()
                
                # Copy URL to clipboard
                from emdx.commands.gist import copy_to_clipboard
                if copy_to_clipboard(gist_url):
                    status.update(f"✓ Gist created & copied: {gist_url}")
                else:
                    status.update(f"✓ Gist created: {gist_url}")
            else:
                status.update("Failed to create gist")
                
        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error creating gist: {e}")

    def action_log_browser(self):
        """Switch to log browser mode to view and switch between execution logs."""
        self.mode = "LOG_BROWSER"
        self.setup_log_browser()
    
    def action_mark_execution_complete(self):
        """Mark the currently selected execution as complete (in LOG_BROWSER mode)."""
        if self.mode != "LOG_BROWSER" or not hasattr(self, 'executions') or not self.executions:
            return
        
        try:
            # Get currently selected execution
            if hasattr(self, 'current_execution_index') and 0 <= self.current_execution_index < len(self.executions):
                execution = self.executions[self.current_execution_index]
                
                # Only mark running executions as complete
                if execution.status == 'running':
                    update_execution_status(execution.id, "completed", 130)
                    
                    # Show confirmation message
                    status = self.query_one("#status", Label)
                    status.update(f"✅ Marked execution {execution.id[:8]}... as complete!")
                    
                    # Refresh the execution list to show updated status
                    self.refresh_execution_list()
                    
                    # Restore normal status after 2 seconds
                    self.set_timer(2.0, self.restore_log_browser_status)
                else:
                    # Show message if execution is not running
                    status = self.query_one("#status", Label)
                    status.update(f"⚠️ Execution {execution.id[:8]}... is already {execution.status}")
                    self.set_timer(2.0, self.restore_log_browser_status)
        except Exception as e:
            # Show error message
            status = self.query_one("#status", Label)
            status.update(f"❌ Error marking execution complete: {str(e)}")
            self.set_timer(2.0, self.restore_log_browser_status)
    
    def action_open_file_browser(self):
        """Open file browser mode."""
        logger.info("🗂️ Opening file browser mode")
        
        # If already in file browser mode, just refresh
        if hasattr(self, 'mode') and self.mode == "FILE_BROWSER":
            logger.info("🗂️ Already in file browser mode, refreshing")
            if hasattr(self, 'file_browser'):
                self.file_browser.refresh_files()
            return
        
        # Set mode first, then setup
        self.mode = "FILE_BROWSER"
        logger.info(f"🗂️ Mode set to: {self.mode}")
        self.setup_file_browser()
    
    def setup_file_browser(self):
        """Set up the file browser interface."""
        try:
            logger.info("🗂️ Setting up file browser interface")
            
            # Clean up any existing file browser first
            if hasattr(self, 'file_browser'):
                logger.info("🗂️ Removing existing file browser")
                try:
                    self.file_browser.remove()
                except Exception as e:
                    logger.warning(f"🗂️ Error removing existing file browser: {e}")
                delattr(self, 'file_browser')
            
            # Import the standalone file browser
            from .file_browser import FileBrowser
            logger.info("🗂️ FileBrowser imported successfully")
            
            # Hide search inputs
            self.query_one("#search-input", Input).display = False
            logger.info("🗂️ Search input hidden")
            self.query_one("#tag-input", Input).display = False
            self.query_one("#tag-selector", Label).display = False
            self.query_one("#vim-mode-indicator", Label).display = False
            
            # Hide the entire document area
            sidebar = self.query_one("#sidebar", Vertical)
            sidebar.display = False
            
            preview_container = self.query_one("#preview-container", Vertical)
            preview_container.display = False
            
            # Create and mount file browser in full width container
            logger.info("🗂️ Getting main horizontal container")
            # Find the horizontal container that contains sidebar and preview
            horizontal_container = self.query_one("#sidebar").parent
            logger.info("🗂️ Creating FileBrowser widget")
            self.file_browser = FileBrowser(id="file-browser-widget")
            logger.info("🗂️ Mounting FileBrowser in full container")
            horizontal_container.mount(self.file_browser)
            logger.info("🗂️ FileBrowser mounted successfully")
            
            # Focus the file browser after mounting is complete
            self.call_after_refresh(lambda: self._focus_file_browser())
            
            # Update status
            status = self.query_one("#status", Label)
            status.update("FILE BROWSER: Navigate with j/k/h/l, 's' to save, 'x' to execute, 'q' to exit")
            logger.info("🗂️ File browser setup complete")
            
        except Exception as e:
            logger.error(f"Error setting up file browser: {e}")
            status = self.query_one("#status", Label)
            status.update(f"Error setting up file browser: {e}")
    
    def _focus_file_browser(self):
        """Focus the file browser widget."""
        try:
            if hasattr(self, 'file_browser') and self.file_browser:
                self.file_browser.focus()
                logger.info("🗂️ FileBrowser focused")
        except Exception as e:
            logger.error(f"🗂️ Error focusing file browser: {e}")
    
    
    def exit_file_browser(self):
        """Exit file browser and return to document browser."""
        try:
            logger.info("🗂️ Exiting file browser mode")
            # Remove file browser
            if hasattr(self, 'file_browser'):
                self.file_browser.remove()
                logger.info("🗂️ File browser widget removed")
            
            # Show hidden widgets
            self.query_one("#search-input", Input).display = True
            self.query_one("#tag-input", Input).display = True
            self.query_one("#tag-selector", Label).display = True
            self.query_one("#vim-mode-indicator", Label).display = True
            logger.info("🗂️ Input widgets restored")
            
            self.query_one("#sidebar", Vertical).display = True
            self.query_one("#preview-container", Vertical).display = True
            logger.info("🗂️ Document table and preview restored")
            
            # Reset mode and reload
            self.mode = "NORMAL"
            logger.info("🗂️ Mode reset to NORMAL")
            self.reload_documents()
            
        except Exception as e:
            logger.error(f"Error exiting file browser: {e}")
            # Fallback
            self.mode = "NORMAL"
            self.reload_documents()
    
    
    def on_file_browser_quit_file_browser(self, event):
        """Handle file browser quit event."""
        self.exit_file_browser()

    def setup_log_browser(self):
        """Set up the log browser interface with execution list and log viewer."""
        try:
            # Load recent executions from database
            self.executions = get_recent_executions(limit=50)

            if not self.executions:
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                status.update("No executions found - Press 'q' to return")
                return

            # Start with the most recent execution
            self.current_execution_index = 0

            # Replace the documents table with executions table
            table = self.query_one("#doc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Recent", "Status", "Document", "Started")

            # Populate executions table
            for i, execution in enumerate(self.executions):
                status_icon = {
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌'
                }.get(execution.status, '❓')

                duration = ""
                if execution.duration:
                    if execution.duration < 60:
                        duration = f"{int(execution.duration)}s"
                    else:
                        mins = int(execution.duration // 60)
                        secs = int(execution.duration % 60)
                        duration = f"{mins}m{secs}s"
                elif execution.status == 'running':
                    duration = "running..."

                # Create recency indicator  
                if i == 0:
                    recency = "Latest"
                elif i == 1:
                    recency = "2nd"
                elif i == 2:
                    recency = "3rd"
                else:
                    recency = f"{i+1}th"
                
                table.add_row(
                    recency,
                    f"{status_icon} {execution.status}",
                    execution.doc_title[:30],
                    execution.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                )

            # Select first row and load its log
            table.move_cursor(row=0)
            self.load_execution_log(0)

            # Update status with instructions
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"📋 LOG BROWSER: {len(self.executions)} executions (j/k to navigate, 'm' to mark complete, 'q' to exit, auto-refresh every 2s)")

            # Start monitoring for log updates
            self.start_log_monitoring()

        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error setting up log browser: {e}")

    def _extract_log_content(self) -> str:
        """Extract plain text content from the current log for selection mode."""
        try:
            if self.mode == "LOG_BROWSER" and hasattr(self, 'current_log_file') and self.current_log_file:
                # Get execution info for header
                execution = self.executions[self.current_execution_index] if self.executions else None

                # Build header
                lines = []
                if execution:
                    lines.append(f"=== Execution {execution.id} ===")
                    lines.append(f"Document: {execution.doc_title}")
                    lines.append(f"Status: {execution.status}")
                    lines.append(f"Started: {execution.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    if execution.completed_at:
                        lines.append(f"Completed: {execution.completed_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    lines.append("=== Log Output ===")
                    lines.append("")

                # Read actual log file content
                if self.current_log_file.exists():
                    with open(self.current_log_file) as f:
                        log_content = f.read()
                        if log_content:
                            lines.append(log_content)
                        else:
                            lines.append("(No log content yet)")
                else:
                    lines.append("Log file not found")

                return "\n".join(lines)
            else:
                return "No log content available"
        except Exception as e:
            return f"Error extracting log content: {e}"

    def start_log_monitoring(self):
        """Start monitoring the log file for changes."""
        if hasattr(self, 'log_monitor_timer'):
            self.log_monitor_timer.stop()

        # Monitor every 2 seconds in log browser mode
        self.log_monitor_timer = self.set_interval(2.0, self.update_log_content)
        self.last_log_size = 0
        self.last_log_mtime = 0
        logger.debug(f"Started log monitoring for {getattr(self, 'current_log_file', 'unknown file')}")

    def update_log_content(self):
        """Update log content if file has changed and refresh execution list."""
        logger.debug(f"update_log_content called: mode={getattr(self, 'mode', 'unknown')}, has_file={hasattr(self, 'current_log_file')}")
        
        # Auto-refresh fires silently - no visual indicators
        
        if not hasattr(self, 'current_log_file') or self.mode != "LOG_BROWSER":
            logger.debug("Skipping log update: not in LOG_BROWSER mode or no log file")
            # Skip update silently
            return

        # Refresh execution list every 10 seconds (every 5th call) to avoid interfering with scrolling
        if not hasattr(self, 'refresh_counter'):
            self.refresh_counter = 0
        self.refresh_counter += 1
        
        if self.refresh_counter >= 5:  # Every 10 seconds
            self.refresh_counter = 0
            self.refresh_execution_list()

        try:
            if not self.current_log_file or not self.current_log_file.exists():
                logger.debug(f"Log file doesn't exist: {self.current_log_file}")
                return

            # Check if file has grown or modified
            file_stat = self.current_log_file.stat()
            current_size = file_stat.st_size
            current_mtime = file_stat.st_mtime
            
            # Initialize tracking variables if not set
            if not hasattr(self, 'last_log_mtime'):
                self.last_log_mtime = 0
            
            size_changed = current_size != self.last_log_size
            time_changed = current_mtime != self.last_log_mtime
            
            logger.debug(f"File check: size={current_size} (was {self.last_log_size}), "
                        f"mtime={current_mtime} (was {self.last_log_mtime}), "
                        f"size_changed={size_changed}, time_changed={time_changed}")
            
            if size_changed or time_changed:
                # Update in progress silently
                
                # Handle file truncation or full rewrite
                if current_size < self.last_log_size:
                    logger.debug("Log file was truncated, reloading from beginning")
                    self.last_log_size = 0
                
                # Read new content
                with open(self.current_log_file) as f:
                    f.seek(self.last_log_size)
                    new_content = f.read()

                if new_content:
                    try:
                        preview = self.query_one("#preview-content", RichLog)
                        preview.write(new_content)
                        # Auto-scroll to bottom
                        preview.scroll_end(animate=False)
                        logger.debug(f"Updated log content: {len(new_content)} characters")
                        # Content updated silently
                    except Exception as e:
                        logger.debug(f"Failed to update preview widget: {e}")
                        # Widget doesn't exist (different screen) - skip update
                        # Widget error handled silently

                self.last_log_size = current_size
                self.last_log_mtime = current_mtime
            else:
                logger.debug("No file changes detected")
                # No changes detected, continue silently

        except Exception as e:
            logger.error(f"Error in update_log_content: {e}", exc_info=True)

    def load_execution_log(self, index: int):
        """Load the log file for the execution at the given index."""
        if index < 0 or index >= len(self.executions):
            return

        try:
            execution = self.executions[index]
            self.current_execution_index = index
            self.current_log_file = Path(execution.log_file)

            # Clear preview and load log content
            try:
                preview = self.query_one("#preview-content", RichLog)
            except Exception:
                # Widget doesn't exist (different screen) - cannot load log
                return

            preview.clear()

            # Show execution header
            preview.write(f"[bold cyan]=== Execution {execution.id} ===[/bold cyan]")
            preview.write(f"[yellow]Document:[/yellow] {execution.doc_title}")
            preview.write(f"[yellow]Status:[/yellow] {execution.status}")
            preview.write(f"[yellow]Started:[/yellow] {execution.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
            if execution.completed_at:
                preview.write(f"[yellow]Completed:[/yellow] {execution.completed_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
            preview.write("[bold cyan]=== Log Output ===[/bold cyan]")
            preview.write("")

            # Load log file content
            if self.current_log_file.exists():
                with open(self.current_log_file) as f:
                    content = f.read()
                    if content:
                        preview.write(content)
                    else:
                        preview.write("[dim](No log content yet)[/dim]")

                # Reset size tracking for live updates
                self.last_log_size = self.current_log_file.stat().st_size
            else:
                preview.write("[red]Log file not found[/red]")
                self.last_log_size = 0

            # Auto-scroll to bottom
            preview.scroll_end(animate=False)

            # Highlight current row in table
            try:
                table = self.query_one("#doc-table", DataTable)
                table.move_cursor(row=index)
            except Exception:
                # Table doesn't exist (different screen) - skip highlighting
                pass

        except Exception as e:
            self.cancel_refresh_timer()
            try:
                status = self.query_one("#status", Label)
                status.update(f"Error loading execution log: {e}")
            except Exception:
                # Status widget doesn't exist (different screen) - ignore error
                pass

    def action_next_log(self):
        """Switch to next execution log (j in LOG_BROWSER mode)."""
        if self.mode != "LOG_BROWSER":
            return

        if hasattr(self, 'current_execution_index') and hasattr(self, 'executions') and self.executions:
            self.current_execution_index = (self.current_execution_index + 1) % len(self.executions)
            self.load_execution_log(self.current_execution_index)
            self.update_status(f"Viewing log {self.current_execution_index + 1}/{len(self.executions)}")

    def action_prev_log(self):
        """Switch to previous execution log (k in LOG_BROWSER mode)."""
        if self.mode != "LOG_BROWSER":
            return

        if hasattr(self, 'current_execution_index') and hasattr(self, 'executions') and self.executions:
            self.current_execution_index = (self.current_execution_index - 1) % len(self.executions)
            self.load_execution_log(self.current_execution_index)
            self.update_status(f"Viewing log {self.current_execution_index + 1}/{len(self.executions)}")

    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially j/k for log switching in LOG_BROWSER mode."""
        try:
            key_logger.info(f"MinimalBrowser.on_key: key={event.key}")

            # j/k keys are handled by the app-level key handler, not here
            
            # Handle j/k/w keys for git diff switching in git diff browser mode
            if hasattr(self, 'mode') and self.mode == "GIT_DIFF_BROWSER":
                if hasattr(event, 'key') and event.key:
                    if event.key == "j" and hasattr(self, 'git_files'):
                        self.action_git_diff_next()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "k" and hasattr(self, 'git_files'):
                        self.action_git_diff_prev()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "w":
                        # Handle worktree switching
                        self.action_switch_worktree()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "a":
                        # Stage current file
                        self.action_git_stage_file()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "u":
                        # Unstage current file
                        self.action_git_unstage_file()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "c":
                        # Commit staged changes
                        self.action_git_commit()
                        event.stop()
                        event.prevent_default()
                        return
                    elif event.key == "R":
                        # Discard changes to current file
                        self.action_git_discard_changes()
                        event.stop()
                        event.prevent_default()
                        return

            # Note: App class doesn't have on_key method, so we don't call super()
            pass
        except Exception as e:
            # Log error but don't crash
            key_logger.error(f"Error in on_key: {e}")
            # Don't try to call super().on_key() as App doesn't have this method

    async def on_event(self, event) -> None:
        """Handle all events safely."""
        try:
            await super().on_event(event)
        except Exception as e:
            logger.error(f"Error handling event {type(event).__name__}: {e}")
            # Don't re-raise, just log and continue

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        """Handle row selection in both document and execution modes."""
        try:
            if hasattr(self, 'mode') and self.mode == "LOG_BROWSER":
                # In log browser mode, load the selected execution's log
                if hasattr(self, 'executions') and message.cursor_row < len(self.executions):
                    self.load_execution_log(message.cursor_row)
            elif hasattr(self, 'mode') and self.mode == "GIT_DIFF_BROWSER":
                # In git diff browser mode, load the selected file's diff
                if hasattr(self, 'git_files') and message.cursor_row < len(self.git_files):
                    self.load_git_diff(message.cursor_row)
            else:
                # Original document preview logic
                if hasattr(self, 'filtered_docs') and message.cursor_row < len(self.filtered_docs):
                    doc = self.filtered_docs[message.cursor_row]
                    self.current_doc_id = doc["id"]

                    # Exit selection mode when switching documents
                    if hasattr(self, 'selection_mode') and self.selection_mode:
                        self.action_toggle_selection_mode()

                    self.update_preview(doc["id"])
        except Exception as e:
            logger.error(f"Error in on_data_table_row_highlighted: {e}")
            # Don't crash, just log the error

    def action_git_diff_browser(self):
        """Switch to git diff browser mode to view file changes."""
        # Check if we're in a git repository
        if not is_git_repository():
            status = self.query_one("#status", Label)
            status.update("Not in a git repository - cannot show git diff")
            return
        
        self.mode = "GIT_DIFF_BROWSER"
        self.setup_git_diff_browser()

    
    
    def action_git_diff_next(self):
        """Switch to next git file (j in GIT_DIFF_BROWSER mode)."""
        self.navigate_git_diff(1)
    
    def action_git_diff_prev(self):
        """Switch to previous git file (k in GIT_DIFF_BROWSER mode)."""
        self.navigate_git_diff(-1)
    
    def action_switch_worktree(self):
        """Show worktree picker modal (w key)."""
        if self.mode != "GIT_DIFF_BROWSER":
            return
        
        if not hasattr(self, 'worktrees') or len(self.worktrees) <= 1:
            status = self.query_one("#status", Label)
            status.update("No other worktrees available")
            return
        
        # Show worktree picker modal
        def on_worktree_selected(new_index: int):
            """Handle worktree selection from picker."""
            try:
                old_index = self.current_worktree_index
                self.current_worktree_index = new_index
                new_worktree = self.worktrees[new_index]
                old_worktree = self.worktrees[old_index]
                
                # Show detailed switching info
                status = self.query_one("#status", Label)
                status.update(f"🔄 Switching: {old_worktree.name} → {new_worktree.name} | Path: {new_worktree.path}")
                
                # Update the current worktree path
                old_path = self.current_worktree_path
                self.current_worktree_path = new_worktree.path
                
                # Debug info
                logger.info(f"Worktree switch: {old_path} → {new_worktree.path}")
                
                # Reload git status for new worktree
                self.setup_git_diff_browser()
                
            except Exception as e:
                logger.error(f"Error switching worktree: {e}")
                status = self.query_one("#status", Label)
                status.update(f"❌ Error switching worktree: {e}")
        
        # Launch the worktree picker modal
        picker = WorktreePickerScreen(
            worktrees=self.worktrees,
            current_index=self.current_worktree_index,
            callback=on_worktree_selected
        )
        self.push_screen(picker)


    def action_quit(self):
        try:
            if hasattr(self, 'mode'):
                if self.mode == "LOG_BROWSER":
                    # Exit log browser mode and return to document mode
                    self.mode = "NORMAL"
                    self.stop_log_monitoring()
                    self.reload_documents()
                elif self.mode == "FILE_BROWSER":
                    # Exit file browser mode and return to document mode
                    self.exit_file_browser()
                elif self.mode == "GIT_DIFF_BROWSER":
                    # Exit git diff browser mode and return to document mode
                    self.mode = "NORMAL"
                    self.reload_documents()
                else:
                    # Clean exit - subprocess are detached and will continue running
                    self.exit()
            else:
                # Clean exit - subprocess are detached and will continue running
                self.exit()
        except Exception as e:
            logger.error(f"Error in action_quit: {e}")
            # Fallback to exit
            self.exit()

    def exit_file_browser(self):
        """Exit file browser mode and return to document mode."""
        # Placeholder for file browser functionality that will come from main
        self.mode = "NORMAL"
        self.reload_documents()
    
    def stop_log_monitoring(self):
        """Stop the log monitoring timer."""
        self.cancel_log_monitor_timer()

    def reload_documents(self):
        """Reload the document view after exiting log browser."""
        try:
            # Clear and recreate the table with documents
            table = self.query_one("#doc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Title", "Tags")

            # Reload documents
            self.load_documents()

            # Repopulate the table
            for doc in self.filtered_docs:
                # Format timestamp as MM-DD HH:MM (11 chars)
                timestamp = doc["created_at"].strftime("%m-%d %H:%M")

                # Calculate available space for title (50 total - 11 for timestamp)
                title_space = 50 - 11
                title = doc["title"][:title_space]
                if len(doc["title"]) >= title_space:
                    title = title[:title_space-3] + "..."

                # Right-justify timestamp by padding title to full width
                formatted_title = f"{title:<{title_space}}{timestamp}"

                # Expanded tag display - limit to 30 chars with emoji-safe truncation
                formatted_tags = format_tags(doc.get("tags", []))
                tags_str, was_truncated = truncate_emoji_safe(formatted_tags, 30)
                if was_truncated:
                    tags_str += "..."

                table.add_row(
                    str(doc["id"]),
                    formatted_title,
                    tags_str or "-",
                )

            # Focus the table and update preview
            table.focus()
            if self.filtered_docs:
                # Ensure we scroll to top and select first document
                table.scroll_home(animate=False)
                table.move_cursor(row=0)
                self.current_doc_id = self.filtered_docs[0]["id"]
                self.update_preview(self.current_doc_id)

            # Update status
            self.update_status()

        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error reloading documents: {e}")


def run_minimal():
    """Run the minimal browser and return exit code."""
    try:
        # Check if documents exist
        db.ensure_schema()
        docs = db.list_documents(limit=1)
        if not docs:
            print("No documents found in knowledge base.")
            print("\nGet started with:")
            print("  emdx save <file>         - Save a markdown file")
            print("  emdx direct <title>      - Create a document directly")
            print("  emdx note 'quick note'   - Save a quick note")
            return 0

        # Run the browser with better error handling
        try:
            app = MinimalDocumentBrowser()
            app.run()
        except Exception as e:
            import traceback
            logger.error(f"Error during app startup: {e}")
            logger.error(traceback.format_exc())
            # Re-raise with original traceback
            raise

        # Check if edit signal exists to determine return code
        edit_signal = f"/tmp/emdx_edit_signal_{os.getpid()}"
        if os.path.exists(edit_signal):
            return 42  # Edit requested
        else:
            return 0  # Normal exit

    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_minimal())
