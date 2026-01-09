#!/usr/bin/env python3
"""
Main browser application for EMDX TUI.

DEPRECATION NOTICE:
This file has been cleaned up as part of technical debt reduction.
- SimpleVimLineNumbers has been extracted to vim_line_numbers.py
- MinimalDocumentBrowser and run_minimal() have been removed 
- The main GUI now uses DocumentBrowser from document_browser.py via BrowserContainer

For the modern UI system, see:
- document_browser.py: Main document browser widget
- browser_container.py: Container for switching browsers
- vim_line_numbers.py: Line numbers for vim mode
"""

import logging
from pathlib import Path

# Set up logging using shared utility
from ..utils.logging import setup_tui_logging
logger, key_logger = setup_tui_logging(__name__)

# Log build ID for version tracking
try:
    from emdx import __build_id__
    logger.info(f"EMDX TUI starting up - Build: {__build_id__}")
except Exception:
    pass


# Deprecated functions have been removed as part of technical debt cleanup.
# For modern replacements:
# - Use emdx.ui.vim_line_numbers.SimpleVimLineNumbers instead of SimpleVimLineNumbers
# - Use 'emdx gui' instead of MinimalDocumentBrowser or run_minimal()


if __name__ == "__main__":
    print("❌ main_browser.py has been deprecated.")
    print("✅ Use 'emdx gui' for the modern interface.")
    import sys
    sys.exit(1)
