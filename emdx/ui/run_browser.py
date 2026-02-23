#!/usr/bin/env python3
"""
Run the new browser container.
"""

from ..utils.logging_utils import setup_tui_logging

logger, _key_logger = setup_tui_logging(__name__)


def run_browser(theme: str | None = None) -> None:
    """Run the browser container.

    Args:
        theme: Optional theme name to use (overrides saved preference for this session)
    """
    import sys
    import traceback

    from .browser_container import BrowserContainer

    # Eagerly import sentence-transformers BEFORE Textual enters application
    # mode.  This library (or its torch dependency) corrupts terminal state
    # on Python 3.13.  Importing it here — while the terminal is still in
    # normal cooked mode — means the damage is harmless.  Textual's own
    # startup will then set up raw mode + mouse tracking cleanly afterward.
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401

        logger.info("Pre-loaded sentence-transformers for QA")
    except ImportError:
        pass

    app = BrowserContainer(initial_theme=theme)
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
