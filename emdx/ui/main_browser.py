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

# Only enable debug logging if explicitly requested
import os

debug_enabled = os.environ.get("EMDX_DEBUG", "").lower() in ("1", "true", "yes")

if debug_enabled:
    try:
        log_dir = Path.home() / ".config" / "emdx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "tui_debug.log"

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file)],
        )

        # Also create a dedicated key events log
        key_log_file = log_dir / "key_events.log"
        key_logger = logging.getLogger("key_events")
        key_handler = logging.FileHandler(key_log_file)
        key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        key_logger.addHandler(key_handler)
        key_logger.setLevel(logging.DEBUG)

        # Import build ID for version tracking
        from emdx import __build_id__
        logger = logging.getLogger(__name__)
        logger.info(f"EMDX TUI starting up - Build: {__build_id__}")
    except Exception:
        # Fallback if debug setup fails
        logging.basicConfig(level=logging.WARNING)
        key_logger = logging.getLogger("key_events")
        logger = logging.getLogger(__name__)
else:
    # Minimal logging setup for production
    logging.basicConfig(level=logging.WARNING)
    key_logger = logging.getLogger("key_events")
    logger = logging.getLogger(__name__)


# SimpleVimLineNumbers has been moved to vim_line_numbers.py


# Deprecated functions have been removed - textual_browser.py provides fallback implementations


if __name__ == "__main__":
    print("❌ main_browser.py has been deprecated.")
    print("✅ Use 'emdx gui' for the modern interface.")
    import sys
    sys.exit(1)
