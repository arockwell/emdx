"""Environment utilities for EMDX execution system."""

import os
from pathlib import Path

from emdx.utils.output import console


def get_subprocess_env() -> dict[str, str]:
    """Get a clean environment dict for spawning CLI subprocesses.

    Removes environment variables that prevent nested execution, such as
    CLAUDECODE which blocks Claude Code from running inside another session.
    """
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def ensure_claude_in_path() -> None:
    """Ensure claude command is in PATH for subprocess calls."""
    # Common locations where claude might be installed
    claude_paths: list[str | Path] = [
        "/usr/local/bin",
        "/opt/homebrew/bin",  # macOS ARM
        Path.home() / ".local" / "bin",  # pip install --user
        Path.home() / ".npm" / "bin",  # npm global
    ]

    # Add any missing paths that contain claude
    current_path = os.environ.get("PATH", "").split(os.pathsep)
    added_paths = []

    for p in claude_paths:
        path = Path(p)
        if path.exists() and str(path) not in current_path:
            claude_exe = path / "claude"
            if claude_exe.exists() and claude_exe.is_file():
                current_path.append(str(path))
                added_paths.append(str(path))

    if added_paths:
        os.environ["PATH"] = os.pathsep.join(current_path)
        console.print(f"[dim]Added to PATH: {', '.join(added_paths)}[/dim]")
