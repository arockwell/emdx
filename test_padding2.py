#!/usr/bin/env python3
"""Test with DEFAULT_CSS like LogBrowser."""

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.containers import Horizontal, Vertical
from textual.widgets import Label

class TestWidget(Widget):
    DEFAULT_CSS = """
    TestWidget {
        layout: vertical;
        height: 100%;
        border: solid red;
    }
    
    .content {
        layout: horizontal;
        height: 1fr;
        border: solid yellow;
    }
    
    .test-label {
        border: solid blue;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Horizontal(classes="content"):
            yield Label("This should be at the top", classes="test-label")

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield TestWidget()

if __name__ == "__main__":
    app = TestApp()
    app.run()