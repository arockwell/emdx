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

import warnings

from ..utils.logging import get_logger

logger = get_logger(__name__)
key_logger = get_logger("key_events")

# Import build ID for version tracking
try:
    from emdx import __build_id__
    logger.info(f"EMDX TUI starting up - Build: {__build_id__}")
except ImportError:
    pass  # Build ID not available


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
