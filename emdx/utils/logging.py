"""Simple logging utilities for EMDX."""

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