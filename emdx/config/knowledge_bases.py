"""Named knowledge bases.

One emdx install can hold several independent knowledge bases — separate
SQLite files with their own FTS index, embeddings, tasks and tags. Nothing
leaks between them. Names are arbitrary (``propolis``, ``acme-client``,
``notes``); the reserved name ``default`` is the classic
``~/.config/emdx/knowledge.db`` so existing installs keep working untouched.

Layout::

    ~/.config/emdx/knowledge.db        # "default"
    ~/.config/emdx/kb/<name>.db        # every other KB

Resolution order for the active KB (first hit wins):

1. ``--kb NAME`` global CLI flag (exported as ``EMDX_KB`` by the callback)
2. ``EMDX_KB`` environment variable
3. Per-directory mapping: ``kb.dirs.<name>`` settings (``emdx kb map``) —
   the deepest directory containing the cwd wins
4. ``kb.default`` setting (``emdx kb use``)
5. ``default``

Explicit selection of a KB that does not exist is an error, so a typo can
never silently create an empty knowledge base — use ``emdx kb create``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import constants
from .app_config import ConfigValue, load_config

DEFAULT_KB = "default"
KB_ENV_VAR = "EMDX_KB"
KB_DEFAULT_SETTING = "kb.default"
KB_DIRS_PREFIX = "kb.dirs."

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class KnowledgeBaseError(Exception):
    """Base class for KB selection problems (bad name, unknown KB)."""


class InvalidKnowledgeBaseName(KnowledgeBaseError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Invalid knowledge base name {name!r}: use lowercase letters, digits, "
            "'-' or '_' (1-64 chars, must start with a letter or digit)"
        )
        self.name = name


class UnknownKnowledgeBase(KnowledgeBaseError):
    def __init__(self, name: str, path: Path) -> None:
        super().__init__(
            f"Knowledge base {name!r} does not exist ({path}). "
            f"Create it with: emdx kb create {name}"
        )
        self.name = name
        self.path = path


@dataclass(frozen=True)
class KBSelection:
    """The resolved knowledge base and where the choice came from."""

    name: str
    path: Path
    reason: str


def validate_kb_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise InvalidKnowledgeBaseName(name)
    return name


def kb_dir() -> Path:
    """Directory holding all non-default knowledge bases."""
    return constants.EMDX_CONFIG_DIR / "kb"


def kb_db_path(name: str) -> Path:
    """Database file for a KB name (does not check existence)."""
    validate_kb_name(name)
    if name == DEFAULT_KB:
        return constants.EMDX_CONFIG_DIR / "knowledge.db"
    return kb_dir() / f"{name}.db"


def kb_exists(name: str) -> bool:
    return kb_db_path(name).exists()


def _split_dirs(value: ConfigValue) -> list[Path]:
    if not isinstance(value, str) or not value.strip():
        return []
    return [Path(p).expanduser() for p in value.split(":") if p.strip()]


def dir_mappings(config: dict[str, ConfigValue] | None = None) -> dict[str, list[Path]]:
    """``{kb_name: [directories]}`` from ``kb.dirs.<name>`` settings."""
    if config is None:
        config = load_config()
    result: dict[str, list[Path]] = {}
    for key, value in config.items():
        if key.startswith(KB_DIRS_PREFIX):
            name = key[len(KB_DIRS_PREFIX) :]
            dirs = _split_dirs(value)
            if dirs:
                result[name] = dirs
    return result


def kb_for_directory(cwd: Path, config: dict[str, ConfigValue] | None = None) -> str | None:
    """KB mapped to ``cwd`` (deepest matching directory wins), or None."""
    try:
        cwd = cwd.resolve()
    except OSError:
        return None
    best: tuple[int, str] | None = None
    for name, dirs in dir_mappings(config).items():
        for d in dirs:
            try:
                d = d.resolve()
            except OSError:
                continue
            if cwd == d or d in cwd.parents:
                depth = len(d.parts)
                if best is None or depth > best[0]:
                    best = (depth, name)
    return best[1] if best else None


def resolve_kb(cwd: Path | None = None) -> KBSelection:
    """Work out which named KB is active, without touching the filesystem.

    Raises :class:`InvalidKnowledgeBaseName` for malformed names. Existence
    is checked separately by :func:`require_kb` so callers like
    ``emdx kb create`` can resolve a not-yet-existing name.
    """
    env_name = os.environ.get(KB_ENV_VAR)
    if env_name:
        name = validate_kb_name(env_name)
        return KBSelection(name, kb_db_path(name), f"{KB_ENV_VAR} / --kb")

    config = load_config()
    mapped = kb_for_directory(cwd or Path.cwd(), config)
    if mapped:
        name = validate_kb_name(mapped)
        return KBSelection(name, kb_db_path(name), "directory mapping (kb.dirs)")

    configured = config.get(KB_DEFAULT_SETTING)
    if isinstance(configured, str) and configured:
        name = validate_kb_name(configured)
        return KBSelection(name, kb_db_path(name), "kb.default setting")

    return KBSelection(DEFAULT_KB, kb_db_path(DEFAULT_KB), "default")


def require_kb(cwd: Path | None = None) -> KBSelection:
    """Resolve the active KB and ensure it exists.

    The ``default`` KB is created on demand (classic behaviour). Any other
    KB must have been created explicitly.
    """
    sel = resolve_kb(cwd)
    if sel.name != DEFAULT_KB and not sel.path.exists():
        raise UnknownKnowledgeBase(sel.name, sel.path)
    return sel


def list_kbs() -> list[str]:
    """All known KB names: ``default`` first, then ``kb/*.db`` sorted."""
    names = [DEFAULT_KB]
    d = kb_dir()
    if d.is_dir():
        names.extend(
            sorted(
                p.stem for p in d.glob("*.db") if _NAME_RE.match(p.stem) and p.stem != DEFAULT_KB
            )
        )
    return names
