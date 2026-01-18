"""
FileBrowser - File browser using the panel system.

A simplified file browser that demonstrates the panel architecture:
- ListPanel for directory listing with vim navigation
- PreviewPanel for file content preview
- ~100 lines vs the original complex implementation

Features:
- Directory navigation (Enter to enter, h for parent)
- File preview with syntax highlighting
- Hidden files toggle (.)
- Search with /
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget

from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
    StatusPanel,
    StatusSection,
)


class FileBrowser(Widget):
    """File browser using panel components.

    A clean, minimal file browser implementation:
    - ~100 lines of code
    - Full vim-style navigation (j/k/g/G)
    - Directory traversal (l/Enter to enter, h for parent)
    - File preview with markdown rendering
    - Hidden files toggle (.)
    """

    DEFAULT_CSS = """
    FileBrowser {
        layout: vertical;
        height: 100%;
    }

    FileBrowser #fb-path {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    FileBrowser #fb-content {
        height: 1fr;
        layout: horizontal;
    }

    FileBrowser #fb-list {
        width: 50%;
        min-width: 30;
    }

    FileBrowser #fb-preview {
        width: 50%;
        min-width: 30;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("h", "parent_dir", "Parent", show=True),
        Binding("l", "enter_item", "Enter", show=False),
        Binding("period", "toggle_hidden", "Toggle Hidden", show=True),
    ]

    current_path: reactive[Path] = reactive(Path.cwd)
    show_hidden: reactive[bool] = reactive(False)

    def __init__(self, start_path: Optional[Path] = None, **kwargs):
        """Initialize file browser.

        Args:
            start_path: Initial directory to browse (defaults to cwd)
        """
        super().__init__(**kwargs)
        if start_path and start_path.exists():
            self._start_path = start_path.resolve()
        else:
            self._start_path = Path.cwd()

    def compose(self) -> ComposeResult:
        """Compose the file browser layout."""
        # Path display
        yield StatusPanel(
            sections=[StatusSection(key="path", default=str(self._start_path))],
            id="fb-path",
        )

        with Horizontal(id="fb-content"):
            # List panel for files
            yield ListPanel(
                columns=[
                    ColumnDef("Type", width=4),
                    ColumnDef("Name", width=40),
                    ColumnDef("Size", width=10),
                ],
                config=ListPanelConfig(
                    show_search=True,
                    search_placeholder="Search files...",
                    status_format="{filtered}/{total} items",
                ),
                show_status=True,
                id="fb-list",
            )

            # Preview panel for file content
            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=False,
                    enable_selection=True,
                    empty_message="Select a file to preview",
                ),
                id="fb-preview",
            )

    async def on_mount(self) -> None:
        """Initialize with the start path."""
        self.current_path = self._start_path
        await self._refresh_files()

    def watch_current_path(self, old_path: Path, new_path: Path) -> None:
        """React to path changes."""
        if self.is_mounted:
            # Update path display
            try:
                status = self.query_one("#fb-path", StatusPanel)
                status.set_section("path", str(new_path))
            except Exception:
                pass

            # Refresh file list
            import asyncio
            asyncio.create_task(self._refresh_files())

    def watch_show_hidden(self, old: bool, new: bool) -> None:
        """React to hidden files toggle."""
        if self.is_mounted:
            import asyncio
            asyncio.create_task(self._refresh_files())

    async def _refresh_files(self) -> None:
        """Refresh the file listing."""
        items = []

        # Add parent directory entry if not at root
        if self.current_path.parent != self.current_path:
            items.append(ListItem(
                id="..",
                values=["[D]", "..", ""],
                data={"path": self.current_path.parent, "is_dir": True},
            ))

        try:
            entries = sorted(
                self.current_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )

            for entry in entries:
                # Skip hidden files unless showing them
                if not self.show_hidden and entry.name.startswith("."):
                    continue

                type_indicator = "[D]" if entry.is_dir() else "[F]"
                size = ""
                if entry.is_file():
                    try:
                        size = self._format_size(entry.stat().st_size)
                    except (OSError, PermissionError):
                        size = "?"

                items.append(ListItem(
                    id=str(entry),
                    values=[type_indicator, entry.name, size],
                    data={"path": entry, "is_dir": entry.is_dir()},
                ))

        except PermissionError:
            self.notify("Permission denied", severity="error")
        except Exception as e:
            self.notify(f"Error reading directory: {e}", severity="error")

        list_panel = self.query_one("#fb-list", ListPanel)
        list_panel.set_items(items)

    def _format_size(self, size: int) -> str:
        """Format file size for display."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Update preview when item is selected."""
        item = event.item
        preview = self.query_one("#fb-preview", PreviewPanel)

        if not item.data:
            return

        path: Path = item.data["path"]
        is_dir: bool = item.data["is_dir"]

        if is_dir:
            await preview.show_content(
                f"# Directory: {path.name}\n\nPress `l` or `Enter` to enter.",
                title=path.name,
            )
        else:
            # Preview file content
            await self._preview_file(path, preview)

    async def _preview_file(self, path: Path, preview: PreviewPanel) -> None:
        """Preview a file's content."""
        try:
            # Check file size first
            size = path.stat().st_size
            if size > 1_000_000:  # 1MB limit
                await preview.show_content(
                    f"# {path.name}\n\nFile too large to preview ({self._format_size(size)})",
                    title=path.name,
                )
                return

            # Try to read as text
            try:
                content = path.read_text(encoding="utf-8")
                # Add markdown code fence for syntax highlighting
                suffix = path.suffix.lstrip(".")
                if suffix in ("py", "js", "ts", "go", "rs", "java", "c", "cpp", "h"):
                    content = f"```{suffix}\n{content}\n```"
                await preview.show_content(content, title=path.name)
            except UnicodeDecodeError:
                await preview.show_content(
                    f"# {path.name}\n\nBinary file - cannot preview",
                    title=path.name,
                )

        except PermissionError:
            await preview.show_content(
                f"# {path.name}\n\nPermission denied",
                title=path.name,
            )
        except Exception as e:
            await preview.show_content(
                f"# {path.name}\n\nError reading file: {e}",
                title=path.name,
            )

    async def on_list_panel_item_activated(
        self, event: ListPanel.ItemActivated
    ) -> None:
        """Handle Enter key - enter directory."""
        await self._enter_selected_item()

    def action_enter_item(self) -> None:
        """Enter the selected directory (l key)."""
        import asyncio
        asyncio.create_task(self._enter_selected_item())

    async def _enter_selected_item(self) -> None:
        """Enter the selected directory."""
        list_panel = self.query_one("#fb-list", ListPanel)
        item = list_panel.get_selected_item()

        if item and item.data and item.data.get("is_dir"):
            path: Path = item.data["path"]
            try:
                # Check permission by listing
                list(path.iterdir())
                self.current_path = path
            except PermissionError:
                self.notify(f"Permission denied: {path}", severity="error")

    def action_parent_dir(self) -> None:
        """Go to parent directory (h key)."""
        parent = self.current_path.parent
        if parent != self.current_path:
            self.current_path = parent

    def action_toggle_hidden(self) -> None:
        """Toggle showing hidden files."""
        self.show_hidden = not self.show_hidden
        status = "shown" if self.show_hidden else "hidden"
        self.notify(f"Hidden files {status}")

    def action_quit(self) -> None:
        """Quit the file browser."""
        self.app.exit()
