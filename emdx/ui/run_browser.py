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
    import traceback
    import sys

    app = BrowserContainer()
    try:
        logger.info("=== STARTING BROWSER APP ===")
        # Run with Textual devtools console enabled for debugging
        app.run()
        logger.info("=== BROWSER APP EXITED NORMALLY ===")
    except SystemExit as e:
        logger.error(f"SystemExit caught: {e}")
        print(f"SystemExit: {e}", file=sys.stderr)
        traceback.print_exc()
        raise
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt - user cancelled")
        raise
    except BaseException as e:
        logger.error(f"FATAL ERROR (BaseException) in run_browser: {e}", exc_info=True)
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_browser()