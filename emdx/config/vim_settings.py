#!/usr/bin/env python3
"""
Vim editor settings for EMDX.
"""

from typing import Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_VIM_SETTINGS = {
    "line_numbers": {
        "enabled": True,
        "relative": True,  # True for relative, False for absolute
        "width": 4,
        "highlight_current": True
    },
    "cursor": {
        "blink": True,
        "style": "block"  # block, line, underline
    },
    "colors": {
        "line_numbers": {
            "background": "$background",
            "foreground": "$text-muted",
            "current_line": "bold yellow"
        }
    }
}


class VimSettings:
    """Manages vim editor settings."""
    
    def __init__(self):
        self.settings = DEFAULT_VIM_SETTINGS.copy()
        self._load_user_settings()
        
    def _load_user_settings(self):
        """Load user settings from config file."""
        try:
            config_file = Path.home() / ".config" / "emdx" / "vim_settings.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    user_settings = json.load(f)
                    self._merge_settings(self.settings, user_settings)
                    logger.debug(f"Loaded vim settings from {config_file}")
        except Exception as e:
            logger.warning(f"Failed to load vim settings: {e}")
            
    def _merge_settings(self, base: dict, updates: dict):
        """Recursively merge settings."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_settings(base[key], value)
            else:
                base[key] = value
                
    def save_settings(self):
        """Save current settings to config file."""
        try:
            config_dir = Path.home() / ".config" / "emdx"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "vim_settings.json"
            
            with open(config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
                logger.debug(f"Saved vim settings to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save vim settings: {e}")
            
    @property
    def line_numbers_enabled(self) -> bool:
        """Check if line numbers are enabled."""
        return self.settings["line_numbers"]["enabled"]
        
    @property
    def line_numbers_relative(self) -> bool:
        """Check if relative line numbers are enabled."""
        return self.settings["line_numbers"]["relative"]
        
    @property
    def line_numbers_width(self) -> int:
        """Get line numbers width."""
        return self.settings["line_numbers"]["width"]
        
    def toggle_line_numbers(self):
        """Toggle line numbers on/off."""
        self.settings["line_numbers"]["enabled"] = not self.settings["line_numbers"]["enabled"]
        self.save_settings()
        
    def toggle_relative_numbers(self):
        """Toggle between relative and absolute line numbers."""
        self.settings["line_numbers"]["relative"] = not self.settings["line_numbers"]["relative"]
        self.save_settings()


# Global instance
vim_settings = VimSettings()