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

# Set up logging
import os
log_dir = None
debug_enabled = os.getenv("EMDX_DEBUG", "").lower() in ("1", "true", "yes", "on")

try:
    if debug_enabled:
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
    else:
        key_logger = logging.getLogger("key_events")
        key_logger.setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    if not debug_enabled:
        logger.setLevel(logging.INFO)

    # Import build ID for version tracking
    from emdx import __build_id__
    if debug_enabled:
        logger.info(f"EMDX TUI starting up - Build: {__build_id__}")
except Exception:
    # Fallback if logging setup fails
    import logging
    key_logger = logging.getLogger("key_events")
    logger = logging.getLogger(__name__)


# Note: SimpleVimLineNumbers has been moved to emdx.ui.vim_line_numbers
# Note: MinimalDocumentBrowser has been removed - use DocumentBrowser instead


# Note: run_minimal has been removed - use 'emdx gui' instead


if __name__ == "__main__":
    print("❌ main_browser.py has been deprecated.")
    print("✅ Use 'emdx gui' for the modern interface.")
    import sys
    sys.exit(1)
