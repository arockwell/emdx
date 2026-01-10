#!/usr/bin/env python3
"""
External nvim wrapper that completely manages terminal state to eliminate flash.
"""

import os
import secrets
import subprocess
import sys
import tempfile
import termios
from pathlib import Path


def save_terminal_state():
    """Save current terminal state."""
    try:
        fd = sys.stdin.fileno()
        return termios.tcgetattr(fd)
    except (OSError, ValueError, termios.error):
        return None


def restore_terminal_state(state):
    """Restore terminal state."""
    if state:
        try:
            fd = sys.stdin.fileno()
            termios.tcsetattr(fd, termios.TCSADRAIN, state)
        except (OSError, ValueError, termios.error):
            pass


def clear_screen_completely():
    """Clear screen and reset cursor completely."""
    # Multiple approaches to ensure clean screen
    sys.stdout.write("\033[2J")  # Clear entire screen
    sys.stdout.write("\033[H")  # Move cursor to home
    sys.stdout.write("\033[3J")  # Clear scrollback
    sys.stdout.write("\033[0m")  # Reset all attributes
    sys.stdout.flush()


def get_secure_signal_path() -> str:
    """Generate a secure, unpredictable signal file path.

    Uses cryptographically secure random token instead of predictable PID.
    Returns a path in the user's temp directory with restricted permissions.
    """
    # Use a random token instead of predictable PID
    token = secrets.token_hex(16)
    # Use system temp dir which is typically per-user on modern systems
    signal_dir = Path(tempfile.gettempdir()) / "emdx_signals"
    signal_dir.mkdir(mode=0o700, exist_ok=True)
    return str(signal_dir / f"edit_signal_{token}")


def validate_temp_file_path(temp_file: str) -> bool:
    """Validate that a temp file path is safe to use.

    Prevents path traversal attacks by ensuring the file is in the temp directory.
    """
    try:
        temp_path = Path(temp_file).resolve()
        temp_dir = Path(tempfile.gettempdir()).resolve()

        # Ensure the file is within the temp directory
        if not str(temp_path).startswith(str(temp_dir)):
            return False

        # Ensure no path traversal components
        if ".." in temp_file:
            return False

        return True
    except (ValueError, OSError):
        return False


def safe_delete_file(file_path: str) -> None:
    """Safely delete a file with proper validation.

    Only deletes files in the temp directory to prevent accidental deletion
    of important files.
    """
    if not validate_temp_file_path(file_path):
        return

    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
    except (OSError, PermissionError):
        pass  # Ignore errors during cleanup


def run_textual_with_nvim_wrapper():
    """Run textual browser with external nvim wrapper."""

    # Save initial terminal state
    initial_state = save_terminal_state()

    try:
        while True:
            # Clear screen before starting textual
            clear_screen_completely()

            # Check for edit signal first - use secure signal path
            # Note: In practice, the signal path should be passed/stored securely
            # For now, we check for any signal files in the secure directory
            signal_dir = Path(tempfile.gettempdir()) / "emdx_signals"
            edit_signal = None
            if signal_dir.exists():
                for signal_file in signal_dir.glob("edit_signal_*"):
                    edit_signal = str(signal_file)
                    break  # Process first signal found

            if edit_signal and os.path.exists(edit_signal):
                try:
                    with open(edit_signal) as f:
                        signal_content = f.read().strip()

                    # Validate signal content format
                    if "|" not in signal_content:
                        safe_delete_file(edit_signal)
                        continue

                    temp_file, doc_id_str = signal_content.split("|", 1)

                    # Validate temp file path to prevent path traversal
                    if not validate_temp_file_path(temp_file):
                        safe_delete_file(edit_signal)
                        continue

                    # Validate doc_id is a number
                    try:
                        doc_id = int(doc_id_str)
                    except ValueError:
                        safe_delete_file(edit_signal)
                        continue

                    safe_delete_file(edit_signal)

                    # Clear screen completely before nvim
                    clear_screen_completely()

                    # Launch nvim with saved terminal state
                    restore_terminal_state(initial_state)
                    result = subprocess.run(["nvim", temp_file])

                    # Process changes if nvim succeeded
                    if result.returncode == 0:
                        process_nvim_changes(temp_file, doc_id)

                    # Clean up temp file safely
                    safe_delete_file(temp_file)

                    # Continue loop to restart textual
                    continue
                except (ValueError, OSError) as e:
                    # Invalid signal file format, clean up and continue
                    safe_delete_file(edit_signal)
                    continue

            # Run textual browser
            from emdx.ui.run_browser import run_browser

            # For now, just run the browser - no special exit codes yet
            run_browser()
            exit_code = 0

            # Check exit code to see if we should continue
            if exit_code == 42:  # Special code for edit request
                continue
            else:
                break  # Normal exit

    finally:
        # Restore original terminal state
        restore_terminal_state(initial_state)
        clear_screen_completely()


def process_nvim_changes(temp_file: str, doc_id: int):
    """Process changes from nvim editing."""
    try:
        # Validate temp file path before reading
        if not validate_temp_file_path(temp_file):
            return

        if not os.path.exists(temp_file):
            return

        with open(temp_file) as f:
            lines = f.readlines()

        # Remove comment lines
        lines = [line for line in lines if not line.strip().startswith("#")]

        if not lines:
            return

        # Extract title and content
        new_title = ""
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip():
                new_title = line.strip()
                content_start = i + 1
                break

        if not new_title:
            return

        new_content = "".join(lines[content_start:]).strip()

        # Update document
        from emdx.database import db

        db.update_document(doc_id, new_title, new_content)

    except Exception as e:
        print(f"Error processing changes: {e}")


if __name__ == "__main__":
    run_textual_with_nvim_wrapper()
