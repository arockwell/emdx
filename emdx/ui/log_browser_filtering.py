#!/usr/bin/env python3
"""
Filtering mixin for LogBrowser.

Handles log content filtering, noise reduction, and content formatting.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emdx.services.execution_service import Execution

logger = logging.getLogger(__name__)


class LogBrowserFilteringMixin:
    """Mixin class for log filtering functionality in LogBrowser."""

    def _is_wrapper_noise(self, line: str) -> bool:
        """Check if a line is wrapper orchestration noise that should be filtered out."""
        if not line.strip():
            return False

        # Common wrapper patterns to filter out
        wrapper_patterns = [
            "🔄 Wrapper script started",
            "📋 Command:",
            "🚀 Starting Claude process...",
            "✅ Claude process finished",
            "📊 Updating execution status",
            "✅ Database updated successfully",
            "🔧 Background process started with PID:",
            "📄 Output is being written to this log file",
            "🔄 Wrapper will update status on completion",
            "📝 Prompt being sent to Claude:",
            "────────────────────────────────────────────────────────────",
        ]

        # Check for exact matches or patterns that start lines
        for pattern in wrapper_patterns:
            if pattern in line:
                return True

        # Filter out execution metadata lines
        if any(line.startswith(prefix) for prefix in [
            "⚡ Execution type:",
            "📋 Available tools:",
            "🔧 Background process",
            "📄 Output is being",
        ]):
            return True

        return False

    def _filter_log_content(self, content: str) -> str:
        """Apply filtering to new content (without header formatting)."""
        lines = content.splitlines()
        filtered_lines = []

        for line in lines:
            # Skip wrapper orchestration messages
            if self._is_wrapper_noise(line):
                continue
            filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def _format_initial_content(self, content: str, execution: "Execution") -> str:
        """Apply same filtering and formatting logic as current LogBrowser."""
        if not content.strip():
            return ""

        # Simple header - just the execution info
        lines = [f"[bold]Execution #{execution.id}[/bold] - {execution.doc_title}", ""]

        # Split content into header and log lines
        content_lines = content.splitlines()
        header_lines = []
        log_lines = []
        in_header = True

        for line in content_lines:
            if in_header and (
                line.startswith('=') or line.startswith('Version:') or
                line.startswith('Doc ID:') or line.startswith('Execution ID:') or
                line.startswith('Worktree:') or line.startswith('Started:') or
                line.startswith('Build ID:') or line.startswith('-')
            ):
                header_lines.append(line)
            else:
                in_header = False
                log_lines.append(line)

        # Extract prompt and filter out wrapper noise
        filtered_lines = []
        prompt_content = []
        in_prompt = False

        for line in log_lines:
            # Detect prompt section
            if "📝 Prompt being sent to Claude:" in line:
                in_prompt = True
                continue
            elif line.strip() == "─" * 60:
                if in_prompt:
                    in_prompt = False
                    continue
            elif in_prompt:
                prompt_content.append(line)
                continue

            # Skip wrapper orchestration messages
            if self._is_wrapper_noise(line):
                continue
            filtered_lines.append(line)

        # Show prompt first if we found one
        if prompt_content:
            lines.append("[bold blue]Prompt:[/bold blue]")
            for prompt_line in prompt_content:
                if prompt_line.strip():
                    lines.append(prompt_line)
            lines.append("")
            lines.append("[bold blue]Claude Response:[/bold blue]")

        # Add the filtered log content
        lines.extend(filtered_lines)

        return '\n'.join(lines)
