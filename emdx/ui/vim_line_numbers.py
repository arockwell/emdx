#!/usr/bin/env python3
"""
Simple vim-style line numbers widget for EMDX TUI.
Extracted from main_browser.py to reduce technical debt.
"""

import logging
from textual.widgets import Static

logger = logging.getLogger(__name__)


class SimpleVimLineNumbers(Static):
    """Dead simple vim-style line numbers widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("vim-line-numbers")
        self.text_area = None  # Reference to associated text area

    def set_line_numbers(self, current_line, total_lines, text_area=None, relative=True):
        """Set line numbers given current line (0-based) and total lines.
        
        Args:
            current_line: Current cursor line (0-based)
            total_lines: Total number of lines
            text_area: Reference to the text area widget
            relative: If True, show relative numbers; if False, show absolute numbers
        """
        logger.debug(f"🔢 set_line_numbers called: current={current_line}, total={total_lines}, relative={relative}")
        
        # Store text area reference if provided
        if text_area:
            self.text_area = text_area
        
        from rich.text import Text
        from ..config.vim_settings import vim_settings
        
        # Use settings to determine relative mode
        relative = vim_settings.line_numbers_relative
        
        # Check if text area has focus - only highlight current line if it does
        has_focus = self.text_area and self.text_area.has_focus if self.text_area else False
        logger.debug(f"🔢 Text area has focus: {has_focus}")
        
        # Get highlight color from settings
        current_line_style = vim_settings.settings["colors"]["line_numbers"]["current_line"]
        
        lines = []
        for i in range(total_lines):
            if i == current_line:
                # Current line always shows absolute number (1-based)
                line_num = i + 1
                if has_focus and vim_settings.settings["line_numbers"]["highlight_current"]:
                    line_text = Text(f"{line_num:>3}", style=current_line_style)
                    logger.debug(f"  Line {i}: CURRENT (focused) -> {current_line_style} '{line_num}'")
                else:
                    line_text = Text(f"{line_num:>3}", style="dim yellow")
                    logger.debug(f"  Line {i}: CURRENT (not focused) -> dim yellow '{line_num}'")
                lines.append(line_text)
            else:
                if relative:
                    # Relative mode: show distance from current line
                    distance = abs(i - current_line)
                    line_text = Text(f"{distance:>3}", style="dim cyan")
                    logger.debug(f"  Line {i}: distance {distance} -> dim cyan '{distance}'")
                else:
                    # Absolute mode: show actual line number
                    line_num = i + 1
                    line_text = Text(f"{line_num:>3}", style="dim cyan")
                    logger.debug(f"  Line {i}: absolute {line_num} -> dim cyan '{line_num}'")
                lines.append(line_text)
        
        # Join with Rich Text newlines
        result = Text("\n").join(lines)
        logger.debug(f"🔢 Rich Text result created with {len(lines)} lines")
        logger.debug(f"🔢 Widget content BEFORE update: {repr(self.renderable)}")
        
        # Update widget content with Rich Text
        self.update(result)
        
        logger.debug(f"🔢 Widget content AFTER update: {repr(self.renderable)}")