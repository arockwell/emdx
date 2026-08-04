"""
emdx - A knowledge base that AI agents can read, write, and search
"""

import hashlib
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib


def _get_version() -> str:
    """Return the installed package version, falling back to pyproject.toml.

    Reading from importlib.metadata reflects what was actually installed
    (e.g. by ``uv tool upgrade``), rather than a hardcoded string that can
    drift from the running package. The pyproject.toml fallback covers
    running from a source checkout without an installed distribution.
    """
    try:
        return version("emdx")
    except PackageNotFoundError:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        return str(data["tool"]["poetry"]["version"])


__version__ = _get_version()


# Generate a unique build identifier based on current timestamp and file modification times
def _generate_build_id() -> str:
    """Generate a unique build identifier for version tracking."""
    try:
        # Get current file modification time
        current_file = Path(__file__)
        mtime = current_file.stat().st_mtime

        # Create hash from timestamp and version
        build_data = f"{__version__}-{mtime}-{time.time()}"
        build_hash = hashlib.md5(build_data.encode()).hexdigest()[:8]
        return f"{__version__}-{build_hash}"
    except Exception:
        # Fallback to timestamp if file ops fail
        return f"{__version__}-{int(time.time())}"


__build_id__ = _generate_build_id()
