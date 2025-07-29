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

    DEFAULT_CSS = """
        SimpleVimLineNumbers {
            background: $background;
            color: $text-muted;
            text-align: right;
            padding-right: 1;
            margin-top: 1;
            border: none;
            overflow-y: hidden;
            scrollbar-size: 0 0;
            text-wrap: nowrap
        }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("vim-line-numbers")
        self.text_area = None  # Reference to associated text area

    def set_line_numbers(self, current_line, total_lines, text_area=None):
        """Set line numbers given current line (0-based) and total lines."""
        logger.debug(f"🔢 set_line_numbers called: current={current_line}, total={total_lines}")
        
        # Store text area reference if provided
        if text_area:
            self.text_area = text_area
        
        from rich.text import Text
        
        # Check if text area has focus - only highlight current line if it does
        has_focus = self.text_area and self.text_area.has_focus if self.text_area else False
        logger.debug(f"🔢 Text area has focus: {has_focus}")
        
        lines = []
        for i in range(total_lines):
            if i == current_line:
                # Current line always shows absolute number (1-based)
                line_num = i + 1
                if has_focus:
                    line_text = Text(f"{line_num:>3}", style="bold yellow")
                    logger.debug(f"  Line {i}: CURRENT (focused) -> bold yellow '{line_num}'")
                else:
                    line_text = Text(f"{line_num:>3}", style="dim yellow")
                    logger.debug(f"  Line {i}: CURRENT (not focused) -> dim yellow '{line_num}'")
                lines.append(line_text)
            else:
                # Other lines show distance from current line
                distance = abs(i - current_line)
                line_text = Text(f"{distance:>3}", style="dim cyan")
                logger.debug(f"  Line {i}: distance {distance} -> dim cyan '{distance}'")
                lines.append(line_text)
        
        # Join with Rich Text newlines
        result = Text("\n").join(lines)
        logger.debug(f"🔢 Rich Text result created with {len(lines)} lines")
        logger.debug(f"🔢 Widget content BEFORE update: {repr(self.renderable)}")
        
        # Update widget content with Rich Text
        self.update(result)
        
        logger.debug(f"🔢 Widget content AFTER update: {repr(self.renderable)}")
