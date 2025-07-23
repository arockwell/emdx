#!/usr/bin/env python3
"""Minimal test case for padding issue."""

from textual.app import App, ComposeResult
from textual.containers import Vertical, Container
from textual.widgets import Label, Static
from textual.screen import Screen

class NoPaddingScreen(Screen):
    """Custom screen with no padding."""
    DEFAULT_CSS = """
    NoPaddingScreen {
        padding: 0;
    }
    """

class TestApp(App):
    CSS = """
    Screen {
        padding: 0 !important;
        margin: 0 !important;
        border: solid red;
    }
    
    Vertical {
        padding: 0;
        margin: 0;
        border: solid yellow;
    }
    
    Container {
        padding: 0;
        margin: 0;
        border: solid green;
    }
    
    Label {
        border: solid blue;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Vertical():
            with Container():
                yield Label("This should be at the top")
            yield Label("Status bar")
    
    def on_mount(self) -> None:
        """Use our custom screen."""
        self.install_screen(NoPaddingScreen(), name="main")
        self.push_screen("main")

if __name__ == "__main__":
    app = TestApp()
    app.run()