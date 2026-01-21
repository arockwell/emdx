"""Diff viewer modal for GitHub PRs."""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, ListItem, ListView, RichLog

logger = logging.getLogger(__name__)


@dataclass
class DiffFile:
    """A file in the diff."""
    path: str
    line_offset: int  # Line number where this file starts in the rendered output
    additions: int = 0
    deletions: int = 0


class FileListItem(ListItem):
    """A file item in the file list."""

    def __init__(self, diff_file: DiffFile, index: int, **kwargs):
        super().__init__(**kwargs)
        self.diff_file = diff_file
        self.file_index = index

    def compose(self) -> ComposeResult:
        path = self.diff_file.path
        if len(path) > 25:
            path = "..." + path[-22:]
        stats = f"+{self.diff_file.additions} -{self.diff_file.deletions}"
        yield Static(f"{path}\n{stats}", markup=False)


class DiffModal(ModalScreen):
    """Modal to display PR diff with file navigation."""

    CSS = """
    DiffModal {
        align: center middle;
    }

    #diff-container {
        width: 95%;
        height: 90%;
        background: $surface;
        border: solid $primary;
    }

    #diff-header {
        height: 2;
        padding: 0 2;
        background: $surface-darken-1;
    }

    #diff-title {
        text-style: bold;
    }

    #diff-main {
        height: 1fr;
    }

    #file-list-container {
        width: 28;
        height: 100%;
        border-right: solid $primary-darken-2;
    }

    #file-list {
        height: 100%;
    }

    #file-list > ListItem {
        height: 3;
        padding: 0 1;
    }

    #diff-content {
        height: 100%;
        width: 1fr;
        padding: 0 1;
    }

    #diff-footer {
        height: 1;
        background: $surface-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
        Binding("q", "close", "Close", show=False),
        Binding("j", "nav_down", "Down", show=False),
        Binding("k", "nav_up", "Up", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("d", "page_down", "PgDn", show=False),
        Binding("u", "page_up", "PgUp", show=False),
        Binding("n", "next_file", "Next", show=True),
        Binding("p", "prev_file", "Prev", show=True),
        Binding("h", "focus_files", "Files", show=True),
        Binding("l", "focus_diff", "Diff", show=True),
    ]

    def __init__(self, pr_number: int, pr_title: str, diff_content: str, **kwargs):
        super().__init__(**kwargs)
        self.pr_number = pr_number
        self.pr_title = pr_title
        self.diff_content = diff_content
        self.files: List[DiffFile] = []
        self.current_file_idx = 0
        self._line_count = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-container"):
            with Vertical(id="diff-header"):
                title = f"PR #{self.pr_number}: {self.pr_title[:50]}"
                yield Static(title, id="diff-title", markup=False)
            with Horizontal(id="diff-main"):
                with Vertical(id="file-list-container"):
                    yield ListView(id="file-list")
                # RichLog has built-in scrolling, no need for ScrollableContainer
                yield RichLog(id="diff-content", highlight=False, markup=True, wrap=False, auto_scroll=False)
            yield Static("Esc=Close | h/l=Files/Diff | n/p=Next/Prev | j/k=Scroll", id="diff-footer")

    def on_mount(self) -> None:
        """Parse diff, populate file list, render content."""
        self._parse_and_render()
        self.call_later(self._initial_focus)

    def _initial_focus(self) -> None:
        """Set initial focus and scroll position."""
        log = self.query_one("#diff-content", RichLog)
        log.scroll_home(animate=False)
        log.focus()

    def _parse_and_render(self) -> None:
        """Parse diff and render in one pass."""
        log = self.query_one("#diff-content", RichLog)
        file_list = self.query_one("#file-list", ListView)

        lines = self.diff_content.split("\n")
        current_file: Optional[DiffFile] = None
        line_num = 0

        for line in lines:
            if line.startswith("diff --git"):
                # Save previous file
                if current_file:
                    self.files.append(current_file)

                # Extract path
                match = re.search(r"diff --git a/(.*) b/", line)
                if match:
                    path = match.group(1)
                else:
                    parts = line.split()
                    path = parts[-1] if parts else "unknown"
                    if path.startswith("b/"):
                        path = path[2:]

                # Add blank line before file (except first)
                if self.files or current_file:
                    log.write("")
                    line_num += 1

                # Record line_offset BEFORE writing header so header appears at top
                header_line = line_num

                # Render file header - more visible
                log.write(f"[yellow bold]{'━' * 60}[/]")
                line_num += 1
                log.write(f"[yellow bold]  {self._esc(path)}[/]")
                line_num += 1
                log.write(f"[yellow bold]{'━' * 60}[/]")
                line_num += 1

                current_file = DiffFile(path=path, line_offset=header_line)
                continue  # Skip further processing of this line

            # Render line with color
            if line.startswith("+") and not line.startswith("+++"):
                log.write(f"[green]{self._esc(line)}[/]")
                if current_file:
                    current_file.additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                log.write(f"[red]{self._esc(line)}[/]")
                if current_file:
                    current_file.deletions += 1
            elif line.startswith("@@"):
                log.write(f"[cyan]{self._esc(line)}[/]")
            elif line.startswith("+++") or line.startswith("---"):
                log.write(f"[yellow dim]{self._esc(line)}[/]")
            else:
                log.write(self._esc(line))

            line_num += 1

        # Don't forget the last file
        if current_file:
            self.files.append(current_file)

        self._line_count = line_num

        # Populate file list
        for i, f in enumerate(self.files):
            file_list.append(FileListItem(f, i))

        if self.files:
            file_list.index = 0

        # Update footer with file count
        footer = self.query_one("#diff-footer", Static)
        footer.update(f"Esc=Close | h/l=Files/Diff | n/p=Next/Prev | j/k=Scroll | {len(self.files)} files")

    def _esc(self, text: str) -> str:
        """Escape Rich markup."""
        return text.replace("[", "\\[").replace("]", "\\]")

    def _jump_to_file(self, idx: int) -> None:
        """Jump to a specific file in the diff."""
        if not self.files or idx < 0 or idx >= len(self.files):
            return

        self.current_file_idx = idx
        file = self.files[idx]

        # Update file list selection
        file_list = self.query_one("#file-list", ListView)
        file_list.index = idx

        # Scroll RichLog directly to file position
        log = self.query_one("#diff-content", RichLog)
        log.scroll_to(y=file.line_offset, animate=False, force=True)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection from list."""
        if isinstance(event.item, FileListItem):
            self._jump_to_file(event.item.file_index)
            self.call_later(lambda: self.query_one("#diff-content", RichLog).focus())

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle file highlight (j/k navigation in list)."""
        if isinstance(event.item, FileListItem):
            self._jump_to_file(event.item.file_index)

    def _is_file_list_focused(self) -> bool:
        """Check if the file list has focus."""
        try:
            file_list = self.query_one("#file-list", ListView)
            return file_list.has_focus
        except Exception:
            return False

    def action_close(self) -> None:
        self.dismiss()

    def action_nav_down(self) -> None:
        """Navigate down - scroll diff or move to next file depending on focus."""
        if self._is_file_list_focused():
            self.action_next_file()
        else:
            self.query_one("#diff-content", RichLog).scroll_down()

    def action_nav_up(self) -> None:
        """Navigate up - scroll diff or move to prev file depending on focus."""
        if self._is_file_list_focused():
            self.action_prev_file()
        else:
            self.query_one("#diff-content", RichLog).scroll_up()

    def action_scroll_top(self) -> None:
        self.query_one("#diff-content", RichLog).scroll_home()

    def action_scroll_bottom(self) -> None:
        self.query_one("#diff-content", RichLog).scroll_end()

    def action_page_down(self) -> None:
        self.query_one("#diff-content", RichLog).scroll_page_down()

    def action_page_up(self) -> None:
        self.query_one("#diff-content", RichLog).scroll_page_up()

    def action_next_file(self) -> None:
        """Jump to next file."""
        if self.files:
            self._jump_to_file((self.current_file_idx + 1) % len(self.files))

    def action_prev_file(self) -> None:
        """Jump to previous file."""
        if self.files:
            self._jump_to_file((self.current_file_idx - 1) % len(self.files))

    def action_focus_files(self) -> None:
        """Focus the file list."""
        self.query_one("#file-list", ListView).focus()

    def action_focus_diff(self) -> None:
        """Focus the diff content."""
        self.query_one("#diff-content", RichLog).focus()
