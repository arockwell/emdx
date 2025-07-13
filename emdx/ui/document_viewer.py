#!/usr/bin/env python3
"""
Full-screen document viewer for EMDX TUI.
"""

import subprocess
from textual import events
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Label, RichLog
from rich.markdown import Markdown

from emdx.models.documents import get_document


class FullScreenView(Screen):
    """Full screen document viewer."""

    CSS = """
    FullScreenView {
        align: center middle;
    }

    #doc-viewer {
        width: 100%;
        height: 100%;
        padding: 0;
    }

    #header {
        dock: top;
        height: 3;
        background: $surface;
        padding: 0 2;
    }

    #footer {
        dock: bottom;
        height: 1;
        background: $surface;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("q", "close", "Close"),
        ("escape", "close", "Close"),
        ("j", "scroll_down", "Down"),
        ("k", "scroll_up", "Up"),
        ("ctrl+d", "page_down", "Page down"),
        ("ctrl+u", "page_up", "Page up"),
        ("g", "scroll_top", "Top"),
        ("shift+g", "scroll_bottom", "Bottom"),
    ]

    def __init__(self, doc_id: int):
        """Initialize the full screen viewer.

        Args:
            doc_id: The ID of the document to display.

        """
        super().__init__()
        self.doc_id = doc_id

    def compose(self) -> ComposeResult:
        # Just the document content - no header metadata
        with ScrollableContainer(id="doc-viewer"):
            yield RichLog(id="content", wrap=True, highlight=True, markup=True, auto_scroll=False)

        # Footer
        yield Label("Press q or ESC to return", id="footer")

    def on_mount(self) -> None:
        """Load document content when mounted."""
        doc = get_document(str(self.doc_id))
        if doc:
            content_log = self.query_one("#content", RichLog)
            content_log.clear()

            # Smart title handling - avoid double titles
            content = doc["content"].strip()

            # Check if content already starts with the title as H1
            content_lines = content.split("\n")
            first_line = content_lines[0].strip() if content_lines else ""

            if first_line == f"# {doc['title']}":
                # Content already has the title, just show content
                markdown_content = content
            else:
                # Add title if not already present
                markdown_content = f"""# {doc['title']}

{content}"""
            md = Markdown(markdown_content, code_theme="monokai")
            content_log.write(md)
            content_log.scroll_to(0, 0, animate=False)

    def action_close(self) -> None:
        """Close the viewer."""
        self.dismiss()

    def action_scroll_down(self) -> None:
        """Scroll down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=1)

    def action_scroll_up(self) -> None:
        """Scroll up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-1)

    def action_page_down(self) -> None:
        """Page down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=10)

    def action_page_up(self) -> None:
        """Page up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-10)

    def action_scroll_top(self) -> None:
        """Scroll to top."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_to(0, 0, animate=False)

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom."""
        container = self.query_one("#doc-viewer", ScrollableContainer)
        container.scroll_to(0, container.max_scroll_y, animate=False)

    def action_copy_content(self) -> None:
        """Copy current document content to clipboard."""
        try:
            doc = get_document(str(self.doc_id))
            if doc:
                self.copy_to_clipboard(doc["content"])
        except Exception:
            # Silently ignore copy errors in full screen view
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key events that aren't bindings."""
        # Let 's' key pass through - handled by main app
        pass

    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess

        # Try pbcopy on macOS first
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"], input=text, text=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(
                        ["xsel", "--clipboard", "--input"], input=text, text=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass