#!/usr/bin/env python3
"""Test with absolute positioning."""

from textual.app import App, ComposeResult
from textual.widgets import Label

class TestApp(App):
    CSS = """
    Label {
        offset: 0 -1;
        border: solid blue;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Label("This should be at the top")

if __name__ == "__main__":
    app = TestApp()
    app.run()