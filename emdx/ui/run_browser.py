#!/usr/bin/env python3
"""
Run the new browser container.
"""

import logging
import sys
from pathlib import Path

# Set up logging
log_dir = Path.home() / ".config" / "emdx"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "tui_debug.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)

logger = logging.getLogger(__name__)


def run_browser():
    """Run the browser container."""
    from .browser_container import BrowserContainer
    
    app = BrowserContainer()
    app.run()


if __name__ == "__main__":
    run_browser()