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
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Max log file size: 5MB, keep 2 backups
_MAX_LOG_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 2


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Create file handler instead of console handler to avoid TUI interference
        log_dir = Path.home() / ".config" / "emdx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "emdx.log"

        handler = RotatingFileHandler(
            log_file, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT
        )
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
    Set up TUI logging for UI modules.

    The root logger is set to WARNING to avoid noise from third-party libs.
    EMDX's own loggers (emdx.*) are set to INFO. Key events get a separate
    file that is only written to when actively editing.

    Returns:
        tuple: (main_logger, key_events_logger)
    """
    try:
        # Set up log directory
        log_dir = Path.home() / ".config" / "emdx"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "tui_debug.log"

        # Configure root logger — WARNING only, with rotation
        if not logging.getLogger().handlers:
            handler = RotatingFileHandler(
                log_file, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            logging.basicConfig(
                level=logging.WARNING,
                handlers=[handler],
            )

        # Let emdx.* loggers through at INFO
        emdx_logger = logging.getLogger("emdx")
        emdx_logger.setLevel(logging.INFO)

        # Key events logger — separate rotating file
        key_log_file = log_dir / "key_events.log"
        key_logger = logging.getLogger("key_events")
        if not key_logger.handlers:
            key_handler = RotatingFileHandler(
                key_log_file, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT
            )
            key_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            key_logger.addHandler(key_handler)
            key_logger.setLevel(logging.WARNING)  # Only errors, not every keystroke

        main_logger = logging.getLogger(module_name)

        return main_logger, key_logger

    except Exception as e:
        # Fallback if logging setup fails - use basic loggers
        # We can't log this failure since logging is what's failing
        import sys
        print(f"Warning: TUI logging setup failed: {e}", file=sys.stderr)
        return logging.getLogger(module_name), logging.getLogger("key_events")
