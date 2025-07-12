#!/usr/bin/env python3
"""
mdcat integration for enhanced terminal markdown rendering.

This module provides a way to capture mdcat output and display it in Textual widgets.
mdcat provides superior markdown rendering with:
- Better code syntax highlighting
- Image support (iTerm2, Kitty)
- Better table formatting
- Proper link handling
"""

import os
import shutil
import subprocess
import tempfile
from typing import Optional


class MdcatRenderer:
    """Render markdown using mdcat and capture the output."""

    @staticmethod
    def is_available() -> bool:
        """Check if mdcat is available on the system."""
        return shutil.which("mdcat") is not None

    @staticmethod
    def get_terminal_info() -> tuple[str, bool]:
        """Get terminal type and whether it supports images."""
        term = os.environ.get("TERM", "")
        term_program = os.environ.get("TERM_PROGRAM", "")

        # Check for terminals that support images
        supports_images = any(
            [
                "kitty" in term.lower(),
                term_program == "iTerm.app",
                "wezterm" in term.lower(),
            ]
        )

        return term, supports_images

    @staticmethod
    def render(content: str, width: Optional[int] = None) -> str:
        """
        Render markdown content using mdcat and return the formatted output.

        Args:
            content: Markdown content to render
            width: Optional terminal width for rendering

        Returns:
            Formatted terminal output from mdcat
        """
        if not MdcatRenderer.is_available():
            raise RuntimeError("mdcat is not installed. Install with: cargo install mdcat")

        # Create a temporary file with the markdown content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            # Build mdcat command
            cmd = ["mdcat"]

            # Add width if specified
            if width:
                cmd.extend(["--columns", str(width)])

            # Disable paging for capture
            cmd.append("--no-pager")

            # Add the file
            cmd.append(temp_path)

            # Run mdcat and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "TERM": "xterm-256color"},  # Ensure color support
            )

            if result.returncode != 0:
                raise RuntimeError(f"mdcat failed: {result.stderr}")

            return result.stdout

        finally:
            # Clean up temp file
            os.unlink(temp_path)

    @staticmethod
    def render_to_html(content: str) -> str:
        """
        Render markdown to HTML using mdcat's HTML output.

        Note: mdcat doesn't directly support HTML output,
        so this would need a different tool like pandoc.
        """
        # This is a placeholder - mdcat focuses on terminal output
        # For HTML, you'd want to use a different tool
        raise NotImplementedError("mdcat does not support HTML output. Use pandoc or similar.")


class MdcatWidget:
    """
    A concept for integrating mdcat output into Textual.

    This is experimental and shows how you might capture mdcat's
    ANSI output and display it in a Textual widget.
    """

    @staticmethod
    def create_ansi_widget(content: str):
        """
        Create a Textual widget that can display ANSI formatted text from mdcat.

        Note: This would require a custom widget that can properly
        interpret ANSI escape codes, which is non-trivial.
        """
        # This is a conceptual implementation
        # In practice, you'd need to:
        # 1. Parse ANSI escape codes from mdcat output
        # 2. Convert them to Textual's rendering format
        # 3. Handle special features like images (if supported)

        try:
            rendered = MdcatRenderer.render(content)
            # TODO: Create a custom widget that can display ANSI text
            # For now, return the raw output
            return rendered
        except Exception as e:
            return f"Error rendering with mdcat: {e}"


if __name__ == "__main__":
    import sys

    if not MdcatRenderer.is_available():
        print("mdcat is not installed. Install with:", file=sys.stderr)
        print("  cargo install mdcat", file=sys.stderr)
        print("or", file=sys.stderr)
        print("  brew install mdcat", file=sys.stderr)
        sys.exit(1)

    # Read from stdin or file
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    # Render and output
    print(MdcatRenderer.render(content))
