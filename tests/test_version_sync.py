"""Guard against version drift across the four files that must stay in sync.

See CLAUDE.md "Release Process": pyproject.toml, emdx/__init__.py,
.claude-plugin/plugin.json, and .claude-plugin/marketplace.json must all
carry the same version.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from emdx import __version__

REPO_ROOT = Path(__file__).parent.parent


def test_pyproject_version_matches() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None, "no version field found in pyproject.toml"
    assert match.group(1) == __version__


def test_plugin_json_version_matches() -> None:
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == __version__


def test_marketplace_json_plugin_version_matches() -> None:
    marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    # The top-level "version" is the marketplace descriptor version and is
    # intentionally independent; the plugin entry's version must match.
    plugin_versions = [p["version"] for p in marketplace["plugins"]]
    assert plugin_versions, "no plugin entries found in marketplace.json"
    assert all(v == __version__ for v in plugin_versions), (
        f"marketplace.json plugin versions {plugin_versions} != emdx.__version__ {__version__}"
    )
