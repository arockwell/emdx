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
import warnings
from pathlib import Path

# Set up logging
log_dir = None
try:
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
    logger = logging.getLogger(__name__)
    
    # Import build ID for version tracking
    from emdx import __build_id__
    logger.info(f"EMDX TUI starting up - Build: {__build_id__}")
except Exception:
    # Fallback if logging setup fails
    import logging
    key_logger = logging.getLogger("key_events")
    logger = logging.getLogger(__name__)


# DEPRECATED: SimpleVimLineNumbers has been moved to vim_line_numbers.py
def SimpleVimLineNumbers(*args, **kwargs):
    """DEPRECATED: Use emdx.ui.vim_line_numbers.SimpleVimLineNumbers instead."""
    warnings.warn(
        "SimpleVimLineNumbers has been moved to emdx.ui.vim_line_numbers. "
        "Please update your imports.",
        DeprecationWarning,
        stacklevel=2
    )
    from .vim_line_numbers import SimpleVimLineNumbers as _SimpleVimLineNumbers
    return _SimpleVimLineNumbers(*args, **kwargs)


# DEPRECATED: MinimalDocumentBrowser has been removed
def MinimalDocumentBrowser(*args, **kwargs):
    """DEPRECATED: MinimalDocumentBrowser has been removed. Use DocumentBrowser instead."""
    warnings.warn(
        "MinimalDocumentBrowser has been removed as part of technical debt cleanup. "
        "The main GUI now uses DocumentBrowser from document_browser.py via BrowserContainer. "
        "Please update your code to use the modern UI system.",
        DeprecationWarning,
        stacklevel=2
    )
    raise RuntimeError(
        "MinimalDocumentBrowser has been removed. Use 'emdx gui' for the modern interface."
    )


# DEPRECATED: run_minimal has been removed
def run_minimal():
    """DEPRECATED: run_minimal has been removed. Use 'emdx gui' instead."""
    warnings.warn(
        "run_minimal() has been removed as part of technical debt cleanup. "
        "Use 'emdx gui' for the modern interface.",
        DeprecationWarning,
        stacklevel=2
    )
    raise RuntimeError(
        "run_minimal() has been removed. Use 'emdx gui' for the modern interface."
    )


if __name__ == "__main__":
    print("❌ main_browser.py has been deprecated.")
    print("✅ Use 'emdx gui' for the modern interface.")
    import sys
    sys.exit(1)