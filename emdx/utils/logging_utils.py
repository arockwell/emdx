"""Simple logging utilities for EMDX.

Standard Logger Initialization Pattern
--------------------------------------
For most modules, use the standard Python pattern:

    import logging
    logger = logging.getLogger(__name__)

This is the recommended approach because:
- It follows Python conventions and is immediately recognizable
- It allows configuration to be handled at the application level
- It doesn't add overhead of file handler creation on import

Use `get_logger()` only when you need immediate file-based logging

Note: This module uses inline Path construction instead of importing EMDX_CONFIG_DIR
to avoid circular imports, since logging may be needed before config is fully loaded.
with auto-configuration (e.g., for modules that may run standalone).
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Create file handler instead of console handler to avoid TUI interference
        log_dir = Path.home() / ".config" / "emdx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "emdx.log"

        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.INFO)

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


def setup_tui_logging(module_name: str) -> tuple[logging.Logger, logging.Logger]:
    """
    Set up TUI debug logging for UI modules.

    Returns:
        tuple: (main_logger, key_events_logger)
    """
    try:
        # Set up log directory
        log_dir = Path.home() / ".config" / "emdx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "tui_debug.log"

        # Configure basic logging if not already done
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                handlers=[
                    logging.FileHandler(log_file),
                    # logging.StreamHandler()  # Uncomment for console output
                ],
            )

        # Set up key events logger
        key_log_file = log_dir / "key_events.log"
        key_logger = logging.getLogger("key_events")
        if not key_logger.handlers:
            key_handler = logging.FileHandler(key_log_file)
            key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            key_logger.addHandler(key_handler)
            key_logger.setLevel(logging.DEBUG)

        main_logger = logging.getLogger(module_name)

        return main_logger, key_logger

    except Exception:
        # Fallback if logging setup fails
        return logging.getLogger(module_name), logging.getLogger("key_events")