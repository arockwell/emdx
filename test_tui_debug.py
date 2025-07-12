#!/usr/bin/env python3
"""Debug script to test TUI overflow issue with logging."""

import sys
from textual import events
from textual.app import App
from emdx.textual_browser_minimal import MinimalDocumentBrowser

class DebugBrowser(MinimalDocumentBrowser):
    """Browser with debug output redirected to file."""
    
    def __init__(self):
        super().__init__()
        self.debug_file = open("tui_debug.log", "w")
    
    def log(self, message: str):
        """Override log to write to file."""
        self.debug_file.write(f"{message}\n")
        self.debug_file.flush()
        super().log(message)

if __name__ == "__main__":
    app = DebugBrowser()
    app.run()