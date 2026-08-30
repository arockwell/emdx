"""
emdx - A knowledge base that AI agents can read, write, and search

``__version__`` and ``__build_id__`` are resolved lazily via the module-level
``__getattr__`` (PEP 562): the ``importlib.metadata`` lookup costs ~14ms,
which would otherwise be paid on every CLI invocation (#1067) — this package
is imported by every ``emdx.*`` module. Both attributes behave exactly as
before to consumers (``from emdx import __version__`` still works); the
lookup just happens on first access instead of at import time.
"""

from typing import Any


def _get_version() -> str:
    """Return the installed package version, falling back to pyproject.toml.

    Reading from importlib.metadata reflects what was actually installed
    (e.g. by ``uv tool upgrade``), rather than a hardcoded string that can
    drift from the running package. The pyproject.toml fallback covers
    running from a source checkout without an installed distribution.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("emdx")
    except PackageNotFoundError:
        from pathlib import Path

        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        return str(data["tool"]["poetry"]["version"])


def _generate_build_id() -> str:
    """Generate a unique build identifier for version tracking."""
    import hashlib
    import time
    from pathlib import Path

    version = _get_version()
    try:
        # Get current file modification time
        current_file = Path(__file__)
        mtime = current_file.stat().st_mtime

        # Create hash from timestamp and version
        build_data = f"{version}-{mtime}-{time.time()}"
        build_hash = hashlib.md5(build_data.encode()).hexdigest()[:8]
        return f"{version}-{build_hash}"
    except Exception:
        # Fallback to timestamp if file ops fail
        return f"{version}-{int(time.time())}"


def __getattr__(name: str) -> Any:
    """Resolve ``__version__``/``__build_id__`` on first access (PEP 562)."""
    if name == "__version__":
        value = _get_version()
        globals()["__version__"] = value
        return value
    if name == "__build_id__":
        value = _generate_build_id()
        globals()["__build_id__"] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
