"""
Command Palette - VS Code-style quick access overlay.

Provides:
- CommandPaletteScreen: Modal overlay for quick search and commands
- CommandRegistry: Registry of available commands
"""

from .palette_screen import CommandPaletteScreen
from .palette_commands import CommandRegistry, PaletteCommand

__all__ = [
    "CommandPaletteScreen",
    "CommandRegistry",
    "PaletteCommand",
]
