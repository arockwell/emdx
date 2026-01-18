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

    Uses cryptographically secure random token instead of predictable PID
    to prevent signal file path prediction attacks.

    Returns:
        Secure path for the edit signal file
    """
    # Use cryptographically secure random token (32 hex chars = 128 bits entropy)
    token = secrets.token_hex(16)
    # Use system temp directory with secure permissions
    return os.path.join(tempfile.gettempdir(), f"emdx_edit_signal_{token}")


def validate_temp_file_path(path: str) -> bool:
    """Validate that a path is within the system temp directory.

    Prevents path traversal attacks by ensuring the path:
    1. Is absolute
    2. Is within the system temp directory
    3. Does not contain path traversal components

    Args:
        path: Path to validate

    Returns:
        True if the path is safe, False otherwise
    """
    if not path:
        return False

    try:
        # Resolve to absolute path and normalize
        resolved = os.path.realpath(path)
        temp_dir = os.path.realpath(tempfile.gettempdir())

        # Check if the resolved path is within temp directory
        # Use os.path.commonpath to safely check containment
        common = os.path.commonpath([resolved, temp_dir])
        return common == temp_dir
    except (ValueError, OSError):
        return False


def secure_remove(path: str) -> bool:
    """Securely remove a file after validating its path.

    Only removes files within the system temp directory to prevent
    accidental or malicious deletion of system files.

    Args:
        path: Path to the file to remove

    Returns:
        True if file was removed, False otherwise
    """
    if not validate_temp_file_path(path):
        return False

    try:
        if os.path.exists(path) and os.path.isfile(path):
            os.unlink(path)
            return True
    except OSError:
        pass
    return False


def run_textual_with_nvim_wrapper(theme: str | None = None):
    """Run textual browser with external nvim wrapper.

    Args:
        theme: Optional theme name to use (overrides saved preference for this session)
    """

    # Save initial terminal state
    initial_state = save_terminal_state()

    # Generate a secure signal path for this session
    # Note: For backwards compatibility, we also check for legacy signal files
    # but new signal files use secure random tokens
    session_signal = get_secure_signal_path()

    try:
        while True:
            # Clear screen before starting textual
            clear_screen_completely()

            # Check for edit signal - look for any emdx signal files in temp dir
            # This maintains compatibility while transitioning to secure paths
            edit_signal = None
            temp_dir = tempfile.gettempdir()
            for filename in os.listdir(temp_dir):
                if filename.startswith("emdx_edit_signal_"):
                    candidate = os.path.join(temp_dir, filename)
                    if validate_temp_file_path(candidate):
                        edit_signal = candidate
                        break

            if edit_signal and os.path.exists(edit_signal):
                try:
                    with open(edit_signal) as f:
                        signal_content = f.read().strip()

                    # Validate signal content format
                    if "|" not in signal_content:
                        secure_remove(edit_signal)
                        continue

                    temp_file, doc_id_str = signal_content.split("|", 1)

                    # Validate temp_file path to prevent path traversal
                    if not validate_temp_file_path(temp_file):
                        secure_remove(edit_signal)
                        continue

                    # Validate doc_id is a valid integer
                    try:
                        doc_id = int(doc_id_str)
                    except ValueError:
                        secure_remove(edit_signal)
                        continue

                    # Securely remove the signal file
                    secure_remove(edit_signal)

                    # Clear screen completely before nvim
                    clear_screen_completely()

                    # Launch nvim with saved terminal state
                    restore_terminal_state(initial_state)
                    result = subprocess.run(["nvim", temp_file])

                    # Process changes if nvim succeeded
                    if result.returncode == 0:
                        process_nvim_changes(temp_file, doc_id)

                    # Securely clean up temp file
                    secure_remove(temp_file)

                    # Continue loop to restart textual
                    continue
                except (OSError, ValueError):
                    # Handle malformed signal file gracefully
                    secure_remove(edit_signal)
                    continue

            # Run textual browser
            from emdx.ui.run_browser import run_browser

            # For now, just run the browser - no special exit codes yet
            run_browser(theme=theme)
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
